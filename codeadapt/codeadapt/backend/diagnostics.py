"""Per-test outcomes -> diagnostic evidence.

This is the next link in the pipeline, and deliberately the whole of it. It is
fingerprint comparison against validated reference patterns -- no knowledge
tracing, no BKT, no student model, no adaptivity. Those are out of scope until
this layer is trustworthy.

What the project documents license, and all this does:

  "When a submission fails, the platform may compare the full per-test P/F/R
   pattern against validated fingerprints to identify evidence consistent with
   boundary, midpoint, duplicate-handling, or termination behaviours. This is
   evidence about plausible error classes, not certain proof of the student's
   underlying misconception."

Four rules are enforced in code rather than left to the caller:

1. Compare the FULL pattern, never counts. Two submissions failing three tests
   each are not comparable; which three is the whole signal.
2. Cells where this submission invoked undefined behaviour are EXCLUDED. The
   probe showed those outcomes track memory layout, not the modelled error, so
   matching on them would be matching on noise.
3. Abstain rather than guess. A pattern that matches no modelled error is
   reported as unmodelled, never bent onto the nearest one. An unmodelled
   implementation bug must not become a concept-level claim.
4. A pass is task correctness. It is never evidence of method or mastery.
"""

import problems

# Reference fingerprints, DERIVED BY EXECUTION on the toolchain of record and
# re-verified by tests/run_regression.py on every change. This is instrument
# definition, not test data, which is why it lives here.
REFERENCE = {
    "P1": {"correct": "PPPPPPPPP", "wrong_order_swap": "FPPPPFPFF",
           "boundary_len2": "PPPPPPPPP", "value_compare": "PPPPPPPPF"},
    "P2": {"correct": "PPPPPPPP", "A_noop": "FPPFFFFP",
           "B_wrong_return": "FPFFFFFF", "C_off_by_one": "FPFFFFFF",
           "D_missing_termination": "FPPFFFFF"},
    "P3": {"correct": "PPPPPPPP", "E1_ignores_lifo": "PPFPPPPP",
           "E2_no_underflow_check": "PPPRPPPP",
           "E3_no_leftover_check": "PPPPFPPP", "E4_ignores_type": "PPFPPFPP"},
    "P4": {"correct": "PPPPPPPP", "E1_lifo": "FFPPFFFF",
           "E3_ignores_arrivals": "PPFPPPPP"},
    "P5": {"correct": "PPPPPPPP", "linear_scan": "PPPPPPPP",
           "E1_missing_increment": "RRPRPRPP", "E2_loop_condition": "RRRFRRRR",
           "E3_upper_bound": "FPPPFFPF", "E4_upper_mid": "PPRFRRPR"},
}

# Cells whose outcome derives from undefined behaviour. Declared by static
# reasoning, then verified against the -D_GLIBCXX_ASSERTIONS probe by the
# regression suite. Used to exclude reference cells from matching.
UB_DEPENDENT_CELLS = {
    ("P3", "E2_no_underflow_check"): ["T4"],
    ("P5", "E2_loop_condition"): ["T4", "T7"],
    ("P5", "E4_upper_mid"): ["T4", "T8"],
}

# Rows that are identical under the current suite and cannot be told apart.
# Stated here so the matcher reports the ambiguity instead of picking one.
KNOWN_COLLISIONS = {
    "P2": [("B_wrong_return", "C_off_by_one")],
    # A correct Binary Search and a correct linear scan are indistinguishable.
    # This is the construct-validity limit of P5, not a defect.
    "P5": [("correct", "linear_scan")],
}

# Plain-language description of what each modelled error is, for report text.
DESCRIPTIONS = {
    "P1": {"wrong_order_swap": "not preserving the relative order of non-zero elements",
           "boundary_len2": "mishandling arrays shorter than two elements",
           "value_compare": "treating non-positive values as if they were zero"},
    "P2": {"A_noop": "no transformation occurring at all",
           "B_wrong_return": "returning the wrong node as the new head",
           "C_off_by_one": "a loop bound that drops the final node",
           "D_missing_termination": "leaving the original head linked, forming a cycle"},
    "P3": {"E1_ignores_lifo": "treating validity as counting rather than LIFO ordering",
           "E2_no_underflow_check": "not checking for an empty stack before matching",
           "E3_no_leftover_check": "not checking the stack is empty after the scan",
           "E4_ignores_type": "tracking depth without comparing bracket types"},
    "P4": {"E1_lifo": "using LIFO order instead of FIFO for the ready queue",
           "E3_ignores_arrivals": "ignoring arrival times and admitting in index order"},
    "P5": {"E1_missing_increment": "omitting the +1 when advancing the lower bound",
           "E2_loop_condition": "an off-by-one termination condition",
           "E3_upper_bound": "computing upper bound instead of lower bound",
           "E4_upper_mid": "an upper-mid convention the bounds check does not match"},
}


def _canonical(problem_id):
    return problems.get(problem_id)["problem_id"]


def _alias(problem_id):
    """Map PILOT-00N back to the PN key the reference tables use."""
    for short, full in problems.ALIASES.items():
        if full == _canonical(problem_id):
            return short
    return problem_id


def interpret(record):
    """Turn one execution record into diagnostic evidence.

    Returns a dict carrying the observed pattern, the excluded cells, matching
    candidates, and an explicit verdict. Never returns a bare label, and never
    claims a root cause.
    """
    if record.get("compile_status") != "OK":
        return {"verdict": "no_execution_evidence",
                "summary": "The submission did not compile, so no per-test "
                           "evidence exists. A compile error is not evidence "
                           "about concept knowledge.",
                "observed": None, "candidates": [], "excluded_cells": [],
                "dynamic_ub_cells": [], "reference_ub_cells": {}}

    pid = _alias(record["problem_id"])
    tests = record["tests"]
    test_ids = [t["test_id"] for t in tests]
    observed = "".join(t["status"] for t in tests)

    # Rule 2: a cell where THIS submission invoked undefined behaviour carries
    # no information about the modelled error, so it is dropped from matching.
    excluded = {i for i, t in enumerate(tests)
                if t.get("ub_check") == "violation"}
    excluded_ids = [test_ids[i] for i in sorted(excluded)]

    reference = REFERENCE.get(pid, {})
    candidates = []
    reference_ub_cells = {}
    for name, ref in reference.items():
        if len(ref) != len(observed):
            continue
        # Also drop cells the reference row itself is known to reach via UB.
        ref_ub = set(UB_DEPENDENT_CELLS.get((pid, name), []))
        reference_ub_cells[name] = [tid for tid in test_ids if tid in ref_ub]
        skip = set(excluded) | {i for i, tid in enumerate(test_ids) if tid in ref_ub}
        diffs = [test_ids[i] for i in range(len(ref))
                 if i not in skip and ref[i] != observed[i]]
        compared = len(ref) - len(skip)
        candidates.append({"error": name, "reference": ref,
                           "reference_ub_cells": reference_ub_cells[name],
                           "mismatched_tests": diffs,
                           "cells_compared": compared,
                           "exact": not diffs and compared > 0,
                           "description": DESCRIPTIONS.get(pid, {}).get(name)})

    exact = [c for c in candidates if c["exact"]]
    all_pass = set(observed) == {"P"}
    result = {"problem_id": record["problem_id"], "observed": observed,
              "test_ids": test_ids, "excluded_cells": excluded_ids,
              "dynamic_ub_cells": excluded_ids,
              "reference_ub_cells": reference_ub_cells,
              "candidates": sorted(candidates, key=lambda c: len(c["mismatched_tests"])),
              "instrument_hash": record.get("limits", {}).get("instrument_hash"),
              # Carried so a reader can check a match by hand. Matching itself
              # uses P/F/R only, as the documents specify -- but two different
              # errors can share a P/F/R row while returning different values,
              # and when that happens this is the evidence that separates them.
              "observed_outputs": [
                  {"test_id": t["test_id"], "expected": t.get("expected_output"),
                   "actual": t.get("actual_output"), "status": t["status"]}
                  for t in tests]}

    if all_pass:
        result["verdict"] = "task_correct"
        result["summary"] = _pass_summary(pid)
        result["matched"] = []
        return result

    # Drop "correct"/"linear_scan" from candidate attribution on a failing run.
    failing = [c for c in exact if c["error"] not in ("correct", "linear_scan")]

    if len(failing) == 1:
        result["verdict"] = "single_match"
        result["matched"] = [failing[0]["error"]]
        result["cells_compared"] = failing[0]["cells_compared"]
        result["summary"] = (
            "The full pattern matches one modelled error: %s. This is evidence "
            "consistent with that error class, not proof of it. Matching uses "
            "P/F/R only, and a different mistake can produce an identical row "
            "-- verified: a submission returning n whenever the target is found "
            "yields P5's E3 row exactly, while returning different values. "
            "Check observed_outputs before relying on this attribution."
            % (failing[0]["description"] or failing[0]["error"]))
    elif len(failing) > 1:
        names = [c["error"] for c in failing]
        collides = any(set(pair) <= set(names)
                       for pair in KNOWN_COLLISIONS.get(pid, []))
        result["verdict"] = "ambiguous"
        result["matched"] = names
        result["summary"] = (
            "The pattern matches %d modelled errors equally well (%s)%s. No "
            "single error class is licensed; report difficulty with the concept "
            "rather than a specific mistake."
            % (len(names), ", ".join(names),
               " -- a known, documented collision" if collides else ""))
    else:
        nearest = result["candidates"][0] if result["candidates"] else None
        result["verdict"] = "unmodelled"
        result["matched"] = []
        result["summary"] = (
            "The pattern matches no modelled error%s. Treat this as an "
            "unmodelled implementation failure. Do NOT convert it into a "
            "concept-level knowledge claim."
            % ("" if not nearest else
               "; the nearest is %s, still differing on %s"
               % (nearest["error"], ", ".join(nearest["mismatched_tests"]))))

    if excluded_ids:
        result["summary"] += (
            " Note: %s excluded from matching because this submission invoked "
            "undefined behaviour there, so those outcomes are not evidence."
            % ", ".join(excluded_ids))
    return result


def _pass_summary(pid):
    base = ("All tests produced the expected results. This establishes task "
            "correctness on the cases tested.")
    limits = problems.get(pid).get("documented_limitations", [])
    unenforceable = problems.get(pid).get("unenforceable_constraints", [])
    if pid == "P5":
        return (base + " It does NOT establish that Binary Search was used: a "
                "correct linear scan passes every test in this suite.")
    if pid == "P2":
        return (base + " It does NOT establish that pointer manipulation was "
                "used: a value-copy-and-rebuild submission passes identically.")
    if unenforceable:
        return (base + " Note that %s" % unenforceable[0])
    if limits:
        return base + " " + limits[0]
    return base
