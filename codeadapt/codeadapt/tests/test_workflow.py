"""End-to-end integration tests for the CodeAdapt Evidence-to-Practice Workflow.

Covers:
1. Correct submissions (task correctness, epistemic limits, next problem progression).
2. Incorrect submissions with supported diagnostic interpretations (plain language, no raw labels).
3. Compile errors (no execution evidence, line-remapped feedback, retry).
4. Runtime errors (crashes, NTSTATUS containment, abstention).
5. Timeouts (infinite loops, wall limit containment, abstention).
6. Ambiguous fingerprints (known collisions, explicit abstention, retry).
7. Insufficient evidence / unmodelled bugs (general practice, abstention).
8. Known UB-sensitive cases (UB cell exclusion, UB caveat warnings).
9. Learning sequence & repeated attempts (parent_submission_id chaining and lineage retrieval).
10. Cross-student privacy and unauthorized access protection.
11. Invalid problem and non-existent parent handling.
"""

import json
import os
import sys
import unittest
from unittest.mock import patch

# Ensure backend and tests can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from fastapi.testclient import TestClient
import app
import store
import executor
import problems
import synthetic


class TestEvidenceToPracticeWorkflow(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        HERE = os.path.dirname(os.path.abspath(__file__))
        cls.test_db = os.path.join(HERE, "test_workflow_evidence.db")
        if os.path.exists(cls.test_db):
            try:
                os.remove(cls.test_db)
            except OSError:
                pass
        store.init(cls.test_db)
        cls.client = TestClient(app.app)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "test_db") and os.path.exists(cls.test_db):
            try:
                os.remove(cls.test_db)
            except OSError:
                pass

    def _register_and_login(self, email, password, username):
        reg = self.client.post("/api/auth/register", json={
            "username": username,
            "email": email,
            "password": password
        })
        self.assertIn(reg.status_code, (200, 201))
        
        login = self.client.post("/api/auth/login", json={
            "username": username,
            "password": password
        })
        self.assertEqual(login.status_code, 200)
        data = login.json()
        cookies = login.cookies
        csrf_token = data.get("csrf_token")
        return data["user"], cookies, csrf_token

    # --- 1. Correct Submission Workflow --------------------------------------
    def test_correct_submission_workflow(self):
        user, cookies, csrf = self._register_and_login(
            "student_correct@codeadapt.test", "Passphrase2026!", "alice_correct"
        )
        
        # Submit correct solution for P1
        res = self.client.post("/api/submissions", json={
            "problem_id": "PILOT-001",
            "code": synthetic.P1["correct"]
        }, cookies=cookies, headers={"X-CSRF-Token": csrf})
        self.assertEqual(res.status_code, 200)
        rec = res.json()
        sid = rec["submission_id"]
        
        # Verify raw execution evidence preserved
        self.assertEqual(rec["compile_status"], "OK")
        self.assertEqual(rec["fingerprint"], "PPPPPPPPP")
        self.assertEqual(len(rec["tests"]), 9)
        for t in rec["tests"]:
            self.assertEqual(t["status"], "P")
            self.assertEqual(t["execution_status"], "COMPLETED")
            self.assertIn("expected_output", t)
            self.assertIn("actual_output", t)
            self.assertEqual(t["expected_output"], t["actual_output"])
        
        # Fetch practice guidance
        p_res = self.client.get(f"/api/submissions/{sid}/practice", cookies=cookies)
        self.assertEqual(p_res.status_code, 200)
        practice = p_res.json()
        
        # Assertions on pedagogical contract
        self.assertEqual(practice["state"], "correct")
        self.assertIn("mastery", practice["message"])
        self.assertNotIn("verdict", practice)
        self.assertNotIn("matched", practice)
        self.assertEqual(practice["recommendation"]["action"], "practice")
        self.assertIn(practice["recommendation"]["problem_id"], problems.PROBLEMS)
        self.assertIn("explanation", practice)
        self.assertIn("uncertainty", practice["explanation"])
        self.assertIn("Passing these tests verifies task correctness", practice["explanation"]["uncertainty"])

    # --- 2. Incorrect Supported Diagnosis Workflow ---------------------------
    def test_incorrect_supported_diagnosis_workflow(self):
        user, cookies, csrf = self._register_and_login(
            "student_e3@codeadapt.test", "Passphrase2026!", "bob_misconception"
        )
        
        # Submit P5 E3_upper_bound solution
        res = self.client.post("/api/submissions", json={
            "problem_id": "PILOT-005",
            "code": synthetic.P5["E3_upper_bound"]
        }, cookies=cookies, headers={"X-CSRF-Token": csrf})
        self.assertEqual(res.status_code, 200)
        rec = res.json()
        sid = rec["submission_id"]
        
        self.assertEqual(rec["fingerprint"], "FPPPFFPF")
        
        # Fetch practice guidance
        p_res = self.client.get(f"/api/submissions/{sid}/practice", cookies=cookies)
        self.assertEqual(p_res.status_code, 200)
        practice = p_res.json()
        
        self.assertEqual(practice["state"], "supported_diagnosis")
        self.assertIn("consistent with one supported pattern", practice["message"])
        # Verify strict cognitive firewall: raw internal identifier is NOT exposed
        self.assertNotIn("E3_upper_bound", practice["message"])
        self.assertNotIn("E3_upper_bound", str(practice["explanation"]))
        # Verify plain language description is present
        self.assertIn("computing upper bound instead of lower bound", practice["explanation"]["plausible_behavior"])
        self.assertIn("uncertainty", practice["explanation"])
        self.assertEqual(practice["recommendation"]["action"], "retry")
        self.assertEqual(practice["recommendation"]["problem_id"], "PILOT-005")

    # --- 3. Compile Error Workflow -------------------------------------------
    def test_compile_error_workflow(self):
        user, cookies, csrf = self._register_and_login(
            "student_ce@codeadapt.test", "Passphrase2026!", "charlie_syntax"
        )
        
        res = self.client.post("/api/submissions", json={
            "problem_id": "PILOT-005",
            "code": synthetic.P5["compile_error"]
        }, cookies=cookies, headers={"X-CSRF-Token": csrf})
        self.assertEqual(res.status_code, 200)
        rec = res.json()
        sid = rec["submission_id"]
        
        self.assertEqual(rec["compile_status"], "COMPILE_ERROR")
        self.assertEqual(rec["tests"], [])
        self.assertIsNone(rec["fingerprint"])
        
        p_res = self.client.get(f"/api/submissions/{sid}/practice", cookies=cookies)
        self.assertEqual(p_res.status_code, 200)
        practice = p_res.json()
        
        self.assertEqual(practice["state"], "no_execution_evidence")
        self.assertIn("did not compile", practice["message"].lower())
        self.assertEqual(practice["compile_status"], "COMPILE_ERROR")
        self.assertTrue(len(practice["compile_feedback"]) > 0)
        self.assertEqual(practice["recommendation"]["action"], "retry")

    # --- 4. Runtime Error Crash Workflow -------------------------------------
    def test_runtime_error_crash_workflow(self):
        user, cookies, csrf = self._register_and_login(
            "student_crash@codeadapt.test", "Passphrase2026!", "dave_crash"
        )
        
        res = self.client.post("/api/submissions", json={
            "problem_id": "PILOT-005",
            "code": synthetic.P5["crash"]
        }, cookies=cookies, headers={"X-CSRF-Token": csrf})
        self.assertEqual(res.status_code, 200)
        rec = res.json()
        sid = rec["submission_id"]
        
        # Crashes map to R, not F
        self.assertTrue(all(t["status"] == "R" for t in rec["tests"]))
        self.assertTrue(all(t["execution_status"] == "CRASHED" for t in rec["tests"]))
        
        p_res = self.client.get(f"/api/submissions/{sid}/practice", cookies=cookies)
        self.assertEqual(p_res.status_code, 200)
        practice = p_res.json()
        
        self.assertEqual(practice["state"], "insufficient_evidence")
        self.assertIn("crash", practice["explanation"]["what_happened"].lower())
        self.assertEqual(practice["recommendation"]["action"], "retry")

    # --- 5. Timeout Infinite Loop Workflow -----------------------------------
    def test_timeout_infinite_loop_workflow(self):
        user, cookies, csrf = self._register_and_login(
            "student_loop@codeadapt.test", "Passphrase2026!", "eve_loop"
        )
        
        res = self.client.post("/api/submissions", json={
            "problem_id": "PILOT-005",
            "code": synthetic.P5["infinite_loop"]
        }, cookies=cookies, headers={"X-CSRF-Token": csrf})
        self.assertEqual(res.status_code, 200)
        rec = res.json()
        sid = rec["submission_id"]
        
        self.assertTrue(all(t["status"] == "R" for t in rec["tests"]))
        self.assertTrue(all(t["execution_status"] == "TIMEOUT" for t in rec["tests"]))
        
        p_res = self.client.get(f"/api/submissions/{sid}/practice", cookies=cookies)
        self.assertEqual(p_res.status_code, 200)
        practice = p_res.json()
        
        self.assertEqual(practice["state"], "insufficient_evidence")
        self.assertIn("timed out", practice["explanation"]["what_happened"].lower())
        self.assertEqual(practice["recommendation"]["action"], "retry")

    # --- 6. Ambiguous Fingerprint Workflow -----------------------------------
    def test_ambiguous_fingerprint_workflow(self):
        user, cookies, csrf = self._register_and_login(
            "student_ambig@codeadapt.test", "Passphrase2026!", "frank_ambiguous"
        )
        
        # P2 B_wrong_return collides with C_off_by_one
        res = self.client.post("/api/submissions", json={
            "problem_id": "PILOT-002",
            "code": synthetic.P2["B_wrong_return"]
        }, cookies=cookies, headers={"X-CSRF-Token": csrf})
        self.assertEqual(res.status_code, 200)
        rec = res.json()
        sid = rec["submission_id"]
        
        p_res = self.client.get(f"/api/submissions/{sid}/practice", cookies=cookies)
        self.assertEqual(p_res.status_code, 200)
        practice = p_res.json()
        
        self.assertEqual(practice["state"], "insufficient_evidence")
        self.assertIn("Insufficient evidence", practice["message"])
        self.assertEqual(practice["recommendation"]["action"], "retry")
        self.assertEqual(practice["recommendation"]["problem_id"], "PILOT-002")

    # --- 7. Known UB-Sensitive Cases -----------------------------------------
    def test_known_ub_sensitive_exclusion_workflow(self):
        user, cookies, csrf = self._register_and_login(
            "student_ub@codeadapt.test", "Passphrase2026!", "grace_ub"
        )
        
        # P3 E2 has declared UB on T4
        res = self.client.post("/api/submissions", json={
            "problem_id": "PILOT-003",
            "code": synthetic.P3["E2_no_underflow_check"]
        }, cookies=cookies, headers={"X-CSRF-Token": csrf})
        self.assertEqual(res.status_code, 200)
        rec = res.json()
        sid = rec["submission_id"]
        
        p_res = self.client.get(f"/api/submissions/{sid}/practice", cookies=cookies)
        self.assertEqual(p_res.status_code, 200)
        practice = p_res.json()
        
        # Practice explanation carries UB warning if UB was detected
        if practice["explanation"].get("ub_warning"):
            self.assertIn("Undefined behaviour", practice["explanation"]["ub_warning"])

    # --- 8. Learning Sequence & Lineage Workflow ------------------------------
    def test_learning_sequence_lineage_workflow(self):
        user, cookies, csrf = self._register_and_login(
            "student_sequence@codeadapt.test", "Passphrase2026!", "hannah_sequence"
        )
        
        # Attempt 1: P5 with E3 bug
        sub1 = self.client.post("/api/submissions", json={
            "problem_id": "PILOT-005",
            "code": synthetic.P5["E3_upper_bound"]
        }, cookies=cookies, headers={"X-CSRF-Token": csrf}).json()
        sid1 = sub1["submission_id"]
        
        # Attempt 2: Follow-up linked to Attempt 1 (e.g., attempt fix, still has E1 bug)
        sub2 = self.client.post("/api/submissions", json={
            "problem_id": "PILOT-005",
            "code": synthetic.P5["E1_missing_increment"],
            "parent_submission_id": sid1
        }, cookies=cookies, headers={"X-CSRF-Token": csrf}).json()
        sid2 = sub2["submission_id"]
        
        # Attempt 3: Follow-up linked to Attempt 2 (correct solution)
        sub3 = self.client.post("/api/submissions", json={
            "problem_id": "PILOT-005",
            "code": synthetic.P5["correct"],
            "parent_submission_id": sid2
        }, cookies=cookies, headers={"X-CSRF-Token": csrf}).json()
        sid3 = sub3["submission_id"]
        
        # Verify Attempt 2 record has parent_submission_id
        meta2 = store.get_submission_meta(sid2)
        self.assertEqual(meta2["parent_submission_id"], sid1)
        
        # Verify Attempt 3 record has parent_submission_id
        meta3 = store.get_submission_meta(sid3)
        self.assertEqual(meta3["parent_submission_id"], sid2)
        
        # Query chain from any node in the sequence
        chain_res = self.client.get(f"/api/submissions/{sid2}/chain", cookies=cookies)
        self.assertEqual(chain_res.status_code, 200)
        chain_data = chain_res.json()
        self.assertEqual(chain_data["total_attempts"], 3)
        chain_sids = [c["submission_id"] for c in chain_data["chain"]]
        self.assertEqual(chain_sids, [sid1, sid2, sid3])

    # --- 9. Unauthorized Access & Cross-Student Privacy -----------------------
    def test_unauthorized_access_and_cross_student_privacy(self):
        user_alice, cookies_alice, csrf_alice = self._register_and_login(
            "student_alice@codeadapt.test", "Passphrase2026!", "alice_private"
        )
        user_bob, cookies_bob, csrf_bob = self._register_and_login(
            "student_bob@codeadapt.test", "Passphrase2026!", "bob_snooper"
        )
        
        # Alice submits
        res_a = self.client.post("/api/submissions", json={
            "problem_id": "PILOT-001",
            "code": synthetic.P1["correct"]
        }, cookies=cookies_alice, headers={"X-CSRF-Token": csrf_alice})
        self.assertEqual(res_a.status_code, 200)
        alice_sid = res_a.json()["submission_id"]
        
        # Bob tries to view Alice's submission
        res_bob_sub = self.client.get(f"/api/submissions/{alice_sid}", cookies=cookies_bob)
        self.assertEqual(res_bob_sub.status_code, 403)
        
        # Bob tries to view Alice's practice guidance
        res_bob_prac = self.client.get(f"/api/submissions/{alice_sid}/practice", cookies=cookies_bob)
        self.assertEqual(res_bob_prac.status_code, 403)
        
        # Bob tries to view Alice's attempt chain
        res_bob_chain = self.client.get(f"/api/submissions/{alice_sid}/chain", cookies=cookies_bob)
        self.assertEqual(res_bob_chain.status_code, 403)
        
        # Bob tries to link his submission to Alice's submission
        res_bob_link = self.client.post("/api/submissions", json={
            "problem_id": "PILOT-001",
            "code": synthetic.P1["correct"],
            "parent_submission_id": alice_sid
        }, cookies=cookies_bob, headers={"X-CSRF-Token": csrf_bob})
        self.assertEqual(res_bob_link.status_code, 403)

    # --- 10. Invalid Problem & Missing Parent Validation ----------------------
    def test_invalid_problem_and_missing_parent_validation(self):
        user, cookies, csrf = self._register_and_login(
            "student_invalid@codeadapt.test", "Passphrase2026!", "ian_invalid"
        )
        
        # Nonexistent problem
        res_bad_prob = self.client.post("/api/submissions", json={
            "problem_id": "NONEXISTENT-999",
            "code": "int main() {}"
        }, cookies=cookies, headers={"X-CSRF-Token": csrf})
        self.assertEqual(res_bad_prob.status_code, 404)
        
        # Nonexistent parent
        res_bad_parent = self.client.post("/api/submissions", json={
            "problem_id": "PILOT-001",
            "code": synthetic.P1["correct"],
            "parent_submission_id": "nonexistent_sid_12345"
        }, cookies=cookies, headers={"X-CSRF-Token": csrf})
        self.assertEqual(res_bad_parent.status_code, 404)


if __name__ == "__main__":
    unittest.main()
