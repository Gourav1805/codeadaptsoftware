"""Compile and execute untrusted C++ submissions, producing raw per-test evidence.

Non-negotiables encoded here:
  * Student code never runs inside this process.
  * One compile per submission; ONE PROCESS PER TEST.  A single infinite loop
    must not destroy the other tests' outcomes -- the per-test P/F/R row IS the
    instrument, so it must stay readable when one cell fails.
  * Compile errors are a separate status.  They are never mapped to F.
  * Runtime failure (R) is never collapsed into wrong answer (F).
  * Raw evidence is preserved: generated source, compiler diagnostics, raw
    stdout text, exit code, wall time, peak memory.
"""
import functools
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid

import problems
from winjob import run_sandboxed, label_dir_low

# --- Engineering defaults (NOT research conclusions) ----------------------
# Toolchain of record: MinGW-w64 GCC 16.1.0 (x86_64-ucrt-posix-seh), relocated
# to a space-free path because GCC's own driver splits its internal ld
# invocation on a space in the install path.
_DEFAULT_GXX = "C:/mingw64/bin/g++.exe"
GXX = os.environ.get("SI_GXX") or (_DEFAULT_GXX if os.path.exists(_DEFAULT_GXX) else "g++")
CXX_STD = os.environ.get("SI_CXX_STD", "c++17")
WALL_TIMEOUT_S = float(os.environ.get("SI_TIMEOUT_S", "3.0"))
MEMORY_BYTES = int(os.environ.get("SI_MEMORY_MB", "256")) * 1024 * 1024
COMPILE_TIMEOUT_S = float(os.environ.get("SI_COMPILE_TIMEOUT_S", "20"))
# Optimization level is pinned and recorded: it is NOT a free engineering
# knob, because it changes P/F/R outcomes for submissions that exercise
# undefined behaviour. See the UB-stability finding.
OPT_LEVEL = os.environ.get("SI_OPT", "-O1")

# Concurrency requirement is UNSPECIFIED in the project documents. This bounds
# resource use without committing to a number; raise it once the real figure
# is known.
MAX_CONCURRENT = int(os.environ.get("SI_MAX_CONCURRENT", "4"))

# Second build with libstdc++ precondition checks, used to detect undefined
# behaviour per test. Costs one extra compile and one extra run per test;
# worth it, because UB-derived outcomes are the known weak point in the
# fingerprint matrices. Set SI_UB_PROBE=0 to skip.
UB_PROBE = os.environ.get("SI_UB_PROBE", "1") != "0"
_slots = threading.Semaphore(MAX_CONCURRENT)

# Driver-internal failures. These mean the PLATFORM is broken, not the student.
_HARNESS_EXITS = {64: "driver called with too few arguments",
                  65: "driver received an unknown test index",
                  66: "driver could not open its result file"}

_NTSTATUS = {
    0xC0000005: "ACCESS_VIOLATION",
    0xC000001D: "ILLEGAL_INSTRUCTION",
    0xC0000025: "NONCONTINUABLE_EXCEPTION",
    0xC0000094: "INTEGER_DIVIDE_BY_ZERO",
    0xC0000096: "PRIVILEGED_INSTRUCTION",
    0xC00000FD: "STACK_OVERFLOW",
    0xC0000374: "HEAP_CORRUPTION",
    0xC0000409: "STACK_BUFFER_OVERRUN",
    0xC0000017: "NO_MEMORY",
    3: "ABORT (unhandled exception / assertion)",
}


@functools.lru_cache(maxsize=1)
def compiler_version():
    try:
        p = subprocess.run([GXX, "--version"], capture_output=True, text=True,
                           timeout=30)
        return p.stdout.splitlines()[0].strip() if p.stdout else "unknown"
    except (OSError, subprocess.SubprocessError, IndexError):
        return "unknown"


@functools.lru_cache(maxsize=16)
def instrument_hash(problem_id):
    """Identify the exact measurement instrument that produced a result.

    Covers the compiler build, the language/optimisation flags, and the
    generated harness for this problem -- everything that decides how a
    submission is compiled and driven, with the student's own code held
    constant.

    This exists because outcomes that depend on undefined behaviour shift when
    the harness or toolchain changes. Recording the hash makes such a shift
    detectable after the fact instead of silently splitting a dataset. A stale
    backend really did produce a different P/F/R row for an identical
    submission during development.
    """
    problem = problems.get(problem_id)
    skeleton = problems.render_source(problem, "/*STUDENT*/")
    blob = "\n".join([compiler_version(), CXX_STD, OPT_LEVEL,
                      str(WALL_TIMEOUT_S), str(MEMORY_BYTES), skeleton])
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _describe_exit(code):
    u = code & 0xFFFFFFFF
    if u in _NTSTATUS:
        return "%s (0x%08X)" % (_NTSTATUS[u], u)
    return "exit code %d (0x%08X)" % (code, u)


# --- Result parsing -------------------------------------------------------

def _parse(kind, text):
    """Raw result text -> comparable value. Raises ValueError on garbage."""
    if kind == "int":
        return int(text.strip())
    if kind == "bool":
        return text.strip() == "1"
    if kind == "int_list":
        return [int(x) for x in text.split()]
    if kind == "linked_list":
        parts = [int(x) for x in text.split()]
        if len(parts) < 3:
            raise ValueError("truncated structural record")
        cycle, terminated, count = parts[0], parts[1], parts[2]
        return {"cycle": bool(cycle), "terminated": bool(terminated),
                "values": parts[3:3 + count]}
    raise ValueError("unknown kind %r" % kind)


def _matches(kind, actual, expected):
    if kind != "linked_list":
        return actual == expected
    # STRUCTURAL: correct sequence is necessary but not sufficient -- the
    # returned list must also be acyclic and properly null-terminated.
    return (not actual["cycle"] and actual["terminated"]
            and actual["values"] == list(expected))


def _render_actual(kind, actual):
    if kind != "linked_list":
        return actual
    return {"values": actual["values"], "cycle": actual["cycle"],
            "terminated": actual["terminated"]}


# --- Compilation (Phase 2) ------------------------------------------------

def compile_submission(problem, student_code, workdir):
    """Returns (compile_status, exe_path_or_None, evidence_dict)."""
    source = problems.render_source(problem, student_code)
    src_path = os.path.join(workdir, "submission.cpp")
    exe_path = os.path.join(workdir, "submission.exe")
    with open(src_path, "w", encoding="utf-8") as fh:
        fh.write(source)

    cmd = [GXX, "-std=" + CXX_STD, OPT_LEVEL, "-w", src_path, "-o", exe_path]
    try:
        proc = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True,
                              timeout=COMPILE_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return "COMPILE_TIMEOUT", None, {
            "generated_source": source, "command": " ".join(cmd),
            "compiler_stdout": "", "compiler_stderr": "",
            "detail": "compiler exceeded %.1fs" % COMPILE_TIMEOUT_S}
    except FileNotFoundError:
        return "TOOLCHAIN_MISSING", None, {
            "generated_source": source, "command": " ".join(cmd),
            "compiler_stdout": "", "compiler_stderr": "",
            "detail": "compiler %r not found on PATH" % GXX}

    evidence = {"generated_source": source, "command": " ".join(cmd),
                "compiler_stdout": proc.stdout, "compiler_stderr": proc.stderr,
                "compiler_returncode": proc.returncode,
                "student_line_offset": _student_offset(source)}

    if proc.returncode != 0 or not os.path.exists(exe_path):
        return "COMPILE_ERROR", None, evidence
    return "OK", exe_path, evidence


def compile_ub_probe(source, workdir):
    """Second build of the SAME source with libstdc++ precondition checks on.

    `-D_GLIBCXX_ASSERTIONS` turns silent undefined behaviour -- indexing a
    vector out of range, calling top() on an empty stack -- into an immediate,
    labelled abort. Phase 0 showed those cases otherwise return plausible
    garbage on one build and segfault on another, which is exactly what made
    three fingerprint cells untrustworthy.

    Returns an exe path, or None if the probe build is unavailable. A probe
    failure is never fatal: it degrades evidence, it does not block execution.
    """
    src_path = os.path.join(workdir, "probe.cpp")
    exe_path = os.path.join(workdir, "probe.exe")
    with open(src_path, "w", encoding="utf-8") as fh:
        fh.write(source)
    cmd = [GXX, "-std=" + CXX_STD, OPT_LEVEL, "-w", "-D_GLIBCXX_ASSERTIONS",
           src_path, "-o", exe_path]
    try:
        proc = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True,
                              timeout=COMPILE_TIMEOUT_S)
    except (subprocess.SubprocessError, OSError):
        return None
    return exe_path if proc.returncode == 0 and os.path.exists(exe_path) else None


def _student_offset(source):
    """Line number where student code begins, so compiler diagnostics can be
    remapped to the student's own line numbers rather than the generated file."""
    for i, line in enumerate(source.splitlines(), 1):
        if "STUDENT SUBMISSION BEGINS" in line:
            return i
    return 0


def remap_diagnostics(stderr, offset, source_name="submission.cpp"):
    """Rewrite '<tmp path>/submission.cpp:47:' -> 'line 12', numbered relative
    to the student's own code rather than the generated translation unit.

    Also strips the bare '<tmp path>/submission.cpp: ' prefix that GCC puts on
    context lines like "In function '...'", which carry no line number. Those
    would otherwise leak the internal temp directory into student-facing output.
    """
    if not offset:
        return stderr
    name = re.escape(source_name)

    def sub(m):
        n = int(m.group(1)) - offset
        return "line %d:" % n if n > 0 else "<platform harness>:"

    out = re.sub(r"\S*" + name + r":(\d+):", sub, stderr)
    out = re.sub(r"\S*" + name + r":\s*", "", out)

    # GCC's source excerpt has its own line-number gutter ("    7 | ..."), which
    # would otherwise contradict the remapped "line 1:" above it.
    def gutter(m):
        n = int(m.group(2)) - offset
        return "%s%d%s" % (m.group(1), n, m.group(3)) if n > 0 else m.group(0)

    return re.sub(r"(?m)^(\s*)(\d+)(\s*\|)", gutter, out)


# --- Execution + classification (Phases 3-5) ------------------------------

_STDERR_CAP = 4000


def _read_capped(path, cap=_STDERR_CAP):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read(cap + 1)
    if not text:
        return None
    return text[:cap] + ("... [truncated]" if len(text) > cap else "")


def _run_ub_probe(probe_exe, workdir, index, primary_timed_out=False):
    """Re-run one test against the assertions build.

    Returns (verdict, detail). Verdict is evidence, never a classification:
      clean     -- ran to completion with no precondition violated
      violation -- libstdc++ caught undefined behaviour; detail names it
      timeout   -- did not terminate under the probe, so nothing was learned
      crash     -- died for some other reason
    """
    out_path = os.path.join(workdir, "probe_result_%d.txt" % index)
    err_path = os.path.join(workdir, "probe_stderr_%d.txt" % index)
    for p in (out_path, err_path):
        if os.path.exists(p):
            os.remove(p)

    # A precondition failure aborts almost immediately, so when the primary run
    # already proved non-termination there is nothing to gain from waiting the
    # full budget again -- either the assertion fires fast, or it hangs and
    # teaches us nothing. This is the difference between ~39s and ~15s on a
    # submission that loops forever.
    budget = min(WALL_TIMEOUT_S, 1.0) if primary_timed_out else WALL_TIMEOUT_S

    sb = run_sandboxed([probe_exe, str(index), out_path], workdir,
                       budget, MEMORY_BYTES, stderr_path=err_path)
    text = _read_capped(err_path) or ""

    if sb.timed_out:
        return "timeout", None
    if "Assertion" in text or "assertion" in text or "__glibcxx" in text:
        return "violation", _first_assertion(text)
    if sb.exit_code not in (0,) and sb.exit_code not in _HARNESS_EXITS:
        return "crash", _describe_exit(sb.exit_code)
    return "clean", None


def _first_assertion(text):
    """The libstdc++ message names the violated precondition; keep that line."""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # Strip the include path prefix, keep the human-readable part.
        m = re.search(r"(?:Assertion|assertion)\s*['\"]?(.+)", line)
        if m:
            return m.group(1).strip().rstrip("'\" ")[:300]
        if "__glibcxx" in line or "error:" in line:
            return line[:300]
    return text.strip().splitlines()[0][:300] if text.strip() else None



def _run_one_test(exe_path, workdir, index, test, kind):
    """Execute exactly one test in its own process + own Job Object."""
    out_path = os.path.join(workdir, "result_%d.txt" % index)
    if os.path.exists(out_path):
        os.remove(out_path)                      # no stale state between runs

    err_path = os.path.join(workdir, "stderr_%d.txt" % index)
    sb = run_sandboxed([exe_path, str(index), out_path], workdir,
                       WALL_TIMEOUT_S, MEMORY_BYTES, stderr_path=err_path)

    row = {"test_id": test["test_id"], "expected_output": test["expected"],
           "runtime_ms": round(sb.wall_ms, 2),
           "memory_bytes": sb.peak_memory_bytes,
           "exit_code": sb.exit_code, "integrity": sb.integrity,
           "actual_output": None,
           "raw_stdout": None, "stderr": _read_capped(err_path), "error": None,
           # Filled in later by the UB probe, if one is available. It is
           # additional evidence ONLY and never influences status.
           "ub_check": "not_run", "ub_detail": None}

    if sb.timed_out:
        row.update(execution_status="TIMEOUT", status="R",
                   error="wall-clock timeout after %.1fs (non-termination)"
                         % WALL_TIMEOUT_S)
        return row

    if sb.exit_code in _HARNESS_EXITS:
        row.update(execution_status="HARNESS_ERROR", status="R",
                   error="PLATFORM BUG: " + _HARNESS_EXITS[sb.exit_code])
        return row

    if sb.exit_code != 0:
        row.update(execution_status="CRASHED", status="R",
                   error=_describe_exit(sb.exit_code))
        return row

    if not os.path.exists(out_path):
        row.update(execution_status="NO_RESULT", status="R",
                   error="process exited 0 without producing a result")
        return row

    with open(out_path, "r", encoding="utf-8", errors="replace") as fh:
        raw = fh.read()
    row["raw_stdout"] = raw

    try:
        actual = _parse(kind, raw)
    except (ValueError, IndexError) as exc:
        row.update(execution_status="PARSE_ERROR", status="R",
                   error="unparseable result: %s" % exc)
        return row

    row["actual_output"] = _render_actual(kind, actual)
    row["execution_status"] = "COMPLETED"
    row["status"] = "P" if _matches(kind, actual, test["expected"]) else "F"
    return row


_pending_cleanup = set()
_pending_lock = threading.Lock()
_active_workdirs = set()
_active_lock = threading.Lock()


def sweep():
    """Retry any work directory a previous submission could not delete.

    Windows holds a handle on a terminated process's files for a short window,
    so cleanup is eventual rather than instantaneous. Rather than block a
    submission on a long sleep, failures are queued and retried on the next
    call. Also sweeps any orphaned si_sub_* directories left behind in TEMP
    from previous interrupted or crashed processes. Returns the number still
    outstanding.
    """
    with _pending_lock:
        stale = list(_pending_cleanup)
    for p in stale:
        for _ in range(5):
            shutil.rmtree(p, ignore_errors=True)
            if not os.path.exists(p):
                with _pending_lock:
                    _pending_cleanup.discard(p)
                break
            time.sleep(0.05)

    # Sweep any orphaned si_sub_* directories in TEMP that are not active
    temp_dir = os.environ.get("TEMP") or tempfile.gettempdir()
    now = time.time()
    with _active_lock:
        active = set(_active_workdirs)
    try:
        for entry in os.listdir(temp_dir):
            if entry.startswith("si_sub_"):
                full_path = os.path.join(temp_dir, entry)
                if full_path in active:
                    continue
                try:
                    mtime = os.path.getmtime(full_path)
                    if now - mtime < 5.0:
                        continue
                except OSError:
                    continue
                shutil.rmtree(full_path, ignore_errors=True)
    except OSError:
        pass
    with _pending_lock:
        return len(_pending_cleanup)



def _cleanup_workdir(path, attempts=8, delay=0.05):
    """Delete a submission's work directory, retrying briefly.

    Windows keeps a lock on a terminated process's image and on any file it
    still had open for a short window after the process dies. A single rmtree
    therefore loses a race against a just-killed probe and leaves the whole
    directory behind. `ignore_errors=True` hid that, which is how a leak of one
    directory per timed-out probe went unnoticed until the hardening check
    counted them.

    Returns True if the directory is gone. The result is recorded rather than
    swallowed: a cleanup failure is a real resource leak, not a detail.
    """
    for i in range(attempts):
        shutil.rmtree(path, ignore_errors=True)
        if not os.path.exists(path):
            return True
        time.sleep(delay * (i + 1))
    # Still locked. Queue it instead of blocking this submission any longer;
    # sweep() picks it up. The leak is bounded and eventual, never permanent.
    with _pending_lock:
        _pending_cleanup.add(path)
    return False


def evaluate(problem_id, student_code, submission_id=None, keep_workdir=False):
    """Compile once, run every test in its own sandboxed process, return the
    full raw evidence record.  Never reduces to a bare score."""
    problem = problems.get(problem_id)
    submission_id = submission_id or uuid.uuid4().hex

    record = {
        "submission_id": submission_id,
        "problem_id": problem["problem_id"],
        "concept": problem["concept"],
        "limits": {"wall_timeout_s": WALL_TIMEOUT_S,
                   "memory_bytes": MEMORY_BYTES,
                   "compiler": GXX, "std": CXX_STD, "opt": OPT_LEVEL,
                   "compiler_version": compiler_version(),
                   "instrument_hash": instrument_hash(problem["problem_id"]),
                   "isolation": "windows-job-object+low-integrity"},
        "compile_status": None, "compile": None, "tests": [],
    }

    sweep()                      # retry anything a previous run left behind
    with _slots:
        workdir = tempfile.mkdtemp(prefix="si_sub_")
        with _active_lock:
            _active_workdirs.add(workdir)
        # Student processes run at Low integrity and cannot write to
        # anything the backend user owns -- including this directory,
        # unless it is explicitly labelled Low.
        labelled = label_dir_low(workdir)
        record["limits"]["workdir_labelled_low"] = labelled
        try:
            status, exe, cev = compile_submission(problem, student_code, workdir)
            record["compile_status"] = status
            record["compile"] = {
                "command": cev["command"],
                "stderr": cev.get("compiler_stderr", ""),
                "stderr_student_lines": remap_diagnostics(
                    cev.get("compiler_stderr", ""),
                    cev.get("student_line_offset", 0)),
                "detail": cev.get("detail"),
                "generated_source": cev["generated_source"],
            }
            if status != "OK":
                # No execution statuses at all. A compile error is its own
                # evidence type, never an F.
                return record

            probe = (compile_ub_probe(cev["generated_source"], workdir)
                     if UB_PROBE else None)
            record["limits"]["ub_probe"] = (
                "-D_GLIBCXX_ASSERTIONS" if probe else
                ("unavailable" if UB_PROBE else "disabled"))

            for i, test in enumerate(problem["tests"]):
                row = _run_one_test(exe, workdir, i, test, problem["kind"])
                if probe:
                    # Runs AFTER classification and cannot alter it. The probe
                    # answers "did this test rely on undefined behaviour?",
                    # which is a separate question from P/F/R.
                    verdict, detail = _run_ub_probe(
                        probe, workdir, i,
                        primary_timed_out=(row["execution_status"] == "TIMEOUT"))
                    row["ub_check"], row["ub_detail"] = verdict, detail
                else:
                    row["ub_check"] = "unavailable" if UB_PROBE else "disabled"
                row["research"] = test["research"]     # annotation only
                record["tests"].append(row)
            return record
        finally:
            with _active_lock:
                _active_workdirs.discard(workdir)
            if keep_workdir:
                record["workdir"] = workdir
            else:
                record["workdir_cleaned"] = _cleanup_workdir(workdir)


def fingerprint(record):
    """Compact P/F/R row. Compile failure yields no fingerprint by design."""
    if record["compile_status"] != "OK":
        return None
    return "".join(t["status"] for t in record["tests"])
