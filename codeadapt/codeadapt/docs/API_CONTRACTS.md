# CodeAdapt API Specification & Contracts

This document provides the definitive REST API contracts, request/response schemas, authentication headers, error formats, and backward-compatibility mappings for CodeAdapt.

---

## 1. General API Conventions

### 1.1 Base Paths
- Modern Standard API: `/api/`
- Legacy Compatible API: `/` (preserved for backward compatibility with existing tests and scripts)

### 1.2 Authentication & Authorization Headers
- **Session Cookie:** `codeadapt_session=<session_token>` (HTTP-only, `SameSite=Lax`, `Path=/`).
- **Authorization Header (Alternative for API/CLI clients):** `Authorization: Bearer <session_token>`.
- **Role Permissions:**
  - `public`: Accessible without authentication.
  - `authenticated`: Accessible to any valid session (`student`, `researcher`, `admin`).
  - `student`: Accessible to authenticated students and researchers. Private resources (such as specific submissions or history) are scoped strictly to the authenticated user's own data.
  - `researcher`: Accessible strictly to users with `role IN ('researcher', 'admin')`. Enforced at the backend controller level.

### 1.3 Standard Error Format
All 4xx and 5xx error responses return JSON matching this schema:

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Problem 'PILOT-999' was not found in the problem library.",
    "status": 404,
    "details": null
  }
}
```

Standard status codes:
- `200 OK`: Request succeeded.
- `201 Created`: Resource successfully created.
- `400 Bad Request`: Invalid request payload, malformed JSON, or validation failure.
- `401 Unauthorized`: Missing or invalid session token.
- `403 Forbidden`: Authenticated user lacks permission (e.g., student attempting to access researcher endpoints).
- `404 Not Found`: Requested resource does not exist.
- `429 Too Many Requests`: Submission rate limit exceeded.
- `500 Internal Server Error`: Unexpected server failure.

---

## 2. Authentication & User Management Endpoints

### 2.1 Register User
- **Endpoint:** `POST /api/auth/register`
- **Access:** Public
- **Description:** Creates a new user account. Defaults to role `student`.

#### Request
```http
POST /api/auth/register HTTP/1.1
Content-Type: application/json

{
  "username": "coder_alex",
  "email": "alex@example.edu",
  "password": "Password123!",
  "role": "student"
}
```

| Field | Type | Required | Constraints |
|---|---|---|---|
| `username` | string | Yes | 3–32 alphanumeric characters, `_`, `-` |
| `email` | string | Yes | Valid email format |
| `password` | string | Yes | Minimum 8 characters |
| `role` | string | No | `student` (default) or `researcher` |

#### Response (`201 Created`)
```http
HTTP/1.1 201 Created
Set-Cookie: codeadapt_session=a8f9c0e2...; HttpOnly; SameSite=Lax; Path=/
Content-Type: application/json

{
  "user": {
    "user_id": "usr_9b1deb4d3b7d4e5f",
    "username": "coder_alex",
    "email": "alex@example.edu",
    "role": "student",
    "created_at": "2026-10-13T10:30:00Z"
  },
  "session_token": "a8f9c0e2718293a4b5c6d7e8f9012345"
}
```

---

### 2.2 Login User
- **Endpoint:** `POST /api/auth/login`
- **Access:** Public
- **Description:** Authenticates user and establishes a session.

#### Request
```http
POST /api/auth/login HTTP/1.1
Content-Type: application/json

{
  "username": "coder_alex",
  "password": "Password123!"
}
```

#### Response (`200 OK`)
```http
HTTP/1.1 200 OK
Set-Cookie: codeadapt_session=a8f9c0e2...; HttpOnly; SameSite=Lax; Path=/
Content-Type: application/json

{
  "user": {
    "user_id": "usr_9b1deb4d3b7d4e5f",
    "username": "coder_alex",
    "email": "alex@example.edu",
    "role": "student",
    "created_at": "2026-10-13T10:30:00Z"
  },
  "session_token": "a8f9c0e2718293a4b5c6d7e8f9012345"
}
```

---

### 2.3 Logout User
- **Endpoint:** `POST /api/auth/logout`
- **Access:** Authenticated
- **Description:** Invalidates the current session token on the server and clears the session cookie.

#### Response (`200 OK`)
```http
HTTP/1.1 200 OK
Set-Cookie: codeadapt_session=; Max-Age=0; HttpOnly; SameSite=Lax; Path=/
Content-Type: application/json

{
  "ok": true,
  "message": "Successfully logged out."
}
```

---

### 2.4 Current User Profile
- **Endpoint:** `GET /api/auth/me`
- **Access:** Authenticated
- **Description:** Returns profile and role information for the currently active session.

#### Response (`200 OK`)
```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "user_id": "usr_9b1deb4d3b7d4e5f",
  "username": "coder_alex",
  "email": "alex@example.edu",
  "role": "student",
  "created_at": "2026-10-13T10:30:00Z"
}
```

---

## 3. Problem Library Endpoints

### 3.1 List All Problems
- **Endpoint:** `GET /api/problems` (and legacy `GET /problems`)
- **Access:** Authenticated / Public
- **Description:** Returns all problems available in the problem library. Note that researcher-facing metadata (`unenforceable_constraints`, `documented_limitations`) are included in the API for researcher inspection, but are strictly hidden from the student UI.

#### Response (`200 OK`)
```json
[
  {
    "problem_id": "PILOT-001",
    "title": "Move Zeroes",
    "concept": "Arrays",
    "difficulty": "Easy",
    "signature": "void moveZeroes(std::vector<int>& nums);",
    "test_count": 9,
    "statement": "Given an integer array `nums`, move all 0's to the end of it while maintaining the relative order of the non-zero elements.\n\nThe platform constructs the input vector and calls your function directly...",
    "constraints": [
      "1 <= nums.length <= 10^4",
      "-2^31 <= nums[i] <= 2^31 - 1"
    ],
    "note": "The intended solution uses O(1) auxiliary space...",
    "starter_code": "void moveZeroes(std::vector<int>& nums) {\n    // your code here\n}\n",
    "unenforceable_constraints": [
      "in-place / no copy of the array (O(1) auxiliary space) -- NOT OBSERVABLE by this harness. Never treat a pass as evidence the constraint was met."
    ],
    "documented_limitations": []
  },
  {
    "problem_id": "PILOT-005",
    "title": "First Position Not Less Than Target (Lower Bound)",
    "concept": "Binary Search",
    "difficulty": "Easy–Medium",
    "signature": "int lowerBound(const std::vector<int>& arr, int target);",
    "test_count": 8,
    "statement": "Given a sorted array `arr` in non-decreasing order, return the first index `i` such that `arr[i] >= target`...",
    "constraints": [
      "arr is sorted non-decreasing",
      "0 <= arr.size() <= 10^5",
      "values fit within the C++ int range"
    ],
    "note": null,
    "starter_code": "int lowerBound(const std::vector<int>& arr, int target) {\n    // your code here\n}\n",
    "unenforceable_constraints": [],
    "documented_limitations": [
      "A correct linear scan passes all 8 tests. PASS establishes task correctness only -- never that Binary Search was used or mastered.",
      "Expected O(log n) is a label. The harness performs no complexity enforcement of any kind.",
      "E1, E2 and E4 produce only P/R outcomes and are separable only by which specific tests fail, not by outcome type."
    ]
  }
]
```

---

### 3.2 Get Problem Detail
- **Endpoint:** `GET /api/problems/{problem_id}`
- **Access:** Authenticated / Public
- **Description:** Retrieves the complete problem specification for a single problem ID. Accepts canonical IDs (`PILOT-001`) or short aliases (`P1`, `p1`).

#### Response (`200 OK`)
```json
{
  "problem_id": "PILOT-005",
  "title": "First Position Not Less Than Target (Lower Bound)",
  "concept": "Binary Search",
  "difficulty": "Easy–Medium",
  "signature": "int lowerBound(const std::vector<int>& arr, int target);",
  "test_count": 8,
  "statement": "Given a sorted array `arr` in non-decreasing order...",
  "constraints": [
    "arr is sorted non-decreasing",
    "0 <= arr.size() <= 10^5",
    "values fit within the C++ int range"
  ],
  "note": null,
  "starter_code": "int lowerBound(const std::vector<int>& arr, int target) {\n    // your code here\n}\n",
  "unenforceable_constraints": [],
  "documented_limitations": [
    "A correct linear scan passes all 8 tests. PASS establishes task correctness only -- never that Binary Search was used or mastered."
  ]
}
```

---

### 3.3 Get Starter Code
- **Endpoint:** `GET /api/problems/{problem_id}/starter`
- **Access:** Authenticated / Public
- **Description:** Returns the starter code snippet for the specified problem.

#### Response (`200 OK`)
```json
{
  "problem_id": "PILOT-005",
  "starter_code": "int lowerBound(const std::vector<int>& arr, int target) {\n    // your code here\n}\n"
}
```

---

## 4. Submission & Execution Endpoints

### 4.1 Submit Solution
- **Endpoint:** `POST /api/submissions` (and legacy `POST /submissions`)
- **Access:** Authenticated (or Anonymous with auto-assigned session ID)
- **Description:** Submits student C++ code for sandboxed compilation and execution. Evaluates each test in its own isolated process, runs the secondary undefined behavior probe, records results in the database, and returns the complete execution record.

#### Request
```http
POST /api/submissions HTTP/1.1
Content-Type: application/json

{
  "problem_id": "PILOT-005",
  "code": "int lowerBound(const std::vector<int>& arr, int target) {\n    int lo = 0, hi = (int)arr.size();\n    while (lo < hi) {\n        int mid = lo + (hi - lo) / 2;\n        if (arr[mid] <= target) lo = mid + 1;\n        else hi = mid;\n    }\n    return lo;\n}",
  "submission_id": "sub_custom_uuid_optional",
  "parent_submission_id": "sub_previous_attempt_optional"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `problem_id` | string | Yes | Problem identifier (e.g. `PILOT-005` or `P5`). |
| `code` | string | Yes | Untrusted C++ source code authored by the student. |
| `submission_id` | string | No | Optional client-generated UUID for deduplication. |
| `parent_submission_id` | string | No | Optional UUID of the prior attempt to support attempt chaining. |

#### Response (`200 OK` — Compilation & Execution Succeeded)
```json
{
  "submission_id": "sub_c482e56ef5bf498a81358c2da73ea923",
  "problem_id": "PILOT-005",
  "concept": "Binary Search",
  "compile_status": "OK",
  "fingerprint": "FPPPFFPF",
  "limits": {
    "wall_timeout_s": 3.0,
    "memory_bytes": 268435456,
    "compiler": "C:/tools/.../g++.exe",
    "std": "c++17",
    "opt": "-O1",
    "compiler_version": "g++.exe (MinGW-W64 x86_64-ucrt-posix-seh) 16.1.0",
    "instrument_hash": "5fe83a411127192e",
    "isolation": "windows-job-object+low-integrity",
    "workdir_labelled_low": true,
    "ub_probe": "-D_GLIBCXX_ASSERTIONS"
  },
  "compile": {
    "command": "g++ -std=c++17 -O1 -w submission.cpp -o submission.exe",
    "stderr": "",
    "stderr_student_lines": "",
    "detail": null
  },
  "tests": [
    {
      "test_id": "T1",
      "expected_output": 2,
      "actual_output": 3,
      "status": "F",
      "execution_status": "COMPLETED",
      "runtime_ms": 14.2,
      "memory_bytes": 2486272,
      "exit_code": 0,
      "integrity": "low",
      "raw_stdout": "3",
      "stderr": null,
      "error": null,
      "ub_check": "clean",
      "ub_detail": null,
      "research": {
        "role": "Core",
        "diagnostic_target": "interior exact-match convergence",
        "confidence": "Medium",
        "informativeness": "High",
        "confound": "Low",
        "validation_type": "OUTPUT"
      }
    },
    {
      "test_id": "T2",
      "expected_output": 2,
      "actual_output": 2,
      "status": "P",
      "execution_status": "COMPLETED",
      "runtime_ms": 12.8,
      "memory_bytes": 2486272,
      "exit_code": 0,
      "integrity": "low",
      "raw_stdout": "2",
      "stderr": null,
      "error": null,
      "ub_check": "clean",
      "ub_detail": null,
      "research": {
        "role": "Core",
        "diagnostic_target": "interior absent-value convergence",
        "confidence": "Medium",
        "informativeness": "Medium",
        "confound": "Low",
        "validation_type": "OUTPUT"
      }
    }
  ]
}
```

#### Response (`200 OK` — Compilation Error)
When student code fails to compile, `compile_status` is `COMPILE_ERROR`. No tests are run, `tests` is empty, and `fingerprint` is `null`.

```json
{
  "submission_id": "sub_b753f82c1148495ba7225a43240ac879",
  "problem_id": "PILOT-005",
  "concept": "Binary Search",
  "compile_status": "COMPILE_ERROR",
  "fingerprint": null,
  "limits": {
    "wall_timeout_s": 3.0,
    "memory_bytes": 268435456,
    "compiler": "C:/tools/.../g++.exe",
    "std": "c++17",
    "opt": "-O1",
    "compiler_version": "16.1.0",
    "instrument_hash": "5fe83a411127192e",
    "isolation": "windows-job-object+low-integrity"
  },
  "compile": {
    "command": "g++ -std=c++17 -O1 -w submission.cpp -o submission.exe",
    "stderr": "submission.cpp:42:5: error: 'retrun' was not declared in this scope",
    "stderr_student_lines": "line 2: error: 'retrun' was not declared in this scope",
    "detail": null
  },
  "tests": []
}
```

---

### 4.2 Get Submission Record
- **Endpoint:** `GET /api/submissions/{submission_id}` (and legacy `GET /submissions/{id}`)
- **Access:** Owner of submission or Researcher
- **Description:** Returns the complete, unreduced execution record as executed and stored in the database.

#### Response (`200 OK`)
Returns the exact JSON record saved during submission.

---

### 4.3 Student Practice Recommendation
- **Endpoint:** `GET /api/submissions/{submission_id}/practice` (and legacy `GET /submissions/{id}/practice`)
- **Access:** Owner of submission or Researcher
- **Description:** Evaluates the submission's evidence through `diagnostics.interpret()` and returns a **student-safe pedagogical follow-up** response without exposing internal researcher error taxonomy labels.

#### Case 1: Task Correct (`task_correct` / All `P`)
```json
{
  "submission_id": "sub_c482e56ef5bf498a81358c2da73ea923",
  "problem_id": "PILOT-005",
  "state": "correct",
  "message": "Your solution produced the expected results on the tested cases. This does not establish mastery or that binary search was used.",
  "recommendation": {
    "action": "practice",
    "problem_id": "PILOT-001",
    "title": "Move Zeroes",
    "reason": "Continue with another existing problem in the curriculum."
  }
}
```

#### Case 2: Insufficient Evidence / Single Match or Ambiguous
```json
{
  "submission_id": "sub_355c52f1dcf74c26abacdd8853b384c8",
  "problem_id": "PILOT-005",
  "state": "insufficient_evidence",
  "message": "Your results are consistent with one supported pattern, but this is not proof of the underlying cause. Review duplicate handling and interval boundaries.",
  "recommendation": {
    "action": "retry",
    "problem_id": "PILOT-005",
    "title": "First Position Not Less Than Target (Lower Bound)",
    "reason": "Try this problem again with the same requirements."
  }
}
```

#### Case 3: Compilation Error (`no_execution_evidence`)
```json
{
  "submission_id": "sub_b753f82c1148495ba7225a43240ac879",
  "problem_id": "PILOT-005",
  "state": "no_execution_evidence",
  "message": "A diagnosis cannot be made because the code did not compile.",
  "compile_status": "COMPILE_ERROR",
  "compile_feedback": "line 2: error: 'retrun' was not declared in this scope",
  "recommendation": {
    "action": "retry",
    "problem_id": "PILOT-005",
    "title": "First Position Not Less Than Target (Lower Bound)",
    "reason": "Fix the compilation issue and retry this problem."
  }
}
```

---

## 5. Student Progress & History Endpoints

### 5.1 Student Submission History
- **Endpoint:** `GET /api/student/history`
- **Access:** Authenticated Student
- **Description:** Returns the chronological submission history for the logged-in student, including problem identifiers, timestamps, compile status, compact fingerprints, and attempt chaining links.

#### Response (`200 OK`)
```json
{
  "total_submissions": 3,
  "submissions": [
    {
      "submission_id": "sub_c482e56ef5bf498a81358c2da73ea923",
      "problem_id": "PILOT-005",
      "problem_title": "First Position Not Less Than Target (Lower Bound)",
      "concept": "Binary Search",
      "compile_status": "OK",
      "fingerprint": "PPPPPPPP",
      "created_at": "2026-10-13T10:45:00Z",
      "attempt_number": 2,
      "parent_submission_id": "sub_355c52f1dcf74c26abacdd8853b384c8"
    },
    {
      "submission_id": "sub_355c52f1dcf74c26abacdd8853b384c8",
      "problem_id": "PILOT-005",
      "problem_title": "First Position Not Less Than Target (Lower Bound)",
      "concept": "Binary Search",
      "compile_status": "OK",
      "fingerprint": "FPPPFFPF",
      "created_at": "2026-10-13T10:35:00Z",
      "attempt_number": 1,
      "parent_submission_id": null
    }
  ]
}
```

---

### 5.2 Student Progress Summary
- **Endpoint:** `GET /api/student/progress`
- **Access:** Authenticated Student
- **Description:** Returns overall concept completion and attempt counts computed strictly from stored submission records.

#### Response (`200 OK`)
```json
{
  "user_id": "usr_9b1deb4d3b7d4e5f",
  "solved_problems_count": 1,
  "total_problems_count": 5,
  "concepts": [
    {
      "concept": "Binary Search",
      "problem_id": "PILOT-005",
      "status": "solved",
      "attempts_count": 2,
      "last_attempt_at": "2026-10-13T10:45:00Z"
    },
    {
      "concept": "Arrays",
      "problem_id": "PILOT-001",
      "status": "not_started",
      "attempts_count": 0,
      "last_attempt_at": null
    }
  ]
}
```

---

## 6. Researcher Workspace Endpoints

All endpoints in this section are protected by backend role gating (`role IN ('researcher', 'admin')`). If an authenticated student requests any of these endpoints, the server returns `403 Forbidden`.

### 6.1 List Cohort Submissions
- **Endpoint:** `GET /api/research/submissions`
- **Access:** Researcher Only
- **Query Parameters:**
  - `problem_id` (optional): Filter by problem (e.g. `PILOT-005`).
  - `verdict` (optional): Filter by diagnostic verdict (`task_correct`, `single_match`, `ambiguous`, `unmodelled`, `no_execution_evidence`).
  - `fingerprint` (optional): Filter by exact fingerprint string (e.g. `FPPPFFPF`).
  - `limit` (default: 50, max: 200).
  - `offset` (default: 0).

#### Response (`200 OK`)
```json
{
  "total_count": 42,
  "submissions": [
    {
      "submission_id": "sub_355c52f1dcf74c26abacdd8853b384c8",
      "user_id": "usr_9b1deb4d3b7d4e5f",
      "username": "coder_alex",
      "problem_id": "PILOT-005",
      "compile_status": "OK",
      "fingerprint": "FPPPFFPF",
      "instrument_hash": "5fe83a411127192e",
      "created_at": "2026-10-13T10:35:00Z",
      "verdict": "single_match",
      "matched_errors": ["E3_upper_bound"],
      "has_ub_violation": false
    }
  ]
}
```

---

### 6.2 Submission Diagnostic Deep-Dive
- **Endpoint:** `GET /api/research/submissions/{submission_id}/diagnostics` (and legacy `GET /submissions/{id}/diagnostics`)
- **Access:** Researcher Only
- **Description:** Returns the complete diagnostic attribution trace, candidate error scores, reference diffs, excluded undefined behavior cells, and observed outputs for manual discrimination.

#### Response (`200 OK`)
```json
{
  "problem_id": "PILOT-005",
  "observed": "FPPPFFPF",
  "test_ids": ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"],
  "excluded_cells": [],
  "dynamic_ub_cells": [],
  "reference_ub_cells": {
    "E1_missing_increment": [],
    "E2_loop_condition": ["T4", "T7"],
    "E3_upper_bound": [],
    "E4_upper_mid": ["T4", "T8"]
  },
  "verdict": "single_match",
  "matched": ["E3_upper_bound"],
  "cells_compared": 8,
  "summary": "The full pattern matches one modelled error: computing upper bound instead of lower bound. This is evidence consistent with that error class, not proof of it. Matching uses P/F/R only, and a different mistake can produce an identical row -- verified: a submission returning n whenever the target is found yields P5's E3 row exactly, while returning different values. Check observed_outputs before relying on this attribution.",
  "instrument_hash": "5fe83a411127192e",
  "candidates": [
    {
      "error": "E3_upper_bound",
      "reference": "FPPPFFPF",
      "reference_ub_cells": [],
      "mismatched_tests": [],
      "cells_compared": 8,
      "exact": true,
      "description": "computing upper bound instead of lower bound"
    },
    {
      "error": "correct",
      "reference": "PPPPPPPP",
      "reference_ub_cells": [],
      "mismatched_tests": ["T1", "T5", "T6", "T8"],
      "cells_compared": 8,
      "exact": false,
      "description": null
    }
  ],
  "observed_outputs": [
    {
      "test_id": "T1",
      "expected": 2,
      "actual": 3,
      "status": "F"
    },
    {
      "test_id": "T2",
      "expected": 2,
      "actual": 2,
      "status": "P"
    }
  ]
}
```

---

### 6.3 Problem Reference Matrices & Benchmarks
- **Endpoint:** `GET /api/research/problems/{problem_id}/matrices` (and legacy `GET /problems/{id}/fingerprints`)
- **Access:** Researcher Only
- **Description:** Returns the verified reference fingerprints, documented claims, static UB cell declarations, and known collision sets for the problem.

#### Response (`200 OK`)
```json
{
  "problem_id": "PILOT-005",
  "reference_matrix": {
    "correct": "PPPPPPPP",
    "linear_scan": "PPPPPPPP",
    "E1_missing_increment": "RRPRPRPP",
    "E2_loop_condition": "RRRFRRRR",
    "E3_upper_bound": "FPPPFFPF",
    "E4_upper_mid": "PPRFRRPR"
  },
  "documented_claims": {
    "correct": "PPPPPPPP",
    "linear_scan": "PPPPPPPP",
    "E1_missing_increment": "RRPRPRPP",
    "E2_loop_condition": "RRRRRRRR",
    "E3_upper_bound": "FPPPFFPF",
    "E4_upper_mid": "PPRRRRPR"
  },
  "documented_divergences": [
    {
      "error": "E2_loop_condition",
      "doc_claimed": "RRRRRRRR",
      "observed": "RRRFRRRR",
      "divergent_cells": ["T4: doc=R observed=F"]
    },
    {
      "error": "E4_upper_mid",
      "doc_claimed": "PPRRRRPR",
      "observed": "PPRFRRPR",
      "divergent_cells": ["T4: doc=R observed=F"]
    }
  ],
  "ub_dependent_cells": {
    "E2_loop_condition": ["T4", "T7"],
    "E4_upper_mid": ["T4", "T8"]
  },
  "known_collisions": [
    ["correct", "linear_scan"]
  ],
  "error_descriptions": {
    "E1_missing_increment": "omitting the +1 when advancing the lower bound",
    "E2_loop_condition": "an off-by-one termination condition",
    "E3_upper_bound": "computing upper bound instead of lower bound",
    "E4_upper_mid": "an upper-mid convention the bounds check does not match"
  }
}
```

---

### 6.4 Research Cohort Telemetry
- **Endpoint:** `GET /api/research/telemetry`
- **Access:** Researcher Only
- **Description:** Provides aggregated telemetry metrics across all submissions for experimental tracking.

#### Response (`200 OK`)
```json
{
  "total_submissions": 128,
  "unique_students": 24,
  "verdict_distribution": {
    "task_correct": 48,
    "single_match": 36,
    "ambiguous": 14,
    "unmodelled": 18,
    "no_execution_evidence": 12
  },
  "ub_violations_detected": 15,
  "active_instrument_hashes": [
    "5fe83a411127192e"
  ]
}
```

---

### 6.5 Export Dataset
- **Endpoint:** `GET /api/research/export?format=json`
- **Access:** Researcher Only
- **Description:** Streams complete verbatim database records in JSON or CSV for offline analysis.

---

## 7. System Health Endpoint

### 7.1 Health & Environment Limits
- **Endpoint:** `GET /api/health` (and legacy `GET /health`)
- **Access:** Public
- **Description:** Returns service operational status, compiler configuration, and sandbox limits.

#### Response (`200 OK`)
```json
{
  "ok": true,
  "limits": {
    "wall_timeout_s": 3.0,
    "memory_mb": 256,
    "compiler": "C:/tools/winlibs-x86_64-posix-seh-gcc-16.1.0-mingw-w64ucrt-14.0.0-r4/mingw64/bin/g++.exe",
    "std": "c++17",
    "opt": "-O1",
    "max_concurrent": 4
  }
}
```
