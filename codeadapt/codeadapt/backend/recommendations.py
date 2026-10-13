"""Pedagogical recommendation and decision explanation engine.

Translates raw execution records and diagnostic evidence into student-safe
practice recommendations and transparent explanations.

Enforces four core research principles:
1. Strict Cognitive Firewall: Internal researcher error labels (e.g., E3_upper_bound)
   are NEVER surfaced to students. Only plain-language descriptions are used.
2. Epistemic Honesty: Passes establish task correctness on tested inputs, NOT
   concept mastery. Fingerprint matches indicate consistency with a known pattern,
   NOT definitive proof of a cognitive misconception.
3. Explicit Abstention: Ambiguous collisions and unmodelled failures produce
   an explicit abstention statement, never a forced or guessed attribution.
4. Genuine Problem Selection: Recommendations choose only from real problems in the
   catalogue with transparent selection rationales, never synthetic or random assignments.
"""

from typing import Dict, Any, Optional, List
import problems
import diagnostics

CURRICULUM_ORDER = ["PILOT-001", "PILOT-002", "PILOT-003", "PILOT-004", "PILOT-005"]

CURRICULUM_NEXT = {
    "PILOT-001": "PILOT-002",  # Arrays -> Linked Lists
    "PILOT-002": "PILOT-003",  # Linked Lists -> Stacks
    "PILOT-003": "PILOT-004",  # Stacks -> Queues
    "PILOT-004": "PILOT-005",  # Queues -> Binary Search
    "PILOT-005": "PILOT-001",  # Binary Search -> Arrays (cycle)
}


def _canonical_pid(problem_id: str) -> str:
    try:
        return problems.get(problem_id)["problem_id"]
    except KeyError:
        return problem_id


def _alias_pid(problem_id: str) -> str:
    for short, full in problems.ALIASES.items():
        if full == _canonical_pid(problem_id):
            return short
    return problem_id


def generate_practice_response(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Produce a student-safe follow-up and decision explanation from an execution record.
    
    Guarantees that raw execution evidence is not mutated and researcher-only
    labels remain strictly isolated from student view.
    """
    evidence = diagnostics.interpret(rec)
    prob = problems.get(rec["problem_id"])
    pid_alias = _alias_pid(rec["problem_id"])
    tests = rec.get("tests", [])

    base = {
        "submission_id": rec["submission_id"],
        "problem_id": prob["problem_id"],
        "parent_submission_id": rec.get("parent_submission_id"),
    }

    # Identify any UB violations observed during execution
    ub_cells = [t["test_id"] for t in tests if t.get("ub_check") == "violation"]
    excluded_cells = evidence.get("excluded_cells", [])
    all_ub_cells = sorted(list(set(ub_cells + excluded_cells)))
    ub_warning = None
    if all_ub_cells:
        ub_warning = (
            f"Undefined behaviour was detected on test(s) {', '.join(all_ub_cells)}. "
            "Under C++ semantics, outcomes on these tests reflect memory layout and "
            "compiler-dependent artifacts rather than intended algorithm logic, "
            "and were excluded from diagnostic matching."
        )

    # --- 1. Task Correct (All tests passed) -----------------------------------
    if evidence["verdict"] == "task_correct":
        next_pid = CURRICULUM_NEXT.get(prob["problem_id"], "PILOT-001")
        target = problems.get(next_pid)
        return {
            **base,
            "state": "correct",
            "message": (
                "Your solution produced the expected results on the tested cases. "
                "This does not establish mastery."
            ),
            "explanation": {
                "what_happened": "All test cases completed successfully within time and memory caps.",
                "evidence_summary": f"All {len(tests)} test cases produced matching outputs.",
                "concept": prob["concept"],
                "why_selected": "Advancing to the next topic in the practice curriculum.",
                "uncertainty": (
                    "Passing these tests verifies task correctness on the specific tested inputs. "
                    "It does not establish mastery or prove that a specific optimal method was used."
                ),
                "failing_tests": [],
                "ub_warning": ub_warning,
            },
            "recommendation": {
                "action": "practice",
                "problem_id": target["problem_id"],
                "title": target["title"],
                "reason": "Continue with another existing problem.",
                "recommendation_type": "curriculum_progression",
                "relationship_to_evidence": (
                    f"All tests passed for {prob['title']} ({prob['concept']}). "
                    f"Advancing to {target['title']} ({target['concept']})."
                ),
            },
        }

    # --- 2. Compilation Failure (No Execution Evidence) ----------------------
    if evidence["verdict"] == "no_execution_evidence":
        compile_info = rec.get("compile") or {}
        feedback = (
            compile_info.get("stderr_student_lines")
            or compile_info.get("detail")
            or "No compiler feedback was recorded."
        )
        return {
            **base,
            "state": "no_execution_evidence",
            "message": "A diagnosis cannot be made because the code did not compile.",
            "compile_status": rec.get("compile_status"),
            "compile_feedback": feedback,
            "explanation": {
                "what_happened": "Compilation failed. The C++ compiler rejected the code.",
                "evidence_summary": "0 tests executed; no executable binary could be produced.",
                "concept": prob["concept"],
                "why_selected": "Syntax and type errors must be fixed before runtime behavior can be examined.",
                "uncertainty": "No execution evidence exists; impossible to evaluate concept understanding.",
                "failing_tests": [],
                "ub_warning": None,
            },
            "recommendation": {
                "action": "retry",
                "problem_id": prob["problem_id"],
                "title": prob["title"],
                "reason": "Fix the compilation issue and retry this problem.",
                "recommendation_type": "compilation_fix",
                "relationship_to_evidence": "Compilation failed; retry requires resolving compiler errors.",
            },
        }

    # Compute failing test list
    failing_tests = [t["test_id"] for t in tests if t.get("status") != "P"]

    # --- 2.1 Execution Failures Preventing Valid Diagnosis --------------------
    all_crashed = bool(tests) and all(t.get("execution_status") == "CRASHED" for t in tests)
    all_timeout = bool(tests) and all(t.get("execution_status") == "TIMEOUT" for t in tests)

    if all_crashed:
        crash_detail = [t.get("error") for t in tests if t.get("error")]
        first_err = crash_detail[0] if crash_detail else "Process terminated abnormally"
        return {
            **base,
            "state": "insufficient_evidence",
            "message": (
                "Insufficient evidence for a supported diagnosis. "
                "A runtime execution failure prevented valid diagnostic observation."
            ),
            "explanation": {
                "what_happened": f"Runtime crash occurred across all test cases ({first_err}).",
                "evidence_summary": f"All {len(tests)} tests terminated abnormally (status R).",
                "concept": prob["concept"],
                "why_selected": "General problem debugging is recommended.",
                "uncertainty": (
                    "Execution failures prevent observing the algorithm's functional outputs. "
                    "The platform abstains from making any conceptual knowledge claim."
                ),
                "failing_tests": failing_tests,
                "ub_warning": ub_warning,
            },
            "recommendation": {
                "action": "retry",
                "problem_id": prob["problem_id"],
                "title": prob["title"],
                "reason": "Fix memory access and pointer validity, then retry this problem.",
                "recommendation_type": "general_practice",
                "relationship_to_evidence": "Runtime crash prevents functional output evaluation.",
            },
        }

    if all_timeout:
        limit_s = rec.get("limits", {}).get("wall_timeout_s", 3.0)
        return {
            **base,
            "state": "insufficient_evidence",
            "message": (
                "Insufficient evidence for a supported diagnosis. "
                "Execution timed out across all test cases, preventing valid diagnostic observation."
            ),
            "explanation": {
                "what_happened": f"Execution timed out on all tests (exceeded {limit_s}s wall limit).",
                "evidence_summary": f"All {len(tests)} tests timed out (status R). Likely infinite loop or non-terminating recursion.",
                "concept": prob["concept"],
                "why_selected": "Termination loop debugging is recommended.",
                "uncertainty": (
                    "Non-terminating execution prevents observing return values or final outputs. "
                    "The platform abstains from making any conceptual diagnosis."
                ),
                "failing_tests": failing_tests,
                "ub_warning": ub_warning,
            },
            "recommendation": {
                "action": "retry",
                "problem_id": prob["problem_id"],
                "title": prob["title"],
                "reason": "Ensure all loops and recursions have proper termination conditions, then retry.",
                "recommendation_type": "general_practice",
                "relationship_to_evidence": "All tests timed out; termination logic must be resolved.",
            },
        }

    # --- 3. Single Supported Match -------------------------------------------
    if evidence["verdict"] == "single_match":
        matched_err = evidence["matched"][0] if evidence.get("matched") else None
        # Convert internal error identifier to student-safe plain language
        student_desc = diagnostics.DESCRIPTIONS.get(pid_alias, {}).get(
            matched_err, "a specific boundary or invariant condition"
        )
        return {
            **base,
            "state": "supported_diagnosis",
            "message": (
                "Your results are consistent with one supported pattern, "
                "but this is not proof of the underlying cause."
            ),
            "explanation": {
                "what_happened": (
                    f"Your solution compiled, but {len(failing_tests)} of {len(tests)} tests "
                    "produced unexpected outputs or runtime failures."
                ),
                "evidence_summary": f"Observed failure pattern on tests: {', '.join(failing_tests)}.",
                "concept": prob["concept"],
                "plausible_behavior": student_desc,
                "why_selected": (
                    f"Focal review regarding {student_desc} addresses the specific test discrepancies."
                ),
                "uncertainty": (
                    "Execution patterns can sometimes collide with unmodelled bugs. "
                    "This observation indicates empirical consistency, not a proven cognitive misconception."
                ),
                "failing_tests": failing_tests,
                "ub_warning": ub_warning,
            },
            "recommendation": {
                "action": "retry",
                "problem_id": prob["problem_id"],
                "title": prob["title"],
                "reason": f"Review your logic regarding {student_desc} and test again.",
                "recommendation_type": "targeted_followup",
                "relationship_to_evidence": (
                    f"Observed test failures ({', '.join(failing_tests)}) are consistent with {student_desc}."
                ),
            },
        }

    # --- 4. Ambiguous Collisions (Explicit Abstention) ------------------------
    if evidence["verdict"] == "ambiguous":
        return {
            **base,
            "state": "insufficient_evidence",
            "message": (
                "Insufficient evidence for a single supported diagnosis. "
                "The observed results do not justify choosing one explanation."
            ),
            "explanation": {
                "what_happened": (
                    f"{len(failing_tests)} test(s) failed, but the observed outcome row matches "
                    "multiple distinct error mechanisms equally well."
                ),
                "evidence_summary": f"Tests failing: {', '.join(failing_tests)}.",
                "concept": prob["concept"],
                "why_selected": (
                    "The platform abstains from guessing when multiple explanations fit the evidence."
                ),
                "uncertainty": (
                    "Attributing a single misconception when multiple errors produce identical "
                    "P/F/R outputs would be unsupported speculation."
                ),
                "failing_tests": failing_tests,
                "ub_warning": ub_warning,
            },
            "recommendation": {
                "action": "retry",
                "problem_id": prob["problem_id"],
                "title": prob["title"],
                "reason": "Try this problem again with the same requirements.",
                "recommendation_type": "ambiguity_retry",
                "relationship_to_evidence": (
                    "Multiple error models explain the observed failure pattern; "
                    "retrying with detailed trace testing is recommended."
                ),
            },
        }

    # --- 5. Unmodelled or Other Failures (Explicit Abstention) ---------------
    # Determine if timeouts or crashes dominated
    timeouts = [t["test_id"] for t in tests if t.get("execution_status") == "TIMEOUT"]
    crashes = [t["test_id"] for t in tests if t.get("execution_status") == "CRASHED"]
    
    if timeouts:
        detail_msg = f"Execution timed out on test(s) {', '.join(timeouts)} (exceeded wall time limit)."
    elif crashes:
        detail_msg = f"A runtime crash occurred on test(s) {', '.join(crashes)}."
    else:
        detail_msg = f"Unexpected outputs on test(s) {', '.join(failing_tests)}."

    return {
        **base,
        "state": "insufficient_evidence",
        "message": (
            "Insufficient evidence for a supported diagnosis. "
            "The observed results do not justify choosing one explanation."
        ),
        "explanation": {
            "what_happened": detail_msg,
            "evidence_summary": (
                f"{len(failing_tests)} test(s) did not produce the expected output. "
                "The pattern does not match any modeled misconception."
            ),
            "concept": prob["concept"],
            "why_selected": "General problem debugging is recommended.",
            "uncertainty": (
                "The observed behavior is treated as an unmodelled implementation failure. "
                "The platform does not convert it into a concept-level claim."
            ),
            "failing_tests": failing_tests,
            "ub_warning": ub_warning,
        },
        "recommendation": {
            "action": "retry",
            "problem_id": prob["problem_id"],
            "title": prob["title"],
            "reason": "Try this problem again with the same requirements.",
            "recommendation_type": "general_practice",
            "relationship_to_evidence": (
                "Unmodelled implementation defect; revise the algorithm and test again."
            ),
        },
    }
