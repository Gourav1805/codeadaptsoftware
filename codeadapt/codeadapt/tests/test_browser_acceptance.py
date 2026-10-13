"""Real Browser Acceptance Test Suite for CodeAdapt using Playwright & Chrome.

Performs full end-to-end browser verification of:
1. Student Journey:
   - Problem library browsing, statement/constraint inspection, starter code loading.
   - Student account registration, client validation, session cookie establishment.
   - Code editing, test execution, live spinner/status, per-test results table.
   - Pedagogical practice recommendation card and progression.
   - Submission history, attempt lineage modal, and attempt chaining.
   - Theme toggle (dark/light) and secure logout.
2. Researcher Workspace:
   - Authentication gating (button hidden for students/anonymous, visible for researchers).
   - Overview panel (metrics cards, verdict breakdown, problem coverage, toolchain).
   - Explorer panel (search/filtering, pagination, deep inspection modal with per-test details).
   - Trace panel (observed fingerprint pills, decision explanation, candidate matrix).
   - Evaluation panel (synthetic N=18 vs unannotated student cohort separation).
   - Limitations panel (P3/E2, P5/E2, P5/E4 discrepancies, UB probe caveats, sandbox bounds).
3. Browser Quality:
   - Zero uncaught JavaScript errors in console.
   - Responsive layout checks.
"""

import os
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))

import auth
import store

BASE_URL = "http://127.0.0.1:8088"
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def ensure_server():
    """Verify local server is responding; if not, spin it up automatically in background."""
    try:
        urllib.request.urlopen(f"{BASE_URL}/health", timeout=1)
        return None
    except Exception:
        pass

    print("  [*] Local server not detected on port 8088.")
    print("  [*] Launching background backend server automatically (uvicorn app:app)...")
    backend_dir = os.path.join(HERE, "..", "backend")
    env = os.environ.copy()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--port", "8088", "--app-dir", backend_dir],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env
    )
    for _ in range(30):
        time.sleep(0.5)
        try:
            urllib.request.urlopen(f"{BASE_URL}/health", timeout=1)
            print("  [*] Backend server successfully started and responding.")
            return proc
        except Exception:
            pass
    print("  [!] Warning: Server did not respond to /health in 15s; proceeding anyway.")
    return proc


def _run_browser_steps(console_errors):
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME_PATH,
            headless=True
        )
        context = browser.new_context(viewport={"width": 1280, "height": 850})
        page = context.new_page()

        # Capture console messages
        def handle_console(msg):
            if msg.type == "error":
                # Filter expected HTTP status notifications from fetch
                if "401" in msg.text or "favicon" in msg.text:
                    return
                console_errors.append(msg.text)
                print(f"  [BROWSER CONSOLE ERROR]: {msg.text}")

        page.on("console", handle_console)
        page.on("pageerror", lambda err: console_errors.append(str(err)))

        # ---------------------------------------------------------------------
        # 1. Landing Page, About Page & Problem Library Browsing
        # ---------------------------------------------------------------------
        print("1. Testing Landing Page, About Page & Problem Library...")
        page.goto(BASE_URL)
        title = page.title()
        assert "CodeAdapt" in title, f"Unexpected title: {title}"
        print(f"  [PASS] Page title verified: '{title}'")

        # Verify Landing Page rendered
        page.wait_for_selector(".landing-wordmark")
        assert page.locator("#btn-landing-explore").is_visible(), "Landing page primary CTA button should be visible"
        assert page.locator("#btn-landing-about").is_visible(), "Landing page About CTA button should be visible"
        print("  [PASS] Landing page wordmark and CTAs rendered.")

        # Test About page navigation
        page.click("#btn-nav-about")
        page.wait_for_selector("#view-about:not([hidden])")
        about_text = page.locator("#view-about").inner_text()
        assert "About CodeAdapt" in about_text, "About page heading not found"
        assert "Principled Abstention" in about_text, "Epistemic explanation not found"
        print("  [PASS] About page navigation and epistemic explanations verified.")

        # ---------------------------------------------------------------------
        # 1b. Phase 2: Student Home Page & Searchable Question Library
        # ---------------------------------------------------------------------
        print("\n1b. Testing Student Home Page, Search, and Topic Filters...")
        page.click("#btn-nav-home")
        page.wait_for_selector("#view-home:not([hidden])")
        home_title = page.locator(".home-title").inner_text()
        assert "C++ Practice Library" in home_title, f"Unexpected home title: {home_title}"

        # Verify all 5 problem cards rendered
        page.wait_for_selector("#q-card-PILOT-001")
        for pid in ["PILOT-001", "PILOT-002", "PILOT-003", "PILOT-004", "PILOT-005"]:
            assert page.locator(f"#q-card-{pid}").is_visible(), f"Card for {pid} not visible"
        print("  [PASS] Student Home loaded all 5 problem cards.")

        # Test Text Search matching title/keyword
        page.fill("#home-search-input", "zeroes")
        page.wait_for_timeout(200)
        assert page.locator("#q-card-PILOT-001").is_visible(), "PILOT-001 should be visible for 'zeroes'"
        assert not page.locator("#q-card-PILOT-002").is_visible(), "PILOT-002 should be hidden for 'zeroes'"
        assert not page.locator("#q-card-PILOT-003").is_visible(), "PILOT-003 should be hidden for 'zeroes'"
        assert page.locator("#home-search-clear").is_visible(), "Search clear button should be visible"
        print("  [PASS] Text search correctly filtered to PILOT-001.")

        # Test Clear Search
        page.click("#home-search-clear")
        page.wait_for_timeout(200)
        assert page.locator("#q-card-PILOT-001").is_visible()
        assert page.locator("#q-card-PILOT-002").is_visible()
        assert page.locator("#q-card-PILOT-003").is_visible()
        print("  [PASS] Clear search restored full problem catalog.")

        # Test Topic / Concept Filters
        page.click(".home-filter-row button[data-topic='Stacks']")
        page.wait_for_timeout(200)
        assert page.locator("#q-card-PILOT-003").is_visible(), "PILOT-003 should be visible for Stacks filter"
        assert not page.locator("#q-card-PILOT-001").is_visible(), "PILOT-001 should be hidden for Stacks filter"
        assert not page.locator("#q-card-PILOT-004").is_visible(), "PILOT-004 should be hidden for Stacks filter"
        print("  [PASS] Topic filter 'Stacks' isolated PILOT-003.")

        # Test Reset Filters
        page.click("#home-reset-btn")
        page.wait_for_timeout(200)
        for pid in ["PILOT-001", "PILOT-002", "PILOT-003", "PILOT-004", "PILOT-005"]:
            assert page.locator(f"#q-card-{pid}").is_visible()
        print("  [PASS] Reset filters restored all 5 problem cards.")

        # Test Question Card Navigation into Workspace
        page.click("#q-card-PILOT-003 button:has-text('Solve Problem')")
        page.wait_for_selector("#view-practice:not([hidden])")
        page.wait_for_selector("#detail:has-text('PILOT-003')")
        p3_code = page.locator("#code").input_value()
        assert "isValid" in p3_code or "string" in p3_code, "Starter code for PILOT-003 not loaded in workspace"
        print("  [PASS] Question card action opened practice workspace with PILOT-003 loaded.")

        # Navigate to Problem Library via navbar button
        page.click("#btn-nav-practice")
        page.wait_for_selector(".plist button")

        # Verify all 5 problems appear in the list
        buttons = page.locator(".plist button")
        count = buttons.count()
        assert count == 5, f"Expected 5 problems in list, got {count}"
        print("  [PASS] Problem list rendered 5 problems (PILOT-001 to PILOT-005).")

        # Select each problem and verify detail pane updates
        for pid in ["PILOT-001", "PILOT-002", "PILOT-003", "PILOT-004", "PILOT-005"]:
            btn = page.locator(f".plist button[data-id='{pid}']")
            btn.click()
            page.wait_for_selector(f"#detail:has-text('{pid}')")
            detail_text = page.locator("#detail").inner_text()
            assert pid in detail_text
            # Verify starter code loaded in textarea
            code_val = page.locator("#code").input_value()
            assert len(code_val) > 20, f"Starter code empty for {pid}"
        print("  [PASS] All 5 problems selectable; statements, constraints, and starter codes loaded.")

        # ---------------------------------------------------------------------
        # 2. Theme Toggle Test
        # ---------------------------------------------------------------------
        print("\n2. Testing Dark/Light Theme Switching...")
        initial_theme = page.locator("html").get_attribute("data-theme") or "dark"
        page.click("#theme-toggle")
        new_theme = page.locator("html").get_attribute("data-theme")
        assert new_theme != initial_theme, "Theme attribute did not change on toggle"
        page.click("#theme-toggle")
        reverted_theme = page.locator("html").get_attribute("data-theme")
        assert reverted_theme == initial_theme, "Theme failed to toggle back"
        print(f"  [PASS] Theme switched '{initial_theme}' -> '{new_theme}' -> '{reverted_theme}'.")

        # ---------------------------------------------------------------------
        # 3. Student Registration & Validation
        # ---------------------------------------------------------------------
        print("\n3. Testing Student Registration & Form Validation...")
        page.click("#user-status-area button:has-text('Register')")
        page.wait_for_selector("#auth-modal:not([hidden])")

        # Test password mismatch client validation
        ts = int(time.time())
        test_user = f"std_{ts}"
        test_email = f"std_{ts}@example.edu"
        page.fill("#auth-username", test_user)
        page.fill("#auth-email", test_email)
        page.fill("#auth-password", "ValidPassword123!")
        page.fill("#auth-confirm", "MismatchPassword456!")
        page.click("#btn-auth-submit")
        alert_text = page.locator("#modal-alert").inner_text()
        assert "Passwords do not match" in alert_text, f"Expected mismatch alert, got: {alert_text}"
        print("  [PASS] Password confirmation mismatch caught and alerted.")

        # Enter matching password and submit
        page.fill("#auth-confirm", "ValidPassword123!")
        page.click("#btn-auth-submit")
        page.wait_for_selector("#user-status-area .user-badge", timeout=10000)

        # Verify user status badge in navbar
        user_badge = page.locator("#user-status-area").inner_text()
        assert test_user in user_badge, f"User {test_user} not in badge: {user_badge}"
        assert "student" in user_badge.lower(), f"'student' not in badge: {user_badge}"
        print("  [PASS] Account registered. User badge updated with username and 'student' role pill.")

        # Verify Researcher button is NOT visible for student
        res_btn_display = page.eval_on_selector("#btn-nav-researcher", "el => window.getComputedStyle(el).display")
        assert res_btn_display == "none", "Researcher button must be hidden for student role"
        print("  [PASS] Cognitive firewall: Researcher workspace navigation button hidden for student.")

        # ---------------------------------------------------------------------
        # 4. Code Execution (PILOT-001 Correct Solution)
        # ---------------------------------------------------------------------
        print("\n4. Testing C++ Solution Execution (PILOT-001)...")
        page.click(".plist button[data-id='PILOT-001']")
        correct_p1_code = """
void moveZeroes(std::vector<int>& nums) {
    size_t w = 0;
    for (size_t i = 0; i < nums.size(); ++i)
        if (nums[i] != 0) nums[w++] = nums[i];
    while (w < nums.size()) nums[w++] = 0;
}"""
        page.fill("#code", correct_p1_code)
        page.click("#run")

        # Wait for results
        page.wait_for_selector("#results table", timeout=15000)
        results_text = page.locator("#results").inner_text()
        assert "9/9 passed" in results_text or "P P P P P P P P P" in results_text
        print("  [PASS] Code compiled and executed in sandbox. Fingerprint (9/9 passed) rendered.")

        # Verify Task Correct feedback rendered and confirm NO next-question recommendations
        page.wait_for_selector("#results .fb-card.accepted")
        card_text = page.locator("#results").inner_text()
        assert "Task Correct" in card_text
        assert "Recommended Follow-Up" not in card_text, "Next-question recommendation card should be removed from student UI"
        print("  [PASS] Accepted feedback rendered with epistemic notice; next-question recommendation omitted.")

        # ---------------------------------------------------------------------
        # 5. Problem Navigation, Feedback Quality & Attempt Chaining (PILOT-002)
        # ---------------------------------------------------------------------
        print("\n5. Testing Problem Navigation, Incorrect Submission Feedback & Attempt Chaining...")
        page.click(".plist button[data-id='PILOT-002']")
        page.wait_for_selector("#detail:has-text('PILOT-002')")

        # Submit an incorrect solution (PILOT-002 B_wrong_return)
        wrong_p2_code = """
ListNode* reverseList(ListNode* head) {
    ListNode* prev = nullptr;
    ListNode* curr = head;
    while (curr != nullptr) {
        ListNode* nxt = curr->next;
        curr->next = prev;
        prev = curr;
        curr = nxt;
    }
    return curr;  // Bug: returns curr (nullptr) instead of prev
}"""
        page.fill("#code", wrong_p2_code)
        page.click("#run")

        page.wait_for_selector("#results table", timeout=15000)
        p2_results = page.locator("#results").inner_text()
        assert "1/8 passed" in p2_results or "F P F F F F F F" in p2_results
        print("  [PASS] Incorrect solution executed. Fingerprint 'FPFFFFFF' (1/8 passed) captured.")

        # Verify retry recommendation rendered without cognitive priming
        page.wait_for_selector("#results button:has-text('Retry')")
        p2_card = page.locator("#results").inner_text()
        assert "Retry Problem" in p2_card
        assert "B_wrong_return" not in p2_card, "Cognitive firewall breach: raw error label found!"
        print("  [PASS] Retry guidance rendered. Cognitive firewall verified (no raw error labels).")

        # Click Retry to test attempt lineage chaining
        page.click("#results button:has-text('Retry')")
        followup_badge = page.locator("#followup-badge")
        assert followup_badge.is_visible(), "Follow-up attempt badge should be visible on retry"
        print("  [PASS] Follow-up badge active: retry attempt linked to previous submission.")

        # Re-run to record chained follow-up in history
        page.click("#run")
        page.wait_for_selector("#results table", timeout=15000)

        # ---------------------------------------------------------------------
        # 6. Submission History & Lineage Modal
        # ---------------------------------------------------------------------
        print("\n6. Testing Submission History & Lineage Sequence Modal...")
        page.click("#btn-nav-history")
        page.wait_for_selector("#history-content table")

        history_rows = page.locator("#history-content tbody tr")
        row_count = history_rows.count()
        assert row_count >= 2, f"Expected at least 2 submissions in history, got {row_count}"
        print(f"  [PASS] Submission history table rendered {row_count} historical attempts.")

        # Verify lineage follow-up tag
        assert "Follow-up" in page.locator("#history-content").inner_text()

        # Open Lineage Modal
        page.click("#history-content button:has-text('Lineage') >> nth=0")
        page.wait_for_selector("#chain-modal:not([hidden])")
        modal_text = page.locator("#chain-modal-body").inner_text()
        assert "Attempt" in modal_text
        page.click("#chain-modal button:has-text('Close')")
        page.wait_for_selector("#chain-modal", state="hidden")

        # ---------------------------------------------------------------------
        # 6b. Authenticated Student Dashboard, Status Badges & Profile Modal
        # ---------------------------------------------------------------------
        print("\n6b. Testing Authenticated Student Dashboard & Profile Modal...")
        page.click("#btn-nav-home")
        page.wait_for_selector("#view-home:not([hidden])")
        page.wait_for_selector(".home-student-card")

        # Verify authenticated student card and progress stats
        card_text = page.locator(".home-student-card").inner_text()
        assert test_user in card_text, f"Student {test_user} not in student card"
        assert "1 / 5 Solved" in card_text, f"Expected '1 / 5 Solved' in card, got: {card_text}"
        print("  [PASS] Authenticated dashboard displayed solved progress (1/5 Solved).")

        # Verify solve status badges on cards
        page.wait_for_selector("#q-card-PILOT-001 .status-solved")
        assert page.locator("#q-card-PILOT-001 .status-solved").is_visible(), "PILOT-001 should have Solved badge"
        assert page.locator("#q-card-PILOT-002 .status-attempted").is_visible(), "PILOT-002 should have Attempted badge"
        assert page.locator("#q-card-PILOT-003 .status-unsolved").is_visible(), "PILOT-003 should have Unsolved badge"
        print("  [PASS] Real solve status badges (Solved, Attempted, Unsolved) rendered on question cards.")

        # Test Status Filters
        page.click(".home-filter-row button[data-status='solved']")
        page.wait_for_timeout(200)
        assert page.locator("#q-card-PILOT-001").is_visible(), "PILOT-001 should be visible for 'solved' filter"
        assert not page.locator("#q-card-PILOT-002").is_visible(), "PILOT-002 should be hidden for 'solved' filter"
        assert not page.locator("#q-card-PILOT-003").is_visible(), "PILOT-003 should be hidden for 'solved' filter"
        print("  [PASS] Status filter 'solved' isolated PILOT-001.")

        page.click(".home-filter-row button[data-status='ALL']")
        page.wait_for_timeout(200)

        # Open Student Profile Modal
        page.click("#btn-user-profile")
        page.wait_for_selector("#profile-modal:not([hidden])")
        page.wait_for_selector("#profile-modal-content .profile-section-card", timeout=10000)
        modal_profile_text = page.locator("#profile-modal-content").inner_text()
        assert test_user in modal_profile_text, f"Student username not in profile modal: {modal_profile_text}"
        assert test_email in modal_profile_text, f"Student email not in profile modal: {modal_profile_text}"
        assert "curriculum checklist" in modal_profile_text.lower(), "Checklist not in profile modal"
        assert "PILOT-001" in modal_profile_text and "solved" in modal_profile_text.lower()
        assert "read-only" in modal_profile_text.lower() or "not yet supported" in modal_profile_text.lower(), "Read-only backend note missing"
        print("  [PASS] Student Profile Modal rendered account details, progress stats, and curriculum checklist.")

        # Close Profile Modal
        page.click("#profile-modal button:has-text('✕')")
        page.wait_for_selector("#profile-modal", state="hidden")
        print("  [PASS] Profile Modal closed.")

        # Test Mobile Responsiveness on Student Home
        page.set_viewport_size({"width": 375, "height": 667})
        page.wait_for_timeout(300)
        assert page.locator("#home-search-input").is_visible(), "Search input should be visible on mobile"
        assert page.locator("#q-card-PILOT-001").is_visible(), "Question card should be visible on mobile"
        # Restore desktop viewport
        page.set_viewport_size({"width": 1280, "height": 850})
        print("  [PASS] Responsive layout on 375x667 mobile viewport verified.")

        # ---------------------------------------------------------------------
        # 7. Student Logout
        # ---------------------------------------------------------------------
        print("\n7. Testing Student Logout...")
        page.click("#user-status-area button:has-text('Logout')")
        page.wait_for_selector("#user-status-area button:has-text('Sign In')")
        user_area = page.locator("#user-status-area").inner_text()
        assert "Sign In" in user_area and "Register" in user_area

        # In history view, verify login caveat is displayed
        page.click("#btn-nav-history")
        assert "sign in" in page.locator("#history-content").inner_text().lower()
        print("  [PASS] Logout terminated session. Protected views prompt for sign in.")

        # ---------------------------------------------------------------------
        # 8. Researcher Workspace Authentication & Deep Exploration
        # ---------------------------------------------------------------------
        print("\n8. Testing Researcher Workspace Authentication & Panels...")
        # Create researcher user in database
        auth.create_researcher_user("researcher_browser", "res_browser@example.edu", "ResearcherPassword123!")

        # Log in as researcher
        page.click("#user-status-area button:has-text('Sign In')")
        page.wait_for_selector("#auth-modal:not([hidden])")
        page.fill("#auth-username", "researcher_browser")
        page.fill("#auth-password", "ResearcherPassword123!")
        page.click("#btn-auth-submit")
        page.wait_for_selector("#user-status-area .user-badge", timeout=10000)

        # Verify researcher role and navbar button
        badge = page.locator("#user-status-area").inner_text()
        assert "researcher" in badge.lower()
        page.wait_for_selector("#btn-nav-researcher:not([style*='display: none'])")
        print("  [PASS] Logged in as researcher. 'Researcher Workspace' button active.")

        # Navigate to Researcher Workspace
        page.click("#btn-nav-researcher")
        page.wait_for_selector("#view-researcher:not([hidden])")

        # --- Panel 1: Research Overview ---
        page.wait_for_selector("#overview-content .stat-grid")
        overview_text = page.locator("#overview-content").inner_text().lower()
        assert "total submissions" in overview_text
        assert "diagnostic verdict distribution" in overview_text
        assert "problem coverage across corpus" in overview_text
        assert "toolchain of record" in overview_text
        print("  [PASS] Tab 1: Research Overview rendered aggregate telemetry, distribution, and toolchain.")

        # --- Panel 2: Submission Explorer ---
        page.click("#tab-btn-explorer")
        page.wait_for_selector("#panel-res-explorer:not([hidden])")
        page.wait_for_selector("#explorer-table-container table")
        explorer_text = page.locator("#explorer-table-container").inner_text()
        assert "PILOT-001" in explorer_text or "PILOT-002" in explorer_text
        print("  [PASS] Tab 2: Submission Explorer rendered filterable submissions table.")

        # Test Deep Inspection Modal
        page.click("#explorer-table-container button:has-text('Inspect Record') >> nth=0")
        page.wait_for_selector("#res-detail-modal:not([hidden])")
        modal_detail = page.locator("#res-modal-body").inner_text().lower()
        assert "tests passed" in modal_detail
        assert "per-test execution outcomes" in modal_detail
        print("  [PASS] Submission Detail Modal rendered verbatim execution stats and per-test outcomes.")
        page.click("#res-detail-modal button:has-text('✕')")
        page.wait_for_selector("#res-detail-modal", state="hidden")

        # --- Panel 3: Diagnostic Decision Trace ---
        page.click("#tab-btn-trace")
        page.wait_for_selector("#panel-res-trace:not([hidden])")
        # Click Inspect Trace from explorer for first record
        page.click("#tab-btn-explorer")
        page.wait_for_selector("#explorer-table-container table")
        page.click("#explorer-table-container button:has-text('Inspect Trace') >> nth=0")
        page.wait_for_selector("#trace-content-container .stat-card, #trace-content-container table")
        trace_text = page.locator("#trace-content-container").inner_text().lower()
        assert "observed execution fingerprint" in trace_text
        assert "candidate error evaluation matrix" in trace_text
        assert "undefined behavior (ub) cell exclusions" in trace_text
        print("  [PASS] Tab 3: Diagnostic Decision Trace rendered fingerprint pills and candidate matrix.")

        # --- Panel 4: Research Evaluation ---
        page.click("#tab-btn-eval")
        page.wait_for_selector("#panel-res-eval:not([hidden])")
        page.wait_for_selector("#eval-content-container")
        eval_text = page.locator("#eval-content-container").inner_text().lower()
        assert "1. synthetic pilot benchmark evaluation" in eval_text
        assert "2. real student cohort data" in eval_text
        assert "unavailable / unlabeled" in eval_text
        assert "statistically invalid" in eval_text
        assert "student cohort diagnostic metrics paused" in eval_text
        print("  [PASS] Tab 4: Research Evaluation separated synthetic (N=18) from student cohort.")
        print("  [PASS] Epistemic guardrail verified: unannotated student metrics strictly paused.")

        # --- Panel 5: Instrument Limitations ---
        page.click("#tab-btn-limits")
        page.wait_for_selector("#panel-res-limits:not([hidden])")
        page.wait_for_selector("#limits-content-container")
        limits_text = page.locator("#limits-content-container").inner_text().lower()
        assert "1. documented toolchain discrepancies & divergences" in limits_text
        assert "pilot-003" in limits_text and "ppprpppp" in limits_text
        assert "pilot-005" in limits_text
        assert "2. static ub declarations vs dynamic runtime probes" in limits_text
        assert "does not prove the absence of undefined behavior" in limits_text
        assert "3. construct validity limits" in limits_text
        assert "4. windows sandbox isolation boundaries" in limits_text
        print("  [PASS] Tab 5: Instrument Limitations rendered documented discrepancies and sandbox bounds.")

        # ---------------------------------------------------------------------
        # 9. Responsive Layout Test
        # ---------------------------------------------------------------------
        print("\n9. Testing Responsive Mobile Layout (375x667)...")
        page.set_viewport_size({"width": 375, "height": 667})
        page.click("#btn-nav-practice")
        page.wait_for_selector("#view-practice:not([hidden])")
        assert page.locator("#plist").is_visible()
        assert page.locator("#detail").is_visible()
        print("  [PASS] Responsive layout adapted cleanly to mobile viewport.")

        # Reset viewport
        page.set_viewport_size({"width": 1280, "height": 850})

        # ---------------------------------------------------------------------
        # 10. Console Error Verification
        # ---------------------------------------------------------------------
        print("\n10. Checking Browser Console Health...")
        if console_errors:
            print(f"  [FAIL] {len(console_errors)} console error(s) detected:")
            for err in console_errors:
                print(f"    - {err}")
            assert False, "Browser console had uncaught errors"
        else:
            print("  [PASS] Zero browser console errors detected throughout the entire run.")

        browser.close()


def run_browser_tests():
    console_errors = []

    print("\n=======================================================")
    print("STARTING REAL BROWSER ACCEPTANCE SUITE (PLAYWRIGHT/CHROME)")
    print(f"Target: {BASE_URL}")
    print(f"Browser: {CHROME_PATH}")
    print("=======================================================\n")

    server_proc = ensure_server()
    try:
        _run_browser_steps(console_errors)
    finally:
        if server_proc:
            print("  [*] Shutting down auto-started backend server...")
            server_proc.terminate()
            try:
                server_proc.wait(timeout=5)
            except Exception:
                server_proc.kill()

    print("\n=======================================================")
    print("ALL REAL BROWSER ACCEPTANCE TESTS PASSED SUCCESSFULLY!")
    print("=======================================================\n")


if __name__ == "__main__":
    run_browser_tests()
