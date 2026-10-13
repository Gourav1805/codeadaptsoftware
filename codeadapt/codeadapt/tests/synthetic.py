"""Controlled submissions used to validate the harness itself.

These are NOT claims about real student behaviour. They exist so the
infrastructure can be checked against known-expected outcomes before any real
data is collected.

Where a project document supplies an error as executable code (P2) or exact
pseudocode (P5), it is transcribed verbatim. Where a document describes an
error only in prose (P1, P4), the most natural faithful reading is used and
the divergence -- if any -- is reported rather than tuned away.
"""

# --- generic misbehaviour, reused across problems -------------------------

INFINITE_LOOP_BODY = "{ volatile int x = 0; while (true) { x = x + 1; } return %s; }"
CRASH_BODY = "{ std::abort(); return %s; }"
MEMORY_BOMB_BODY = ("{ std::vector<long long> v; "
                    "while (true) { v.resize(v.size() + 4000000); v.back() = 1; } "
                    "return %s; }")

# ============================== P1 ========================================

P1 = {
    "correct": """
void moveZeroes(std::vector<int>& nums) {
    size_t w = 0;
    for (size_t i = 0; i < nums.size(); ++i)
        if (nums[i] != 0) nums[w++] = nums[i];
    while (w < nums.size()) nums[w++] = 0;
}""",
    # Doc Error A: "swaps zeroes with elements from the end" (prose only).
    "wrong_order_swap": """
void moveZeroes(std::vector<int>& nums) {
    int last = (int)nums.size() - 1;
    int i = 0;
    while (i <= last) {
        if (nums[i] == 0 && i < last) { int t = nums[i]; nums[i] = nums[last]; nums[last] = t; last--; }
        else i++;
    }
}""",
    # Doc Error C: "assumes array length is at least 2" (prose only).
    "boundary_len2": """
void moveZeroes(std::vector<int>& nums) {
    if (nums.size() < 2) return;
    size_t w = 0;
    for (size_t i = 0; i < nums.size(); ++i)
        if (nums[i] != 0) nums[w++] = nums[i];
    while (w < nums.size()) nums[w++] = 0;
}""",
    # Doc Error D: "treats non-positive values as zero-like" (prose only).
    "value_compare": """
void moveZeroes(std::vector<int>& nums) {
    size_t w = 0;
    for (size_t i = 0; i < nums.size(); ++i)
        if (nums[i] > 0) nums[w++] = nums[i];
    while (w < nums.size()) nums[w++] = 0;
}""",
    "infinite_loop": "void moveZeroes(std::vector<int>& nums) { volatile int x=0; while(true){x=x+1;} }",
    "crash": "void moveZeroes(std::vector<int>& nums) { std::abort(); }",
    "memory_bomb": ("void moveZeroes(std::vector<int>& nums) { std::vector<long long> v;"
                    " while(true){ v.resize(v.size()+4000000); v.back()=1; } }"),
    "compile_error": "void moveZeroes(std::vector<int>& nums) { retrun; }",
}

# ============================== P2 ========================================
# Errors A-D are transcribed verbatim from PILOT-002 section 10.

P2 = {
    "correct": """
ListNode* reverseList(ListNode* head) {
    ListNode* prev = nullptr;
    ListNode* curr = head;
    while (curr != nullptr) {
        ListNode* nxt = curr->next;
        curr->next = prev;
        prev = curr;
        curr = nxt;
    }
    return prev;
}""",
    "A_noop": "ListNode* reverseList(ListNode* head) { return head; }",
    "B_wrong_return": """
ListNode* reverseList(ListNode* head) {
    ListNode* prev = nullptr;
    ListNode* curr = head;
    while (curr != nullptr) {
        ListNode* nxt = curr->next;
        curr->next = prev;
        prev = curr;
        curr = nxt;
    }
    return curr;  // bug: should return prev
}""",
    "C_off_by_one": """
ListNode* reverseList(ListNode* head) {
    ListNode* prev = nullptr;
    ListNode* curr = head;
    while (curr != nullptr && curr->next != nullptr) {
        ListNode* nxt = curr->next;
        curr->next = prev;
        prev = curr;
        curr = nxt;
    }
    return prev;
}""",
    "D_missing_termination": """
ListNode* reverseList(ListNode* head) {
    if (head == nullptr || head->next == nullptr) return head;
    ListNode* newHead = reverseList(head->next);
    head->next->next = head;
    // bug: missing head->next = nullptr;
    return newHead;
}""",
    "infinite_loop": "ListNode* reverseList(ListNode* head) { volatile int x=0; while(true){x=x+1;} return head; }",
    "crash": "ListNode* reverseList(ListNode* head) { std::abort(); return head; }",
}

# ============================== P3 ========================================

_P3_CORRECT = """
#include <stack>
#include <map>
bool isValidParentheses(const std::string& s) {
    std::stack<char> st;
    std::map<char,char> m; m[')']='('; m[']']='['; m['}']='{';
    for (size_t i = 0; i < s.size(); ++i) {
        char c = s[i];
        if (c=='('||c=='['||c=='{') st.push(c);
        else { if (st.empty() || st.top()!=m[c]) return false; st.pop(); }
    }
    return st.empty();
}"""

P3 = {
    "correct": _P3_CORRECT,
    "E1_ignores_lifo": """
bool isValidParentheses(const std::string& s) {
    int a=0,b=0,c=0;
    for (size_t i = 0; i < s.size(); ++i) {
        char x = s[i];
        if (x=='(') a++; else if (x==')') a--;
        else if (x=='[') b++; else if (x==']') b--;
        else if (x=='{') c++; else c--;
        if (a<0||b<0||c<0) return false;
    }
    return a==0 && b==0 && c==0;
}""",
    "E2_no_underflow_check": """
#include <stack>
#include <map>
bool isValidParentheses(const std::string& s) {
    std::stack<char> st;
    std::map<char,char> m; m[')']='('; m[']']='['; m['}']='{';
    for (size_t i = 0; i < s.size(); ++i) {
        char x = s[i];
        if (x=='('||x=='['||x=='{') st.push(x);
        else { if (st.top()!=m[x]) return false; st.pop(); }   // no empty() check
    }
    return st.empty();
}""",
    "E3_no_leftover_check": """
#include <stack>
#include <map>
bool isValidParentheses(const std::string& s) {
    std::stack<char> st;
    std::map<char,char> m; m[')']='('; m[']']='['; m['}']='{';
    for (size_t i = 0; i < s.size(); ++i) {
        char x = s[i];
        if (x=='('||x=='['||x=='{') st.push(x);
        else { if (st.empty() || st.top()!=m[x]) return false; st.pop(); }
    }
    return true;   // no post-scan empty check
}""",
    "E4_ignores_type": """
#include <stack>
bool isValidParentheses(const std::string& s) {
    std::stack<char> st;
    for (size_t i = 0; i < s.size(); ++i) {
        char x = s[i];
        if (x=='('||x=='['||x=='{') st.push(x);
        else { if (st.empty()) return false; st.pop(); }   // no type comparison
    }
    return st.empty();
}""",
    "infinite_loop": "bool isValidParentheses(const std::string& s) { volatile int x=0; while(true){x=x+1;} return true; }",
    "crash": "bool isValidParentheses(const std::string& s) { std::abort(); return true; }",
}

# ============================== P4 ========================================
# The correct solution implements the arrival-at-slice-boundary rule as
# specified in the consolidated statements document: a process arriving
# exactly at slice end is admitted BEFORE the preempted process is requeued.

P4 = {
    "correct": """
#include <deque>
#include <algorithm>
std::vector<int> roundRobinCompletionOrder(const std::vector<int>& burstTimes,
                                           const std::vector<int>& arrivalTimes,
                                           int quantum) {
    int n = (int)burstTimes.size();
    std::vector<int> rem(burstTimes.begin(), burstTimes.end());
    std::vector<char> admitted(n, 0);
    std::vector<int> order;
    std::deque<int> q;

    std::vector<int> byArrival(n);
    for (int i = 0; i < n; ++i) byArrival[i] = i;
    std::sort(byArrival.begin(), byArrival.end(), [&](int a, int b) {
        if (arrivalTimes[a] != arrivalTimes[b]) return arrivalTimes[a] < arrivalTimes[b];
        return a < b;
    });

    long long t = 0;
    // admit every process whose arrival time is <= upto, in (arrival, index) order
    auto admit = [&](long long upto) {
        for (size_t k = 0; k < byArrival.size(); ++k) {
            int i = byArrival[k];
            if (!admitted[i] && arrivalTimes[i] <= upto) { admitted[i] = 1; q.push_back(i); }
        }
    };

    admit(t);
    while ((int)order.size() < n) {
        if (q.empty()) {
            long long nxt = -1;
            for (int i = 0; i < n; ++i)
                if (!admitted[i] && (nxt < 0 || arrivalTimes[i] < nxt)) nxt = arrivalTimes[i];
            if (nxt < 0) break;
            if (nxt > t) t = nxt;
            admit(t);
            continue;
        }
        int p = q.front(); q.pop_front();
        int run = quantum < rem[p] ? quantum : rem[p];
        long long end = t + run;
        rem[p] -= run;
        admit(end);           // arrivals AT the slice boundary enter first
        t = end;
        if (rem[p] == 0) order.push_back(p);
        else q.push_back(p);  // ...then the preempted process is requeued
    }
    return order;
}""",
    "E1_lifo": """
#include <vector>
#include <algorithm>
std::vector<int> roundRobinCompletionOrder(const std::vector<int>& burstTimes,
                                           const std::vector<int>& arrivalTimes,
                                           int quantum) {
    int n = (int)burstTimes.size();
    std::vector<int> rem(burstTimes.begin(), burstTimes.end());
    std::vector<char> admitted(n, 0);
    std::vector<int> order, st;
    long long t = 0;
    auto admit = [&](long long upto) {
        for (int i = 0; i < n; ++i)
            if (!admitted[i] && arrivalTimes[i] <= upto) { admitted[i] = 1; st.push_back(i); }
    };
    admit(t);
    while ((int)order.size() < n) {
        if (st.empty()) {
            long long nxt = -1;
            for (int i = 0; i < n; ++i)
                if (!admitted[i] && (nxt < 0 || arrivalTimes[i] < nxt)) nxt = arrivalTimes[i];
            if (nxt < 0) break;
            if (nxt > t) t = nxt;
            admit(t); continue;
        }
        int p = st.back(); st.pop_back();      // LIFO instead of FIFO
        int run = quantum < rem[p] ? quantum : rem[p];
        long long end = t + run; rem[p] -= run;
        admit(end); t = end;
        if (rem[p] == 0) order.push_back(p); else st.push_back(p);
    }
    return order;
}""",
    "E3_ignores_arrivals": """
#include <deque>
std::vector<int> roundRobinCompletionOrder(const std::vector<int>& burstTimes,
                                           const std::vector<int>& arrivalTimes,
                                           int quantum) {
    int n = (int)burstTimes.size();
    std::vector<int> rem(burstTimes.begin(), burstTimes.end());
    std::vector<int> order;
    std::deque<int> q;
    for (int i = 0; i < n; ++i) q.push_back(i);   // all available at t=0
    while (!q.empty()) {
        int p = q.front(); q.pop_front();
        int run = quantum < rem[p] ? quantum : rem[p];
        rem[p] -= run;
        if (rem[p] == 0) order.push_back(p); else q.push_back(p);
    }
    return order;
}""",
    "infinite_loop": ("std::vector<int> roundRobinCompletionOrder(const std::vector<int>& b,"
                      " const std::vector<int>& a, int q) { volatile int x=0; while(true){x=x+1;}"
                      " return std::vector<int>(); }"),
    "crash": ("std::vector<int> roundRobinCompletionOrder(const std::vector<int>& b,"
              " const std::vector<int>& a, int q) { std::abort();"
              " return std::vector<int>(); }"),
}

# ============================== P5 ========================================
# E1-E4 are transcribed verbatim from PILOT-005 section 7 pseudocode.

P5 = {
    "correct": """
int lowerBound(const std::vector<int>& arr, int target) {
    int lo = 0, hi = (int)arr.size();
    while (lo < hi) {
        int mid = lo + (hi - lo) / 2;
        if (arr[mid] < target) lo = mid + 1; else hi = mid;
    }
    return lo;
}""",
    # The construct-validity bypass: a correct linear scan. MUST pass.
    "linear_scan": """
int lowerBound(const std::vector<int>& arr, int target) {
    for (size_t i = 0; i < arr.size(); ++i) if (arr[i] >= target) return (int)i;
    return (int)arr.size();
}""",
    "E1_missing_increment": """
int lowerBound(const std::vector<int>& arr, int target) {
    int lo = 0, hi = (int)arr.size();
    while (lo < hi) {
        int mid = lo + (hi - lo) / 2;
        if (arr[mid] < target) lo = mid;      // BUG: should be mid + 1
        else hi = mid;
    }
    return lo;
}""",
    "E2_loop_condition": """
int lowerBound(const std::vector<int>& arr, int target) {
    int lo = 0, hi = (int)arr.size();
    while (lo <= hi) {                        // BUG: should be lo < hi
        int mid = lo + (hi - lo) / 2;
        if (arr[mid] < target) lo = mid + 1; else hi = mid;
    }
    return lo;
}""",
    "E3_upper_bound": """
int lowerBound(const std::vector<int>& arr, int target) {
    int lo = 0, hi = (int)arr.size();
    while (lo < hi) {
        int mid = lo + (hi - lo) / 2;
        if (arr[mid] <= target) lo = mid + 1; // BUG: should be arr[mid] < target
        else hi = mid;
    }
    return lo;
}""",
    "E4_upper_mid": """
int lowerBound(const std::vector<int>& arr, int target) {
    int lo = 0, hi = (int)arr.size();
    while (lo < hi) {
        int mid = (lo + hi + 1) / 2;          // BUG: upper-mid convention
        if (arr[mid] < target) lo = mid + 1; else hi = mid;
    }
    return lo;
}""",
    "infinite_loop": "int lowerBound(const std::vector<int>& a, int t) { volatile int x=0; while(true){x=x+1;} return 0; }",
    "crash": "int lowerBound(const std::vector<int>& a, int t) { std::abort(); return 0; }",
    "memory_bomb": ("int lowerBound(const std::vector<int>& a, int t) { std::vector<long long> v;"
                    " while(true){ v.resize(v.size()+4000000); v.back()=1; } return 0; }"),
    "compile_error": "int lowerBound(const std::vector<int>& a, int t) { retrun 0 }",
}

SUBMISSIONS = {"P1": P1, "P2": P2, "P3": P3, "P4": P4, "P5": P5}

# --- Fingerprints as CLAIMED by the frozen documents ----------------------
# The regression suite re-derives these by execution and reports every
# divergence. Divergences are NOT silently reconciled in either direction.

DOCUMENTED_FINGERPRINTS = {
    "P2": {"correct": "PPPPPPPP", "A_noop": "FPPFFFFP", "B_wrong_return": "FPFFFFFF",
           "C_off_by_one": "FPFFFFFF", "D_missing_termination": "FPPFFFFF"},
    "P3": {"correct": "PPPPPPPP", "E1_ignores_lifo": "PPFPPPPP",
           "E2_no_underflow_check": "PPPFPPPP", "E3_no_leftover_check": "PPPPFPPP",
           "E4_ignores_type": "PPFPPFPP"},
    "P5": {"correct": "PPPPPPPP", "linear_scan": "PPPPPPPP",
           "E1_missing_increment": "RRPRPRPP", "E2_loop_condition": "RRRRRRRR",
           "E3_upper_bound": "FPPPFFPF", "E4_upper_mid": "PPRRRRPR"},
    # P1 and P4 synthetic errors are described in prose only, with no code or
    # pseudocode. They are not independently reproducible, so no documented
    # fingerprint can be asserted here.
}


# --- Fingerprints DERIVED BY EXECUTION on the toolchain of record ----------
# MinGW-w64 GCC 16.1.0 (x86_64-ucrt-posix-seh), -std=c++17 -O1, Windows 11,
# Job Object isolation, 3s wall timeout, 256MB cap.
#
# These are the authoritative baseline. The regression suite fails if any row
# drifts, which is what makes an execution-layer change detectable.
# DOCUMENTED_FINGERPRINTS above is retained as the historical record of what
# the frozen documents claimed, so divergences stay visible rather than being
# quietly overwritten.

import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                                  "..", "backend"))

# Single source of truth: the reference matrices are instrument definition
# and live in backend/diagnostics.py. The regression re-derives them by
# execution and fails on any drift.
from diagnostics import REFERENCE as DERIVED_FINGERPRINTS  # noqa: E402

# --- Cells whose outcome derives from UNDEFINED BEHAVIOUR ------------------
# Established empirically: P3/E2 on T4 produced R, then P, then R again across
# three builds (standalone GCC 6.3, harness GCC 6.3, harness GCC 16.1) for the
# same source logic. The outcome tracks incidental memory layout, not the
# error being modelled.
#
# Flagged cells are still executed and still tracked in the baseline -- drift
# is informative -- but they must NOT be used as diagnostic evidence about a
# student, because the value is a property of the build, not of the mistake.
#
# Membership is by static reasoning about where an out-of-bounds or empty
# container access can occur. Non-termination is NOT included: an infinite
# loop is well-defined and reliably reaches the timeout.

from diagnostics import UB_DEPENDENT_CELLS  # noqa: E402


def ub_cells(problem_id, error_name):
    return UB_DEPENDENT_CELLS.get((problem_id, error_name), [])
