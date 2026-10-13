"""Windows Job Object sandbox for untrusted student binaries.

Phase 0 established this machine has no working container runtime and no
seccomp/cgroups/setrlimit.  Job Objects are the isolation primitive that IS
available, and they give us the four guarantees P/F/R integrity depends on:
memory cap, process-spawn block, guaranteed cleanup, and silent death on
unhandled exception (no WER dialog stalling a crash into a fake timeout).

The child is created SUSPENDED and assigned to the job before its first
instruction runs, so there is no window in which it could spawn a child that
escapes the limits.
"""
import ctypes
import os
import sys

if sys.platform != "win32":
    raise RuntimeError(
        "This sandbox is Windows-only. It relies on Job Objects and integrity\n"
        "levels, which have no equivalent here, and there is deliberately no\n"
        "silent fallback: running student code without the memory cap, process\n"
        "limit and timeout would produce evidence under unknown conditions.\n"
        "\n"
        "To port it, replace winjob.run_sandboxed() with a POSIX equivalent\n"
        "(setrlimit for memory, process groups for cleanup, SIGKILL on\n"
        "timeout) keeping the same SandboxResult fields. Everything above it\n"
        "-- executor, diagnostics, store, API, UI -- is platform-independent.\n"
        "Detected platform: %s" % sys.platform)

import ctypes.wintypes as w  # noqa: E402  (Windows-only, guarded above)

k32 = ctypes.WinDLL("kernel32", use_last_error=True)

# --- Job limit flags ---
_ACTIVE_PROCESS = 0x00000008
_PROCESS_MEMORY = 0x00000100
_JOB_MEMORY = 0x00000200
_DIE_ON_UNHANDLED_EXCEPTION = 0x00000400
_KILL_ON_JOB_CLOSE = 0x00002000

_CREATE_SUSPENDED = 0x00000004
_CREATE_NO_WINDOW = 0x08000000
_STARTF_USESTDHANDLES = 0x00000100
_GENERIC_WRITE = 0x40000000
_FILE_SHARE_READ = 0x00000001
_CREATE_ALWAYS = 2
_FILE_ATTRIBUTE_NORMAL = 0x80
_INVALID_HANDLE = w.HANDLE(-1).value
_INFINITE = 0xFFFFFFFF
_WAIT_TIMEOUT = 0x00000102
_JOBOBJECT_EXTENDED_LIMIT_INFORMATION = 9


class _BASIC(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", w.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", w.DWORD),
        ("Affinity", ctypes.POINTER(ctypes.c_ulong)),
        ("PriorityClass", w.DWORD),
        ("SchedulingClass", w.DWORD),
    ]


class _IO(ctypes.Structure):
    _fields_ = [("ReadOperationCount", ctypes.c_uint64),
                ("WriteOperationCount", ctypes.c_uint64),
                ("OtherOperationCount", ctypes.c_uint64),
                ("ReadTransferCount", ctypes.c_uint64),
                ("WriteTransferCount", ctypes.c_uint64),
                ("OtherTransferCount", ctypes.c_uint64)]


class _EXT(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", _BASIC), ("IoInfo", _IO),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t)]


class _STARTUPINFOW(ctypes.Structure):
    _fields_ = [("cb", w.DWORD), ("lpReserved", w.LPWSTR),
                ("lpDesktop", w.LPWSTR), ("lpTitle", w.LPWSTR),
                ("dwX", w.DWORD), ("dwY", w.DWORD), ("dwXSize", w.DWORD),
                ("dwYSize", w.DWORD), ("dwXCountChars", w.DWORD),
                ("dwYCountChars", w.DWORD), ("dwFillAttribute", w.DWORD),
                ("dwFlags", w.DWORD), ("wShowWindow", w.WORD),
                ("cbReserved2", w.WORD), ("lpReserved2", ctypes.c_void_p),
                ("hStdInput", w.HANDLE), ("hStdOutput", w.HANDLE),
                ("hStdError", w.HANDLE)]


class _PROCINFO(ctypes.Structure):
    _fields_ = [("hProcess", w.HANDLE), ("hThread", w.HANDLE),
                ("dwProcessId", w.DWORD), ("dwThreadId", w.DWORD)]


class _SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("nLength", w.DWORD), ("lpSecurityDescriptor", ctypes.c_void_p),
                ("bInheritHandle", w.BOOL)]


k32.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD,
                            ctypes.POINTER(_SECURITY_ATTRIBUTES),
                            w.DWORD, w.DWORD, w.HANDLE]
k32.CreateFileW.restype = w.HANDLE


def _open_inheritable_log(path):
    """A single inheritable write handle for the child's stderr.

    This is the ONLY inheritable handle we create, and Python marks its own
    handles non-inheritable (PEP 446), so turning on handle inheritance does
    not hand the untrusted child anything else.
    """
    sa = _SECURITY_ATTRIBUTES()
    sa.nLength = ctypes.sizeof(sa)
    sa.lpSecurityDescriptor = None
    sa.bInheritHandle = True
    h = k32.CreateFileW(path, _GENERIC_WRITE, _FILE_SHARE_READ, ctypes.byref(sa),
                        _CREATE_ALWAYS, _FILE_ATTRIBUTE_NORMAL, None)
    return None if (h is None or h == _INVALID_HANDLE) else h


advapi = ctypes.WinDLL("advapi32", use_last_error=True)

# --- Low-integrity support ------------------------------------------------
# Job Objects bound CPU, memory, process count and lifetime, but NOT the
# filesystem. Dropping the child to Low integrity does: a Low process cannot
# write to any object whose mandatory label is higher, which is everything the
# backend user owns. This needs no new account and no elevation -- a process
# may always lower its own token.
_TOKEN_QUERY = 0x0008
_TOKEN_ADJUST_DEFAULT = 0x0080
_TOKEN_INTEGRITY_LEVEL = 25
_SE_GROUP_INTEGRITY = 0x00000020
_LOW_INTEGRITY_SID = "S-1-16-4096"


class _SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", w.DWORD)]


class _TOKEN_MANDATORY_LABEL(ctypes.Structure):
    _fields_ = [("Label", _SID_AND_ATTRIBUTES)]


# Explicit signatures. Without these, ctypes defaults HANDLE returns/args to
# 32-bit int and silently truncates them on x64.
advapi.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)]
advapi.OpenProcessToken.restype = w.BOOL
advapi.ConvertStringSidToSidW.argtypes = [w.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
advapi.ConvertStringSidToSidW.restype = w.BOOL
advapi.SetTokenInformation.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
advapi.SetTokenInformation.restype = w.BOOL


def _set_low_integrity(h_process):
    """Drop an already-created (still suspended) process to Low integrity.

    Lowering a token is always permitted, so unlike CreateProcessAsUser this
    needs no SE_ASSIGNPRIMARYTOKEN privilege and no separate account. Applied
    while the child is suspended, so it takes effect before the first
    instruction runs -- the same race-free guarantee as the job assignment.
    """
    tok = w.HANDLE()
    if not advapi.OpenProcessToken(h_process,
                                   _TOKEN_ADJUST_DEFAULT | _TOKEN_QUERY,
                                   ctypes.byref(tok)):
        return False
    sid = ctypes.c_void_p()
    try:
        if not advapi.ConvertStringSidToSidW(_LOW_INTEGRITY_SID, ctypes.byref(sid)):
            return False
        label = _TOKEN_MANDATORY_LABEL()
        label.Label.Sid = sid
        label.Label.Attributes = _SE_GROUP_INTEGRITY
        return bool(advapi.SetTokenInformation(
            tok, _TOKEN_INTEGRITY_LEVEL, ctypes.byref(label), ctypes.sizeof(label)))
    finally:
        if sid:
            k32.LocalFree(sid)
        k32.CloseHandle(tok)


def label_dir_low(path):
    """Mark a directory Low-integrity-writable so the sandboxed child can still
    write its result file there. Returns True on success."""
    import subprocess
    try:
        p = subprocess.run(["icacls", path, "/setintegritylevel", "(OI)(CI)Low"],
                           capture_output=True, text=True, timeout=30)
        return p.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


class SandboxResult:
    __slots__ = ("timed_out", "exit_code", "wall_ms", "peak_memory_bytes",
                 "integrity")

    def __init__(self, timed_out, exit_code, wall_ms, peak_memory_bytes,
                 integrity="unknown"):
        self.timed_out = timed_out
        self.exit_code = exit_code
        self.wall_ms = wall_ms
        self.peak_memory_bytes = peak_memory_bytes
        # Recorded, never assumed: if the low-integrity launch could not be
        # set up we fall back to the caller's integrity, and the evidence
        # record must say which actually happened.
        self.integrity = integrity

    def __repr__(self):
        return ("SandboxResult(timed_out=%r, exit_code=%s, wall_ms=%.1f, peak=%d)"
                % (self.timed_out, hex(self.exit_code & 0xFFFFFFFF)
                   if self.exit_code else self.exit_code,
                   self.wall_ms, self.peak_memory_bytes))


def run_sandboxed(argv, cwd, timeout_s, memory_bytes, low_integrity=True,
                  stderr_path=None):
    """Run argv under a Job Object, by default at Low integrity. Returns
    SandboxResult; never raises on student misbehaviour. stdout/stderr are
    discarded by design -- the harness reports through a result file, so there
    are no pipes to deadlock on."""
    import time

    job = k32.CreateJobObjectW(None, None)
    if not job:
        raise OSError("CreateJobObjectW failed: %d" % ctypes.get_last_error())

    info = _EXT()
    info.BasicLimitInformation.LimitFlags = (
        _PROCESS_MEMORY | _JOB_MEMORY | _ACTIVE_PROCESS
        | _KILL_ON_JOB_CLOSE | _DIE_ON_UNHANDLED_EXCEPTION)
    info.ProcessMemoryLimit = memory_bytes
    info.JobMemoryLimit = memory_bytes
    info.BasicLimitInformation.ActiveProcessLimit = 1  # blocks process spawning
    if not k32.SetInformationJobObject(job, _JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
                                       ctypes.byref(info), ctypes.sizeof(info)):
        err = ctypes.get_last_error()
        k32.CloseHandle(job)
        raise OSError("SetInformationJobObject failed: %d" % err)

    si = _STARTUPINFOW()
    si.cb = ctypes.sizeof(si)
    pi = _PROCINFO()
    cmdline = ctypes.create_unicode_buffer(_quote(argv))

    # stderr to a file, never a pipe: a pipe can deadlock if the child fills
    # the buffer while we are blocked waiting on it.
    log = _open_inheritable_log(stderr_path) if stderr_path else None
    if log:
        si.dwFlags |= _STARTF_USESTDHANDLES
        si.hStdError = log
        si.hStdOutput = log
        si.hStdInput = None

    ok = k32.CreateProcessW(None, cmdline, None, None, bool(log),
                            _CREATE_SUSPENDED | _CREATE_NO_WINDOW,
                            None, cwd, ctypes.byref(si), ctypes.byref(pi))
    if log:
        k32.CloseHandle(log)          # child holds its own copy
    if not ok:
        err = ctypes.get_last_error()
        k32.CloseHandle(job)
        raise OSError("CreateProcessW failed: %d" % err)

    # Still suspended: lower integrity before anything executes. Falling back
    # rather than refusing to run, but the record always says which happened.
    integrity = "low" if (low_integrity and _set_low_integrity(pi.hProcess)) else "medium"

    started = time.perf_counter()
    try:
        # Assign BEFORE the first instruction runs -- no escape window.
        if not k32.AssignProcessToJobObject(job, pi.hProcess):
            raise OSError("AssignProcessToJobObject failed: %d"
                          % ctypes.get_last_error())
        k32.ResumeThread(pi.hThread)

        rc = k32.WaitForSingleObject(pi.hProcess, int(timeout_s * 1000))
        wall_ms = (time.perf_counter() - started) * 1000.0

        if rc == _WAIT_TIMEOUT:
            k32.TerminateJobObject(job, 1)
            k32.WaitForSingleObject(pi.hProcess, 2000)
            peak = _peak(job)
            return SandboxResult(True, None, wall_ms, peak, integrity)

        code = w.DWORD()
        k32.GetExitCodeProcess(pi.hProcess, ctypes.byref(code))
        peak = _peak(job)
        return SandboxResult(False, int(code.value), wall_ms, peak, integrity)
    finally:
        k32.CloseHandle(pi.hThread)
        k32.CloseHandle(pi.hProcess)
        k32.CloseHandle(job)  # KILL_ON_JOB_CLOSE guarantees no survivors


def _peak(job):
    info = _EXT()
    ret = w.DWORD()
    if k32.QueryInformationJobObject(job, _JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
                                     ctypes.byref(info), ctypes.sizeof(info),
                                     ctypes.byref(ret)):
        return int(info.PeakProcessMemoryUsed)
    return 0


def _quote(argv):
    out = []
    for a in argv:
        a = str(a)
        out.append('"%s"' % a.replace('"', '\\"') if (" " in a or not a) else a)
    return " ".join(out)
