"""Researcher telemetry, diagnostic decision tracing, and empirical evaluation engine.

Provides inspection data for researchers to evaluate the CodeAdapt diagnostic instrument.
Enforces research integrity:
- Separates observed execution facts from inferred diagnostic attributions.
- Strictly abstains from fabricating metrics when ground truth is missing.
- Discloses all known toolchain divergences and undefined behavior limits.
- Never conflates iterative debugging accuracy with learning improvement or mastery.
"""

from typing import Dict, Any, List, Optional
import json

import store
import problems
import diagnostics
import executor


def get_research_overview() -> Dict[str, Any]:
    """Return actual aggregate telemetry across stored submissions and problem coverage."""
    all_subs = store.list_submissions(limit=2000)
    total_count = len(all_subs)

    compile_ok = sum(1 for s in all_subs if s.get("compile_status") == "OK")
    compile_err = sum(1 for s in all_subs if s.get("compile_status") != "OK")

    # Group by problem
    problem_counts = {}
    student_users = set()
    for s in all_subs:
        pid = s.get("problem_id")
        problem_counts[pid] = problem_counts.get(pid, 0) + 1
        if s.get("user_id"):
            student_users.add(s["user_id"])

    # Problem coverage
    problem_coverage = []
    unrepresented = []
    for pid, pdata in problems.PROBLEMS.items():
        cnt = problem_counts.get(pid, 0)
        has_data = cnt > 0
        if not has_data:
            unrepresented.append(pid)
        problem_coverage.append({
            "problem_id": pid,
            "title": pdata["title"],
            "concept": pdata["concept"],
            "total_submissions": cnt,
            "has_data": has_data
        })

    # Diagnostic verdicts across compiled submissions (sample up to 200 for deep trace)
    verdict_counts = {
        "task_correct": 0,
        "single_match": 0,
        "ambiguous": 0,
        "unmodelled": 0,
        "no_execution_evidence": compile_err
    }

    # Sample compiled submissions to assess verdict distribution
    sampled_compiled = [s for s in all_subs if s.get("compile_status") == "OK"][:200]
    for s in sampled_compiled:
        try:
            rec = store.load(s["submission_id"])
            if rec:
                diag = diagnostics.interpret(rec)
                v = diag.get("verdict", "unmodelled")
                if v in verdict_counts:
                    verdict_counts[v] += 1
                else:
                    verdict_counts["unmodelled"] += 1
        except Exception:
            pass

    total_evaluated = sum(verdict_counts.values())
    abstentions = (
        verdict_counts["ambiguous"] +
        verdict_counts["unmodelled"] +
        verdict_counts["no_execution_evidence"]
    )
    abstention_rate = round((abstentions / total_evaluated * 100), 1) if total_evaluated > 0 else 0.0

    return {
        "total_submissions": total_count,
        "compile_ok_count": compile_ok,
        "compile_error_count": compile_err,
        "unique_students_count": len(student_users),
        "verdict_distribution": verdict_counts,
        "total_evaluated_sample": total_evaluated,
        "abstentions_count": abstentions,
        "abstention_rate_pct": abstention_rate,
        "problem_coverage": problem_coverage,
        "unrepresented_problems": unrepresented,
        "missing_data_indicators": {
            "has_unrepresented_problems": len(unrepresented) > 0,
            "zero_submissions": total_count == 0,
            "insufficient_sample": total_count < 10
        },
        "toolchain": {
            "compiler": executor.GXX,
            "version": executor.compiler_version(),
            "optimization": executor.OPT_LEVEL,
            "cxx_standard": executor.CXX_STD,
            "wall_timeout_s": executor.WALL_TIMEOUT_S,
            "memory_cap_bytes": executor.MEMORY_BYTES,
            "isolation": "Windows Job Object + Low Integrity Level"
        },
        "epistemic_notice": (
            "Telemetry reflects empirical executions in the local sandbox store. "
            "Passes indicate test suite satisfaction, not verified concept mastery."
        )
    }


def get_submission_detail(submission_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve complete verbatim execution record and researcher diagnostic breakdown."""
    rec = store.load(submission_id)
    if not rec:
        return None

    diag = diagnostics.interpret(rec)
    meta = store.get_submission_meta(submission_id) or {}
    chain = store.get_submission_chain(submission_id)

    tests = rec.get("tests", [])
    compile_info = rec.get("compile") or {}

    # Execution failure classification
    has_compile_error = rec.get("compile_status") != "OK"
    crashes = [t for t in tests if t.get("execution_status") == "CRASHED"]
    timeouts = [t for t in tests if t.get("execution_status") == "TIMEOUT"]
    wrong_answers = [t for t in tests if t.get("status") == "F"]
    passed = [t for t in tests if t.get("status") == "P"]
    ub_violations = [t for t in tests if t.get("ub_check") == "violation"]

    prob = problems.get(rec.get("problem_id", ""))

    return {
        "submission_id": submission_id,
        "user_id": meta.get("user_id"),
        "created_at": meta.get("created_at"),
        "problem_id": rec.get("problem_id"),
        "problem_title": prob.get("title") if prob else "Unknown",
        "concept": rec.get("concept"),
        "compile_status": rec.get("compile_status"),
        "fingerprint": rec.get("fingerprint"),
        "limits": rec.get("limits"),
        "execution_summary": {
            "total_tests": len(tests),
            "passed_count": len(passed),
            "wrong_answer_count": len(wrong_answers),
            "crash_count": len(crashes),
            "timeout_count": len(timeouts),
            "ub_violation_count": len(ub_violations),
            "is_compile_error": has_compile_error,
            "has_runtime_failures": len(crashes) > 0,
            "has_timeouts": len(timeouts) > 0,
        },
        "compiler_diagnostics": {
            "command": compile_info.get("command"),
            "stderr_raw": compile_info.get("stderr"),
            "stderr_remapped": compile_info.get("stderr_student_lines"),
            "generated_source": compile_info.get("generated_source")
        },
        "test_results": tests,
        "diagnostic_interpretation": diag,
        "lineage": {
            "parent_submission_id": meta.get("parent_submission_id"),
            "is_followup": bool(meta.get("parent_submission_id")),
            "chain_total": len(chain),
            "chain_attempts": chain
        }
    }


def get_decision_trace(submission_id: str) -> Optional[Dict[str, Any]]:
    """Return full decision trace: observed fingerprint, reference rules, excluded UB cells, and abstention rationale."""
    rec = store.load(submission_id)
    if not rec:
        return None

    diag = diagnostics.interpret(rec)
    pid = rec.get("problem_id")
    short_id = diagnostics._alias(pid)

    # Detailed candidate score breakdown
    candidates_detail = []
    for c in diag.get("candidates", []):
        candidates_detail.append({
            "error_name": c["error"],
            "description": c.get("description"),
            "reference_fingerprint": c["reference"],
            "reference_ub_cells": c.get("reference_ub_cells", []),
            "mismatched_test_ids": c.get("mismatched_tests", []),
            "cells_compared": c.get("cells_compared"),
            "is_exact_match": c.get("exact", False)
        })

    # Collision check
    known_collisions = diagnostics.KNOWN_COLLISIONS.get(short_id, [])
    is_known_collision = False
    if diag.get("verdict") == "ambiguous":
        matched_set = set(diag.get("matched", []))
        for pair in known_collisions:
            if set(pair) <= matched_set:
                is_known_collision = True
                break

    return {
        "submission_id": submission_id,
        "problem_id": pid,
        "observed_fingerprint": diag.get("observed"),
        "test_ids": diag.get("test_ids", []),
        "compile_status": rec.get("compile_status"),
        "verdict": diag.get("verdict"),
        "verdict_summary": diag.get("summary"),
        "matched_errors": diag.get("matched", []),
        "candidates_evaluated": candidates_detail,
        "abstention_analysis": {
            "is_abstention": diag.get("verdict") in ("ambiguous", "unmodelled", "no_execution_evidence"),
            "is_known_collision": is_known_collision,
            "abstention_reason": (
                "Ambiguous collision between modeled error rows" if diag.get("verdict") == "ambiguous" else
                ("Unmodeled implementation failure" if diag.get("verdict") == "unmodelled" else
                 ("No executable binary produced" if diag.get("verdict") == "no_execution_evidence" else None))
            )
        },
        "undefined_behavior_exclusions": {
            "dynamic_ub_cells": diag.get("dynamic_ub_cells", []),
            "reference_ub_cells": diag.get("reference_ub_cells", {}),
            "excluded_from_matching": diag.get("excluded_cells", []),
            "rationale": (
                "Cells where undefined behavior was invoked track incidental memory layout "
                "rather than modeled conceptual error patterns. Matching on them would introduce "
                "non-deterministic noise into diagnostic attribution."
            )
        },
        "observed_outputs": diag.get("observed_outputs", [])
    }


def get_research_evaluation() -> Dict[str, Any]:
    """Provide research evaluation metrics distinguishing synthetic benchmarks from real student data.
    
    Refuses to fabricate diagnostic accuracy on student data where ground truth is missing.
    """
    # 1. Synthetic Benchmark Evaluation (known ground truth by construction)
    synthetic_eval = {
        "dataset_name": "Synthetic Instrument Pilot Fixtures",
        "population": "Synthetic pilot implementations derived from frozen design specifications",
        "sample_size": 18,
        "ground_truth_status": "Validated by Construction",
        "evaluation_metrics": {
            "modeled_error_attributions_tested": 12,
            "exact_matches_on_modeled_rows": 11,
            "construct_validity_bypasses": [
                {
                    "problem_id": "PILOT-005",
                    "fixture": "linear_scan",
                    "observed_fingerprint": "PPPPPPPP",
                    "verdict": "task_correct",
                    "limitation": "A correct linear scan passes 100% of binary search test cases; cannot verify O(log n) complexity by execution alone."
                }
            ],
            "known_ambiguities": [
                {
                    "problem_id": "PILOT-002",
                    "fixtures": ["B_wrong_return", "C_off_by_one"],
                    "observed_fingerprint": "FPFFFFFF",
                    "verdict": "ambiguous",
                    "limitation": "Both bugs produce identical P/F/R rows under the 8-test suite."
                }
            ]
        }
    }

    # 2. Real Student Cohort Data
    student_subs = store.list_submissions(limit=2000)
    actual_students = set(s["user_id"] for s in student_subs if s.get("user_id"))

    student_eval = {
        "dataset_name": "Classroom Deployment Submissions",
        "population": "Registered student learners",
        "sample_size_submissions": len(student_subs),
        "sample_size_learners": len(actual_students),
        "ground_truth_status": "UNAVAILABLE / UNLABELED",
        "has_ground_truth": False,
        "evaluation_metrics": None,
        "methodological_notice": (
            "No external ground-truth misconception labels (e.g., independent expert code reviews "
            "or think-aloud interview transcripts) currently exist for student submissions in this deployment. "
            "Computing sensitivity, specificity, or PPV on unannotated student submissions is statistically invalid. "
            "The platform strictly abstains from fabricating unverified accuracy figures."
        ),
        "learning_gain_notice": (
            "Changes in test accuracy or pass rates across repeated attempts reflect iterative code debugging, "
            "NOT validated Programming Knowledge Tracing (PKT) or mastery improvement. Controlled pre/post "
            "experimental protocols are required before claiming learning gains."
        )
    }

    return {
        "synthetic_benchmark": synthetic_eval,
        "student_cohort": student_eval,
        "summary": {
            "instrument_status": "Experimental Pilot",
            "validated_findings_available": True,
            "student_accuracy_claimable": False
        }
    }


def get_instrument_limitations() -> Dict[str, Any]:
    """Document all known research divergences, UB declarations, and construct validity limits."""
    return {
        "known_divergences": [
            {
                "problem_id": "PILOT-003",
                "problem_title": "Valid Parentheses (Stacks)",
                "error_name": "E2_no_underflow_check",
                "claimed_doc_fingerprint": "PPPFPPPP",
                "observed_baseline_fingerprint": "PPPRPPPP",
                "divergent_cells": ["T4: doc=F, observed=R"],
                "mechanism": (
                    "Attempting to pop from an empty std::stack invokes undefined container behavior. "
                    "On MinGW-w64 GCC 16.1 UCRT, libstdc++ aborts with STACK_BUFFER_OVERRUN (0xC0000409), "
                    "yielding runtime failure (R) rather than output failure (F)."
                ),
                "ub_declared_cells": ["T4"],
                "action": "Preserved as documented discrepancy; T4 excluded from diagnostic matching."
            },
            {
                "problem_id": "PILOT-005",
                "problem_title": "Lower Bound (Binary Search)",
                "error_name": "E2_loop_condition",
                "claimed_doc_fingerprint": "RRRRRRRR",
                "observed_baseline_fingerprint": "RRRFRRRR",
                "divergent_cells": ["T4: doc=R, observed=F"],
                "mechanism": (
                    "Bounds condition `lo <= hi` triggers out-of-bounds array reads. "
                    "On T4 and T7, reading past the vector boundary hits undefined behavior."
                ),
                "ub_declared_cells": ["T4", "T7"],
                "action": "Preserved as documented discrepancy; T4 and T7 excluded from diagnostic matching."
            },
            {
                "problem_id": "PILOT-005",
                "problem_title": "Lower Bound (Binary Search)",
                "error_name": "E4_upper_mid",
                "claimed_doc_fingerprint": "PPRRRRPR",
                "observed_baseline_fingerprint": "PPRFRRPR",
                "divergent_cells": ["T4: doc=R, observed=F"],
                "mechanism": (
                    "Upper-mid computation `(lo + hi + 1) / 2` invokes undefined bounds access. "
                    "Outcomes vary across memory layout and compiler optimization flags."
                ),
                "ub_declared_cells": ["T4", "T8"],
                "action": "Preserved as documented discrepancy; T4 and T8 excluded from diagnostic matching."
            }
        ],
        "construct_validity_limits": [
            {
                "problem_id": "PILOT-005",
                "issue": "Binary Search vs Linear Scan Equivalence",
                "detail": (
                    "A naive linear scan satisfies all 8 test cases and produces 'PPPPPPPP'. "
                    "Black-box output testing cannot enforce O(log n) algorithmic complexity."
                )
            },
            {
                "problem_id": "PILOT-002",
                "issue": "In-place Pointer Reversal vs Value Copying",
                "detail": (
                    "A solution that copies node values to a buffer and overwrites values "
                    "produces correct sequence outputs without performing pointer manipulation."
                )
            },
            {
                "problem_id": "PILOT-001",
                "issue": "In-place Array Modification (O(1) Auxiliary Space)",
                "detail": (
                    "Constructing a secondary vector and copying non-zero elements passes all output "
                    "checks; auxiliary space allocation cannot be monitored via output files."
                )
            }
        ],
        "undefined_behavior_probes": {
            "probe_mechanism": "-D_GLIBCXX_ASSERTIONS compile flag",
            "epistemic_limitation": (
                "A clean or inconclusive probe does NOT prove the absence of undefined behavior. "
                "C++ undefined behavior encompasses memory alignment, strict aliasing, and pointer arithmetic "
                "that standard library runtime assertions do not intercept."
            ),
            "declared_vs_measured": (
                "Declared cells are identified through static formal code inspection. "
                "Measured cells are runtime assertions caught by the probe during harness execution."
            )
        },
        "windows_sandbox_limitations": {
            "process_isolation": "Windows Job Object enforces ActiveProcessLimit=1, 3.0s wall timeout, and 256MB memory cap.",
            "write_protection": "Low Mandatory Integrity Label blocks write operations outside the designated work directory.",
            "read_boundary": "Low integrity gates writes, not reads. Read access follows Windows Discretionary Access Control Lists (DACLs)."
        }
    }
