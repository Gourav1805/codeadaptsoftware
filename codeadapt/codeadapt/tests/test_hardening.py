"""Concurrency and isolation-boundary probes.

These do not test the pilot problems. They test claims about the sandbox --
by attempting the hostile action and reporting what actually happened, rather
than asserting that a flag was set.

Probes report through the submission's own return value: 1 means the hostile
action SUCCEEDED, 0 means it was blocked.
"""
import concurrent.futures
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import executor      # noqa: E402
import synthetic     # noqa: E402

RESULTS = []


def note(label, verdict, detail):
    RESULTS.append((label, verdict, detail))
    print("  [%-8s] %-34s %s" % (verdict, label, detail))


def probe(code, test_index=0):
    """Run a probe submission; return (status, actual_output, error)."""
    rec = executor.evaluate("P5", code)
    if rec["compile_status"] != "OK":
        return "COMPILE_ERROR", None, rec["compile"]["stderr_student_lines"][:200]
    t = rec["tests"][test_index]
    return t["status"], t["actual_output"], t["error"]


# --------------------------------------------------------------- probes
SPAWN = """
#include <cstdlib>
int lowerBound(const std::vector<int>& arr, int target) {
    std::system("cmd /c echo x > spawned_probe.txt");
    FILE* f = fopen("spawned_probe.txt", "r");
    if (f) { fclose(f); return 1; }
    return 0;
}"""

FS_WRITE_OUTSIDE = """
#include <cstdlib>
int lowerBound(const std::vector<int>& arr, int target) {
    const char* tmp = getenv("TEMP");
    if (!tmp) return 0;
    std::string p = std::string(tmp) + "\\\\si_escape_probe.txt";
    FILE* f = fopen(p.c_str(), "w");
    if (f) { fputs("escaped", f); fclose(f); return 1; }
    return 0;
}"""

FS_READ_OUTSIDE = """
#include <cstdlib>
int lowerBound(const std::vector<int>& arr, int target) {
    FILE* f = fopen("C:\\\\Windows\\\\win.ini", "r");
    if (f) { fclose(f); return 1; }
    return 0;
}"""

STACK_OVERFLOW = """
int burn(int n) { volatile int pad[256]; pad[0] = n; return burn(n + 1) + pad[0]; }
int lowerBound(const std::vector<int>& arr, int target) { return burn(1); }"""


def isolation():
    print("\n=== ISOLATION BOUNDARY PROBES ===")

    st, out, err = probe(SPAWN)
    if out == 0 or st == "R":
        note("process spawning", "BLOCKED", "ActiveProcessLimit=1 held (%s)" % st)
    else:
        note("process spawning", "ALLOWED", "child process ran -- limit did NOT hold")

    st, out, err = probe(FS_WRITE_OUTSIDE)
    probe_file = os.path.join(os.environ.get("TEMP", ""), "si_escape_probe.txt")
    landed = os.path.exists(probe_file)
    if out == 1 or landed:
        # Was the accepted gap until the Low-integrity sandbox landed. If it
        # comes back, the sandbox is not in effect -- treat it as a failure.
        note("write outside workdir", "LEAKED",
             "REGRESSION -- Low-integrity token not applied")
        if landed:
            os.remove(probe_file)
    else:
        note("write outside workdir", "BLOCKED", "Low-integrity mandatory label")

    st, out, err = probe(FS_READ_OUTSIDE)
    note("read outside workdir", "ALLOWED" if out == 1 else "BLOCKED",
         "EXPECTED -- integrity levels gate writes, not reads; reads follow DACLs"
         if out == 1 else "blocked (%s)" % st)

    st, out, err = probe(STACK_OVERFLOW)
    note("unbounded recursion", "CONTAINED" if st == "R" else "LEAKED",
         "%s / %s" % (st, err))

    st, out, err = probe(synthetic.P5["memory_bomb"])
    note("memory exhaustion", "CONTAINED" if st == "R" else "LEAKED",
         "%s / %s" % (st, err))


def concurrency(workers=8):
    print("\n=== CONCURRENCY (%d parallel submissions) ===" % workers)
    names = ["correct", "linear_scan", "E1_missing_increment", "E2_loop_condition",
             "E3_upper_bound", "E4_upper_mid", "crash", "infinite_loop"]

    serial = {}
    for n in names:
        rec = executor.evaluate("P5", synthetic.P5[n])
        serial[n] = executor.fingerprint(rec)

    def one(n):
        rec = executor.evaluate("P5", synthetic.P5[n])
        return n, executor.fingerprint(rec)

    batch = names * 2
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        parallel = list(ex.map(one, batch))

    mismatches = [(n, fp, serial[n]) for n, fp in parallel if fp != serial[n]]
    if mismatches:
        for n, got, want in mismatches:
            note("parallel %s" % n, "MISMATCH", "%s != serial %s" % (got, want))
    else:
        note("parallel == serial results", "OK",
             "%d submissions, %d workers, all fingerprints identical"
             % (len(batch), workers))

    # Cleanup is eventual: Windows keeps a handle on a terminated process's
    # files briefly, so a just-finished submission may still be queued.
    import time as _t
    _t.sleep(2)
    outstanding = executor.sweep()
    leftovers = [d for d in os.listdir(os.environ.get("TEMP", "."))
                 if d.startswith("si_sub_")]
    note("temp directory cleanup", "OK" if not leftovers else "LEAK",
         "%d si_sub_* dirs remain, %d queued for retry" % (len(leftovers), outstanding))


def main():
    isolation()
    concurrency()
    print("\n" + "=" * 72)
    bad = [r for r in RESULTS if r[1] in ("MISMATCH", "LEAK", "LEAKED")]
    gaps = [r for r in RESULTS if r[1] == "ALLOWED"]
    if bad:
        print("HARDENING FAILURES (%d):" % len(bad))
        for label, verdict, detail in bad:
            print("  - %s: %s" % (label, detail))
    else:
        print("No hardening failures.")
    if gaps:
        print("\nKNOWN, ACCEPTED GAPS (%d) -- documented, not silently ignored:" % len(gaps))
        for label, _, detail in gaps:
            print("  - %s: %s" % (label, detail))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
