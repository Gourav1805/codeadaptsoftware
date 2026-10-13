"""P1-P5 definitions: execution data and research metadata, kept apart.

Execution fields  : test_id, input_cpp, expected, kind
Research metadata : the `research` dict -- role, diagnostic_target,
                    confidence, informativeness, confound, validation_type.

The executor reads ONLY execution fields. Research annotations can never
alter execution behaviour, per the requirement that annotations on the
instrument must not feed back into the measurement.

Expected outputs are deliberately NOT compiled into the student binary --
validation happens in Python, so a submission cannot read the answer key.
"""

# --- C++ literal emitters -------------------------------------------------

def _vec(name, values):
    if not values:
        return "/* %s stays empty */" % name
    return ("{ static const int _a[] = {%s}; %s.assign(_a, _a + %d); }"
            % (",".join(str(v) for v in values), name, len(values)))


def _meta(role, target, confidence, informativeness, confound, validation="OUTPUT"):
    return {"role": role, "diagnostic_target": target, "confidence": confidence,
            "informativeness": informativeness, "confound": confound,
            "validation_type": validation}


# --- Shared driver skeleton ----------------------------------------------

_SKELETON = """#include <vector>
#include <string>
#include <cstdio>
#include <cstdlib>
__PROLOGUE__
/* ===== STUDENT SUBMISSION BEGINS ===== */
__STUDENT__
/* ===== STUDENT SUBMISSION ENDS ===== */

int main(int argc, char** argv) {
    if (argc < 3) return 64;
    int t = atoi(argv[1]);
__BODY__
    return 0;
}
"""

# ============================== P1 ========================================

P1_BODY = """    std::vector<int> nums;
    switch (t) {
__CASES__
        default: return 65;
    }
    moveZeroes(nums);
    FILE* f = fopen(argv[2], "w");
    if (!f) return 66;
    for (size_t i = 0; i < nums.size(); ++i) fprintf(f, "%d ", nums[i]);
    fclose(f);"""

P1 = {
    "problem_id": "PILOT-001", "title": "Move Zeroes", "concept": "Arrays",
    "signature": "void moveZeroes(std::vector<int>& nums);",
    "kind": "int_list", "prologue": "", "body": P1_BODY,
    "tests": [
        {"test_id": "T1", "input_cpp": _vec("nums", [0, 3, 0, 7, 5]), "expected": [3, 7, 5, 0, 0],
         "research": _meta("Core", "order preservation / general correctness", "High", "Medium",
                           "off-by-one, zero detection, traversal bugs")},
        {"test_id": "T2", "input_cpp": _vec("nums", [5, 3, 7, 2]), "expected": [5, 3, 7, 2],
         "research": _meta("Control", "no-op handling", "Medium", "Low",
                           "almost any implementation bug fails this")},
        {"test_id": "T3", "input_cpp": _vec("nums", [0, 0, 0, 0]), "expected": [0, 0, 0, 0],
         "research": _meta("Boundary", "all-zero boundary", "High", "Low-Medium",
                           "initialization or loop-termination bugs")},
        {"test_id": "T4", "input_cpp": _vec("nums", [0]), "expected": [0],
         "research": _meta("Boundary", "single-element (zero)", "High", "Low-Medium",
                           "generic length-one boundary bugs")},
        {"test_id": "T5", "input_cpp": _vec("nums", [7]), "expected": [7],
         "research": _meta("Boundary", "single-element (non-zero)", "High", "Low-Medium",
                           "generic length-one boundary bugs")},
        {"test_id": "T6", "input_cpp": _vec("nums", [0, 0, 3, 7]), "expected": [3, 7, 0, 0],
         "research": _meta("Behavioral Diagnostic", "consecutive zeroes (leading)", "High", "Medium",
                           "generic traversal or pointer-update bugs")},
        {"test_id": "T7", "input_cpp": _vec("nums", [3, 0, 0, 7]), "expected": [3, 7, 0, 0],
         "research": _meta("Behavioral Diagnostic", "consecutive zeroes (middle)", "High", "Medium",
                           "generic traversal or pointer-update bugs")},
        {"test_id": "T8", "input_cpp": _vec("nums", [5, 0, 2, 0, 9]), "expected": [5, 2, 9, 0, 0],
         "research": _meta("Core", "observable order preservation", "High", "High", "some overlap with T1")},
        {"test_id": "T9", "input_cpp": _vec("nums", [-1, 0, -3, 0, 2]), "expected": [-1, -3, 2, 0, 0],
         "research": _meta("Robustness", "value handling (negatives)", "Medium", "Low",
                           "low diagnostic specificity")},
    ],
    # Recorded as NOT enforced. An output-only harness cannot observe copying.
    "unenforceable_constraints": [
        "in-place / no copy of the array (O(1) auxiliary space) -- NOT OBSERVABLE "
        "by this harness. Never treat a pass as evidence the constraint was met.",
    ],
}

# ============================== P2 ========================================

P2_PROLOGUE = """struct ListNode {
    int val;
    ListNode* next;
    ListNode(int x) : val(x), next(nullptr) {}
};
"""

P2_BODY = """    std::vector<int> in;
    switch (t) {
__CASES__
        default: return 65;
    }
    ListNode* head = nullptr; ListNode* tail = nullptr;
    for (size_t i = 0; i < in.size(); ++i) {
        ListNode* n = new ListNode(in[i]);
        if (!head) { head = n; tail = n; } else { tail->next = n; tail = n; }
    }
    ListNode* r = reverseList(head);

    /* Bounded, address-tracking traversal. A returned cycle must never hang
       the harness, so traversal is capped and repeated addresses detected. */
    size_t limit = in.size() + 1;
    std::vector<ListNode*> seen;
    std::vector<int> vals;
    int cycle = 0;
    ListNode* cur = r;
    while (cur != nullptr && vals.size() <= limit) {
        int dup = 0;
        /* ponytail: O(n^2) address scan, fine at pilot sizes; swap for a hash
           set if node counts ever approach the 10^4 constraint. */
        for (size_t i = 0; i < seen.size(); ++i) if (seen[i] == cur) { dup = 1; break; }
        if (dup) { cycle = 1; break; }
        seen.push_back(cur); vals.push_back(cur->val); cur = cur->next;
    }
    int terminated = (!cycle && cur == nullptr) ? 1 : 0;

    FILE* f = fopen(argv[2], "w");
    if (!f) return 66;
    fprintf(f, "%d %d %d", cycle, terminated, (int)vals.size());
    for (size_t i = 0; i < vals.size(); ++i) fprintf(f, " %d", vals[i]);
    fclose(f);"""

P2 = {
    "problem_id": "PILOT-002", "title": "Reverse a Singly Linked List",
    "concept": "Linked Lists",
    "signature": "ListNode* reverseList(ListNode* head);",
    "kind": "linked_list", "prologue": P2_PROLOGUE, "body": P2_BODY,
    "tests": [
        {"test_id": "T1", "input_cpp": _vec("in", [1, 2, 3, 4, 5]), "expected": [5, 4, 3, 2, 1],
         "research": _meta("Core", "pointer reversal", "High", "Medium",
                           "broad -- many bug types produce this failure")},
        {"test_id": "T2", "input_cpp": _vec("in", []), "expected": [],
         "research": _meta("Boundary", "empty-list handling", "High", "Low-Medium",
                           "generic null-check omission")},
        {"test_id": "T3", "input_cpp": _vec("in", [42]), "expected": [42],
         "research": _meta("Boundary", "single-node handling", "High", "Medium",
                           "not reversal-specific; no reversal is required")},
        {"test_id": "T4", "input_cpp": _vec("in", [1, 2]), "expected": [2, 1],
         "research": _meta("Behavioral Diagnostic", "minimal reversal", "High", "Medium",
                           "generic two-node boundary bug")},
        {"test_id": "T5", "input_cpp": _vec("in", [1, 2, 3, 4, 5, 6, 7]), "expected": [7, 6, 5, 4, 3, 2, 1],
         "research": _meta("Core", "pointer reversal on a longer list", "High", "Medium",
                           "broad; overlaps with T1")},
        {"test_id": "T6", "input_cpp": _vec("in", [-3, 0, 7, -1]), "expected": [-1, 7, 0, -3],
         "research": _meta("Robustness", "value transfer", "Medium", "Low", "low specificity")},
        {"test_id": "T7", "input_cpp": _vec("in", [1, 2, 3, 4, 5, 6]), "expected": [6, 5, 4, 3, 2, 1],
         "research": _meta("Behavioral Diagnostic", "list integrity / termination", "High", "Medium",
                           "overlaps the global bounded-traversal rule", "STRUCTURAL")},
        {"test_id": "T8", "input_cpp": _vec("in", [7, 3, 7]), "expected": [7, 3, 7],
         "research": _meta("Behavioral Diagnostic", "no-op vs transformation discrimination",
                           "Medium", "Medium",
                           "multiple incorrect implementations could coincidentally pass")},
    ],
    "documented_limitations": [
        "A value-copy-and-rebuild submission can pass every test. Passing is NOT "
        "evidence that pointer-level manipulation was performed.",
        "Errors B (wrong return variable) and C (off-by-one loop bound) share an "
        "identical fingerprint under this suite and cannot be separated.",
    ],
}

# ============================== P3 ========================================

P3_BODY = """    std::string s;
    switch (t) {
__CASES__
        default: return 65;
    }
    bool r = isValidParentheses(s);
    FILE* f = fopen(argv[2], "w");
    if (!f) return 66;
    fprintf(f, "%d", (int)r);
    fclose(f);"""


def _str_lit(s):
    return 's = "%s";' % s.replace("\\", "\\\\").replace('"', '\\"')


P3 = {
    "problem_id": "PILOT-003", "title": "Valid Parentheses", "concept": "Stacks",
    "signature": "bool isValidParentheses(const std::string& s);",
    "kind": "bool", "prologue": "", "body": P3_BODY,
    "tests": [
        {"test_id": "T1", "input_cpp": _str_lit("()[]{}"), "expected": True,
         "research": _meta("Core", "baseline sequential correctness", "High", "Low", "None")},
        {"test_id": "T2", "input_cpp": _str_lit(""), "expected": True,
         "research": _meta("Boundary", "empty-input handling", "High", "Low", "None")},
        {"test_id": "T3", "input_cpp": _str_lit("([)]"), "expected": False,
         "research": _meta("Behavioral Diagnostic", "LIFO order-ignorance", "Medium", "High",
                           "may overlap with type-matching failure")},
        {"test_id": "T4", "input_cpp": _str_lit("]"), "expected": False,
         "research": _meta("Behavioral Diagnostic", "stack underflow", "Medium", "High",
                           "runtime failure could stem from a generic bounds bug",
                           "OUTPUT; crash recorded separately as RUNTIME ERROR")},
        {"test_id": "T5", "input_cpp": _str_lit("("), "expected": False,
         "research": _meta("Behavioral Diagnostic", "missing leftover-state check", "High", "Medium", "Low")},
        {"test_id": "T6", "input_cpp": _str_lit("(]"), "expected": False,
         "research": _meta("Behavioral Diagnostic", "type matching ignored", "Medium", "High",
                           "may overlap with T3")},
        {"test_id": "T7", "input_cpp": _str_lit("{[()()]}"), "expected": True,
         "research": _meta("Control", "nested multi-type control case", "High", "Low", "None")},
        {"test_id": "T8", "input_cpp": "s = std::string(5000, '(') + std::string(5000, ')');",
         "expected": True,
         "research": _meta("Robustness", "scale / depth fragility", "Medium", "Low-Medium",
                           "failure may reflect implementation or resource limits "
                           "rather than Stack-concept weakness")},
    ],
}

# ============================== P4 ========================================

P4_BODY = """    std::vector<int> burst, arrival; int q = 0;
    switch (t) {
__CASES__
        default: return 65;
    }
    std::vector<int> r = roundRobinCompletionOrder(burst, arrival, q);
    FILE* f = fopen(argv[2], "w");
    if (!f) return 66;
    for (size_t i = 0; i < r.size(); ++i) fprintf(f, "%d ", r[i]);
    fclose(f);"""


def _p4(burst, arrival, q):
    return "%s %s q = %d;" % (_vec("burst", burst), _vec("arrival", arrival), q)


P4 = {
    "problem_id": "PILOT-004", "title": "Round Robin Completion Order with Arrivals",
    "concept": "Queues",
    "signature": ("std::vector<int> roundRobinCompletionOrder("
                  "const std::vector<int>& burstTimes, "
                  "const std::vector<int>& arrivalTimes, int quantum);"),
    "kind": "int_list", "prologue": "", "body": P4_BODY,
    "boundary_rule": (
        "A process arriving exactly when a time slice ends is available before "
        "the next dispatch decision and is enqueued BEFORE the just-executed "
        "unfinished process is re-enqueued."),
    "confounding_risk": (
        "Medium -- simulation complexity itself can produce failures that are "
        "not necessarily evidence of a Queue misunderstanding."),
    "tests": [
        {"test_id": "T1", "input_cpp": _p4([3, 1, 2], [0, 0, 0], 2), "expected": [1, 2, 0],
         "research": _meta("Core", "baseline FIFO dispatch, rotation, simultaneous admission",
                           "High", "Medium", "combines multiple behaviors")},
        {"test_id": "T2", "input_cpp": _p4([4, 2], [0, 2], 2), "expected": [1, 0],
         "research": _meta("Behavioral Diagnostic", "arrival-vs-requeue ordering", "High", "High",
                           "none significant")},
        {"test_id": "T3", "input_cpp": _p4([2, 2], [10, 0], 2), "expected": [1, 0],
         "research": _meta("Behavioral Diagnostic", "temporal admission", "High", "High",
                           "none significant")},
        {"test_id": "T4", "input_cpp": _p4([], [], 3), "expected": [],
         "research": _meta("Boundary", "empty input", "High", "Low", "None")},
        {"test_id": "T5", "input_cpp": _p4([1, 1, 1], [3, 3, 3], 5), "expected": [0, 1, 2],
         "research": _meta("Behavioral Diagnostic", "simultaneous-arrival tie-break", "High", "High",
                           "none significant")},
        {"test_id": "T6", "input_cpp": _p4([3, 5, 2], [0, 0, 0], 10), "expected": [0, 1, 2],
         "research": _meta("Control", "no-rotation baseline", "High", "Low-Medium",
                           "also sensitive to tie-break behavior")},
        {"test_id": "T7", "input_cpp": _p4([2, 4], [0, 0], 2), "expected": [0, 1],
         "research": _meta("Boundary", "exact quantum completion", "Medium", "Low",
                           "mainly a general correctness check")},
        # CORRECTED (approved). The frozen document expected [0,2,1,3], which no
        # boundary convention produces, and whose published trace was
        # arithmetically impossible. Re-derived from the specified rules; T2
        # already required this same convention.
        {"test_id": "T8", "input_cpp": _p4([3, 3, 3, 3], [0, 1, 2, 3], 2), "expected": [0, 1, 2, 3],
         "research": _meta("Robustness", "sustained multi-arrival interleaving", "Medium", "Medium",
                           "corrected from doc value [0,2,1,3]; multiple Queue behaviors interact")},
    ],
}

# ============================== P5 ========================================

P5_BODY = """    std::vector<int> arr; int target = 0;
    switch (t) {
__CASES__
        default: return 65;
    }
    int r = lowerBound(arr, target);
    FILE* f = fopen(argv[2], "w");
    if (!f) return 66;
    fprintf(f, "%d", r);
    fclose(f);"""


def _p5(arr, target):
    return "%s target = %d;" % (_vec("arr", arr), target)


P5 = {
    "problem_id": "PILOT-005", "title": "First Position Not Less Than Target (Lower Bound)",
    "concept": "Binary Search",
    "signature": "int lowerBound(const std::vector<int>& arr, int target);",
    "kind": "int", "prologue": "", "body": P5_BODY,
    "tests": [
        {"test_id": "T1", "input_cpp": _p5([1, 3, 5, 7, 9], 5), "expected": 2,
         "research": _meta("Core", "interior exact-match convergence", "Medium", "High", "Low")},
        {"test_id": "T2", "input_cpp": _p5([1, 3, 5, 7, 9], 4), "expected": 2,
         "research": _meta("Core", "interior absent-value convergence", "Medium", "Medium", "Low")},
        # CORRECTED (approved). The frozen table said target=1, but the row's own
        # stated purpose is "target below all elements", which target=1 does not
        # test -- it is an exact match at index 0, already covered by T1/T8.
        # target=0 restores the intended diagnostic role.
        {"test_id": "T3", "input_cpp": _p5([1, 3, 5, 7, 9], 0), "expected": 0,
         "research": _meta("Boundary", "target below all elements; interval collapse at lo=0",
                           "Medium", "High", "Low; corrected from doc table value target=1")},
        {"test_id": "T4", "input_cpp": _p5([1, 3, 5, 7, 9], 10), "expected": 5,
         "research": _meta("Boundary", "answer equals n; probes whether mid can reach n",
                           "High", "High", "Low")},
        {"test_id": "T5", "input_cpp": _p5([2, 2, 2, 2, 2], 2), "expected": 0,
         "research": _meta("Behavioral Diagnostic", "all-duplicate first-occurrence", "Medium", "High", "Low")},
        {"test_id": "T6", "input_cpp": _p5([1, 2, 2, 2, 5, 8], 2), "expected": 1,
         "research": _meta("Behavioral Diagnostic", "mixed duplicates, first occurrence mid-array",
                           "Low", "Medium", "Medium")},
        {"test_id": "T7", "input_cpp": _p5([], 5), "expected": 0,
         "research": _meta("Robustness", "empty array", "Medium", "Medium", "Low")},
        {"test_id": "T8", "input_cpp": _p5([4], 4), "expected": 0,
         "research": _meta("Boundary", "single-element exact match", "High", "High", "Low")},
    ],
    "documented_limitations": [
        "A correct linear scan passes all 8 tests. PASS establishes task "
        "correctness only -- never that Binary Search was used or mastered.",
        "Expected O(log n) is a label. The harness performs no complexity "
        "enforcement of any kind.",
        "E1, E2 and E4 produce only P/R outcomes and are separable only by "
        "which specific tests fail, not by outcome type.",
    ],
}

PROBLEMS = {p["problem_id"]: p for p in (P1, P2, P3, P4, P5)}
ALIASES = {"P1": "PILOT-001", "P2": "PILOT-002", "P3": "PILOT-003",
           "P4": "PILOT-004", "P5": "PILOT-005"}


def get(pid):
    return PROBLEMS[ALIASES.get(pid.upper(), pid)]


def render_source(problem, student_code):
    """Full translation unit: platform prologue + student code + platform
    driver. One compile per submission; the test index is selected at run
    time via argv, so all tests share a binary but never a process."""
    cases = "\n".join(
        "        case %d: { %s break; }" % (i, t["input_cpp"])
        for i, t in enumerate(problem["tests"]))
    body = problem["body"].replace("__CASES__", cases)
    src = _SKELETON.replace("__PROLOGUE__", problem["prologue"])
    src = src.replace("__BODY__", body)
    # Student code is substituted LAST so its contents are never rescanned for
    # placeholders: a stray % or __TOKEN__ in a submission cannot break rendering.
    return src.replace("__STUDENT__", student_code)


# --- Student-facing display text ------------------------------------------
# Transcribed from the consolidated statements document. Display only: nothing
# here is read by the executor, and none of it affects classification.

STATEMENTS = {
    "PILOT-001": {
        "statement": (
            "Given an integer array `nums`, move all 0's to the end of it while "
            "maintaining the relative order of the non-zero elements.\n\n"
            "The platform constructs the input vector and calls your function "
            "directly. You do not need to write `main()`, read from standard "
            "input, or print to standard output.\n\n"
            "Your function must modify `nums` so that all zeroes are at the end "
            "and the relative order of all non-zero elements is preserved."),
        "constraints": ["1 <= nums.length <= 10^4", "-2^31 <= nums[i] <= 2^31 - 1"],
        "note": ("The intended solution uses O(1) auxiliary space. Under this "
                 "output-only harness the platform validates the final state of "
                 "`nums`; it does not enforce whether a submission creates a copy."),
    },
    "PILOT-002": {
        "statement": (
            "You are given the head of a singly linked list. `head` points to the "
            "first node, or is `nullptr` if the list is empty.\n\n"
            "Reverse the list in place and return a pointer to the new head.\n\n"
            "The platform constructs the list and calls your function directly."),
        "constraints": ["0 <= number of nodes <= 10^4", "-10^5 <= ListNode.val <= 10^5"],
        "note": ("The platform validates the returned structure, including its "
                 "sequence, termination and structural integrity."),
    },
    "PILOT-003": {
        "statement": (
            "Given a string `s` containing only `()`, `{}` and `[]`, determine "
            "whether the brackets are valid.\n\n"
            "A string is valid if every opening bracket is closed by the same type "
            "of bracket and brackets are closed in the correct last-in, first-out "
            "order. The empty string is valid."),
        "constraints": ["0 <= s.length() <= 10^4", "s contains only (){}[]"],
        "note": None,
    },
    "PILOT-004": {
        "statement": (
            "There are `n` processes, indexed 0 to n-1. Process i arrives at "
            "`arrivalTimes[i]` and requires `burstTimes[i]` units of CPU time. "
            "Simulate this Round Robin policy:\n\n"
            "1. A process becomes eligible when the clock reaches its arrival time.\n"
            "2. The CPU always runs the process at the front of the ready queue.\n"
            "3. A process runs for min(quantum, remainingTime) units.\n"
            "4. If unfinished, it is placed at the back of the ready queue.\n"
            "5. Processes arriving during the slice are added BEFORE the just-run "
            "unfinished process is placed back.\n"
            "6. A process arriving exactly when a slice ends is available before "
            "the next dispatch decision, and is enqueued before the just-executed "
            "unfinished process is re-enqueued.\n"
            "7. Simultaneous arrivals enter in ascending process-index order.\n"
            "8. If the ready queue is empty, the CPU idles until the next arrival.\n"
            "9. When remaining time reaches zero, record that index immediately.\n\n"
            "Return the process indices in completion order."),
        "constraints": ["0 <= n <= 500", "0 <= arrivalTimes[i] <= 10^4",
                        "1 <= burstTimes[i] <= 10^4", "1 <= quantum <= 10^4"],
        "note": ("You may implement the FIFO ready queue using std::queue, deque, "
                 "an array/vector with front/rear indices, or any equivalent."),
    },
    "PILOT-005": {
        "statement": (
            "Given a sorted array `arr` in non-decreasing order, return the first "
            "index `i` such that `arr[i] >= target`. If no such index exists, "
            "return `arr.size()`.\n\n"
            "The array may contain duplicate values. The required result is the "
            "leftmost position at which `target` could be inserted while preserving "
            "sorted order."),
        "constraints": ["arr is sorted non-decreasing", "0 <= arr.size() <= 10^5",
                        "values fit within the C++ int range"],
        "note": None,
    },
}

STARTER = {
    "PILOT-001": "void moveZeroes(std::vector<int>& nums) {\n    // your code here\n}\n",
    "PILOT-002": ("// struct ListNode { int val; ListNode* next; "
                  "ListNode(int x) : val(x), next(nullptr) {} };\n"
                  "// is provided by the platform.\n\n"
                  "ListNode* reverseList(ListNode* head) {\n    // your code here\n}\n"),
    "PILOT-003": ("bool isValidParentheses(const std::string& s) {\n"
                  "    // your code here\n}\n"),
    "PILOT-004": ("std::vector<int> roundRobinCompletionOrder(\n"
                  "        const std::vector<int>& burstTimes,\n"
                  "        const std::vector<int>& arrivalTimes,\n"
                  "        int quantum) {\n    // your code here\n}\n"),
    "PILOT-005": ("int lowerBound(const std::vector<int>& arr, int target) {\n"
                  "    // your code here\n}\n"),
}
