# CodeAdapt Pilot Problem Catalogue (P1 – P5)

This document provides the definitive, frozen specifications for the initial five pilot problems forming the CodeAdapt problem library. It preserves all problem statements, interfaces, mathematical and structural constraints, test suites, diagnostic intents, synthetic error taxonomies, and verified empirical baselines.

---

## 1. Problem Library Summary

| Problem ID | Canonical ID | Title | Concept | Difficulty | Interface Signature | Validation Model | Test Count |
|---|---|---|---|---|---|---|---|
| **P1** | `PILOT-001` | Move Zeroes | Arrays | Easy | `void moveZeroes(std::vector<int>& nums)` | In-place state validation (`int_list`) | 9 |
| **P2** | `PILOT-002` | Reverse a Singly Linked List | Linked Lists | Easy | `ListNode* reverseList(ListNode* head)` | Bounded traversal + Cycle detection (`linked_list`) | 8 |
| **P3** | `PILOT-003` | Valid Parentheses | Stacks | Easy | `bool isValidParentheses(const std::string& s)` | Return value comparison (`bool`) | 8 |
| **P4** | `PILOT-004` | Round Robin Completion Order with Arrivals | Queues | Medium | `std::vector<int> roundRobinCompletionOrder(const std::vector<int>&, const std::vector<int>&, int)` | Completion sequence comparison (`int_list`) | 8 |
| **P5** | `PILOT-005` | First Position Not Less Than Target (Lower Bound) | Binary Search | Easy–Medium | `int lowerBound(const std::vector<int>& arr, int target)` | Returned index comparison (`int`) | 8 |

---

## 2. Problem Specifications

```
                                    +--------------------------+
                                    |       CodeAdapt Core     |
                                    |      Problem Library     |
                                    +------------+-------------+
                                                 |
         +-------------------+-------------------+-------------------+-------------------+
         |                   |                   |                   |                   |
         v                   v                   v                   v                   v
   [PILOT-001]         [PILOT-002]         [PILOT-003]         [PILOT-004]         [PILOT-005]
   Move Zeroes         Reverse List     Valid Parentheses   Round Robin Order    Lower Bound
     (Arrays)         (Linked Lists)        (Stacks)            (Queues)        (Binary Search)
```

---

### Pilot Problem #1: Move Zeroes (PILOT-001)

#### 1. Problem Overview
- **Problem ID:** `PILOT-001` (Alias: `P1`, `P01`)
- **Problem Title:** Move Zeroes
- **Problem Type:** Single-concept
- **Difficulty:** Easy
- **Top-Level Concept:** Arrays
- **Relevant Subconcepts:** Arrays only (traversal, index manipulation, order preservation)
- **Language:** C++ (C++17)
- **Execution Model:** Function-based, platform-controlled driver
- **Function Signature:** `void moveZeroes(std::vector<int>& nums);`
- **Output Validation:** The platform inspects the modified in-place state of `nums` after execution.

#### 2. Student-Facing Problem Statement
Given an integer array `nums`, move all `0`'s to the end of it while maintaining the relative order of the non-zero elements.

The operation must be performed in-place without making a copy of the array.

You do **not** write `main()`, read from standard input, or print to standard output. The platform constructs `nums`, invokes your function, and checks the contents of `nums` afterwards.

#### 3. Formal Constraints
- `1 <= nums.length <= 10^4`
- `-2^31 <= nums[i] <= 2^31 - 1`

#### 4. Examples
- **Example 1:**
  - Input: `nums = [0, 3, 0, 7, 5]`
  - Output State: `[3, 7, 5, 0, 0]`
- **Example 2:**
  - Input: `nums = [0, 0, 1]`
  - Output State: `[1, 0, 0]`
- **Example 3:**
  - Input: `nums = [5, 3, 7, 2]`
  - Output State: `[5, 3, 7, 2]`

#### 5. Concept Taxonomy
- Arrays / Traversal & General Correctness
- Arrays / Order Preservation
- Arrays / Boundary Handling (all-zero, single-element)
- Arrays / Consecutive-Zero Handling
- Arrays / Value Handling (handling negative values)

#### 6. Diagnostic Test Suite
| Test ID | Input (`nums`) | Expected Output | Role | Target Concept & Error Pattern | Diagnostic Purpose | Confidence | Informativeness | Confound |
|---|---|---|---|---|---|---|---|---|
| **T1** | `[0, 3, 0, 7, 5]` | `[3, 7, 5, 0, 0]` | Core | Arrays / Order preservation | Core behavior with distinct non-zeros | High | Medium | Off-by-one, zero detection, traversal bugs |
| **T2** | `[5, 3, 7, 2]` | `[5, 3, 7, 2]` | Control | Arrays / No-op handling | Array with no zeroes | Medium | Low | General implementation bug |
| **T3** | `[0, 0, 0, 0]` | `[0, 0, 0, 0]` | Boundary | Arrays / All-zero boundary | Array with only zeroes | High | Low–Medium | Initialization or loop-termination bugs |
| **T4** | `[0]` | `[0]` | Boundary | Arrays / Single-element boundary (zero) | Smallest array with zero | High | Low–Medium | Length-one boundary bugs |
| **T5** | `[7]` | `[7]` | Boundary | Arrays / Single-element boundary (non-zero) | Smallest array with non-zero | High | Low–Medium | Length-one boundary bugs |
| **T6** | `[0, 0, 3, 7]` | `[3, 7, 0, 0]` | Behavioral Diagnostic | Arrays / Consecutive-zero handling (leading) | Adjacent zeroes at start | High | Medium | Generic traversal or pointer-update bugs |
| **T7** | `[3, 0, 0, 7]` | `[3, 7, 0, 0]` | Behavioral Diagnostic | Arrays / Consecutive-zero handling (middle) | Adjacent zeroes in middle | High | Medium | Generic traversal or pointer-update bugs |
| **T8** | `[5, 0, 2, 0, 9]` | `[5, 2, 9, 0, 0]` | Core | Arrays / Observable order preservation | Observable reordering | High | High | Partial overlap with T1 |
| **T9** | `[-1, 0, -3, 0, 2]` | `[-1, -3, 2, 0, 0]` | Robustness | Arrays / Value handling | Functional robustness with negatives | Medium | Low | Low diagnostic specificity |

#### 7. Modeled Synthetic Errors & Baseline Fingerprints
| Error ID | Error Description | Defect Mechanism | Claimed Failed Tests | Observed Fingerprint | Status / Empirical Notes |
|---|---|---|---|---|---|
| **A** | `wrong_order_swap` | Swaps zeroes with elements from the end (partition style) | T1, T8 | `FPPPPFPFF` | Fails T1, T6, T8, T9. Document provided prose description only. |
| **B** | Consecutive-zero mishandling | Read/write pointers advance unsynchronized on consecutive zeroes | T6, T7 | N/A | Prose-only specification in pilot draft. |
| **C** | `boundary_len2` | Assumes `nums.size() >= 2` (`if (nums.size() < 2) return;`) | T3, T4, T5 | `PPPPPPPPP` | Single elements `[0]`, `[7]` and `[0,0,0,0]` are already unchanged, so early exit still passes all tests. |
| **D** | `value_compare` | Treats non-positive values (`nums[i] <= 0`) as zero-like | T9 | `PPPPPPPPF` | Fails T9 only. Matches conceptual expectation. |
| **E** | `correct` | Two-pointer read/write index traversal | None | `PPPPPPPPP` | All 9 tests pass. Baseline verified. |

#### 8. Construct Validity & Documented Limitations
- **Unenforceable In-Place Constraint:** Under an output-only execution harness, auxiliary memory allocation cannot be observed. A submission that allocates a secondary vector and copies non-zero elements passes all 9 tests. Passing is task correctness, not proof of $O(1)$ space.
- **Prose-Only Synthetic Errors:** Unlike P2 and P5, the pilot document supplied prose descriptions rather than concrete C++ code or pseudocode for synthetic errors.

---

### Pilot Problem #2: Reverse a Singly Linked List (PILOT-002)

#### 1. Problem Overview
- **Problem ID:** `PILOT-002` (Alias: `P2`)
- **Problem Title:** Reverse a Singly Linked List
- **Problem Type:** Single-concept
- **Difficulty:** Easy
- **Top-Level Concept:** Linked Lists
- **Relevant Subconcepts:** Pointer reversal, returned-head correctness, boundary and small-list handling, list integrity and cycle termination.
- **Provided Data Structure:**
  ```cpp
  struct ListNode {
      int val;
      ListNode* next;
      ListNode(int x) : val(x), next(nullptr) {}
  };
  ```
- **Function Signature:** `ListNode* reverseList(ListNode* head);`
- **Output Validation:** Bounded pointer traversal with node address tracking (detects cycles, verifies null-termination, reachable count, and value order).

#### 2. Student-Facing Problem Statement
You are given the head of a singly linked list. Reverse the list in place and return a pointer to the new head.

`head` points to the first node of the list, or is `nullptr` if the list is empty.

You do not need to read input or print output. The platform constructs the list and calls your function directly.

#### 3. Formal Constraints
- `0 <= number of nodes <= 10^4`
- `-10^5 <= ListNode.val <= 10^5`

#### 4. Examples
- **Example 1:** `1 -> 2 -> 3 -> 4 -> 5` $\rightarrow$ `5 -> 4 -> 3 -> 2 -> 1`
- **Example 2:** `nullptr` $\rightarrow$ `nullptr`
- **Example 3:** `42` $\rightarrow$ `42`

#### 5. Concept Taxonomy
- Linked Lists / Pointer reversal
- Linked Lists / Returned-head correctness
- Linked Lists / Boundary and small-list handling
- Linked Lists / List integrity & termination (cycle freedom)

#### 6. Diagnostic Test Suite
| Test ID | Input List | Expected Output | Method | Role | Primary Concept & Error Pattern | Diagnostic Purpose | Confidence | Informativeness | Confound |
|---|---|---|---|---|---|---|---|---|---|
| **T1** | `1->2->3->4->5` | `5->4->3->2->1` | OUTPUT | Core | Pointer reversal | Baseline distinct-value case | High | Medium | Broad failure mode |
| **T2** | `nullptr` | `nullptr` | OUTPUT | Boundary | Empty-list handling | Null-safety verification | High | Low–Medium | Missing null check |
| **T3** | `42` | `42` | OUTPUT | Boundary | Single-node handling | Smallest valid list | High | Medium | Not reversal-specific |
| **T4** | `1->2` | `2->1` | OUTPUT | Behavioral Diagnostic | Minimal reversal | Smallest two-node reversal | High | Medium | Generic two-node boundary bug |
| **T5** | `1->2->3->4->5->6->7` | `7->6->5->4->3->2->1` | OUTPUT | Core | Pointer reversal on longer list | Non-trivial list coverage | High | Medium | Overlaps T1 |
| **T6** | `-3->0->7->-1` | `-1->7->0->-3` | OUTPUT | Robustness | Value transfer | Robustness against node copying | Medium | Low | Low specificity |
| **T7** | `1->2->3->4->5->6` | `6->5->4->3->2->1` | STRUCTURAL | Behavioral Diagnostic | List integrity / termination | Explicit cycle & termination check | High | Medium | Overlaps bounded traversal rule |
| **T8** | `7->3->7` | `7->3->7` | OUTPUT | Behavioral Diagnostic | No-op discrimination | Palindrome control case | Medium | Medium | Multiple bugs could pass coincidentally |

#### 7. Modeled Synthetic Errors & Failure Fingerprint Matrix
- **Error A (No-op):** `ListNode* reverseList(ListNode* head) { return head; }`
- **Error B (Wrong return variable):** Iterates correctly, but `return curr;` instead of `prev`.
- **Error C (Off-by-one loop bound):** `while (curr != nullptr && curr->next != nullptr)` drops tail node.
- **Error D (Missing termination in recursion):** `head->next->next = head;` without `head->next = nullptr;` creates cycle.
- **Error E (Correct solution):** Full iterative pointer reversal.

| Error Class | T1 | T2 | T3 | T4 | T5 | T6 | T7 | T8 | Fingerprint | Target Attribution |
|---|---|---|---|---|---|---|---|---|---|---|
| **A (No-op)** | F | P | P | F | F | F | F | P | `FPPFFFFP` | Linked Lists / Pointer reversal |
| **B (Wrong return)** | F | P | F | F | F | F | F | F | `FPFFFFFF` | Linked Lists / Returned-head correctness |
| **C (Off-by-one)** | F | P | F | F | F | F | F | F | `FPFFFFFF` | Linked Lists / Boundary handling |
| **D (Missing termination)**| F | P | P | F | F | F | F | F | `FPPFFFFF` | Linked Lists / List integrity |
| **E (Correct)** | P | P | P | P | P | P | P | P | `PPPPPPPP` | Task Correctness |

#### 8. Construct Validity & Documented Limitations
- **B and C Collision:** Under the current test suite, Errors B and C produce identical fingerprints (`FPFFFFFF`). The diagnostic engine reports this as `ambiguous` between B and C.
- **Value-Copy Bypass:** A solution that allocates a new linked list or copies node values into a buffer passes all tests.

---

### Pilot Problem #3: Valid Parentheses (PILOT-003)

#### 1. Problem Overview
- **Problem ID:** `PILOT-003` (Alias: `P3`)
- **Problem Title:** Valid Parentheses
- **Problem Type:** Single-concept
- **Difficulty:** Easy
- **Top-Level Concept:** Stacks
- **Relevant Subconcepts:** LIFO ordering, stack-underflow handling, leftover-state post-scan check, bracket-type matching.
- **Function Signature:** `bool isValidParentheses(const std::string& s);`
- **Output Validation:** Boolean return value validation (`bool`). Crashes or non-terminations classified as `R`.

#### 2. Student-Facing Problem Statement
Given a string `s` containing only the characters `(`, `)`, `{`, `}`, `[`, and `]`, determine whether the brackets are validly matched and nested.

A string is valid if:
1. Every opening bracket has a corresponding closing bracket of the same type.
2. Brackets close in the correct last-in, first-out (LIFO) order.
3. The empty string is valid.

You do not need to write `main()`, read input, or print output. The platform provides the string and calls your function directly.

#### 3. Formal Constraints
- `0 <= s.length() <= 10^4`
- `s` contains only `(){}[]`

#### 4. Examples
- **Example 1:** `s = "()[]{}"` $\rightarrow$ `true`
- **Example 2:** `s = "([)]"` $\rightarrow$ `false`
- **Example 3:** `s = ""` $\rightarrow$ `true`

#### 5. Concept Taxonomy
- Stacks / LIFO ordering
- Stacks / Underflow handling
- Stacks / Leftover-state handling
- Stacks / Type matching

#### 6. Diagnostic Test Suite
| Test ID | Input (`s`) | Expected Output | Role | Target Error Pattern | Diagnostic Purpose | Confidence | Informativeness | Confound |
|---|---|---|---|---|---|---|---|---|
| **T1** | `"()[]{}"` | `true` | Core | --- | Baseline sequential correctness | High | Low | None |
| **T2** | `""` | `true` | Boundary | Empty input | Defined behavior on empty string | High | Low | None |
| **T3** | `"([)]"` | `false` | Behavioral Diagnostic | Order ignorance | Counts brackets without LIFO | Medium | High | May overlap with type-matching failure |
| **T4** | `"]"` | `false` | Behavioral Diagnostic | Stack underflow | Premature closing bracket | Medium | High | Crash from missing empty check |
| **T5** | `"("` | `false` | Behavioral Diagnostic | Missing leftover check | Unmatched opening bracket at EOF | High | Medium | Low |
| **T6** | `"(]"` | `false` | Behavioral Diagnostic | Type matching ignored | Depth-only matching | Medium | High | May overlap with T3 |
| **T7** | `"{[()()]}"` | `true` | Control | --- | Nested multi-type control case | High | Low | None |
| **T8** | $5000\text{ '('} + 5000\text{ ')'}$ | `true` | Robustness | Scale / depth fragility | Maximum nesting depth (length $10^4$) | Medium | Low–Medium | Implementation resource limits |

#### 7. Modeled Synthetic Errors & Failure Fingerprint Matrix
- **E1 (Ignores LIFO ordering):** Counts opening/closing brackets per type; ignores order.
- **E2 (Missing underflow check):** Calls `st.top()` / `st.pop()` without checking `st.empty()`.
- **E3 (Missing leftover-state check):** Returns `true` after loop without verifying `st.empty()`.
- **E4 (Ignores bracket type):** Pushes all opening brackets; pops on any closing bracket without type matching.

| Error Class | T1 | T2 | T3 | T4 | T5 | T6 | T7 | T8 | Claimed FP | Observed FP | Status / Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **E1 (Ignores LIFO)** | P | P | F | P | P | P | P | P | `PPFPPPPP` | `PPFPPPPP` | Matches document exactly. |
| **E2 (No underflow)** | P | P | P | **R** | P | P | P | P | `PPPFPPPP` | `PPPRPPPP` | **UB Divergence:** Calling `top()` on empty stack crashes under GCC 16.1.0 (`R`). Statically excluded from matching. |
| **E3 (No leftover)** | P | P | P | P | F | P | P | P | `PPPPFPPP` | `PPPPFPPP` | Matches document exactly. |
| **E4 (Ignores type)** | P | P | F | P | P | F | P | P | `PPFPPFPP` | `PPFPPFPP` | Matches document exactly. |
| **Correct** | P | P | P | P | P | P | P | P | `PPPPPPPP` | `PPPPPPPP` | All pass. |

#### 8. Construct Validity & Documented Limitations
- **Undefined Behavior Sensitivity (T4):** Calling `st.top()` on an empty `std::stack` is undefined behavior. In older GCC 6.3 builds without assertions, it could read garbage and return `F` (`false`), whereas modern toolchains produce `R` (segmentation fault / crash). This cell is marked in `UB_DEPENDENT_CELLS` and dynamically probed via `-D_GLIBCXX_ASSERTIONS`.

---

### Pilot Problem #4: Round Robin Completion Order with Arrivals (PILOT-004)

#### 1. Problem Overview
- **Problem ID:** `PILOT-004` (Alias: `P4`)
- **Problem Title:** Round Robin Completion Order with Arrivals
- **Problem Type:** Single-concept
- **Difficulty:** Medium
- **Top-Level Concept:** Queues
- **Relevant Subconcepts:** FIFO front-dequeue ordering, arrival-vs-requeue insertion convention, temporal admission, simultaneous-arrival tie-breaking, finish-boundary handling.
- **Function Signature:**
  ```cpp
  std::vector<int> roundRobinCompletionOrder(
      const std::vector<int>& burstTimes,
      const std::vector<int>& arrivalTimes,
      int quantum
  );
  ```
- **Output Validation:** Exact vector comparison of completed process indices (`int_list`).

#### 2. Student-Facing Problem Statement
There are `n` processes, indexed from `0` to `n - 1`. Process `i` arrives at time `arrivalTimes[i]` and requires `burstTimes[i]` units of CPU time.

Simulate the following Round Robin scheduling policy:
1. A process becomes eligible to run when the simulated clock reaches its arrival time.
2. The CPU always runs the process at the front of the ready queue.
3. A process runs for `min(quantum, remainingTime)` units.
4. If unfinished, it is placed at the back of the ready queue.
5. Any processes that arrive during that time slice are added to the ready queue **before** the unfinished running process is re-enqueued.
6. A process arriving exactly when a time slice ends is available before the next dispatch decision and is enqueued before the just-executed unfinished process is re-enqueued.
7. If multiple processes arrive at the same time, they are added in ascending process-index order.
8. If the ready queue is empty while some processes have not arrived, the CPU idles until the next arrival.
9. As soon as a process's remaining time reaches zero, record its index in the completion order.

Return the process indices in the order in which they complete.

#### 3. Formal Constraints
- `0 <= n <= 500`
- `0 <= arrivalTimes[i] <= 10^4`
- `1 <= burstTimes[i] <= 10^4`
- `1 <= quantum <= 10^4`

#### 4. Examples & Critical Test Traces
- **T2 Trace:**
  - Input: `burst = [4, 2], arrival = [0, 2], q = 2`
  - $t=0$: P0 runs $[0, 2]$, remaining = 2.
  - $t=2$: P1 arrives. P1 is enqueued *before* unfinished P0 is requeued. Queue = `[P1, P0]`.
  - P1 runs $[2, 4]$ and finishes. P0 runs $[4, 6]$ and finishes.
  - Expected: `[1, 0]`.
- **T8 Trace (Approved Correction):**
  - Input: `burst = [3, 3, 3, 3], arrival = [0, 1, 2, 3], q = 2`
  - $t=0\text{--}2$: P0 runs. P1 arrives at $t=1$. Queue at $t=2$: `[P1, P0]`.
  - $t=2\text{--}4$: P1 runs. P2 arrives at $t=2$ (slice boundary, enters before requeue), P3 arrives at $t=3$. Queue at $t=4$: `[P0, P2, P3, P1]`.
  - $t=4\text{--}5$: P0 finishes! First completed: `0`.
  - $t=5\text{--}7$: P2 runs (remaining = 1), requeued behind P3, P1.
  - Full completion sequence: `[0, 1, 2, 3]`.

#### 5. Concept Taxonomy
- Queues / FIFO front-dequeue ordering
- Queues / Arrival-vs-requeue insertion convention
- Queues / Temporal admission
- Queues / Simultaneous-arrival tie-break
- Queues / Finish-boundary handling

#### 6. Diagnostic Test Suite
| Test ID | Input Parameters | Expected Output | Role | Target Error Pattern | Diagnostic Purpose | Confidence | Informativeness | Confound |
|---|---|---|---|---|---|---|---|---|
| **T1** | `b=[3,1,2], a=[0,0,0], q=2` | `[1, 2, 0]` | Core | --- | Baseline FIFO dispatch & rotation | High | Medium | Multiple behaviors |
| **T2** | `b=[4,2], a=[0,2], q=2` | `[1, 0]` | Behavioral Diagnostic | Arrival-vs-requeue ordering | P1 arrives at slice boundary | High | High | None |
| **T3** | `b=[2,2], a=[10,0], q=2` | `[1, 0]` | Behavioral Diagnostic | Temporal admission | P1 arrives before P0 despite index | High | High | None |
| **T4** | `b=[], a=[], q=3` | `[]` | Boundary | Empty input | Zero processes handled cleanly | High | Low | None |
| **T5** | `b=[1,1,1], a=[3,3,3], q=5` | `[0, 1, 2]` | Behavioral Diagnostic | Simultaneous-arrival tie-break | Simultaneous arrivals after idle | High | High | None |
| **T6** | `b=[3,5,2], a=[0,0,0], q=10` | `[0, 1, 2]` | Control | --- | Quantum exceeds bursts (no rotation) | High | Low–Medium | Sensitive to tie-break |
| **T7** | `b=[2,4], a=[0,0], q=2` | `[0, 1]` | Boundary | Exact quantum completion | Process completes exactly at slice end | Medium | Low | General correctness |
| **T8** | `b=[3,3,3,3], a=[0,1,2,3], q=2` | `[0, 1, 2, 3]` | Robustness | Sustained interleaving | Multi-arrival interleaving | Medium | Medium | Multiple interactions |

#### 7. Modeled Synthetic Errors & Failure Fingerprint Matrix
- **E1 (LIFO instead of FIFO):** Replaces queue with a stack. Observed fingerprint: `FFPPFFFF`.
- **E2 (Requeue before arrivals):** Unfinished process requeued before admitting new arrivals during slice. Fails T2.
- **E3 (Ignores arrival times):** Assumes all available at $t=0$, admits in index order. Observed fingerprint: `PPFPPPPP`.
- **E4 (Reversed tie-break):** Admits simultaneous arrivals in descending index order. Fails T1, T5, T6.

| Error Class | T1 | T2 | T3 | T4 | T5 | T6 | T7 | T8 | Fingerprint | Target Attribution |
|---|---|---|---|---|---|---|---|---|---|---|
| **E1 (LIFO)** | F | F | P | P | F | F | F | F | `FFPPFFFF` | Queues / FIFO front-dequeue ordering |
| **E2 (Requeue first)** | P | F | P | P | P | P | P | P | `PFPFFFFF`* | Queues / Arrival-vs-requeue convention |
| **E3 (Ignore arrivals)**| P | P | F | P | P | P | P | P | `PPFPPPPP` | Queues / Temporal admission |
| **E4 (Reversed tie-break)**| F | P | P | P | F | F | P | P | `FPPFFPP`* | Queues / Simultaneous tie-break |
| **Correct** | P | P | P | P | P | P | P | P | `PPPPPPPP` | Task Correctness |

*\*Note: E2 and E4 are modeled conceptually; E1, E3, and Correct have verified synthetic fixtures in `synthetic.py`.*

#### 8. Construct Validity & Approved Reconciliations
- **T8 Arithmetic Trace Correction:** The initial pilot draft claimed expected output `[0, 2, 1, 3]`, which was arithmetically impossible and contradicted the slice-boundary rule verified by T2. Corrected to `[0, 1, 2, 3]`, enabling the reference solution to pass with `PPPPPPPP`.
- **Confounding Risk:** Rated Medium. Simulation complexity itself can lead to failures that do not necessarily indicate a queue concept gap.

---

### Pilot Problem #5: First Position Not Less Than Target / Lower Bound (PILOT-005)

#### 1. Problem Overview
- **Problem ID:** `PILOT-005` (Alias: `P5`)
- **Problem Title:** First Position Not Less Than Target (Lower Bound)
- **Problem Type:** Single-concept
- **Difficulty:** Easy–Medium
- **Top-Level Concept:** Binary Search
- **Relevant Subconcepts:** Interval maintenance, boundary movement, midpoint calculation, duplicate handling, termination conditions.
- **Function Signature:** `int lowerBound(const std::vector<int>& arr, int target);`
- **Output Validation:** Returned integer index comparison (`int`). Non-termination / out-of-bounds classified as `R`.

#### 2. Student-Facing Problem Statement
You are given a sorted (non-decreasing) integer array `arr` and an integer `target`. Implement the function:

```cpp
int lowerBound(const std::vector<int>& arr, int target);
```

Return the index of the **first element in `arr` that is greater than or equal to `target`**. If no such element exists, return `arr.size()`.

- `arr` may contain duplicate values.
- `arr` may be empty.
- Do not write `main()`, read input, or print output.

#### 3. Formal Constraints
- `0 <= arr.size() <= 10^5`
- `-10^9 <= arr[i], target <= 10^9`
- `arr` is sorted in non-decreasing order.

#### 4. Examples
- `arr = [1, 3, 5, 7, 9], target = 5` $\rightarrow$ `2`
- `arr = [1, 3, 5, 7, 9], target = 4` $\rightarrow$ `2`
- `arr = []`, `target = 5` $\rightarrow$ `0`

#### 5. Concept Taxonomy
- Binary Search / Interval maintenance
- Binary Search / Boundary movement (`lo` update)
- Binary Search / Midpoint calculation
- Binary Search / Lower-bound vs Upper-bound duplicate convergence
- Binary Search / Termination condition

#### 6. Diagnostic Test Suite
| Test ID | Input (`arr`, `target`) | Expected Output | Role | Target Error Pattern | Diagnostic Purpose | Confidence | Informativeness | Confound |
|---|---|---|---|---|---|---|---|---|
| **T1** | `[1,3,5,7,9], 5` | `2` | Core | Interior exact-match | Interior exact match convergence | Medium | High | Low |
| **T2** | `[1,3,5,7,9], 4` | `2` | Core | Absent value convergence | Interior absent value convergence | Medium | Medium | Low |
| **T3** | `[1,3,5,7,9], 0` | `0` | Boundary | Target below all elements | Collapse at `lo = 0` (Approved correction from `target=1`) | Medium | High | Low |
| **T4** | `[1,3,5,7,9], 10` | `5` | Boundary | Target above all elements | Answer equals `n`; probes if `mid` can reach `n` | High | High | Low |
| **T5** | `[2,2,2,2,2], 2` | `0` | Behavioral Diagnostic | All-duplicate array | First occurrence requirement | Medium | High | Low |
| **T6** | `[1,2,2,2,5,8], 2` | `1` | Behavioral Diagnostic | Mixed duplicates | First occurrence mid-array | Low | Medium | Medium |
| **T7** | `[], 5` | `0` | Robustness | Empty array | Trivial return without crash | Medium | Medium | Low |
| **T8** | `[4], 4` | `0` | Boundary | Single-element exact match | Smallest nontrivial interval | High | High | Low |

#### 7. Modeled Synthetic Errors & Failure Fingerprint Matrix
- **E1 (`missing_increment`):** `if (arr[mid] < target) lo = mid;` $\rightarrow$ infinite loop on 2-element intervals.
- **E2 (`loop_condition`):** `while (lo <= hi)` $\rightarrow$ out-of-bounds read at `arr[n]` or non-termination.
- **E3 (`upper_bound`):** `if (arr[mid] <= target) lo = mid + 1;` $\rightarrow$ computes upper bound instead of lower bound.
- **E4 (`upper_mid`):** `mid = (lo + hi + 1) / 2;` $\rightarrow$ out-of-bounds read when `hi == n` and non-termination.
- **Linear Scan Bypass:** $O(n)$ linear traversal checking `arr[i] >= target`.

| Error Class | T1 | T2 | T3 | T4 | T5 | T6 | T7 | T8 | Claimed FP | Observed FP (GCC 16.1) | Diagnostic Interpretation |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **E1** | R | R | P | R | P | R | P | P | `RRPRPRPP` | `RRPRPRPP` | Missing `+1` on `lo` advance. |
| **E2** | R | R | R | **F** | R | R | R | R | `RRRRRRRR` | `RRRFRRRR` | **UB Divergence:** Loop condition off-by-one. T4 reads `arr[n]` and returns wrong value (`F`) rather than crashing on GCC 16. |
| **E3** | F | P | P | P | F | F | P | F | `FPPPFFPF` | `FPPPFFPF` | Lower-bound vs Upper-bound confusion. |
| **E4** | P | P | R | **F** | R | R | P | R | `PPRRRRPR` | `PPRFRRPR` | **UB Divergence:** Upper-mid convention. T4 reads `arr[n]` and returns `F`. |
| **Linear Scan**| P | P | P | P | P | P | P | P | `PPPPPPPP` | `PPPPPPPP` | Construct-validity bypass (Passes all 8). |
| **Correct** | P | P | P | P | P | P | P | P | `PPPPPPPP` | `PPPPPPPP` | Reference Binary Search. |

#### 8. Construct Validity & Documented Limitations
1. **Linear Scan Bypass:** A simple for-loop linear scan passes all 8 tests. Passing PILOT-005 establishes task correctness, **never** proof that Binary Search was used.
2. **Diagnostic Bluntness of E2:** E2 loops or crashes on virtually every test (`RRRFRRRR`), providing severe negative evidence but little granular localization.
3. **P/F/R Collision with Novel Bugs:** A submission returning `n` whenever the target is found produces fingerprint `FPPPFFPF`, identical to E3. Discriminating between them requires inspecting actual returned values (`observed_outputs`), which CodeAdapt preserves.
4. **Undefined Behavior Discrepancies:** T4 accesses `arr[n]` under E2 and E4. Depending on heap layout, this produces `R` (segfault) or `F` (wrong answer). Statically declared in `UB_DEPENDENT_CELLS` (`T4`, `T7` for E2; `T4`, `T8` for E4) and excluded from diagnostic matching.

---

## 3. Cross-Problem Diagnostic Summary

| Problem | Primary Concept | Dominant Failure Modes Modeled | Known Collisions / Ambiguities | Primary Construct Limitation |
|---|---|---|---|---|
| **P1** | Arrays | Swap scrambling, length assumption, value comparison | Natural implementations diverge from prose claims | In-place execution not observable by output harness |
| **P2** | Linked Lists | No-op, wrong return, off-by-one bound, cycle creation | Error B & Error C share identical fingerprint `FPFFFFFF` | Pointer vs value copy rebuild not separable |
| **P3** | Stacks | Counting-only, empty stack underflow, unclosed bracket, type mismatch | None among modeled synthetic errors | Empty stack underflow is undefined behavior |
| **P4** | Queues | Stack/LIFO substitution, requeue order bug, arrival time omission, tie-break bug | E1 & E4 share baseline failures | High simulation complexity confounds queue attribution |
| **P5** | Binary Search | Missing `lo` advance, off-by-one loop, upper-bound confusion, upper-mid convention | Correct & Linear Scan collide; E3 collides with novel return-$n$ bug | Linear scan passes all tests; UB on out-of-bounds reads |

---

## 4. Verification and Integrity Commitments
1. **Immutable Problem Semantics:** The 5 pilot problems are frozen. No tests, constraints, or expected outputs will be modified to artificially force test suites green.
2. **Preservation of Raw Evidence:** Every test execution outcome is preserved with test ID, status (P/F/R), execution status (COMPLETED, TIMEOUT, CRASHED), runtime, memory, raw stdout, stderr, and assertion violation details.
3. **Explicit Diagnostic Boundaries:** The platform abstains when evidence is ambiguous or unmodeled, and never presents diagnostic error labels to students to prevent cognitive priming.
