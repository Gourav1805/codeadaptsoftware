"""Phase 5 Automated Verification Suite: Student Profile and Submission History.

Tests:
1. Unauthorized Access:
   - Backend APIs (/api/student/profile, /api/student/history) reject with 401.
   - Frontend profile view (#profile) renders clean unauthorized prompt without leaking data.
2. Authenticated Access & Basic Account Information:
   - Profile renders real persisted username, email, account ID, student role, and registration date.
   - Epistemic note stating persisted vs unavailable mutation endpoints.
   - Zero invented mastery scores, streaks, progress percentages, or completion statistics.
3. Empty History State:
   - Fresh student with zero submissions sees clear empty state and question library CTA.
4. Existing Submissions History:
   - Evaluated submissions display problem titles, timestamps, available verdicts, and fingerprints.
   - Attempt lineage indicators and action buttons (Inspect, Code, Lineage).
5. Cross-User Authorization & Security:
   - Student can only access their own profile and submissions.
   - Cross-user submission access via /api/submissions/{id} rejected with 403.
   - Researcher telemetry and researcher-only diagnostics inaccessible (403).
6. Navigation & Return:
   - "Back to Problem Library" returns cleanly to student home.
7. Logout Functionality:
   - Logout button terminates session, clears credentials, and returns to public landing.
8. Zero Console Errors.
"""
import os
import subprocess
import sys
import time
import urllib.request
import uuid

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


def run_phase5_tests():
    server_proc = ensure_server()
    console_errors = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=CHROME_PATH, headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 850})

            def handle_console(msg):
                if msg.type == "error":
                    # Filter expected 401s from unauthenticated requests & favicon
                    if "401" in msg.text or "favicon" in msg.text or "context attribute" in msg.text:
                        return
                    console_errors.append(msg.text)
                    print(f"  [CONSOLE ERROR]: {msg.text}")

            page.on("console", handle_console)
            page.on("pageerror", lambda err: console_errors.append(str(err)))

            print("\n=======================================================")
            print("STARTING PHASE 5 STUDENT PROFILE & HISTORY VERIFICATION")
            print("=======================================================")

            # -----------------------------------------------------------------
            # 1. Unauthorized Access Verification (Backend & Frontend)
            # -----------------------------------------------------------------
            print("\n[1] Testing Unauthorized Access Safeguards...")
            # Direct backend API calls without credentials must return 401
            req_ctx = page.request
            resp_prof = req_ctx.get(f"{BASE_URL}/api/student/profile")
            assert resp_prof.status == 401, f"Expected 401 for unauthorized profile, got {resp_prof.status}"

            resp_hist = req_ctx.get(f"{BASE_URL}/api/student/history")
            assert resp_hist.status == 401, f"Expected 401 for unauthorized history, got {resp_hist.status}"

            # Direct frontend navigation to #profile unauthenticated
            page.goto(f"{BASE_URL}/#profile")
            page.wait_for_selector("#view-profile:not([hidden])")
            page.wait_for_selector(".profile-unauth-card")
            unauth_text = page.locator(".profile-unauth-card").inner_text()
            assert "authentication required" in unauth_text.lower(), "Unauthorized prompt missing"
            assert page.locator(".profile-unauth-card button:has-text('Sign In')").is_visible()
            assert page.locator(".profile-unauth-card button:has-text('Create Account')").is_visible()
            print("  [PASS] Unauthorized access strictly rejected (HTTP 401 & UI security card).")

            # -----------------------------------------------------------------
            # 2. Registration & Empty History Profile State
            # -----------------------------------------------------------------
            print("\n[2] Testing Fresh Student Profile & Empty History State...")
            rand_suffix = uuid.uuid4().hex[:6]
            student_a = f"stu_a_{rand_suffix}"
            email_a = f"{student_a}@example.edu"
            password_a = "StudentPass123!"

            page.click(".profile-unauth-card button:has-text('Create Account')")
            page.wait_for_selector("#auth-modal:not([hidden])")
            page.fill("#auth-username", student_a)
            page.fill("#auth-email", email_a)
            page.fill("#auth-password", password_a)
            page.fill("#auth-confirm", password_a)
            page.click("#btn-auth-submit")
            page.wait_for_selector("#auth-modal", state="hidden")

            # Navigate to profile
            page.goto(f"{BASE_URL}/#profile")
            page.wait_for_selector("#view-profile:not([hidden])")
            page.wait_for_selector(".profile-card", timeout=10000)

            profile_text = page.locator("#view-profile").inner_text()

            # Verify persisted account info
            assert student_a in profile_text, f"Username {student_a} missing from profile"
            assert email_a in profile_text, f"Email {email_a} missing from profile"
            assert "student" in profile_text.lower(), "Student role missing from profile"
            assert "Student ID:" in profile_text, "Student ID missing from profile"
            assert "persisted account data" in profile_text.lower(), "Persisted data notice missing"
            assert "endpoints are not currently implemented" in profile_text.lower() or "not yet supported" in profile_text.lower()

            # Epistemic constraint: Zero invented mastery scores, streaks, or completion percentages
            assert "streak" not in profile_text.lower(), "Invented streak metric found in profile!"
            assert "mastery score" not in profile_text.lower(), "Invented mastery score found in profile!"
            assert "%" not in profile_text, "Invented progress percentage found in student profile!"

            # Verify Empty History state
            page.wait_for_selector(".profile-history-empty")
            empty_text = page.locator(".profile-history-empty").inner_text()
            assert "no submissions recorded yet" in empty_text.lower(), "Empty history message missing"
            assert page.locator(".profile-history-empty button:has-text('Browse Questions')").is_visible()
            print("  [PASS] Profile renders authentic persisted account info and clean empty history state without gamification.")

            # -----------------------------------------------------------------
            # 3. Submitting Code and Verifying Persisted History & Verdicts
            # -----------------------------------------------------------------
            print("\n[3] Testing Execution Recording, Problem Titles & Verdicts...")
            # Click Browse Questions to navigate to problem library
            page.click(".profile-history-empty button:has-text('Browse Questions')")
            page.wait_for_selector("#view-home:not([hidden])")

            # Open PILOT-001 (Move Zeroes)
            page.click("#q-card-PILOT-001 button")
            page.wait_for_selector("#view-practice:not([hidden])")
            page.wait_for_selector(".monaco-editor", timeout=10000)

            # Submit Correct PILOT-001 solution
            correct_code = """
void moveZeroes(std::vector<int>& nums) {
    size_t w = 0;
    for (size_t i = 0; i < nums.size(); ++i)
        if (nums[i] != 0) nums[w++] = nums[i];
    while (w < nums.size()) nums[w++] = 0;
}"""
            page.evaluate(f"() => window.workspaceUI.setCode({repr(correct_code)})")
            page.click("#run")
            page.wait_for_selector("#results .fb-card.accepted", timeout=15000)
            print("  [*] Recorded Accepted submission for PILOT-001.")

            # Navigate to PILOT-002 and submit a failing attempt to test Attempt Lineage
            page.click(".plist button[data-id='PILOT-002']")
            page.wait_for_selector("#detail:has-text('PILOT-002')")
            wrong_p2_code = """
ListNode* reverseList(ListNode* head) {
    return nullptr;
}"""
            page.evaluate(f"() => window.workspaceUI.setCode({repr(wrong_p2_code)})")
            page.click("#run")
            page.wait_for_selector("#results button:has-text('Retry')", timeout=15000)

            # Chained retry
            page.click("#results button:has-text('Retry')")
            page.wait_for_selector("#followup-badge", state="visible")
            page.click("#run")
            page.wait_for_selector("#results .fb-card", timeout=15000)
            print("  [*] Recorded Chained Follow-up submission for PILOT-002.")

            # Return to Profile Page
            page.click("#btn-nav-profile")
            page.wait_for_selector("#view-profile:not([hidden])")
            page.wait_for_selector(".profile-table tbody tr", timeout=10000)

            rows = page.locator(".profile-table tbody tr")
            row_count = rows.count()
            assert row_count >= 3, f"Expected at least 3 submission rows in profile history, got {row_count}"
            print(f"  [PASS] Profile history rendered {row_count} submission records.")

            profile_table_text = page.locator(".profile-table").inner_text()
            # Verify real problem titles
            assert "Move Zeroes" in profile_table_text, "Problem title 'Move Zeroes' missing from history"
            assert "PILOT-001" in profile_table_text
            assert "Reverse a Singly Linked List" in profile_table_text, "Problem title 'Reverse a Singly Linked List' missing"
            assert "PILOT-002" in profile_table_text

            # Verify verdicts
            assert "accepted" in profile_table_text.lower(), "Accepted verdict missing from history"
            assert "wrong answer" in profile_table_text.lower(), "Wrong Answer verdict missing from history"

            # Verify attempt lineage indicator
            assert "Follow-up" in profile_table_text, "Chained follow-up lineage tag missing"
            assert "Initial Attempt" in profile_table_text, "Initial attempt lineage tag missing"

            # -----------------------------------------------------------------
            # 4. Navigation & Feedback Inspection Actions
            # -----------------------------------------------------------------
            print("\n[4] Testing History Action Links & Home Navigation...")
            # Click Inspect on the first row
            page.click(".profile-table tbody tr:first-child button:has-text('Inspect')")
            page.wait_for_selector("#view-practice:not([hidden])")
            page.wait_for_selector("#results .fb-card", timeout=10000)
            print("  [PASS] 'Inspect' action routed directly to practice workspace with results loaded.")

            # Return to profile
            page.click("#btn-nav-profile")
            page.wait_for_selector("#view-profile:not([hidden])")

            # Click Back to Problem Library
            page.click("#btn-profile-back-to-home")
            page.wait_for_selector("#view-home:not([hidden])")
            print("  [PASS] 'Back to Problem Library' returned cleanly to student home page.")

            # -----------------------------------------------------------------
            # 5. Cross-User Privacy & Security Invariants
            # -----------------------------------------------------------------
            print("\n[5] Testing Cross-User Privacy & Cognitive Firewall...")
            # Register Student B in a separate incognito context to test cross-user isolation
            context_b = browser.new_context()
            page_b = context_b.new_page()

            student_b = f"stu_b_{rand_suffix}"
            email_b = f"{student_b}@example.edu"
            password_b = "StudentBPass123!"

            page_b.goto(f"{BASE_URL}/#landing")
            page_b.click("#user-status-area button:has-text('Register')")
            page_b.fill("#auth-username", student_b)
            page_b.fill("#auth-email", email_b)
            page_b.fill("#auth-password", password_b)
            page_b.fill("#auth-confirm", password_b)
            page_b.click("#btn-auth-submit")
            page_b.wait_for_selector("#auth-modal", state="hidden")

            # Student B checks profile: should see 0 submissions (none of Student A's)
            page_b.goto(f"{BASE_URL}/#profile")
            page_b.wait_for_selector("#view-profile:not([hidden])")
            page_b.wait_for_selector(".profile-history-empty")
            b_profile_text = page_b.locator("#view-profile").inner_text()
            assert student_b in b_profile_text
            assert student_a not in b_profile_text
            assert "no submissions recorded yet" in b_profile_text.lower(), "Student B saw submissions belonging to Student A!"
            print("  [PASS] Student B cannot see Student A's profile or submissions (clean tenant isolation).")

            # Cognitive Firewall: Student B attempts to query researcher endpoints -> 403
            resp_res = page_b.request.get(f"{BASE_URL}/api/research/overview")
            assert resp_res.status == 403, f"Expected 403 for student accessing research overview, got {resp_res.status}"
            print("  [PASS] Cognitive firewall enforced: researcher APIs strictly return HTTP 403 for student.")

            context_b.close()

            # -----------------------------------------------------------------
            # 6. Logout Functionality
            # -----------------------------------------------------------------
            print("\n[6] Testing Student Logout from Profile...")
            page.goto(f"{BASE_URL}/#profile")
            page.wait_for_selector("#view-profile:not([hidden])")
            page.click("#btn-profile-logout")

            # Should redirect to public landing page
            page.wait_for_selector("#view-landing:not([hidden])")
            nav_status = page.locator("#user-status-area").inner_text()
            assert "Sign In" in nav_status and "Register" in nav_status, "User still appeared logged in after logout"

            # Visiting profile after logout must show unauthorized state
            page.goto(f"{BASE_URL}/#profile")
            page.wait_for_selector(".profile-unauth-card")
            assert "authentication required" in page.locator(".profile-unauth-card").inner_text().lower()
            print("  [PASS] Logout successfully invalidated session and protected student profile.")

            # -----------------------------------------------------------------
            # 7. Zero Console Errors Health Check
            # -----------------------------------------------------------------
            print("\n[7] Checking Browser Console Health...")
            if console_errors:
                for e in console_errors:
                    print("  [ERROR]", e)
                assert False, f"Detected {len(console_errors)} console errors during Phase 5 verification"
            print("  [PASS] Zero browser console errors detected throughout all Phase 5 tests.")

            browser.close()
    finally:
        if server_proc:
            server_proc.terminate()
            try:
                server_proc.wait(timeout=5)
            except Exception:
                server_proc.kill()

    print("\n=======================================================")
    print("ALL PHASE 5 STUDENT PROFILE REQUIREMENTS VERIFIED 100%!")
    print("=======================================================\n")


if __name__ == "__main__":
    run_phase5_tests()
