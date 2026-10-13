"""Automated tests for the CodeAdapt Protected Researcher Workspace.

Verifies:
1. Role-based access control (unauthenticated returns 401; student returns 403; researcher returns 200).
2. Clean zero-data handling and missing data indicators when database is empty.
3. Accurate research overview telemetry with real stored data and problem coverage.
4. Submission explorer search, pagination, and filtering (by problem_id, compile_status, keyword).
5. Deep submission record inspection and execution failure classification (crashes, timeouts, wrong answers).
6. Diagnostic decision trace with candidate evaluation matrix, UB cell exclusions, and abstention rationale.
7. Research evaluation endpoint verifying synthetic vs. student data separation and absence of fabricated metrics.
8. Documented instrument limitations (P3/E2, P5/E2, P5/E4 divergences, probe caveats, sandbox boundaries).
"""

import os
import sys
import unittest
from unittest.mock import patch

# Ensure backend and tests can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from fastapi.testclient import TestClient
import app
import auth
import store
import problems
import executor
import synthetic


class TestResearcherWorkspace(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        HERE = os.path.dirname(os.path.abspath(__file__))
        cls.test_db = os.path.join(HERE, "test_researcher_evidence.db")
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

    def _login_as(self, username, role="student"):
        """Create user if not present, and login to set session cookie."""
        email = f"{username}@test.edu"
        if role == "researcher":
            auth.create_researcher_user(username, email, "Password123!")
        else:
            try:
                auth.register_user(username, email, "Password123!")
            except auth.DuplicateAccountError:
                pass
        # Login
        resp = self.client.post("/api/auth/login", json={
            "username": username,
            "password": "Password123!"
        })
        self.assertEqual(resp.status_code, 200)
        return resp.json()["csrf_token"]

    # --- 1. Access Control (RBAC) ---

    def test_01_unauthenticated_access_denied(self):
        """Unauthenticated requests to any /api/research/* route must return 401."""
        endpoints = [
            "/api/research/overview",
            "/api/research/submissions",
            "/api/research/submissions/nonexistent-id",
            "/api/research/submissions/nonexistent-id/decision-trace",
            "/api/research/evaluation",
            "/api/research/limitations",
            "/api/research/problems/PILOT-001/matrices"
        ]
        for ep in endpoints:
            resp = self.client.get(ep)
            self.assertEqual(resp.status_code, 401, f"Expected 401 on {ep}, got {resp.status_code}")

    def test_02_student_access_forbidden(self):
        """Authenticated student requests to /api/research/* routes must return 403."""
        self._login_as("student_charlie", role="student")
        endpoints = [
            "/api/research/overview",
            "/api/research/submissions",
            "/api/research/submissions/nonexistent-id",
            "/api/research/submissions/nonexistent-id/decision-trace",
            "/api/research/evaluation",
            "/api/research/limitations",
            "/api/research/problems/PILOT-001/matrices"
        ]
        for ep in endpoints:
            resp = self.client.get(ep)
            self.assertEqual(resp.status_code, 403, f"Expected 403 on {ep}, got {resp.status_code}")
            self.assertIn("privileges required", resp.json()["detail"])

    def test_03_researcher_access_allowed(self):
        """Authenticated researcher requests must successfully access research routes."""
        self._login_as("dr_watson", role="researcher")
        resp = self.client.get("/api/research/overview")
        self.assertEqual(resp.status_code, 200)
        resp_eval = self.client.get("/api/research/evaluation")
        self.assertEqual(resp_eval.status_code, 200)
        resp_limits = self.client.get("/api/research/limitations")
        self.assertEqual(resp_limits.status_code, 200)

    # --- 2. Zero-Data & Missing Data Handling ---

    def test_04_empty_database_overview_handling(self):
        """Overview must return valid telemetry structure with missing data indicators when DB is empty."""
        self._login_as("dr_watson", role="researcher")
        resp = self.client.get("/api/research/overview")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total_submissions"], 0)
        self.assertEqual(data["compile_ok_count"], 0)
        self.assertEqual(data["compile_error_count"], 0)
        self.assertEqual(data["abstention_rate_pct"], 0.0)
        self.assertTrue(data["missing_data_indicators"]["zero_submissions"])
        self.assertTrue(data["missing_data_indicators"]["insufficient_sample"])
        self.assertTrue(data["missing_data_indicators"]["has_unrepresented_problems"])
        self.assertEqual(len(data["unrepresented_problems"]), 5)
        self.assertIn("sandbox store", data["epistemic_notice"])
        self.assertIn("compiler", data["toolchain"])

    # --- 3. Stored Data Telemetry & Problem Coverage ---

    def test_05_populated_telemetry_and_coverage(self):
        """Submit actual solutions and verify telemetry and problem coverage reflect stored records."""
        # Submit as student
        self._login_as("student_charlie", role="student")
        csrf = self.client.get("/api/auth/me").json()["csrf_token"]

        # PILOT-001 Correct
        sub1 = self.client.post("/api/submissions", headers={"X-CSRF-Token": csrf}, json={
            "problem_id": "PILOT-001",
            "code": synthetic.P1["correct"]
        })
        self.assertEqual(sub1.status_code, 200)
        sid1 = sub1.json()["submission_id"]

        # PILOT-001 Compile Error
        sub2 = self.client.post("/api/submissions", headers={"X-CSRF-Token": csrf}, json={
            "problem_id": "PILOT-001",
            "code": "int broken syntax {"
        })
        self.assertEqual(sub2.status_code, 200)
        sid2 = sub2.json()["submission_id"]

        # PILOT-002 Ambiguous Collision (B_wrong_return)
        sub3 = self.client.post("/api/submissions", headers={"X-CSRF-Token": csrf}, json={
            "problem_id": "PILOT-002",
            "code": synthetic.P2["B_wrong_return"]
        })
        self.assertEqual(sub3.status_code, 200)
        sid3 = sub3.json()["submission_id"]

        # Switch to researcher
        self._login_as("dr_watson", role="researcher")
        resp = self.client.get("/api/research/overview")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["total_submissions"], 3)
        self.assertEqual(data["compile_ok_count"], 2)
        self.assertEqual(data["compile_error_count"], 1)
        self.assertEqual(data["unique_students_count"], 1)

        # Check verdict distribution
        vd = data["verdict_distribution"]
        self.assertGreaterEqual(vd["task_correct"], 1)
        self.assertGreaterEqual(vd["ambiguous"], 1)
        self.assertGreaterEqual(vd["no_execution_evidence"], 1)

        # Check problem coverage
        cov = {p["problem_id"]: p for p in data["problem_coverage"]}
        self.assertTrue(cov["PILOT-001"]["has_data"])
        self.assertEqual(cov["PILOT-001"]["total_submissions"], 2)
        self.assertTrue(cov["PILOT-002"]["has_data"])
        self.assertEqual(cov["PILOT-002"]["total_submissions"], 1)
        self.assertFalse(cov["PILOT-003"]["has_data"])
        self.assertIn("PILOT-003", data["unrepresented_problems"])

    # --- 4. Submission Explorer Filtering & Pagination ---

    def test_06_submission_explorer_search_and_filter(self):
        """Verify search, problem filter, and compile_status filter on /api/research/submissions."""
        self._login_as("dr_watson", role="researcher")

        # Total submissions list
        resp = self.client.get("/api/research/submissions?limit=10&offset=0")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total"], 3)
        self.assertEqual(len(data["submissions"]), 3)

        # Pagination: limit=1
        resp_p1 = self.client.get("/api/research/submissions?limit=1&offset=0")
        self.assertEqual(resp_p1.status_code, 200)
        self.assertEqual(len(resp_p1.json()["submissions"]), 1)
        self.assertEqual(resp_p1.json()["total"], 3)

        # Filter by problem_id: PILOT-002
        resp_p2 = self.client.get("/api/research/submissions?problem_id=PILOT-002")
        self.assertEqual(resp_p2.status_code, 200)
        d2 = resp_p2.json()
        self.assertEqual(d2["total"], 1)
        self.assertEqual(d2["submissions"][0]["problem_id"], "PILOT-002")

        # Filter by compile_status: COMPILE_ERROR
        resp_ce = self.client.get("/api/research/submissions?compile_status=COMPILE_ERROR")
        self.assertEqual(resp_ce.status_code, 200)
        dce = resp_ce.json()
        self.assertEqual(dce["total"], 1)
        self.assertEqual(dce["submissions"][0]["compile_status"], "COMPILE_ERROR")

        # Search by username keyword
        resp_search = self.client.get("/api/research/submissions?search=charlie")
        self.assertEqual(resp_search.status_code, 200)
        self.assertEqual(resp_search.json()["total"], 3)

        # Search by non-existent keyword
        resp_none = self.client.get("/api/research/submissions?search=nonexistent_xyz")
        self.assertEqual(resp_none.status_code, 200)
        self.assertEqual(resp_none.json()["total"], 0)

    # --- 5. Submission Deep Detail & Failure Classification ---

    def test_07_submission_detail_inspection(self):
        """Inspect full execution record, compiler diagnostics, and test outcome classifications."""
        self._login_as("dr_watson", role="researcher")
        subs = self.client.get("/api/research/submissions?problem_id=PILOT-001&compile_status=OK").json()["submissions"]
        self.assertGreater(len(subs), 0)
        sid = subs[0]["submission_id"]

        resp = self.client.get(f"/api/research/submissions/{sid}")
        self.assertEqual(resp.status_code, 200)
        rec = resp.json()

        self.assertEqual(rec["submission_id"], sid)
        self.assertEqual(rec["problem_id"], "PILOT-001")
        self.assertEqual(rec["compile_status"], "OK")
        self.assertIn("execution_summary", rec)
        sm = rec["execution_summary"]
        self.assertEqual(sm["passed_count"], sm["total_tests"])
        self.assertEqual(sm["wrong_answer_count"], 0)
        self.assertEqual(sm["crash_count"], 0)
        self.assertEqual(sm["timeout_count"], 0)
        self.assertFalse(sm["is_compile_error"])

        self.assertIn("test_results", rec)
        self.assertEqual(len(rec["test_results"]), sm["total_tests"])
        self.assertEqual(rec["test_results"][0]["status"], "P")
        self.assertEqual(rec["test_results"][0]["execution_status"], "COMPLETED")

        self.assertIn("compiler_diagnostics", rec)
        self.assertIn("diagnostic_interpretation", rec)
        self.assertEqual(rec["diagnostic_interpretation"]["verdict"], "task_correct")

    def test_08_submission_detail_compile_error(self):
        """Inspect compile error detail with compiler stderr and zero test executions."""
        self._login_as("dr_watson", role="researcher")
        subs = self.client.get("/api/research/submissions?compile_status=COMPILE_ERROR").json()["submissions"]
        self.assertGreater(len(subs), 0)
        sid = subs[0]["submission_id"]

        resp = self.client.get(f"/api/research/submissions/{sid}")
        self.assertEqual(resp.status_code, 200)
        rec = resp.json()
        self.assertEqual(rec["compile_status"], "COMPILE_ERROR")
        self.assertTrue(rec["execution_summary"]["is_compile_error"])
        self.assertEqual(len(rec["test_results"]), 0)
        self.assertTrue(bool(rec["compiler_diagnostics"]["stderr_raw"]))

    # --- 6. Diagnostic Decision Trace ---

    def test_09_decision_trace_ambiguous_collision(self):
        """Decision trace must expose candidates, exact mismatch scoring, and collision abstention."""
        self._login_as("dr_watson", role="researcher")
        subs = self.client.get("/api/research/submissions?problem_id=PILOT-002").json()["submissions"]
        self.assertGreater(len(subs), 0)
        sid = subs[0]["submission_id"]

        resp = self.client.get(f"/api/research/submissions/{sid}/decision-trace")
        self.assertEqual(resp.status_code, 200)
        trace = resp.json()

        self.assertEqual(trace["submission_id"], sid)
        self.assertEqual(trace["problem_id"], "PILOT-002")
        self.assertEqual(trace["verdict"], "ambiguous")
        self.assertIn("B_wrong_return", trace["matched_errors"])
        self.assertIn("C_off_by_one", trace["matched_errors"])

        # Abstention analysis
        abst = trace["abstention_analysis"]
        self.assertTrue(abst["is_abstention"])
        self.assertTrue(abst["is_known_collision"])
        self.assertIn("Ambiguous collision", abst["abstention_reason"])

        # Candidates evaluated
        self.assertGreater(len(trace["candidates_evaluated"]), 0)
        matched_cands = [c for c in trace["candidates_evaluated"] if c["is_exact_match"]]
        self.assertEqual(len(matched_cands), 2)

        # Undefined behavior exclusions
        ub = trace["undefined_behavior_exclusions"]
        self.assertIn("rationale", ub)

    # --- 7. Research Evaluation (Synthetic vs Real Separation) ---

    def test_10_research_evaluation_integrity(self):
        """Evaluation endpoint must separate synthetic from student data and refuse to fabricate student accuracy."""
        self._login_as("dr_watson", role="researcher")
        resp = self.client.get("/api/research/evaluation")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # 1. Synthetic Benchmark
        synth = data["synthetic_benchmark"]
        self.assertEqual(synth["sample_size"], 18)
        self.assertEqual(synth["ground_truth_status"], "Validated by Construction")
        self.assertEqual(synth["evaluation_metrics"]["exact_matches_on_modeled_rows"], 11)
        self.assertEqual(synth["evaluation_metrics"]["modeled_error_attributions_tested"], 12)
        # Verify construct validity bypass is documented
        bypasses = synth["evaluation_metrics"]["construct_validity_bypasses"]
        self.assertEqual(bypasses[0]["problem_id"], "PILOT-005")
        self.assertEqual(bypasses[0]["fixture"], "linear_scan")

        # 2. Student Cohort
        stud = data["student_cohort"]
        self.assertEqual(stud["ground_truth_status"], "UNAVAILABLE / UNLABELED")
        self.assertFalse(stud["has_ground_truth"])
        self.assertIsNone(stud["evaluation_metrics"], "Student metrics MUST be None when unlabeled")
        self.assertIn("statistically invalid", stud["methodological_notice"])
        self.assertIn("iterative code debugging", stud["learning_gain_notice"])

        # 3. Overall Summary
        self.assertTrue(data["summary"]["validated_findings_available"])
        self.assertFalse(data["summary"]["student_accuracy_claimable"])

    # --- 8. Instrument Limitations ---

    def test_11_instrument_limitations_structure(self):
        """Limitations endpoint must document P3/E2, P5/E2, P5/E4 divergences, probe caveats, and sandbox boundaries."""
        self._login_as("dr_watson", role="researcher")
        resp = self.client.get("/api/research/limitations")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        divergences = data["known_divergences"]
        self.assertEqual(len(divergences), 3)

        p3_e2 = next(d for d in divergences if d["problem_id"] == "PILOT-003")
        self.assertEqual(p3_e2["claimed_doc_fingerprint"], "PPPFPPPP")
        self.assertEqual(p3_e2["observed_baseline_fingerprint"], "PPPRPPPP")
        self.assertIn("0xC0000409", p3_e2["mechanism"])

        p5_e2 = next(d for d in divergences if d["problem_id"] == "PILOT-005" and d["error_name"] == "E2_loop_condition")
        self.assertEqual(p5_e2["claimed_doc_fingerprint"], "RRRRRRRR")
        self.assertEqual(p5_e2["observed_baseline_fingerprint"], "RRRFRRRR")

        p5_e4 = next(d for d in divergences if d["problem_id"] == "PILOT-005" and d["error_name"] == "E4_upper_mid")
        self.assertEqual(p5_e4["claimed_doc_fingerprint"], "PPRRRRPR")
        self.assertEqual(p5_e4["observed_baseline_fingerprint"], "PPRFRRPR")

        probe_caveats = data["undefined_behavior_probes"]
        self.assertIn("does NOT prove the absence of undefined behavior", probe_caveats["epistemic_limitation"])

        sandbox = data["windows_sandbox_limitations"]
        self.assertIn("Windows Job Object", sandbox["process_isolation"])
        self.assertIn("Low Mandatory Integrity Label", sandbox["write_protection"])

    # --- 9. Problem Matrices ---

    def test_12_problem_matrices(self):
        """Problem matrices endpoint returns reference rows and collision catalogs."""
        self._login_as("dr_watson", role="researcher")
        resp = self.client.get("/api/research/problems/PILOT-002/matrices")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["problem_id"], "PILOT-002")
        self.assertIn("B_wrong_return", data["reference"])
        self.assertIn("C_off_by_one", data["reference"])
        self.assertIn(["B_wrong_return", "C_off_by_one"], data["known_collisions"])

        # Nonexistent problem returns 404
        resp_404 = self.client.get("/api/research/problems/NONEXISTENT/matrices")
        self.assertEqual(resp_404.status_code, 404)


if __name__ == "__main__":
    unittest.main()
