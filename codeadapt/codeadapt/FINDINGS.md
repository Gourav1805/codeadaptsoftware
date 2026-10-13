# Instrument Validation Findings

Every claim below was produced by executing code on this machine, not by
reading the documents. Reproduce with:

```
python tests/run_regression.py
python tests/test_hardening.py
```

**Toolchain of record:** MinGW-w64 **GCC 16.1.0** (`x86_64-ucrt-posix-seh`),
`-std=c++17 -O1`, 64-bit, installed at `C:\mingw64`. Windows 11 build 26200,
Job Object isolation, 3 s wall timeout, 256 MB memory cap.

> GCC's driver splits its internal `ld` invocation on a space in its own
> install path, so the winget-installed toolchain (under `C:\Users\Jasroop
> Singh\...`) compiled but could not link. It is relocated to `C:\mingw64`.
> The original `C:\MinGW` GCC 6.3.0 install is untouched.

---

## A. Infrastructure status — all green

| Requirement | Status |
|---|---|
| Correct submission → all P, all five problems | verified |
| Wrong answer → F, never R | verified |
| Crash → R (`ACCESS_VIOLATION 0xC0000005`) | verified, all 5 |
| Infinite loop → R via TIMEOUT | verified, all 5 |
| Memory bomb → R, peak held under the 256 MB cap | verified |
| Compile error → own status, zero test rows, never an F | verified |
| Compiler diagnostics captured and remapped to student line numbers | verified |
| Student code never executes in the backend process | by construction |
| One process + one Job Object per test | by construction |
| Global state cannot contaminate later tests | verified with a leaky submission |
| Re-running a submission is deterministic | verified |
| Raw record round-trips through the store byte-identical | verified |
| Compile failures retained in the store with a NULL fingerprint | verified |
| 16 submissions across 8 threads == serial results | verified |
| Zero `si_sub_*` temp directories left behind | verified |
| P5 linear scan → all P (construct-validity bypass reproduced) | verified |

Every fingerprint row is re-derived by execution and enforced as a baseline in
`tests/synthetic.py :: DERIVED_FINGERPRINTS`. Any drift fails the suite.

---

## B. Resolved research-semantic defects

### B1. P4 / T8 — corrected to `[0,1,2,3]` ✅

The frozen document expected `[0,2,1,3]`. No boundary convention produces it,
and the document's own §7 trace was arithmetically impossible (it had a
burst-3 process finishing inside a 2-unit slice). T2 and T8 also required
*opposite* conventions.

Corrected to the value the specified rules actually produce — the same
convention T2 already required. **The correct reference solution now scores
`PPPPPPPP`**, where before it failed T8. The arrival-at-slice-boundary rule is
stated explicitly in `problems.py` so the two tests no longer contradict.

### B2. P5 / T3 — corrected to `target=0` ✅

The §6 table said `target=1`; the row's own stated purpose is *"target below
all elements"*, which `target=1` does not test — it is an exact match at index
0, already covered by T1 and T8. Corrected to `target=0`, restoring the
intended diagnostic role.

**E3's row now reproduces the document exactly** (`FPPPFFPF`). P5 went from
2-of-4 rows matching to 3-of-4.

### B3. Toolchain upgraded, matrices re-derived ✅

g++ 6.3.0 (2016, 32-bit, partial C++14) → GCC 16.1.0 (64-bit, full C++17).
Students writing ordinary modern C++ no longer risk compile errors that are
toolchain artifacts rather than evidence.

All 23 fingerprint rows were re-derived on the new toolchain. **Every non-UB
row is unchanged across both compilers** — P2 all five rows, P3 four of five,
P5 E1/E3, P1 and P4 all rows. The instrument is stable where it should be.

---

## C. Remaining divergences — all confined to UB cells

Three cells still disagree with the frozen documents. **All three sit inside
undefined behaviour**, and are flagged in
`tests/synthetic.py :: UB_DEPENDENT_CELLS` as tracked-but-not-diagnostic.

| Row | Doc | Observed | Cell |
|---|---|---|---|
| P3 / E2 missing underflow check | `PPPFPPPP` | `PPPRPPPP` | T4: F→R |
| P5 / E2 loop condition | `RRRRRRRR` | `RRRFRRRR` | T4: R→F |
| P5 / E4 upper-mid | `PPRRRRPR` | `PPRFRRPR` | T4: R→F |

**Why these are not simply "doc errors to fix".** The same source logic for
P3/E2 on T4 produced three different outcomes across three builds:

| Build | T4 |
|---|---|
| Standalone, GCC 6.3.0 | **R** — segfault, 5/5 runs |
| Harness, GCC 6.3.0 | **P** — correct answer, all opt levels |
| Harness, GCC 16.1.0 | **R** — segfault |

Each build is internally deterministic; they disagree with each other. The
outcome tracks incidental heap/stack layout, which the surrounding translation
unit and compiler decide. Writing any single value into the matrix would
record a fact about one binary, not about the mistake being modelled.

The P5 cells are more stable — `arr[n]` returned a wrong answer rather than
trapping on *both* the 32-bit GCC 6.3 and 64-bit GCC 16 builds — but they rest
on the same foundation and are flagged the same way.

**Consequence for interpretation:** E2 is described in the P5 document as
producing a uniform all-R signature. It does not; it produces one F. Any
downstream rule keyed on "E2 ⇒ all-R" is keyed on something that does not
occur.

**Recommendation (not yet applied — it changes what the errors mean):**
replace E2/E4 with variants that fail deterministically without out-of-bounds
reads, so every cell in the matrix is a property of the error rather than of
the build.

### UB is now measured, not inferred

Every submission is compiled a second time with `-D_GLIBCXX_ASSERTIONS` and
each test re-run against that build. libstdc++ then turns exactly these silent
violations into a labelled abort, so `ub_check` on every test row is one of
`clean`, `violation` (with the precondition named), `timeout` or `crash`.

The probe runs **after** classification and cannot alter it. Undefined
behaviour and P/F/R are separate questions, and conflating them would be the
same mistake as collapsing R into F.

It independently reproduced the hand-written flags exactly — same three rows,
same six cells, no false positives on the correct, linear-scan, E1, E3 or P2
submissions — and named the violated preconditions:

| Row | Cells | Precondition |
|---|---|---|
| P3 / E2 | T4 | `!this->empty()` — `top()` on an empty stack |
| P5 / E2 | T4, T7 | `__n < this->size()` — vector index out of range |
| P5 / E4 | T4, T8 | `__n < this->size()` |

The regression now fails if the declared flags and the measured result ever
disagree, so `UB_DEPENDENT_CELLS` is a checked claim rather than an assertion.

Cost: one extra compile plus one extra run per test (~3.5 s on a clean
submission). On a non-terminating submission the probe uses a 1 s budget
instead of the full 3 s, since an assertion aborts immediately or not at all.
Set `SI_UB_PROBE=0` to skip it.

### The instrument version must be recorded

While verifying the probe, a backend left running with stale code produced
`RRRRRRRR` for a submission that a current build scored `RRRFRRRR` — a
different P/F/R row for byte-identical student code. On a fresh build the row
was stable 6/6, so this is not run-to-run noise; it is the same build-to-build
sensitivity as §C, reached by a different route.

Nothing in the record would have revealed it. Every submission now carries
`instrument_hash` — a digest of the compiler build, the language and
optimisation flags, the limits, and the generated harness for that problem,
with the student's code held constant. `GET /problems/{id}/fingerprints`
returns it per row.

**Rows carrying different `instrument_hash` values were measured by different
instruments and must not be pooled without checking.** The dev launch config
now uses `--reload` so an edited backend is never served stale.

### A related catch worth recording

GCC 16 **deleted** the null-pointer store in the P1 crash probe
(`volatile int* p = nullptr; *p = 1;` in a `void` function) — `volatile` there
qualifies the pointee, not the pointer, so the compiler was free to remove it.
The probe silently stopped crashing and the regression caught it as
`['F','P']` instead of `R`. Fixed to `int* volatile p`. Same lesson: a
modern optimiser will exploit UB that an older one left alone.

---

## D. Reproducibility gaps — still open

**P1 and P4 synthetic errors are prose-only.** P2 supplies real C++ and P5
exact pseudocode, so their fingerprints are independently checkable — and both
reproduce. P1's Errors A–D and P4's E1–E4 are one-line English descriptions,
and natural faithful implementations do not reproduce the claimed failed-test
sets:

| Error | Doc claims fails | Natural implementation fails |
|---|---|---|
| P1 Error A (swap from end) | T1, T8 | T1, T6, T8, T9 |
| P1 Error C (assumes len ≥ 2) | T3, T4, T5 | none — T4/T5 are already correct unchanged |
| P1 Error D (non-positive as zero-like) | T9 | T9 |

This is not a defect in the tests. A prose sentence does not determine a
fingerprint. Supplying code or exact pseudocode, as P2 and P5 already do,
would close it.

---

## E. Documentation items from §32 of the brief

| Item | State |
|---|---|
| P1 unenforceable in-place constraint | Recorded as unenforceable in `problems.py`, exposed via `GET /problems`. The frozen `.docx` still asserts it as a requirement while the consolidated statements doc softened it — those two documents still disagree. |
| P2 copy-and-rebuild limitation | Documented; B/C fingerprint collision documented alongside. |
| P3 diagnostic behaviour verified | 4 of 5 rows reproduce; E2/T4 is §C. |
| P4 arrival-at-slice-boundary rule | Stated explicitly and implemented; T8 corrected to match. |
| P4 confounding risk = Medium | Recorded in `problems.py`. |
| P5 pass ≠ Binary Search knowledge | Recorded; linear scan verified to pass all 8. |

---

## F. Isolation boundary — probed, not assumed

Each row came from a submission that actually attempted the action.

| Attack | Result | Mechanism |
|---|---|---|
| Spawn a child process | **BLOCKED** | Job Object `ActiveProcessLimit=1` |
| Write a file outside the work directory | **BLOCKED** | Low-integrity mandatory label |
| Unbounded recursion | **CONTAINED** to R | `STACK_OVERFLOW 0xC00000FD` |
| Memory exhaustion | **CONTAINED** to R | `ProcessMemoryLimit` |
| Infinite loop | **CONTAINED** to R | wall-clock timeout, job terminated |
| Read a file outside the work directory | **ALLOWED** | expected; see below |

### The filesystem gap is closed

Job Objects bound CPU, memory, process count and lifetime, but not the
filesystem. Student processes now additionally run at **Low integrity**, and a
Low process cannot write to any object labelled higher — which is everything
the backend user owns. The per-submission work directory is explicitly
labelled Low (`icacls /setintegritylevel (OI)(CI)Low`) so the harness can
still write its result file there.

Implementation detail that matters: `CreateProcessAsUser` with a lowered token
needs `SE_ASSIGNPRIMARYTOKEN`, which a standard user does not hold. Instead the
child is created **suspended**, its own token is lowered in place, and only
then is it resumed. Lowering a token is always permitted, so this needs no
elevation, no new account, and no Docker. It is applied before the first
instruction executes — the same race-free guarantee as the job assignment.

If the lowering ever fails, execution falls back to normal integrity rather
than refusing to run, and `integrity` on **every test row** records which
actually happened. It is never assumed.

### What remains open, and why it is acceptable

Reads outside the work directory still succeed. This is inherent to the
mechanism: Windows integrity levels gate **writes**, not reads — reads are
governed by DACLs, and the process still runs as the backend user. Closing it
needs a separate low-privilege account or an AppContainer profile.

For the pilot this does not threaten evidence integrity: tests are
deterministic, inputs are constructed in-process, and expected outputs never
reach the student binary, so there is nothing on disk a submission could read
to change its own classification. It would matter for untrusted public
traffic.

## G. Concurrency

Unspecified in every project document. Measured:

- `MAX_CONCURRENT = 4` (semaphore-bounded), driven by 8 client threads.
- 16 submissions, mixed correct / wrong / crash / timeout: every fingerprint
  identical to the serial baseline.
- No temp-directory leakage.

Compilation dominates cost (GCC 16 is slower than 6.3 but produces far better
diagnostics). The architecture holds to roughly 10 concurrent submissions on
this 16-core machine; beyond that it needs a work queue rather than a
semaphore.


---

## H. Two defects the suites caught in their own infrastructure

Both were introduced by the UB probe and found by the checks rather than by
inspection, which is the point of running them after every change.

**1. A silently swallowed temp-directory leak.** Adding the probe added a
second binary and two more open files per test. `shutil.rmtree(...,
ignore_errors=True)` then lost a race against Windows still holding a handle on
a just-terminated process's files, and discarded the failure. Six directories
per hardening run were being left behind with no signal at all.

The leftovers each contained exactly one file — `probe.exe` or a
`*_stderr_N.txt` — and all deleted cleanly seconds later, so the locks are
transient. Cleanup is now bounded-retry then queued: a failure goes into a
pending set that `sweep()` drains at the start of the next submission and at
app startup. Every record carries `workdir_cleaned`, so a failure is recorded
rather than hidden. Cleanup is eventual, never permanent, and never silent.

**2. A stale backend served different results.** See §C — this is what
prompted `instrument_hash`.

The general lesson for this project: `ignore_errors=True` and any other
"failures are fine" default is dangerous in an instrument. Every degraded path
here now records what actually happened — `integrity`, `ub_check`,
`workdir_cleaned`, `instrument_hash` — so a silent change in measurement
conditions is detectable after the fact.

---

## I. Diagnostic layer, and a hard limit on what it can claim

`backend/diagnostics.py` implements the step the documents license and no
more: compare the full per-test P/F/R pattern against the validated reference
matrices and report *plausible error classes*. No knowledge tracing, no BKT,
no student model, no adaptivity.

Four rules are enforced in code rather than left to the caller:

1. **Full pattern, never counts.** Two submissions each failing three tests are
   not comparable; which three is the entire signal.
2. **UB cells are excluded.** Where the probe caught undefined behaviour on
   *this* submission, that cell is dropped from matching — matching on it would
   be matching on memory layout.
3. **Abstain rather than guess.** A pattern matching no modelled error is
   reported as `unmodelled`, never bent onto the nearest row.
4. **A pass is task correctness.** P5 returns "does NOT establish that Binary
   Search was used"; P2 the equivalent about pointer manipulation.

Verified behaviour: P2's B/C collision returns `ambiguous` with both names
rather than picking one; P5's correct and linear-scan submissions are reported
identically; a compile error yields `no_execution_evidence` and no candidates.

### The limit: identical rows, different mistakes

A submission that returns `n` whenever the target is found — a mistake not in
the modelled set, and conceptually unrelated to upper/lower-bound confusion —
produces P5's E3 row **exactly**:

| Test | Expected | E3 upper-bound | Novel return-n bug |
|---|---|---|---|
| T1 | 2 | F, returns **3** | F, returns **5** |
| T5 | 0 | F, returns 5 | F, returns 5 |
| T6 | 1 | F, returns **4** | F, returns **6** |

The P/F/R rows are byte-identical (`FPPPFFPF`); the returned values are not.
The matcher attributes it to E3, because P/F/R is what the documents specify
that it compares.

**So a "single match" is not a root cause, even when it is unique.** The
matcher says so in every such summary, and this exact case is asserted in
`run_regression.py` section 4 so it cannot be quietly forgotten.

The discriminating evidence is already captured. Every diagnostic result
carries `observed_outputs` (expected and actual per test) precisely so a reader
can separate these by hand.

**Not applied, because it is research-semantic:** letting the matcher compare
returned *values* as well as P/F/R would separate these two errors
automatically. That changes what evidence the instrument uses for attribution
and needs an explicit decision, not a quiet upgrade.

Researcher-facing only: `GET /submissions/{id}/diagnostics`. It is deliberately
absent from the student UI — naming a specific error class to a student primes
the reasoning the instrument is trying to observe, and P02's own guidance
cautions against telling a student they definitely have a specific error when
the fingerprint is ambiguous.

---

## J. Option A showcase validation (2026-10-12)

The October 14 showcase preserves the current research instrument. No
fingerprint baselines, expected outputs, problem definitions, test ordering,
synthetic submissions, UB declarations, matching rules, timeout behavior or
research claims are changed to make the regression pass.

### Reproducible toolchain selection

The verified compiler is:

```text
C:\tools\winlibs-x86_64-posix-seh-gcc-16.1.0-mingw-w64ucrt-14.0.0-r4\mingw64\bin\g++.exe
MinGW-W64 x86_64-ucrt-posix-seh, GCC 16.1.0
target: x86_64-w64-mingw32
```

`backend/executor.py` honors `SI_GXX` at process startup. A temporary
PowerShell override is sufficient for both the regression suite and an
application process started from that shell; prepending the compiler `bin`
directory also exposes GCC's auxiliary tools and DLLs. The override must be
restored afterward rather than persisted system-wide:

```powershell
$tool = "C:\tools\winlibs-x86_64-posix-seh-gcc-16.1.0-mingw-w64ucrt-14.0.0-r4\mingw64\bin"
$gxx = Join-Path $tool "g++.exe"
& $gxx --version
& $gxx -dumpmachine
$env:SI_GXX = $gxx
$env:PATH = "$tool;$env:PATH"
python tests\run_regression.py
python tests\test_hardening.py
```

### Known Option A discrepancies

The following observations are measured findings, not hypotheses:

- **P5/E2:** `while (lo <= hi)` combines possible non-termination with an
   out-of-bounds access. GCC 6.3.0 produced `RRRRRRRR`; GCC 16.1.0 UCRT
   produced `RRRFRRRR` in the documented comparison. T7 is statically
   declared UB-sensitive, but a timeout or generic crash is not the same as a
   dynamically observed assertion violation.
- **P5/E4:** the upper-midpoint calculation can access `arr[arr.size()]` and
   can fail to make progress. The observed GCC 16.1.0 UCRT row was
   `PPRFRRPR`; probe results for UB-sensitive cells can be inconclusive when
   the primary run does not terminate within the probe budget.
- **P3/E2:** T4 calls `st.top()` on an empty stack. The observed row is
   `PPPRPPPP`, while the historical documented row is `PPPFPPPP`; T4 is a
   known research-semantic divergence because the R/F outcome is UB-dependent.

Static UB declarations identify cells that may be unreliable for reference
matching. Dynamic `ub_check` values record what the assertion probe observed
for one submission and run. A clean probe does not prove that UB is absent;
`timeout` and `crash` are also inconclusive measurements. These fixtures are
retained for Option A, but UB-dependent outcomes must not be presented as
reliable diagnostic evidence.

Validation on this checkout is not fully green. `python tests\run_regression.py`
continues to report known UB-sensitive baseline/probe failures, while
`python tests\test_hardening.py` is the separate isolation check. The known
failures must remain visible and must not be suppressed or absorbed into the
reference data.

### Deployment boundary

The hardening probes showed that writes outside the work directory are blocked,
but reads outside it remain possible because Windows integrity levels gate
writes rather than reads. The current service is therefore **not approved for
arbitrary public submissions**. Use it only with the controlled local showcase
workload until a separate low-privilege account or AppContainer policy closes
the external-file-read limitation.