"""Setup verification, written for someone who is not a programmer.

Called by 1-SETUP.bat. Actually compiles and runs a submission end to end,
because "the compiler exists" and "the compiler works" are different claims --
and the difference here is usually a space in an install path, which produces
a confusing linker error rather than an obvious one.

Exit code 0 = ready to use. Anything else = a message the reader can act on.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "backend"))


def fail(problem, fix):
    print("       PROBLEM: %s" % problem)
    print("       FIX: %s" % fix)
    return 1


def main():
    try:
        import executor
    except RuntimeError as exc:
        return fail(str(exc).splitlines()[0],
                    "This software only runs on Windows.")
    except ImportError as exc:
        return fail("a Python package is missing (%s)" % exc,
                    "Run 1-SETUP.bat again while connected to the internet.")

    correct = (
        "int lowerBound(const std::vector<int>& arr, int target) {\n"
        "    int lo = 0, hi = (int)arr.size();\n"
        "    while (lo < hi) {\n"
        "        int mid = lo + (hi - lo) / 2;\n"
        "        if (arr[mid] < target) lo = mid + 1; else hi = mid;\n"
        "    }\n"
        "    return lo;\n"
        "}")

    try:
        record = executor.evaluate("P5", correct)
    except Exception as exc:                       # noqa: BLE001 - report anything
        return fail("could not run a test program (%s)" % exc,
                    "Send this whole message to whoever gave you this folder.")

    if record["compile_status"] == "TOOLCHAIN_MISSING":
        return fail(
            "the C++ compiler could not be found or started",
            "Double-click INSTALL-COMPILER.bat, let it finish, then run "
            "1-SETUP.bat again.")

    if record["compile_status"] != "OK":
        detail = ((record["compile"].get("stderr") or "")
                  + (record["compile"].get("detail") or "")).strip()
        if "cannot find" in detail and ":\\" in detail:
            return fail(
                "the compiler is installed somewhere with a SPACE in the path",
                "Move it to C:\\mingw64 exactly. A space breaks its linker.")
        print("       PROBLEM: a known-good test program did not compile.")
        if detail:
            print("       The compiler said:")
            for line in detail.splitlines()[:6]:
                print("         " + line)
        else:
            print("       Status was: %s" % record["compile_status"])
        return fail("see above", "Re-run INSTALL-COMPILER.bat, then 1-SETUP.bat.")

    got = executor.fingerprint(record)
    if got != "PPPPPPPP":
        return fail(
            "a known-correct program gave %s instead of all passes" % got,
            "Do not trust results from this machine. Report this exact line.")

    print("       Compiled and ran a program: all 8 tests passed.")
    print("       Compiler: %s" % executor.compiler_version())
    print("       Instrument ID: %s" % executor.instrument_hash("P5"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
