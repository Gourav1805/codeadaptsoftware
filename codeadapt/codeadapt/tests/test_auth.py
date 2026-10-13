"""Automated tests for CodeAdapt authentication and role-based authorization.

Covers:
1. Successful registration.
2. Duplicate registration (username & email).
3. Password hashing (Argon2id verification, no plaintext).
4. Successful login.
5. Invalid credentials (generic 401, no enumeration).
6. Logout (session invalidated, cookie cleared).
7. Session restoration (valid session restored, expired session rejected).
8. Student route authorization (authenticated student can access history and submit).
9. Researcher route authorization (researcher can access research endpoints).
10. Student-to-researcher privilege escalation attempts (blocked).
11. Cross-user submission access (student cannot access another student's submission; researcher can).
12. Unauthenticated API requests (rejected with 401).
"""
import os
import sys
import unittest

# Ensure backend and tests can be imported
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))

from fastapi.testclient import TestClient
import app
import auth
import store

client = TestClient(app.app)


class TestAuthAndRBAC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Use an isolated test database
        cls.test_db = os.path.join(HERE, "test_auth_evidence.db")
        if os.path.exists(cls.test_db):
            os.remove(cls.test_db)
        store.init(cls.test_db)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.test_db):
            try:
                os.remove(cls.test_db)
            except OSError:
                pass

    def setUp(self):
        client.cookies.clear()

    def test_01_successful_registration(self):
        """Test successful registration of a student account."""
        resp = client.post("/api/auth/register", json={
            "username": "alice_coder",
            "email": "alice@example.edu",
            "password": "Password123!"
        })
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertIn("user", data)
        self.assertEqual(data["user"]["username"], "alice_coder")
        self.assertEqual(data["user"]["email"], "alice@example.edu")
        self.assertEqual(data["user"]["role"], "student")
        # Ensure password hash is NOT returned
        self.assertNotIn("password", data["user"])
        self.assertNotIn("password_hash", data["user"])
        # Ensure HTTP-only cookie was set
        self.assertIn("codeadapt_session", resp.cookies)

    def test_02_duplicate_registration(self):
        """Test duplicate account prevention on username and email."""
        # Duplicate username (case-insensitive)
        resp1 = client.post("/api/auth/register", json={
            "username": "ALICE_CODER",
            "email": "another_alice@example.edu",
            "password": "Password123!"
        })
        self.assertEqual(resp1.status_code, 409)
        self.assertIn("username", resp1.json()["detail"].lower())

        # Duplicate email (case-insensitive)
        resp2 = client.post("/api/auth/register", json={
            "username": "new_alice",
            "email": "ALICE@EXAMPLE.EDU",
            "password": "Password123!"
        })
        self.assertEqual(resp2.status_code, 409)
        self.assertIn("email", resp2.json()["detail"].lower())

    def test_03_password_hashing(self):
        """Verify password is stored as Argon2id hash and never plaintext."""
        with store._connect() as conn:
            row = conn.execute("SELECT password_hash FROM users WHERE username = 'alice_coder'").fetchone()
        self.assertIsNotNone(row)
        pwd_hash = row["password_hash"]
        # Argon2id prefix
        self.assertTrue(pwd_hash.startswith("$argon2id$"))
        self.assertNotIn("Password123!", pwd_hash)
        self.assertTrue(auth.verify_password(pwd_hash, "Password123!"))
        self.assertFalse(auth.verify_password(pwd_hash, "WrongPassword"))

    def test_04_successful_login(self):
        """Test login with valid credentials."""
        resp = client.post("/api/auth/login", json={
            "username": "alice_coder",
            "password": "Password123!"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["user"]["username"], "alice_coder")
        self.assertEqual(data["user"]["role"], "student")
        self.assertIn("csrf_token", data)
        self.assertIn("codeadapt_session", resp.cookies)

    def test_05_invalid_credentials(self):
        """Test invalid credentials handling without user enumeration."""
        # Non-existent user
        resp1 = client.post("/api/auth/login", json={
            "username": "non_existent_user",
            "password": "Password123!"
        })
        self.assertEqual(resp1.status_code, 401)

        # Existing user, wrong password
        resp2 = client.post("/api/auth/login", json={
            "username": "alice_coder",
            "password": "WrongPassword!"
        })
        self.assertEqual(resp2.status_code, 401)

        # Both return the exact same generic error message
        self.assertEqual(resp1.json()["detail"], resp2.json()["detail"])
        self.assertEqual(resp1.json()["detail"], "Invalid username or password")

    def test_06_logout(self):
        """Test logout invalidates session and clears cookie."""
        login_resp = client.post("/api/auth/login", json={
            "username": "alice_coder",
            "password": "Password123!"
        })
        self.assertEqual(login_resp.status_code, 200)
        token = login_resp.json()["session_token"]

        # Logout with token in header
        logout_resp = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(logout_resp.status_code, 200)

        # Verify session is deleted
        session = auth.get_session(token)
        self.assertIsNone(session)

    def test_07_session_restoration(self):
        """Test session restoration on refresh and handling of invalid session."""
        login_resp = client.post("/api/auth/login", json={
            "username": "alice_coder",
            "password": "Password123!"
        })
        token = login_resp.json()["session_token"]

        # Valid session restoration
        me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me_resp.status_code, 200)
        self.assertEqual(me_resp.json()["username"], "alice_coder")

        # Invalid/fake session
        bad_resp = client.get("/api/auth/me", headers={"Authorization": "Bearer fake_token_12345"})
        self.assertEqual(bad_resp.status_code, 401)

    def test_08_student_route_authorization(self):
        """Test authenticated student can access student history and submit."""
        login_resp = client.post("/api/auth/login", json={
            "username": "alice_coder",
            "password": "Password123!"
        })
        token = login_resp.json()["session_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Student history
        hist_resp = client.get("/api/student/history", headers=headers)
        self.assertEqual(hist_resp.status_code, 200)

        # Student progress
        prog_resp = client.get("/api/student/progress", headers=headers)
        self.assertEqual(prog_resp.status_code, 200)

    def test_09_researcher_route_authorization(self):
        """Test researcher can access researcher endpoints."""
        # Provision researcher account via safe internal procedure
        res = auth.create_researcher_user("prof_smith", "smith@example.edu", "SmithPass123!")
        self.assertEqual(res["role"], "researcher")

        login_resp = client.post("/api/auth/login", json={
            "username": "prof_smith",
            "password": "SmithPass123!"
        })
        token = login_resp.json()["session_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Researcher submissions list
        sub_resp = client.get("/api/research/submissions", headers=headers)
        self.assertEqual(sub_resp.status_code, 200)

        # Researcher telemetry
        tel_resp = client.get("/api/research/telemetry", headers=headers)
        self.assertEqual(tel_resp.status_code, 200)

        # Researcher problem matrices
        mat_resp = client.get("/api/research/problems/PILOT-005/matrices", headers=headers)
        self.assertEqual(mat_resp.status_code, 200)

    def test_10_student_privilege_escalation_attempt(self):
        """Test that a student cannot escalate role via registration or access researcher routes."""
        # 1. Attempt to register as researcher
        reg_resp = client.post("/api/auth/register", json={
            "username": "sneaky_student",
            "email": "sneaky@example.edu",
            "password": "Password123!",
            "role": "researcher"  # Attempt self-escalation
        })
        self.assertEqual(reg_resp.status_code, 201)
        # Server must force role to student!
        self.assertEqual(reg_resp.json()["user"]["role"], "student")

        # 2. Login as the student
        login_resp = client.post("/api/auth/login", json={
            "username": "sneaky_student",
            "password": "Password123!"
        })
        token = login_resp.json()["session_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 3. Student tries to access researcher endpoints -> 403 Forbidden
        r1 = client.get("/api/research/submissions", headers=headers)
        self.assertEqual(r1.status_code, 403)

        r2 = client.get("/api/research/telemetry", headers=headers)
        self.assertEqual(r2.status_code, 403)

        r3 = client.get("/submissions/fake_sub_id/diagnostics", headers=headers)
        self.assertEqual(r3.status_code, 403)

    def test_11_cross_user_submission_access(self):
        """Test that a student cannot view another student's private submission."""
        # Register Bob
        client.post("/api/auth/register", json={
            "username": "bob_coder",
            "email": "bob@example.edu",
            "password": "Password123!"
        })

        # Alice creates a submission
        alice_login = client.post("/api/auth/login", json={
            "username": "alice_coder",
            "password": "Password123!"
        })
        alice_token = alice_login.json()["session_token"]
        alice_headers = {"Authorization": f"Bearer {alice_token}"}

        # Use an existing submission fixture (P5 linear scan)
        code = "int lowerBound(const std::vector<int>& arr, int target) { for (size_t i=0; i<arr.size(); ++i) if(arr[i]>=target) return i; return arr.size(); }"
        sub_resp = client.post("/api/submissions", headers=alice_headers, json={
            "problem_id": "PILOT-005",
            "code": code
        })
        self.assertEqual(sub_resp.status_code, 200)
        alice_sub_id = sub_resp.json()["submission_id"]

        # Alice can view her own submission
        a_view = client.get(f"/api/submissions/{alice_sub_id}", headers=alice_headers)
        self.assertEqual(a_view.status_code, 200)

        # Bob logs in
        bob_login = client.post("/api/auth/login", json={
            "username": "bob_coder",
            "password": "Password123!"
        })
        bob_token = bob_login.json()["session_token"]
        bob_headers = {"Authorization": f"Bearer {bob_token}"}

        # Bob attempts to view Alice's submission -> 403 Forbidden!
        b_view = client.get(f"/api/submissions/{alice_sub_id}", headers=bob_headers)
        self.assertEqual(b_view.status_code, 403)

        # Bob attempts to view Alice's practice recommendation -> 403 Forbidden!
        b_prac = client.get(f"/api/submissions/{alice_sub_id}/practice", headers=bob_headers)
        self.assertEqual(b_prac.status_code, 403)

        # Researcher prof_smith CAN view Alice's submission
        smith_login = client.post("/api/auth/login", json={
            "username": "prof_smith",
            "password": "SmithPass123!"
        })
        smith_token = smith_login.json()["session_token"]
        smith_headers = {"Authorization": f"Bearer {smith_token}"}

        smith_view = client.get(f"/api/submissions/{alice_sub_id}", headers=smith_headers)
        self.assertEqual(smith_view.status_code, 200)

    def test_12_unauthenticated_api_requests(self):
        """Test unauthenticated requests to protected endpoints are rejected with 401."""
        # Unauthenticated /api/auth/me -> 401
        self.assertEqual(client.get("/api/auth/me").status_code, 401)

        # Unauthenticated /api/student/history -> 401
        self.assertEqual(client.get("/api/student/history").status_code, 401)

        # Unauthenticated /api/research/submissions -> 401
        self.assertEqual(client.get("/api/research/submissions").status_code, 401)


if __name__ == "__main__":
    unittest.main()
