"""Phase 4 Automated Verification Suite: Submission Feedback & Diagnostic Results.

Tests the explanation panel across all 6 required result categories:
1. Accepted: Task Correct with epistemic limitations & zero next-question recommendations.
2. Compilation error: Remapped compiler diagnostics & source locations without concept claims.
3. Wrong answer: Output mismatch, failing-test details, and supported behavioral pattern.
4. Runtime error: Abnormal termination error without asserting an unsupported root cause.
5. Timeout: 3.0s sandbox wall limit notice and non-termination explanation.
6. Ambiguous or unmodelled: Explicit confidence abstention ("could not determine the cause confidently").
"""
import os
import subprocess
import sys
import time
import urllib.request

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_URL = "http://127.0.0.1:8088"
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def ensure_server():
    try:
        urllib.request.urlopen(f"{BASE_URL}/health", timeout=1)
        return None
    except Exception:
        pass

    backend_dir = os.path.join(HERE, "..", "backend")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--port", "8088", "--app-dir", backend_dir],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    for _ in range(30):
        time.sleep(0.5)
        try:
            urllib.request.urlopen(f"{BASE_URL}/health", timeout=1)
            return proc
        except Exception:
            pass
    return proc


def run_phase4_tests():
    server_proc = ensure_server()
    console_errors = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=CHROME_PATH, headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 850})

            def handle_console(msg):
                if msg.type == "error":
                    if "401" in msg.text or "favicon" in msg.text or "context attribute" in msg.text:
                        return
                    console_errors.append(msg.text)
                    print(f"  [CONSOLE ERROR]: {msg.text}")

            page.on("console", handle_console)
            page.on("pageerror", lambda err: console_errors.append(str(err)))

            print("\n=======================================================")
            print("STARTING PHASE 4 FEEDBACK & DIAGNOSTIC EXPLANATION SUITE")
            print("=======================================================")

            # Navigate to practice workspace
            page.goto(f"{BASE_URL}/#practice")
            page.wait_for_selector("#view-practice:not([hidden])")
            page.wait_for_selector(".monaco-editor", timeout=10000)

            # -----------------------------------------------------------------
            # Category 1: Accepted (Task Correct)
            # -----------------------------------------------------------------
            print("\n[Case 1] Testing Accepted Submission Feedback...")
            page.click(".plist button[data-id='PILOT-001']")
            page.wait_for_selector("#detail:has-text('PILOT-001')")
            correct_p1_code = """
void moveZeroes(std::vector<int>& nums) {
    size_t w = 0;
    for (size_t i = 0; i < nums.size(); ++i)
        if (nums[i] != 0) nums[w++] = nums[i];
    while (w < nums.size()) nums[w++] = 0;
}"""
            page.evaluate(f"() => window.workspaceUI.setCode({repr(correct_p1_code)})")
            page.click("#run")

            page.wait_for_selector("#results .fb-card.accepted", timeout=15000)
            res_text = page.locator("#results").inner_text()
            assert "accepted" in res_text.lower(), "Accepted badge missing"
            assert "task correct" in res_text.lower(), "Task Correct headline missing"
            assert "9/9 passed" in res_text.lower() or "p p p p p p p p p" in res_text.lower()
            assert "verifies task correctness" in res_text.lower(), "Epistemic task correctness notice missing"
            assert "does not establish concept mastery" in res_text.lower() or "does not establish mastery" in res_text.lower()
            # Verify recommendation removal: NO next-question recommendation
            assert "recommended follow-up" not in res_text.lower(), "Next-question recommendation card should be removed"
            assert "practice recommended problem" not in res_text.lower(), "Next-question CTA should be removed"
            print("  [PASS] Case 1 Accepted: Task Correct rendered with epistemic notice; zero next-question recommendations.")

            # -----------------------------------------------------------------
            # Category 2: Compilation Error
            # -----------------------------------------------------------------
            print("\n[Case 2] Testing Compilation Error Feedback...")
            syntax_error_code = """
void moveZeroes(std::vector<int>& nums) {
    invalid_cpp_statement_here;;;
}"""
            page.evaluate(f"() => window.workspaceUI.setCode({repr(syntax_error_code)})")
            page.click("#run")

            page.wait_for_selector("#results .fb-card.compile-error", timeout=15000)
            ce_text = page.locator("#results").inner_text()
            assert "compilation error" in ce_text.lower()
            assert "build failed" in ce_text.lower()
            assert "invalid_cpp_statement_here" in ce_text, "Remapped compiler diagnostics missing in feedback"
            assert "provide no evidence regarding algorithmic concept" in ce_text.lower(), "Epistemic compiler notice missing"
            print("  [PASS] Case 2 Compilation Error: Remapped line diagnostics rendered without concept claims.")

            # -----------------------------------------------------------------
            # Category 3: Wrong Answer with Supported Diagnostic Pattern
            # -----------------------------------------------------------------
            print("\n[Case 3] Testing Wrong Answer with Supported Diagnostic Match (PILOT-003)...")
            page.click(".plist button[data-id='PILOT-003']")
            page.wait_for_selector("#detail:has-text('PILOT-003')")
            # Modelled E1 bug: counts bracket frequencies instead of using LIFO stack
            counting_p3_code = """
bool isValidParentheses(const std::string& s) {
    int round = 0, square = 0, curly = 0;
    for (char c : s) {
        if (c == '(') round++;
        else if (c == ')') round--;
        else if (c == '[') square++;
        else if (c == ']') square--;
        else if (c == '{') curly++;
        else if (c == '}') curly--;
        if (round < 0 || square < 0 || curly < 0) return false;
    }
    return round == 0 && square == 0 && curly == 0;
}"""
            page.evaluate(f"() => window.workspaceUI.setCode({repr(counting_p3_code)})")
            page.click("#run")

            page.wait_for_selector("#results .fb-card.wrong-answer", timeout=15000)
            wa_text = page.locator("#results").inner_text()
            assert "supported pattern identified" in wa_text.lower() or "wrong answer" in wa_text.lower()
            assert "7/8 passed" in wa_text.lower() or "ppfppppp" in wa_text.lower() or "p p f p p p p p" in wa_text.lower()
            # Plain language pattern
            assert "counting rather than lifo" in wa_text.lower(), "Student-friendly pattern explanation missing"
            # Cognitive firewall check: internal label E1_ignores_lifo must NOT leak
            assert "E1_ignores_lifo" not in wa_text, "Cognitive firewall breach: raw error label found!"
            # Distinguish evidence from explanation
            assert "observed evidence" in wa_text.lower()
            assert "consistent behavioral pattern" in wa_text.lower()
            assert "empirical consistency" in wa_text.lower(), "Cautionary uncertainty notice missing"
            print("  [PASS] Case 3 Supported Diagnosis: Observed evidence distinguished from inferred pattern; raw labels quarantined.")

            # -----------------------------------------------------------------
            # Category 4: Runtime Error (Abnormal Termination / Crash)
            # -----------------------------------------------------------------
            print("\n[Case 4] Testing Runtime Error Feedback...")
            page.click(".plist button[data-id='PILOT-001']")
            page.wait_for_selector("#detail:has-text('PILOT-001')")
            crash_p1_code = """
void moveZeroes(std::vector<int>& nums) {
    int* ptr = nullptr;
    *ptr = 42; // Segmentation fault / access violation
}"""
            page.evaluate(f"() => window.workspaceUI.setCode({repr(crash_p1_code)})")
            page.click("#run")

            page.wait_for_selector("#results .fb-card.runtime-error", timeout=15000)
            re_text = page.locator("#results").inner_text()
            assert "runtime error" in re_text.lower()
            assert "ACCESS_VIOLATION" in re_text or "crashed" in re_text.lower() or "abnormal" in re_text.lower()
            assert "does not assert an unsupported cognitive root cause" in re_text.lower()
            print("  [PASS] Case 4 Runtime Error: Sandbox crash details rendered without asserting an unsupported root cause.")

            # -----------------------------------------------------------------
            # Category 5: Timeout (Time Limit Exceeded)
            # -----------------------------------------------------------------
            print("\n[Case 5] Testing Timeout Feedback...")
            timeout_p1_code = """
void moveZeroes(std::vector<int>& nums) {
    while (true) {} // Infinite loop
}"""
            page.evaluate(f"() => window.workspaceUI.setCode({repr(timeout_p1_code)})")
            page.click("#run")

            # Timeout after 3.0s wall limit per test (total ~30s)
            page.wait_for_selector("#results .fb-card.timeout", timeout=50000)
            to_text = page.locator("#results").inner_text()
            assert "time limit exceeded" in to_text.lower()
            assert "3.0s" in to_text or "wall limit" in to_text.lower()
            assert "infinite loop" in to_text.lower()
            assert "abstains from making any conceptual diagnosis" in to_text.lower()
            print("  [PASS] Case 5 Timeout: 3.0s wall limit termination notice and non-termination explanation verified.")

            # -----------------------------------------------------------------
            # Category 6a: Ambiguous Pattern Abstention (Collision)
            # -----------------------------------------------------------------
            print("\n[Case 6a] Testing Ambiguous Collision Abstention (PILOT-002)...")
            page.click(".plist button[data-id='PILOT-002']")
            page.wait_for_selector("#detail:has-text('PILOT-002')")
            # Returns nullptr: produces FPFFFFFF which collides B_wrong_return & C_off_by_one
            ambiguous_p2_code = """
ListNode* reverseList(ListNode* head) {
    ListNode* prev = nullptr;
    ListNode* curr = head;
    while (curr != nullptr) {
        ListNode* nxt = curr->next;
        curr->next = prev;
        prev = curr;
        curr = nxt;
    }
    return curr;
}"""
            page.evaluate(f"() => window.workspaceUI.setCode({repr(ambiguous_p2_code)})")
            page.click("#run")

            page.wait_for_selector("#results .fb-card.abstain", timeout=20000)
            amb_text = page.locator("#results").inner_text()
            assert "could not determine the cause confidently" in amb_text.lower() or "insufficient evidence" in amb_text.lower()
            assert "abstains from guessing" in amb_text.lower() or "multiple distinct error mechanisms" in amb_text.lower()
            assert "B_wrong_return" not in amb_text, "Cognitive firewall breach: raw label found!"
            print("  [PASS] Case 6a Ambiguous Match: Explicit confidence statement and principled abstention rendered.")

            # -----------------------------------------------------------------
            # Category 6b: Unmodelled Implementation Failure Abstention
            # -----------------------------------------------------------------
            print("\n[Case 6b] Testing Unmodelled Failure Abstention (PILOT-001)...")
            page.click(".plist button[data-id='PILOT-001']")
            page.wait_for_selector("#detail:has-text('PILOT-001')")
            unmodelled_p1_code = """
void moveZeroes(std::vector<int>& nums) {
    if (!nums.empty()) nums[0] = 999;
}"""
            page.evaluate(f"() => window.workspaceUI.setCode({repr(unmodelled_p1_code)})")
            page.click("#run")

            page.wait_for_selector("#results .fb-card.abstain", timeout=20000)
            unmod_text = page.locator("#results").inner_text()
            assert "could not determine the cause confidently" in unmod_text.lower() or "insufficient evidence" in unmod_text.lower()
            assert "does not match any" in unmod_text.lower() or "unmodelled implementation failure" in unmod_text.lower()
            print("  [PASS] Case 6b Unmodelled Match: Classified as unmodelled failure without inventing a misconception.")

            # -----------------------------------------------------------------
            # Zero Console Errors Check
            # -----------------------------------------------------------------
            print("\nChecking Browser Console Health...")
            if console_errors:
                for e in console_errors:
                    print("  [ERROR]", e)
                assert False, f"Detected {len(console_errors)} console errors"
            print("  [PASS] Zero console errors during all 6 feedback case evaluations.")

            browser.close()
    finally:
        if server_proc:
            server_proc.terminate()
            try:
                server_proc.wait(timeout=5)
            except Exception:
                server_proc.kill()

    print("\n=======================================================")
    print("ALL 6 RESULT CATEGORIES VERIFIED SUCCESSFULLY!")
    print("=======================================================\n")


if __name__ == "__main__":
    run_phase4_tests()
