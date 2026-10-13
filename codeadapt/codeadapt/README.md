# CodeAdapt — Adaptive C++ Coding Practice & Research Instrument

A C++ coding-practice platform and empirical research instrument that investigates whether execution behaviors from untrusted C++ submissions can provide valid evidence of programming misconceptions and guide targeted pedagogical practice.

---

## 1. Architecture & Repository Layout

```
codeadapt/
├── backend/
│   ├── app.py              # FastAPI application, auth middleware, REST endpoints, and SPA serving
│   ├── auth.py             # Argon2id password hashing, session cookies, and RBAC authorization
│   ├── diagnostics.py      # Diagnostic interpretation engine, candidate matching, and UB exclusions
│   ├── executor.py         # Subprocess compilation, Job Object execution harness, and dynamic UB probe
│   ├── manage_users.py     # Administrative CLI tool to provision researcher accounts safely
│   ├── problems.py         # Pilot problems (PILOT-001..PILOT-005) definitions, test cases, and starter code
│   ├── recommendations.py  # Pedagogical follow-up rules, remediation curriculum, and cognitive firewall
│   ├── research.py         # Researcher telemetry aggregations, exploration, traces, and epistemic metrics
│   ├── store.py            # SQLite database initialization, WAL configuration, and verbatim persistence
│   ├── winjob.py           # Windows Job Object sandbox (limits, low integrity tokens, clean teardown)
│   └── static/
│       └── index.html      # Responsive Single-Page Application (Student Workspace + Researcher Portal)
├── tests/
│   ├── run_regression.py   # Regression suite validating infrastructure invariants and empirical fingerprints
│   ├── synthetic.py        # Authoritative reference error implementations, baseline rows, and UB fixtures
│   ├── test_auth.py        # Authentication, session cookies, CSRF, and RBAC test suite
│   ├── test_workflow.py    # Sandbox execution, follow-up recommendations, attempt lineage, cognitive firewall
│   ├── test_researcher.py  # Researcher overview, explorer, traces, and epistemic evaluation guardrail tests
│   ├── test_e2e_journey.py # Full student-to-researcher journey integration suite
│   ├── test_hardening.py   # Adversarial sandbox probes (process limits, memory bombs, recursion, concurrency)
│   └── test_browser_acceptance.py # Real Google Chrome acceptance suite (Playwright)
├── docs/                   # Original research specifications and catalog documentation
├── ARCHITECTURE.md         # Comprehensive system design and architectural specification
├── FINDINGS.md             # Empirical toolchain validation findings, corrections, and baseline analyses
├── HANDOFF_SUMMARY.md      # Engineering handoff notes and decision rationale
├── IMPLEMENTATION_PLAN.md  # Multi-phase engineering roadmap and validation milestones
├── QA_REPORT.md            # Zero-mock quality assurance report and empirical validation matrix
├── check_setup.py          # Machine environment readiness verifier
├── 1-SETUP.bat             # Windows one-click environment validation script
├── 2-START.bat             # Windows one-click local server launch script
├── INSTALL-COMPILER.bat    # MinGW-w64 compiler installation helper
├── .env.example            # Environment variable configuration template
├── requirements.txt        # Python package dependencies
└── .gitignore              # Git ignore rules for virtualenvs, caches, executables, and local databases
```

---

## 2. Prerequisites & Toolchain of Record

### Operating System Requirements
- **Windows 10 / 11 (64-bit)**: Required. The execution engine enforces sandboxing via Windows Job Objects (`winjob.py`) and Low Mandatory Integrity Levels (`icacls`), which require native Win32 APIs.

### Toolchain of Record
- **Python:** Python 3.10 or higher.
- **Compiler:** **MinGW-w64 GCC 16.1.0** (`x86_64-ucrt-posix-seh`), `-std=c++17 -O1`, installed at a **space-free path** (e.g. `C:\mingw64` or `C:\tools\winlibs-x86_64-posix-seh-gcc-16.1.0-mingw-w64ucrt-14.0.0-r4\mingw64\bin`).
  *Warning:* GCC's driver splits its internal `ld` invocation if installed in a path containing spaces. Always install to a path without spaces.

---

## 3. Quick-Start Guide

### Step 1: Install Python Dependencies
```powershell
pip install -r requirements.txt
```

### Step 2: Configure Environment Variables
Copy `.env.example` to `.env` or set environment variables in your active shell:
```powershell
# Set compiler toolchain for active shell:
$tool = "C:\tools\winlibs-x86_64-posix-seh-gcc-16.1.0-mingw-w64ucrt-14.0.0-r4\mingw64\bin"
$env:SI_GXX = Join-Path $tool "g++.exe"
$env:PATH = "$tool;$env:PATH"
```

### Step 3: Initialize Database
The SQLite database (`backend/evidence.db`) automatically initializes tables, schema indexes, and WAL journal mode on first startup. You can also explicitly verify database initialization via:
```powershell
python -c "import sys; sys.path.insert(0, 'backend'); import store; store.init(); print('Database initialized successfully.')"
```

### Step 4: Provision the Initial Researcher Account
Student accounts can register directly through the web UI (`/`). By design, new registrations are strictly assigned the `student` role, and client role escalation is blocked on the server.

To safely provision an authorized researcher account, use the administrative CLI:
```powershell
python backend/manage_users.py create-researcher --username prof_oak --email oak@kanto.edu --password "ResearcherPassword123!"
```
*(You can also run `python backend/manage_users.py create-researcher` without flags to enter credentials securely via hidden terminal prompts).*

### Step 5: Start the Server
Start the FastAPI backend and frontend service:
```powershell
python -m uvicorn app:app --port 8088 --app-dir backend
```
Open your browser to <http://127.0.0.1:8088>.

---

## 4. Running Tests & Empirical Verification

Run the automated test harnesses from the repository root:

```powershell
# 1. End-to-End Integration Suite (Student journey, RBAC, attempt lineage)
python tests/test_e2e_journey.py

# 2. Authentication & Authorization Suite (Argon2id, session cookies, CSRF)
python tests/test_auth.py

# 3. Workflow & Sandbox Suite (Job Objects, cognitive firewall, follow-up practice)
python tests/test_workflow.py

# 4. Researcher Workspace Suite (Telemetry, exploration, decision traces, epistemic bounds)
python tests/test_researcher.py

# 5. Security Hardening Probes (Process limits, low integrity, recursion, memory caps)
python tests/test_hardening.py

# 6. Research Instrument Regression Suite (Invariants, evidence schema, baseline reproduction)
python tests/run_regression.py

# 7. Real Browser Acceptance Suite (Headless Google Chrome via Playwright)
# Note: Requires 'pip install playwright' and 'playwright install chrome'
python tests/test_browser_acceptance.py
```

---

## 5. Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `SI_GXX` | Auto-detect | Path to `g++.exe` binary. Falls back to `C:\mingw64\bin\g++.exe` or `PATH`. |
| `SI_CXX_STD` | `c++17` | C++ standard version passed to compiler (`-std=c++17`). |
| `SI_OPT` | `-O1` | Compiler optimization level. Pinned to preserve diagnostic reproducibility. |
| `SI_TIMEOUT_S` | `3.0` | Maximum wall-clock execution time (seconds) per test case before terminating process. |
| `SI_MEMORY_MB` | `256` | Maximum commit memory limit (MB) enforced via Windows Job Object. |
| `SI_COMPILE_TIMEOUT_S` | `20` | Maximum compilation time (seconds) before aborting compiler subprocess. |
| `SI_MAX_CONCURRENT` | `4` | Concurrency throttle for parallel compiler and runner executions. |
| `SI_DB` | `backend/evidence.db` | Path to SQLite database file. |
| `SI_UB_PROBE` | `1` | Enable/disable secondary `-D_GLIBCXX_ASSERTIONS` runtime UB probe build. |
| `SI_COOKIE_SECURE` | `0` | Set to `1` when deployed behind HTTPS to enforce `Secure` session cookies. |

---

## 6. Security & Sandbox Isolation Boundaries

### Verified Protections
- **Process Isolation:** Windows Job Object enforces `JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 1`. Attempts to call `system()`, `fork()`, or spawn subprocesses fail immediately with `ERROR_ACCESS_DENIED`.
- **Filesystem Write Protection:** Spawned processes run with a **Low Mandatory Integrity SID** (`S-1-16-4096`). Writes to Medium- or High-integrity files outside the designated temporary sandbox are denied by the Windows kernel.
- **Resource Containment:** Strict 256 MB memory cap and 3.0-second timeout contain infinite loops, memory bombs, and stack overflows (`0xC00000FD`).
- **Temporary File Hygiene:** Submissions execute in isolated ephemeral `si_sub_*` temporary directories, unlinked upon completion.

### Known Isolation Limitations & Public Deployment Warning
> [!CAUTION]
> **DO NOT DEPLOY THIS SERVICE DIRECTLY ON THE PUBLIC INTERNET FOR UNTRUSTED CODE EXECUTION.**
> While Windows Job Objects and Low Integrity SIDs effectively prevent child process creation, memory exhaustion, and filesystem writes, Windows Integrity Levels do **not** gate file *reads*. File read access follows standard Windows Discretionary Access Control Lists (DACLs). Student code running under the local host token can read world-readable files on the machine.
> 
> **Public Deployment Requirement:** For multi-tenant internet deployment, the execution engine must run inside dedicated containerized environments (Docker with Linux seccomp/AppArmor profiles), Hyper-V isolated Windows Containers, or ephemeral Firecracker microVMs.

---

## 7. Research Instrument Fixtures & Discrepancies

### Invariants Preserved
- One compilation per submission, **one process per test case**.
- Test results are classified as `P` (Passed), `F` (Ran but wrong output), or `R` (Crash, timeout, exception). Compile errors are isolated as a separate status (`COMPILE_ERROR`) and never mapped to `F`.
- Raw execution evidence (stdout, stderr, exit codes, peak memory, runtime) is recorded verbatim in the store and never discarded.
- **Cognitive Firewall:** Diagnostic hypotheses and internal error labels (`E1`, `E2`, etc.) are accessible exclusively to researchers and never surfaced to students.

### Documented Discrepancies (UB-Sensitive Rows)
- **`P3 / E2_no_underflow_check`:** Document claims `PPPFPPPP`; execution observes `PPPRPPPP` on T4 because calling `.top()` on an empty stack invokes undefined behavior. Statically excluded via `UB_DEPENDENT_CELLS`.
- **`P5 / E2_loop_condition` & `P5 / E4_upper_mid`:** T4 out-of-bounds vector access invokes undefined behavior, manifesting as crash (`R`) or wrong answer (`F`) depending on heap alignment. Statically excluded from diagnostic distance calculations.
- **`P5 / linear_scan` Construct Validity:** A linear search solution passes 100% of binary search test cases (`PPPPPPPP`). Execution outcome alone cannot prove $O(\log n)$ algorithmic complexity without step-bound or instruction-count instrumentation.
