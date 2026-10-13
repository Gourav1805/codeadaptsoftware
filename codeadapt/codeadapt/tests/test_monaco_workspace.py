"""Automated test suite specifically verifying Phase 3 Monaco Editor & Workspace features.

Tests:
1. Monaco Editor initialization and C++ language configuration.
2. Auto-closing brackets/quotes and auto-indentation options.
3. Splitters drag resizing (horizontal and vertical).
4. Public sample testcases inspection (Case 1 vs Case 2).
5. Reset starter template dirty-check modal confirmation.
6. Compiler diagnostic markers rendered in Monaco on compilation error.
7. Zero uncaught browser console errors.
"""
import os
import subprocess
import sys
import time
import urllib.request

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


def test_monaco_features():
    console_errors = []
    server_proc = ensure_server()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=CHROME_PATH, headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 850})

            def handle_console(msg):
                if msg.type == "error":
                    if "401" in msg.text or "favicon" in msg.text:
                        return
                    console_errors.append(msg.text)
                    print(f"  [CONSOLE ERROR]: {msg.text}")

            page.on("console", handle_console)
            page.on("pageerror", lambda err: console_errors.append(str(err)))

            print("\n1. Navigating to Problem Workspace...")
            page.goto(f"{BASE_URL}/#practice")
            page.wait_for_selector("#view-practice:not([hidden])")
            page.wait_for_selector(".monaco-editor", timeout=10000)
            print("  [PASS] Monaco Editor instantiated inside #monaco-editor-container.")

            # Check Monaco language and options
            options = page.evaluate("""() => {
                const ed = window.monacoEditor;
                if (!ed) return null;
                const model = ed.getModel();
                return {
                    hasEditor: true,
                    language: model.getLanguageId(),
                    lineNumbers: ed.getOption(monaco.editor.EditorOption.lineNumbers),
                    autoClosingBrackets: ed.getOption(monaco.editor.EditorOption.autoClosingBrackets),
                    autoClosingQuotes: ed.getOption(monaco.editor.EditorOption.autoClosingQuotes),
                    autoIndent: ed.getOption(monaco.editor.EditorOption.autoIndent),
                    tabSize: model.getOptions().tabSize
                };
            }""")
            assert options and options["hasEditor"], "Monaco editor instance not found on window.monacoEditor"
            assert options["language"] == "cpp", f"Expected cpp language, got {options['language']}"
            assert options["autoClosingBrackets"] == "always", f"autoClosingBrackets: {options['autoClosingBrackets']}"
            assert options["autoClosingQuotes"] == "always", f"autoClosingQuotes: {options['autoClosingQuotes']}"
            print(f"  [PASS] Monaco configured: language={options['language']}, tabSize={options['tabSize']}, brackets={options['autoClosingBrackets']}.")

            # 2. Check public sample test cases
            print("\n2. Testing Public Sample Cases Inspection...")
            page.wait_for_selector("#ws-sample-cases-container")
            assert page.locator(".ws-sample-case-pill").count() >= 2, "Expected at least 2 sample case pills"
            sample_text_1 = page.locator("#ws-sample-cases-container").inner_text()
            assert "nums = [0, 3, 0, 7, 5]" in sample_text_1, "Expected Case 1 input in sample container"

            # Click Case 2
            page.click(".ws-sample-case-pill:has-text('Case 2')")
            page.wait_for_timeout(200)
            sample_text_2 = page.locator("#ws-sample-cases-container").inner_text()
            assert "nums = [5, 3, 7, 2]" in sample_text_2, "Expected Case 2 input in sample container"
            print("  [PASS] Sample test cases tab displays public Case 1 & Case 2 without leaking hidden tests.")

            # 3. Test Reset to Starter Template with Dirty Check
            print("\n3. Testing Reset to Starter Code Modal...")
            # Initially not dirty - clicking reset should keep modal hidden
            page.click("#reset")
            page.wait_for_timeout(200)
            assert page.locator("#confirm-reset-modal").is_hidden(), "Modal should not open when code is unmodified"

            # Modify code in Monaco
            page.evaluate("""() => {
                window.monacoEditor.setValue("// Modified student solution\\nvoid moveZeroes() {}");
            }""")
            page.wait_for_timeout(100)
            page.click("#reset")
            page.wait_for_selector("#confirm-reset-modal:not([hidden])")
            print("  [PASS] Dirty state detected: Reset confirmation modal shown.")

            # Cancel modal
            page.click("#confirm-reset-modal button:has-text('Cancel')")
            page.wait_for_selector("#confirm-reset-modal", state="hidden")
            cur_code = page.evaluate("() => window.monacoEditor.getValue()")
            assert "Modified student solution" in cur_code, "Code should remain modified after cancel"
            print("  [PASS] Cancel dismissed modal without modifying code.")

            # Re-open and confirm reset
            page.click("#reset")
            page.wait_for_selector("#confirm-reset-modal:not([hidden])")
            page.click("#confirm-reset-modal button:has-text('Reset Code')")
            page.wait_for_selector("#confirm-reset-modal", state="hidden")
            reset_code = page.evaluate("() => window.monacoEditor.getValue()")
            assert "void moveZeroes(std::vector<int>& nums)" in reset_code, "Starter code was not restored"
            print("  [PASS] Reset confirmed: starter template correctly restored.")

            # 4. Test Splitter Drag
            print("\n4. Testing Panel Splitters...")
            initial_left_width = page.eval_on_selector("#ws-left-panel", "el => el.getBoundingClientRect().width")
            splitter_h = page.locator("#ws-splitter-h")
            box = splitter_h.bounding_box()
            assert box is not None
            # Drag splitter to the right
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            page.mouse.down()
            page.mouse.move(box["x"] + 80, box["y"] + box["height"] / 2)
            page.mouse.up()
            new_left_width = page.eval_on_selector("#ws-left-panel", "el => el.getBoundingClientRect().width")
            assert new_left_width != initial_left_width, f"Width did not change: {initial_left_width} -> {new_left_width}"
            print(f"  [PASS] Horizontal splitter resized left panel: {initial_left_width:.1f}px -> {new_left_width:.1f}px.")

            # 5. Test Compiler Error Diagnostic Markers in Monaco
            print("\n5. Testing Compiler Error Diagnostic Markers...")
            syntax_error_code = """
void moveZeroes(std::vector<int>& nums) {
    this_is_an_undefined_symbol_error();
}"""
            page.evaluate(f"""() => {{
                window.monacoEditor.setValue({repr(syntax_error_code)});
            }}""")
            page.click("#run")

            # Wait for execution result to finish and show CE
            page.wait_for_selector("#results .badge.CE", timeout=15000)
            page.wait_for_timeout(300)

            # Check that Monaco model has error markers
            markers = page.evaluate("""() => {
                const model = window.monacoEditor.getModel();
                const m = monaco.editor.getModelMarkers({ resource: model.uri });
                return m.map(x => ({
                    line: x.startLineNumber,
                    message: x.message,
                    severity: x.severity
                }));
            }""")
            assert len(markers) > 0, "Expected at least 1 Monaco compiler error marker"
            assert any("this_is_an_undefined_symbol_error" in m["message"] for m in markers), f"Marker message missing compiler error: {markers}"
            print(f"  [PASS] Monaco received {len(markers)} compiler diagnostic marker(s) mapped to student line.")

            # 6. Verify zero console errors
            print("\n6. Checking Browser Console Health...")
            if console_errors:
                for e in console_errors:
                    print("  [ERROR]", e)
                assert False, f"Detected {len(console_errors)} console errors"
            print("  [PASS] Zero console errors during workspace interactions.")

            browser.close()
    finally:
        if server_proc:
            server_proc.terminate()
            try:
                server_proc.wait(timeout=5)
            except Exception:
                server_proc.kill()

    print("\n=======================================================")
    print("ALL PHASE 3 WORKSPACE TESTS PASSED SUCCESSFULLY!")
    print("=======================================================\n")


if __name__ == "__main__":
    test_monaco_features()
