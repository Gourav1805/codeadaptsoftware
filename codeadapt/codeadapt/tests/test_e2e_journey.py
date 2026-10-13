"""Comprehensive End-to-End Integration & Quality-Assurance Test Suite for CodeAdapt.

Tests:
1. Complete student journey (register, login, session restore, browse, correct solution,
   incorrect solution, practice recommendation, follow-up attempt, attempt chaining,
   history verification, logout).
2. Authorization and security invariants (cross-student privacy, researcher endpoint gating,
   privilege escalation prevention, session invalidation on logout).
3. Backend edge cases (invalid problem IDs, nonexistent parent IDs, unauthorized lineage
   linking, compiler error handling, empty states).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from fastapi.testclient import TestClient
import app
import auth
import store
import problems
import executor
import synthetic


class TestE2EStudentJourneyAndQA(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        HERE = os.path.dirname(os.path.abspath(__file__))
        cls.test_db = os.path.join(HERE, "test_e2e_qa_evidence.db")
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

    def setUp(self):
        self.client.cookies.clear()

    # --- 1. The Complete Student Journey ---

    def test_01_complete_student_journey(self):
        """Walk through the full student experience from registration to follow-up practice."""
        # Step 1: Register a new student
        reg_resp = self.client.post("/api/auth/register", json={
            "username": "student_maya",
            "email": "maya@university.edu",
            "password": "SecurePassword123!"
        })
        self.assertEqual(reg_resp.status_code, 201, f"Registration failed: {reg_resp.text}")
        reg_data = reg_resp.json()
        self.assertEqual(reg_data["user"]["username"], "student_maya")
        self.assertEqual(reg_data["user"]["role"], "student")
        self.assertNotIn("password", reg_data["user"])
        self.assertIn("codeadapt_session", reg_resp.cookies)

        csrf_token = reg_data["csrf_token"]

        # Step 2: Session restoration across simulated page refresh
        me_resp = self.client.get("/api/auth/me")
        self.assertEqual(me_resp.status_code, 200)
        self.assertEqual(me_resp.json()["username"], "student_maya")

        # Step 3: Browse problem library
        probs_resp = self.client.get("/api/problems")
        self.assertEqual(probs_resp.status_code, 200)
        prob_list = probs_resp.json()
        self.assertEqual(len(prob_list), 5)
        p1 = next(p for p in prob_list if p["problem_id"] == "PILOT-001")
        self.assertEqual(p1["title"], "Move Zeroes")

        # Step 4: Open problem detail
        p_detail_resp = self.client.get("/api/problems/PILOT-001")
        self.assertEqual(p_detail_resp.status_code, 200)
        p_detail = p_detail_resp.json()
        self.assertIn("starter_code", p_detail)
        self.assertIn("constraints", p_detail)
        self.assertEqual(p_detail["test_count"], 9)

        # Step 5: Submit a correct C++ solution
        sub1_resp = self.client.post("/api/submissions", headers={"X-CSRF-Token": csrf_token}, json={
            "problem_id": "PILOT-001",
            "code": synthetic.P1["correct"]
        })
        self.assertEqual(sub1_resp.status_code, 200)
        sub1_data = sub1_resp.json()
        sid1 = sub1_data["submission_id"]
        self.assertEqual(sub1_data["compile_status"], "OK")
        self.assertEqual(sub1_data["fingerprint"], "PPPPPPPPP")
        self.assertEqual(len(sub1_data["tests"]), 9)
        for t in sub1_data["tests"]:
            self.assertEqual(t["status"], "P")
            self.assertEqual(t["execution_status"], "COMPLETED")

        # Step 6: Verify actual execution results persist in store
        rec1_resp = self.client.get(f"/api/submissions/{sid1}")
        self.assertEqual(rec1_resp.status_code, 200)
        rec1_data = rec1_resp.json()
        self.assertEqual(rec1_data["submission_id"], sid1)
        self.assertEqual(rec1_data["fingerprint"], "PPPPPPPPP")

        # Verify practice recommendation for correct submission
        prac1_resp = self.client.get(f"/api/submissions/{sid1}/practice")
        self.assertEqual(prac1_resp.status_code, 200)
        prac1_data = prac1_resp.json()
        self.assertEqual(prac1_data["state"], "correct")
        self.assertEqual(prac1_data["recommendation"]["action"], "practice")
        self.assertEqual(prac1_data["recommendation"]["problem_id"], "PILOT-002")

        # Step 7: Submit an incorrect solution (PILOT-002 with B_wrong_return)
        sub2_resp = self.client.post("/api/submissions", headers={"X-CSRF-Token": csrf_token}, json={
            "problem_id": "PILOT-002",
            "code": synthetic.P2["B_wrong_return"]
        })
        self.assertEqual(sub2_resp.status_code, 200)
        sub2_data = sub2_resp.json()
        sid2 = sub2_data["submission_id"]
        self.assertEqual(sub2_data["compile_status"], "OK")
        self.assertEqual(sub2_data["fingerprint"], "FPFFFFFF")

        # Step 8: View diagnostic explanation / recommendation
        prac2_resp = self.client.get(f"/api/submissions/{sid2}/practice")
        self.assertEqual(prac2_resp.status_code, 200)
        prac2_data = prac2_resp.json()
        self.assertEqual(prac2_data["state"], "insufficient_evidence")
        self.assertEqual(prac2_data["recommendation"]["action"], "retry")
        self.assertEqual(prac2_data["recommendation"]["problem_id"], "PILOT-002")
        # Ensure cognitive firewall: no raw error label (like B_wrong_return) exposed in student guidance
        self.assertNotIn("B_wrong_return", str(prac2_data["explanation"]))

        # Step 9: Submit a follow-up attempt linked to sid2
        sub3_resp = self.client.post("/api/submissions", headers={"X-CSRF-Token": csrf_token}, json={
            "problem_id": "PILOT-002",
            "code": synthetic.P2["correct"],
            "parent_submission_id": sid2
        })
        self.assertEqual(sub3_resp.status_code, 200)
        sub3_data = sub3_resp.json()
        sid3 = sub3_data["submission_id"]
        self.assertEqual(sub3_data["fingerprint"], "PPPPPPPP")

        # Step 10: Verify attempt lineage sequence
        chain_resp = self.client.get(f"/api/submissions/{sid3}/chain")
        self.assertEqual(chain_resp.status_code, 200)
        chain_data = chain_resp.json()
        chain = chain_data["chain"]
        self.assertEqual(len(chain), 2)
        self.assertEqual(chain[0]["submission_id"], sid2)
        self.assertEqual(chain[1]["submission_id"], sid3)
        self.assertEqual(chain[1]["parent_submission_id"], sid2)

        # Step 11: Verify student submission history contains all attempts
        hist_resp = self.client.get("/api/student/history")
        self.assertEqual(hist_resp.status_code, 200)
        hist = hist_resp.json()["submissions"]
        self.assertEqual(len(hist), 3)
        hist_ids = [s["submission_id"] for s in hist]
        self.assertIn(sid1, hist_ids)
        self.assertIn(sid2, hist_ids)
        self.assertIn(sid3, hist_ids)

        # Step 12: Logout and verify session termination
        logout_resp = self.client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf_token})
        self.assertEqual(logout_resp.status_code, 200)

        # Protected endpoint must now return 401
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        self.assertEqual(self.client.get("/api/student/history").status_code, 401)

    # --- 2. Authorization & Privacy Invariants ---

    def test_02_authorization_invariants(self):
        """Verify strict multi-tenant boundaries and RBAC enforcement."""
        # Create Student A
        reg_a = self.client.post("/api/auth/register", json={
            "username": "student_alex",
            "email": "alex@test.edu",
            "password": "Password123!"
        })
        csrf_a = reg_a.json()["csrf_token"]

        # Student A submits code
        sub_a = self.client.post("/api/submissions", headers={"X-CSRF-Token": csrf_a}, json={
            "problem_id": "PILOT-001",
            "code": synthetic.P1["correct"]
        })
        sid_a = sub_a.json()["submission_id"]

        # Student A logs out
        self.client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf_a})

        # Create Student B
        reg_b = self.client.post("/api/auth/register", json={
            "username": "student_bob",
            "email": "bob@test.edu",
            "password": "Password123!"
        })
        csrf_b = reg_b.json()["csrf_token"]

        # Check 1: Student B cannot read Student A's submission
        res_read = self.client.get(f"/api/submissions/{sid_a}")
        self.assertEqual(res_read.status_code, 403, "Student B must NOT be able to view Student A's submission")

        # Check 2: Student B cannot link a follow-up to Student A's submission
        res_link = self.client.post("/api/submissions", headers={"X-CSRF-Token": csrf_b}, json={
            "problem_id": "PILOT-001",
            "code": synthetic.P1["correct"],
            "parent_submission_id": sid_a
        })
        self.assertEqual(res_link.status_code, 403, "Student B must NOT be able to link to Student A's submission")

        # Check 3: Student B cannot access researcher endpoints
        res_res = self.client.get("/api/research/overview")
        self.assertEqual(res_res.status_code, 403, "Student B must receive 403 Forbidden on researcher routes")

        # Check 4: Student cannot elevate role via registration payload
        reg_hack = self.client.post("/api/auth/register", json={
            "username": "student_hacker",
            "email": "hacker@test.edu",
            "password": "Password123!",
            "role": "researcher"  # Attempted escalation
        })
        self.assertEqual(reg_hack.status_code, 201)
        self.assertEqual(reg_hack.json()["user"]["role"], "student", "Role MUST default to student regardless of payload")

        # Check 5: Authorized researcher CAN inspect Student A's submission
        auth.create_researcher_user("prof_oak", "oak@kanto.edu", "Password123!")
        login_res = self.client.post("/api/auth/login", json={
            "username": "prof_oak",
            "password": "Password123!"
        })
        self.assertEqual(login_res.status_code, 200)

        res_detail = self.client.get(f"/api/research/submissions/{sid_a}")
        self.assertEqual(res_detail.status_code, 200, "Researcher must be able to inspect submissions")
        self.assertEqual(res_detail.json()["problem_id"], "PILOT-001")

    # --- 3. Edge Cases & Error States ---

    def test_03_edge_cases_and_error_handling(self):
        """Verify robust error responses on missing records and invalid inputs."""
        # Nonexistent submission ID
        resp_404 = self.client.get("/api/submissions/nonexistent-uuid-12345")
        self.assertEqual(resp_404.status_code, 404)

        # Nonexistent parent submission ID
        resp_parent_404 = self.client.post("/api/submissions", json={
            "problem_id": "PILOT-001",
            "code": synthetic.P1["correct"],
            "parent_submission_id": "nonexistent-parent-uuid"
        })
        self.assertEqual(resp_parent_404.status_code, 404)

        # Invalid problem ID
        resp_prob_404 = self.client.post("/api/submissions", json={
            "problem_id": "INVALID-PROBLEM-999",
            "code": "int main() {}"
        })
        self.assertEqual(resp_prob_404.status_code, 404)

        # Long compiler error message handling
        long_ce_code = "\n".join([f"#error Very long compilation diagnostic failure line {i}" for i in range(50)])
        sub_ce = self.client.post("/api/submissions", json={
            "problem_id": "PILOT-001",
            "code": long_ce_code
        })
        self.assertEqual(sub_ce.status_code, 200)
        ce_data = sub_ce.json()
        self.assertIn("compile", ce_data)
        self.assertIn("stderr", ce_data["compile"])
        self.assertGreater(len(ce_data["compile"]["stderr"]), 100)


if __name__ == "__main__":
    unittest.main()
