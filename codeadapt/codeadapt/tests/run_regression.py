"""Full regression suite for the execution/evidence layer.

Every execution-system change must run this. A fix is not complete because the
originally failing case now passes -- the whole suite must still hold.

Checks, in order:
  1. Infrastructure invariants (Phases 3-5): correct -> P, wrong -> F,
     crash -> R, timeout -> R, memory bomb -> R, compile error -> its own
     status and NEVER an F, backend process survives all of it.
  2. Fingerprint re-derivation: every synthetic error is executed and its
     P/F/R row compared against what the frozen documents claim.

Divergences are reported, never silently reconciled.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import diagnostics        # noqa: E402
import executor           # noqa: E402
import app                # noqa: E402
import problems           # noqa: E402
import synthetic          # noqa: E402
from unittest.mock import patch  # noqa: E402

FAILURES = []
NOTES = []


def check(label, condition, detail=""):
    mark = "PASS" if condition else "FAIL"
    print("  [%s] %s%s" % (mark, label, ("  -- " + detail) if detail else ""))
    if not condition:
        FAILURES.append(label + ((" -- " + detail) if detail else ""))
    return condition


_last_record = [None]


def run(pid, name):
    code = synthetic.SUBMISSIONS[pid][name]
    rec = executor.evaluate(pid, code)
    _last_record[0] = rec
    return rec


def row(rec):
    return executor.fingerprint(rec) or ("<%s>" % rec["compile_status"])


# ---------------------------------------------------------------- section 1
def infrastructure():
    print("\n=== 1. INFRASTRUCTURE INVARIANTS ===")

    for pid in ("P1", "P2", "P3", "P4", "P5"):
        rec = run(pid, "correct")
        fp = row(rec)
        ok = rec["compile_status"] == "OK"
        check("%s correct submission compiles" % pid, ok, rec["compile_status"])
        check("%s correct submission is all-P" % pid, fp == "P" * len(rec["tests"]),
              "fingerprint " + fp)

    print()
    rec = run("P5", "E3_upper_bound")
    check("wrong answer classified F (not R)",
          any(t["status"] == "F" for t in rec["tests"])
          and all(t["execution_status"] in ("COMPLETED",) for t in rec["tests"]),
          "fingerprint " + row(rec))

    for pid in ("P1", "P2", "P3", "P4", "P5"):
        rec = run(pid, "crash")
        st = set(t["status"] for t in rec["tests"])
        es = set(t["execution_status"] for t in rec["tests"])
        check("%s crash -> all R" % pid, st == {"R"}, "statuses %s" % sorted(st))
        check("%s crash execution_status is CRASHED" % pid, es == {"CRASHED"},
              "%s / %s" % (sorted(es), rec["tests"][0]["error"]))

    for pid in ("P1", "P2", "P3", "P4", "P5"):
        rec = run(pid, "infinite_loop")
        st = set(t["status"] for t in rec["tests"])
        es = set(t["execution_status"] for t in rec["tests"])
        check("%s infinite loop -> all R via TIMEOUT" % pid,
              st == {"R"} and es == {"TIMEOUT"}, "%s / %s" % (sorted(st), sorted(es)))

    rec = run("P5", "memory_bomb")
    st = set(t["status"] for t in rec["tests"])
    check("memory bomb -> R (limit enforced, not OOM on the host)", st == {"R"},
          "statuses %s / %s" % (sorted(st), rec["tests"][0]["error"]))
    peak = max(t["memory_bytes"] for t in rec["tests"])
    check("memory bomb peak stayed within the 256MB cap",
          peak <= executor.MEMORY_BYTES * 1.05,
          "peak %.1f MB" % (peak / 1048576.0))

    rec = run("P5", "compile_error")
    check("compile error keeps its own status", rec["compile_status"] == "COMPILE_ERROR")
    check("compile error produces NO test rows (never mapped to F)",
          rec["tests"] == [], "%d rows" % len(rec["tests"]))
    check("compile error yields no fingerprint", executor.fingerprint(rec) is None)
    check("compiler diagnostics captured", bool(rec["compile"]["stderr"].strip()))
    check("diagnostics remapped to student line numbers",
          "line 1:" in rec["compile"]["stderr_student_lines"])

    print()
    check("backend process survived every hostile submission", True)


# ---------------------------------------------------------------- section 2
def evidence_integrity():
    print("\n=== 2. EVIDENCE INTEGRITY ===")
    rec = run("P5", "correct")
    t0 = rec["tests"][0]
    for field in ("test_id", "expected_output", "actual_output", "status",
                  "execution_status", "runtime_ms", "memory_bytes", "exit_code"):
        check("raw evidence field present: %s" % field, field in t0)
    check("research metadata carried separately from execution fields",
          "research" in t0 and "diagnostic_target" in t0["research"])
    check("limits recorded on the submission record",
          rec["limits"]["wall_timeout_s"] == executor.WALL_TIMEOUT_S)

    # Determinism: the same submission run twice must produce the same row.
    a = row(run("P5", "E1_missing_increment"))
    b = row(run("P5", "E1_missing_increment"))
    check("re-running a submission is deterministic", a == b, "%s vs %s" % (a, b))

    # Test isolation: a submission that scribbles on static state must not let
    # one test's result leak into the next.
    leaky = """
static std::vector<int> g_cache;
int lowerBound(const std::vector<int>& arr, int target) {
    if (!g_cache.empty()) return -999;
    g_cache = arr;
    int lo = 0, hi = (int)arr.size();
    while (lo < hi) { int m = lo + (hi-lo)/2; if (arr[m] < target) lo = m+1; else hi = m; }
    return lo;
}"""
    rec = executor.evaluate("P5", leaky)
    check("global state cannot contaminate later tests", row(rec) == "PPPPPPPP",
          "fingerprint " + row(rec))


# ---------------------------------------------------------------- section 3
def fingerprints():
    """Re-derive every row by execution. Enforce the measured baseline; report
    (but do not auto-reconcile) disagreement with the frozen documents."""
    print("\n=== 3. FINGERPRINT RE-DERIVATION ===")
    divergences = []
    ub_notes = []
    for pid in ("P1", "P2", "P3", "P4", "P5"):
        claimed = synthetic.DOCUMENTED_FINGERPRINTS.get(pid, {})
        baseline = synthetic.DERIVED_FINGERPRINTS.get(pid, {})
        ids = [t["test_id"] for t in problems.get(pid)["tests"]]
        print("\n%s  (%s)   tests: %s" % (pid, problems.get(pid)["concept"], " ".join(ids)))
        for name in synthetic.SUBMISSIONS[pid]:
            if name in ("infinite_loop", "crash", "memory_bomb", "compile_error"):
                continue
            observed = row(run(pid, name))

            # 1. Baseline drift is an infrastructure failure.
            base = baseline.get(name)
            if base is None:
                check("baseline recorded for %s/%s" % (pid, name), False,
                      "observed %s -- add it to DERIVED_FINGERPRINTS" % observed)
            elif base != observed:
                check("baseline holds for %s/%s" % (pid, name), False,
                      "observed %s, baseline %s" % (observed, base))

            # 2. Disagreement with the frozen document is research-semantic.
            exp = claimed.get(name)
            if exp is None:
                tag = "(no documented claim)"
            elif exp == observed:
                tag = "matches doc"
            else:
                tag = "DOC CLAIMS %s  <-- DIVERGENCE" % exp
                divergences.append((pid, name, exp, observed, ids))

            flagged = synthetic.ub_cells(pid, name)
            if flagged:
                tag += "   [UB cells: %s]" % ",".join(flagged)
            print("    %-24s %s   %s" % (name, observed, tag))

            # Cross-check the hand-written UB flags against what the probe
            # actually measured. The flags were derived by static reasoning;
            # this is what turns them into a verified claim.
            rec = _last_record[0]
            if rec and rec.get("tests"):
                measured = [t["test_id"] for t in rec["tests"]
                            if t["ub_check"] == "violation"]
                inconclusive = [t["test_id"] for t in rec["tests"]
                                if t["ub_check"] in ("timeout", "unavailable",
                                                     "disabled", "not_run")]
                if measured or flagged:
                    ub_notes.append((pid, name, flagged, measured, inconclusive))
                # Declared but not measured, excluding cells we could not observe.
                missed = [c for c in flagged
                          if c not in measured and c not in inconclusive]
                extra = [c for c in measured if c not in flagged]
                if missed:
                    check("UB flags match probe for %s/%s" % (pid, name), False,
                          "declared %s but probe found it clean" % missed)
                if extra:
                    check("UB flags match probe for %s/%s" % (pid, name), False,
                          "probe found undeclared UB at %s" % extra)
    return divergences, ub_notes



# ---------------------------------------------------------------- section 4
_NL = chr(10)

# A mistake that is NOT in the modelled set: return n whenever the target is
# found. It yields P5's E3 row exactly, which is the clearest demonstration
# that P/F/R matching cannot identify a root cause.
NOVEL_P5_BUG = _NL.join([
    "int lowerBound(const std::vector<int>& arr, int target) {",
    "    int lo = 0, hi = (int)arr.size();",
    "    while (lo < hi) {",
    "        int mid = lo + (hi - lo) / 2;",
    "        if (arr[mid] == target) return (int)arr.size();",
    "        if (arr[mid] < target) lo = mid + 1; else hi = mid;",
    "    }",
    "    return lo;",
    "}"])


def diagnostic_layer():
    print(chr(10) + "=== 4. DIAGNOSTIC LAYER ===")

    d = diagnostics.interpret(run("P5", "correct"))
    check("correct P5 -> task_correct, not mastery", d["verdict"] == "task_correct"
          and "does NOT establish that Binary Search was used" in d["summary"])

    d = diagnostics.interpret(run("P5", "linear_scan"))
    check("linear scan is indistinguishable from correct",
          d["verdict"] == "task_correct", d["observed"])

    d = diagnostics.interpret(run("P2", "B_wrong_return"))
    check("P2 B/C collision reported as ambiguous, not guessed",
          d["verdict"] == "ambiguous" and set(d["matched"]) ==
          {"B_wrong_return", "C_off_by_one"}, str(d["matched"]))

    d = diagnostics.interpret(run("P5", "E4_upper_mid"))
    check("UB cells excluded from matching",
            d["reference_ub_cells"].get("E4_upper_mid") == ["T4", "T8"]
            and d["excluded_cells"] == d["dynamic_ub_cells"]
              and set(d["dynamic_ub_cells"]).issubset(set(d["test_ids"])),
            "static=%s dynamic=%s" %
            (d["reference_ub_cells"].get("E4_upper_mid"),
             d["dynamic_ub_cells"]))

    inconclusive_e4 = executor.evaluate("P5", synthetic.P5["E4_upper_mid"])
    inconclusive_e4["tests"][3]["ub_check"] = "violation"
    inconclusive_e4["tests"][7]["ub_check"] = "timeout"
    d = diagnostics.interpret(inconclusive_e4)
    e4_candidate = next(c for c in d["candidates"]
                         if c["error"] == "E4_upper_mid")
    check("inconclusive E4 T8 remains statically excluded",
          d["dynamic_ub_cells"] == ["T4"]
          and d["reference_ub_cells"]["E4_upper_mid"] == ["T4", "T8"]
          and "T8" not in e4_candidate["mismatched_tests"],
          "dynamic=%s static=%s mismatches=%s" %
          (d["dynamic_ub_cells"], d["reference_ub_cells"]["E4_upper_mid"],
           e4_candidate["mismatched_tests"]))

    d = diagnostics.interpret(run("P5", "compile_error"))
    check("compile error yields no diagnostic claim",
          d["verdict"] == "no_execution_evidence" and not d["candidates"])

    # KNOWN LIMITATION, asserted so it cannot be silently forgotten: an
    # unmodelled bug produces E3's row and is attributed to it. The values in
    # observed_outputs do differ, but matching does not look at them.
    rec = executor.evaluate("P5", NOVEL_P5_BUG)
    d = diagnostics.interpret(rec)
    check("KNOWN LIMIT: unmodelled bug collides with E3 row",
          d["observed"] == "FPPPFFPF" and d["matched"] == ["E3_upper_bound"],
          "observed %s matched %s" % (d["observed"], d["matched"]))
    ref = diagnostics.REFERENCE["P5"]["E3_upper_bound"]
    check("...and P/F/R alone cannot separate them", d["observed"] == ref)
    e3 = executor.evaluate("P5", synthetic.P5["E3_upper_bound"])
    differing = [a["test_id"] for a, b in zip(e3["tests"], rec["tests"])
                 if a["actual_output"] != b["actual_output"]]
    check("...but the returned values do differ (evidence is preserved)",
          bool(differing), "differ on %s" % ", ".join(differing))

def practice_endpoint():
    print(chr(10) + "=== 5. PRACTICE FOLLOW-UP CONTRACT ===")

    correct = executor.evaluate("P5", synthetic.P5["correct"])
    original_tests = [dict(t) for t in correct["tests"]]
    with patch.object(app.store, "load", return_value=correct):
        result = app.submission_practice(correct["submission_id"])
    check("correct P5 returns a safe practice result",
          result["state"] == "correct"
          and "mastery" in result["message"]
          and "verdict" not in result
          and "matched" not in result)
    check("recommendation targets an existing problem",
          result["recommendation"]["problem_id"] in problems.PROBLEMS,
          result["recommendation"]["problem_id"])
    check("practice result preserves raw execution evidence",
          correct["tests"] == original_tests)

    ambiguous = executor.evaluate("P2", synthetic.P2["B_wrong_return"])
    with patch.object(app.store, "load", return_value=ambiguous):
        result = app.submission_practice(ambiguous["submission_id"])
    check("ambiguous result is explicit and retries the same problem",
          result["state"] == "insufficient_evidence"
          and "Insufficient evidence" in result["message"]
          and result["recommendation"]["action"] == "retry"
          and result["recommendation"]["problem_id"] == "PILOT-002")

    compile_error = executor.evaluate("P5", synthetic.P5["compile_error"])
    with patch.object(app.store, "load", return_value=compile_error):
        result = app.submission_practice(compile_error["submission_id"])
    check("missing execution evidence preserves compilation feedback",
          result["state"] == "no_execution_evidence"
          and result["compile_status"] == "COMPILE_ERROR"
          and bool(result["compile_feedback"]))


def main():
    infrastructure()
    evidence_integrity()
    diagnostic_layer()
    practice_endpoint()
    divergences, ub_notes = fingerprints()

    print("\n" + "=" * 72)
    if FAILURES:
        print("INFRASTRUCTURE FAILURES (%d):" % len(FAILURES))
        for f in FAILURES:
            print("  - " + f)
    else:
        print("INFRASTRUCTURE: all checks passed.")

    if divergences:
        print("\nDOCUMENT DIVERGENCES (%d) -- research-semantic, NOT auto-corrected:"
              % len(divergences))
        for pid, name, exp, obs, ids in divergences:
            diffs = ["%s: doc=%s observed=%s" % (ids[i], exp[i], obs[i])
                     for i in range(min(len(exp), len(obs))) if exp[i] != obs[i]]
            print("  - %s / %s" % (pid, name))
            print("      doc      %s" % exp)
            print("      observed %s" % obs)
            print("      cells    %s" % "; ".join(diffs))
    else:
        print("\nAll documented fingerprints reproduced exactly.")

    if ub_notes:
        print("\nUNDEFINED BEHAVIOUR (%d rows) -- 'declared' is the hand-written"
              " flag, 'measured'\nis what the -D_GLIBCXX_ASSERTIONS probe actually"
              " caught. These cells are NOT\nusable as diagnostic evidence: their"
              " outcome tracks incidental memory\nlayout, not the modelled error."
              % len(ub_notes))
        for pid, name, declared, measured, incon in ub_notes:
            print("  - %s / %s" % (pid, name))
            print("      declared: %s" % (", ".join(declared) or "none"))
            print("      measured: %s%s" % (", ".join(measured) or "none",
                  ("   [inconclusive: " + ", ".join(incon) + "]") if incon else ""))

    for n in NOTES:
        print("\nNOTE: " + n)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
