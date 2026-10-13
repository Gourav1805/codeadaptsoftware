# CodeAdapt Handoff Summary

## Overview

CodeAdapt is a Windows-only research prototype for Programming Knowledge Tracing (PKT) experiments. It executes C++ submissions under resource and process limits, preserves per-test evidence, compares P/F/R patterns against cautious diagnostic references, and provides a student-facing follow-up practice response.

The research question is whether execution evidence can support reliable diagnosis and targeted practice while explicitly representing uncertainty, abstention, collisions, and undefined behavior. This project does not yet establish learning improvement, mastery detection, or safe public deployment.

## Current Showcase Scope

The realistic showcase scope is one controlled P5 end-to-end path:

`frontend submission -> POST /submissions -> C++ compile/run -> raw per-test evidence -> stored record -> diagnostics.interpret() -> student-safe practice response -> frontend display`

The frontend requests `GET /submissions/{submission_id}/practice` after a successful submission. The researcher-facing diagnostics endpoint remains separate. The showcase should use controlled local submissions and should not be presented as an arbitrary public coding service.

## Architecture

- `backend/app.py`: FastAPI routes, submission persistence, researcher diagnostics endpoint, and student-safe practice endpoint.
- `backend/executor.py`: compiler selection, generated harness compilation, one process per test, Windows Job Object execution, timeouts, memory limits, P/F/R classification, raw evidence, and UB probe.
- `backend/winjob.py`: Windows process/job/integrity controls. Low integrity blocks writes outside the labelled work directory, but does not block all reads.
- `backend/problems.py`: P1-P5 problem definitions, test inputs, expected outputs, starter code, and research metadata.
- `backend/diagnostics.py`: reference fingerprints, static UB declarations, P/F/R matching, abstention, and ambiguity handling.
- `backend/store.py`: SQLite storage of the complete raw record plus searchable denormalized fields.
- `backend/static/index.html`: no-build frontend for problem selection, code submission, evidence display, and practice follow-up display.
- `tests/synthetic.py`: controlled synthetic submissions, documented fingerprints, derived baselines, and UB declarations.
- `tests/run_regression.py`: execution/evidence/diagnostic/practice contract checks and fingerprint re-derivation.
- `tests/test_hardening.py`: isolation, resource, concurrency, and cleanup probes.
- `README.md`: setup, operation, invariants, toolchain, and known deployment limits.
- `FINDINGS.md`: measured instrument findings and research limitations.
- `HANDOFF_SUMMARY.md`: this transfer document.
- `SI-Pilot/`: a duplicated project tree. The active root for this handoff is the parent project, not a separate independently validated product.

## Status Labels

### VERIFIED

- The GCC 16.1.0 UCRT compiler exists at:
  `C:\tools\winlibs-x86_64-posix-seh-gcc-16.1.0-mingw-w64ucrt-14.0.0-r4\mingw64\bin\g++.exe`.
- Its reported target is `x86_64-w64-mingw32` and its version identifies `MinGW-W64 x86_64-ucrt-posix-seh`, GCC 16.1.0.
- `SI_GXX` is read by `backend/executor.py` at process startup and selects the compiler for regression or application processes. Prepending the compiler `bin` directory to the current process PATH is also recommended.
- Correct submissions compile and produce all-P fingerprints for P1-P5 in regression runs.
- Raw per-test fields include expected output, actual output, raw output, status, execution status, timing, memory, exit code, stderr, UB status, and research metadata.
- The practice endpoint reuses `diagnostics.interpret()` and stored records. It does not expose researcher-only matched error labels to students.
- Correct, ambiguous, and compile-error practice contract checks pass in the regression suite.
- Hardening probes have verified process-count containment, write blocking outside the work directory, stack-overflow containment, memory containment, and serial/parallel comparison behavior in successful runs.

### PARTIALLY VERIFIED

- The complete browser workflow has been implemented in source, but browser-level verification is not included in this audit. A server must be started from the correct project directory and the served HTML must be checked.
- The regression suite is toolchain- and UB-sensitive. The latest combined GCC 16.1.0 run exited 1 because P5/E2 observed `RRRRRRRR` against baseline `RRRFRRRR`; other runs can expose different UB-sensitive outcomes because the fixtures intentionally contain UB and non-termination.
- Hardening currently has a cleanup failure in the latest run: two `si_sub_*` directories remained. Isolation and concurrency checks passed in that run.
- The handoff clone contains the current project state as uncommitted changes, but it has not been committed, pushed, or independently accepted as the final source of truth.

### UNVERIFIED

- Learning improvement, mastery inference, PKT/BKT validity, and targeted-practice effectiveness.
- Stability of all UB-sensitive fingerprints across machines, Windows versions, compiler builds, optimization settings, and concurrent load.
- Browser automation or an end-to-end HTTP/browser acceptance test.
- Public-traffic behavior under adversarial volume or hostile submissions.

### NOT IMPLEMENTED

- A student model, knowledge tracing model, BKT model, adaptive policy, or learning-gain evaluation.
- A production authentication/authorization layer.
- Public multi-tenant isolation suitable for arbitrary submissions.
- A complete CI matrix over the documented compiler and Windows environments.

## Research Findings and Limitations

### Static versus dynamic UB evidence

`UB_DEPENDENT_CELLS` is static research reasoning about cells whose outcomes may depend on undefined behavior. `ub_check` is dynamic evidence from a second build using `-D_GLIBCXX_ASSERTIONS`. A dynamic `violation` means the probe caught an assertion in that run. `clean` does not prove that UB is absent; `timeout`, `crash`, and other inconclusive outcomes do not establish cleanliness. Static reference exclusions and dynamic observations are intentionally separate.

UB-dependent outcomes are retained in the execution record and baseline reporting but must not be presented as reliable diagnostic evidence.

### P5/E2 loop condition

The synthetic `while (lo <= hi)` fixture combines possible non-termination with out-of-bounds vector access. GCC 6.3.0 and GCC 16.1.0 UCRT can produce different fingerprints. The documented GCC 16 comparison produced `RRRFRRRR`; the historical/documented row is `RRRRRRRR`. T4 and T7 are statically declared UB-sensitive, and dynamic probe results can be incomplete when a run times out or crashes.

### P5/E4 upper midpoint

The upper-midpoint fixture can reach `arr[arr.size()]` and can fail to make progress. The observed GCC 16.1.0 UCRT row was `PPRFRRPR` against the historical/documented `PPRRRRPR`. T4 and T8 are statically UB-sensitive; probe results can be inconclusive because the primary run and the shortened probe budget interact with non-termination.

### P3/E2 underflow

T4 supplies a closing bracket to an empty stack, and the submission calls `st.top()` without checking `st.empty()`. The observed row is `PPPRPPPP` against the documented `PPPFPPPP`; T4 is classified as runtime error in the observed build. This is a known research-semantic UB divergence, not a stable claim about the modeled misconception.

## Validation Commands and Results

Run from:

`C:\Users\Rupinder Kaur\Downloads\CodeAdapt-main\CodeAdapt-main`

Verify the toolchain:

```powershell
$tool = "C:\tools\winlibs-x86_64-posix-seh-gcc-16.1.0-mingw-w64ucrt-14.0.0-r4\mingw64\bin"
$gxx = Join-Path $tool "g++.exe"
& $gxx --version
& $gxx -dumpmachine
```

Run with temporary process-scoped selection:

```powershell
$oldGxx = $env:SI_GXX
$oldPath = $env:PATH
try {
    $env:SI_GXX = $gxx
    $env:PATH = "$tool;$oldPath"
    python tests\run_regression.py
    $regressionExit = $LASTEXITCODE
    python tests\test_hardening.py
    $hardeningExit = $LASTEXITCODE
} finally {
    $env:SI_GXX = $oldGxx
    $env:PATH = $oldPath
}
```

Most recent separately captured results for this audit:

- Compiler: GCC 16.1.0 UCRT, `x86_64-w64-mingw32`.
- `python tests/run_regression.py`: latest combined run exited `1`. It reported P3/E2 and P5/E4 as documented research divergences and failed the P5/E2 baseline check because it observed `RRRRRRRR` against baseline `RRRFRRRR`.
- `python tests/test_hardening.py`: latest combined run exited `1`. It reported a parallel E2 mismatch (`RRRRRRRR` versus serial `RRRFRRRR`) and one remaining `si_sub_*` cleanup directory. The external read probe was explicitly `ALLOWED` and documented as an accepted limitation.

No test result justifies changing baselines, expected outputs, UB declarations, test fixtures, or diagnostic rules.

## Security and Deployment Boundary

The Windows Job Object limits process count, memory, and lifetime. Low integrity blocks writes outside the labelled work directory. Reads outside the work directory remain possible because integrity levels gate writes rather than reads and the child still runs as the backend user. This is an external-file-read risk.

The service is **not approved for arbitrary public submissions**. Use a controlled local showcase workload only. Public deployment would require at least a separate low-privilege account or AppContainer policy, stronger operational controls, cleanup reliability, authentication/authorization, and a fresh security review.

Do not claim that the sandbox provides complete filesystem isolation or that a successful regression run proves public safety.

## Git and GitHub State

The current working project at `C:\Users\Rupinder Kaur\Downloads\CodeAdapt-main\CodeAdapt-main` is not an independently initialized repository. Git walks upward to the accidental repository at `C:\Users\Rupinder Kaur\.git`, which has no useful project commit history and exposes unrelated home-directory files. Do not run Git operations from that accidental repository and do not stage from the user home directory.

The clean handoff clone at `C:\Users\Rupinder Kaur\Downloads\CodeAdapt-handoff` is the valid Git repository. Its origin was verified as:

`https://github.com/akaur1506/CodeAdapt.git`

It is on branch `handoff/latest-project-state`, based on the initial `origin/main` commit `8f80bdd`. The clone currently has uncommitted changes corresponding to the current project state. No commit, push, merge, force-push, permission change, or GitHub publication was performed during this audit.

## Setup and Operation

Prerequisites:

- Windows 10/11.
- Python 3.10+.
- Dependencies from `requirements.txt` (`fastapi`, `uvicorn`, `pydantic`).
- MinGW-w64 GCC 16.1.0 UCRT x86_64 POSIX SEH at a space-free path.
- The Windows Job Object and integrity APIs used by `backend/winjob.py`.

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Start the app from the project root:

```powershell
$tool = "C:\tools\winlibs-x86_64-posix-seh-gcc-16.1.0-mingw-w64ucrt-14.0.0-r4\mingw64\bin"
$oldGxx = $env:SI_GXX
$oldPath = $env:PATH
try {
    $env:SI_GXX = Join-Path $tool "g++.exe"
    $env:PATH = "$tool;$oldPath"
    python -m uvicorn app:app --port 8077 --app-dir backend
} finally {
    $env:SI_GXX = $oldGxx
    $env:PATH = $oldPath
}
```

Open `http://localhost:8077` locally. Keep the server terminal open. Do not expose the service to public traffic.

Important environment variables include `SI_GXX`, `SI_CXX_STD` (default `c++17`), `SI_OPT` (default `-O1`), `SI_TIMEOUT_S` (default `3.0`), `SI_MEMORY_MB` (default `256`), `SI_COMPILE_TIMEOUT_S` (default `20`), `SI_MAX_CONCURRENT` (default `4`), `SI_DB`, and `SI_UB_PROBE` (default enabled).

## Prioritized Next Steps

### Immediate

1. Use the GCC 16.1.0 UCRT temporary override for every showcase run.
2. Run regression and hardening immediately before the showcase and record the complete outputs.
3. Investigate and fix the cleanup leak before any broader demonstration.
4. Verify the browser requests both `POST /submissions` and `GET /submissions/{submission_id}/practice` from the intended server directory.
5. Keep the showcase local and controlled.

### Short term

1. Add an HTTP/browser acceptance test for P5 submission, stored record, practice response, and frontend display.
2. Make the validation run produce durable machine-readable artifacts without committing generated evidence.
3. Revisit UB-sensitive synthetic fixtures only through an explicitly approved research-instrument change.
4. Add a CI or scripted environment check that rejects the fallback GCC 6.3.0 compiler.

### Long term

1. Design defined-behavior diagnostic fixtures if stable cross-toolchain fingerprints are required.
2. Add a separate low-privilege execution identity or AppContainer policy to close external reads.
3. Establish an experiment protocol for diagnosis accuracy, abstention quality, and practice outcomes.
4. Evaluate learning improvement only after the instrument and deployment boundary are stable.

## Handoff Checklist

- [ ] Confirm the active working tree and do not use `C:\Users\Rupinder Kaur\.git`.
- [ ] Work from the valid handoff clone with the correct GitHub origin.
- [ ] Review all uncommitted changes against `origin/main` before staging.
- [ ] Exclude `.git`, databases, bytecode, caches, executables, credentials, and personal files.
- [ ] Verify GCC 16.1.0 UCRT and use temporary `SI_GXX`/PATH overrides.
- [ ] Run regression and hardening; preserve and report failures.
- [ ] Verify P5 browser requests and student-safe practice response.
- [ ] Check external-file-read risk and keep the service private.
- [ ] Review staged diff and run `git diff --check` before any future commit.
- [ ] Do not change research artifacts to obtain green tests.

## Claims That Must Not Be Made Yet

- The complete regression suite always passes.
- The platform reliably identifies a student's misconception from one fingerprint.
- A clean UB probe proves the absence of undefined behavior.
- The platform detects mastery or improves learning.
- The service is safe for arbitrary public submissions.
- The current hardening result proves complete filesystem isolation.
- The browser workflow has been independently acceptance-tested unless a fresh browser run is recorded.
