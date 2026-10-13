"""HTTP surface for CodeAdapt with authentication and role-based authorization.

Enforces:
- Student registration and secure login with Argon2id password hashing.
- Persistent session management via secure HTTP-only cookies and Bearer tokens.
- Strict role-based authorization: Students cannot access researcher endpoints or
  inspect another student's private submissions.
- Cognitive firewall: Researcher diagnostic error labels are never surfaced to students.
- Preserved backward compatibility with legacy endpoints and tests.
"""
import os
import re
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr

import auth
import diagnostics
import executor
import problems
import recommendations
import research
import store

app = FastAPI(title="CodeAdapt Platform", version="0.2.0")
store.init()
executor.sweep()   # sweep any work directory a previous run could not delete

COOKIE_NAME = "codeadapt_session"
COOKIE_SECURE = os.environ.get("SI_COOKIE_SECURE", "0") == "1"


# --- Request/Response Models -----------------------------------------------

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    role: Optional[str] = "student"  # Server strictly ignores/overrides this


class LoginRequest(BaseModel):
    username: str  # Can be username or email
    password: str


class SubmissionRequest(BaseModel):
    problem_id: str
    code: str
    submission_id: Optional[str] = None
    parent_submission_id: Optional[str] = None


# --- Authentication & Authorization Dependencies -------------------------

def get_current_user_optional(request: Request) -> Optional[dict]:
    """Extract authenticated user if session exists; returns None otherwise."""
    token = None
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    elif COOKIE_NAME in request.cookies:
        token = request.cookies[COOKIE_NAME]

    if not token:
        return None

    return auth.get_session(token)


def get_current_user(request: Request,
                     user: Optional[dict] = Depends(get_current_user_optional)) -> dict:
    """Require an authenticated user session."""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    return user


def require_researcher(user: dict = Depends(get_current_user)) -> dict:
    """Require researcher or admin privileges."""
    if user.get("role") not in ("researcher", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Researcher privileges required"
        )
    return user


def check_csrf(request: Request, user: Optional[dict]):
    """Verify CSRF token for state-changing cookie-authenticated requests."""
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        # Bearer token requests are immune to CSRF
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return
        # If authenticated via cookie, require matching X-CSRF-Token header
        if user and COOKIE_NAME in request.cookies:
            header_csrf = request.headers.get("x-csrf-token")
            if not header_csrf or header_csrf != user.get("csrf_token"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Invalid or missing CSRF token"
                )


# --- Authentication Routes -----------------------------------------------

@app.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest, response: Response):
    try:
        user_dict = auth.register_user(req.username, req.email, req.password)
    except auth.ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except auth.DuplicateAccountError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    # Auto-login on successful registration
    token, csrf_token, _ = auth.create_session(user_dict["user_id"])
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        path="/"
    )
    return {
        "user": user_dict,
        "csrf_token": csrf_token,
        "session_token": token
    }


@app.post("/api/auth/login")
@app.post("/auth/login")
def login(req: LoginRequest, response: Response):
    try:
        user_dict = auth.authenticate_user(req.username, req.password)
    except auth.InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    token, csrf_token, _ = auth.create_session(user_dict["user_id"])
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        path="/"
    )
    return {
        "user": {
            "user_id": user_dict["user_id"],
            "username": user_dict["username"],
            "email": user_dict["email"],
            "role": user_dict["role"],
            "created_at": user_dict.get("created_at")
        },
        "csrf_token": csrf_token,
        "session_token": token
    }


@app.post("/api/auth/logout")
@app.post("/auth/logout")
def logout(request: Request, response: Response):
    token = None
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    elif COOKIE_NAME in request.cookies:
        token = request.cookies[COOKIE_NAME]

    if token:
        auth.invalidate_session(token)

    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"ok": True, "message": "Successfully logged out"}


@app.get("/api/auth/me")
@app.get("/auth/me")
def me(user: dict = Depends(get_current_user)):
    return {
        "user_id": user["user_id"],
        "username": user["username"],
        "email": user["email"],
        "role": user["role"],
        "created_at": user.get("created_at"),
        "csrf_token": user.get("csrf_token")
    }


# --- System Health & Problem Catalog -------------------------------------

@app.get("/health")
@app.get("/api/health")
def health():
    return {"ok": True, "limits": {
        "wall_timeout_s": executor.WALL_TIMEOUT_S,
        "memory_mb": executor.MEMORY_BYTES // (1024 * 1024),
        "compiler": executor.GXX, "std": executor.CXX_STD,
        "opt": executor.OPT_LEVEL, "max_concurrent": executor.MAX_CONCURRENT}}


@app.get("/problems")
@app.get("/api/problems")
def list_problems():
    out = []
    for p in problems.PROBLEMS.values():
        text = problems.STATEMENTS.get(p["problem_id"], {})
        out.append({"problem_id": p["problem_id"], "title": p["title"],
                    "concept": p["concept"], "signature": p["signature"],
                    "test_count": len(p["tests"]),
                    "statement": text.get("statement"),
                    "constraints": text.get("constraints", []),
                    "note": text.get("note"),
                    "starter_code": problems.STARTER.get(p["problem_id"], ""),
                    "unenforceable_constraints": p.get("unenforceable_constraints", []),
                    "documented_limitations": p.get("documented_limitations", [])})
    return out


@app.get("/api/problems/{problem_id}")
def get_problem(problem_id: str):
    try:
        p = problems.get(problem_id)
    except KeyError:
        raise HTTPException(404, f"unknown problem_id {problem_id!r}")
    text = problems.STATEMENTS.get(p["problem_id"], {})
    return {
        "problem_id": p["problem_id"], "title": p["title"],
        "concept": p["concept"], "signature": p["signature"],
        "test_count": len(p["tests"]),
        "statement": text.get("statement"),
        "constraints": text.get("constraints", []),
        "note": text.get("note"),
        "starter_code": problems.STARTER.get(p["problem_id"], ""),
        "unenforceable_constraints": p.get("unenforceable_constraints", []),
        "documented_limitations": p.get("documented_limitations", [])
    }


@app.get("/api/problems/{problem_id}/starter")
def get_starter(problem_id: str):
    try:
        pid = problems.get(problem_id)["problem_id"]
    except KeyError:
        raise HTTPException(404, f"unknown problem_id {problem_id!r}")
    return {"problem_id": pid, "starter_code": problems.STARTER.get(pid, "")}


# --- Submissions & Execution ----------------------------------------------

@app.post("/submissions")
@app.post("/api/submissions")
def submit(sub: SubmissionRequest, request: Request,
           current_user: Optional[dict] = Depends(get_current_user_optional)):
    try:
        problems.get(sub.problem_id)
    except KeyError:
        raise HTTPException(404, "unknown problem_id %r" % sub.problem_id)

    # Validate CSRF if user is authenticated via cookie
    check_csrf(request, current_user)

    user_id = current_user["user_id"] if current_user else None

    # Validate parent_submission_id ownership if provided
    if sub.parent_submission_id:
        parent_meta = store.get_submission_meta(sub.parent_submission_id)
        if parent_meta is None:
            raise HTTPException(404, "unknown parent_submission_id %r" % sub.parent_submission_id)
        if parent_meta.get("user_id"):
            if not current_user:
                raise HTTPException(401, "Authentication required to link to this submission")
            is_parent_owner = current_user["user_id"] == parent_meta["user_id"]
            is_researcher = current_user.get("role") in ("researcher", "admin")
            if not (is_parent_owner or is_researcher):
                raise HTTPException(403, "Cannot link follow-up attempt to another student's submission")

    # evaluate() is synchronous and CPU/process bound; runs in threadpool
    record = executor.evaluate(sub.problem_id, sub.code, sub.submission_id)
    record["fingerprint"] = executor.fingerprint(record)
    if user_id:
        record["user_id"] = user_id
    if sub.parent_submission_id:
        record["parent_submission_id"] = sub.parent_submission_id

    # Persist the COMPLETE record verbatim before returning response
    store.save(record, record["fingerprint"], user_id=user_id,
               parent_submission_id=sub.parent_submission_id)

    # Drop generated source from the HTTP response; retained in database record
    record["compile"] = {k: v for k, v in record["compile"].items()
                         if k != "generated_source"}
    return record


@app.get("/submissions/{submission_id}")
@app.get("/api/submissions/{submission_id}")
def get_submission(submission_id: str,
                   current_user: Optional[dict] = Depends(get_current_user_optional)):
    """Retrieve execution record. Enforces privacy for registered submissions."""
    rec = store.load(submission_id)
    if rec is None:
        raise HTTPException(404, "unknown submission_id")

    # If submission belongs to a registered student, verify permission
    if rec.get("user_id"):
        if not current_user:
            raise HTTPException(401, "Authentication required to view this submission")
        is_owner = current_user["user_id"] == rec["user_id"]
        is_researcher = current_user.get("role") in ("researcher", "admin")
        if not (is_owner or is_researcher):
            raise HTTPException(403, "Access to private submission denied")

    return rec


@app.get("/problems/{problem_id}/fingerprints")
def problem_fingerprints(problem_id: str):
    try:
        pid = problems.get(problem_id)["problem_id"]
    except KeyError:
        raise HTTPException(404, "unknown problem_id %r" % problem_id)
    return store.fingerprints(pid)


# --- Diagnostic & Practice Endpoints --------------------------------------

@app.get("/submissions/{submission_id}/diagnostics")
@app.get("/api/research/submissions/{submission_id}/diagnostics")
def submission_diagnostics(submission_id: str,
                           researcher: dict = Depends(require_researcher)):
    """Researcher-facing only. Strictly barred from student access to prevent
    cognitive priming."""
    rec = store.load(submission_id)
    if rec is None:
        raise HTTPException(404, "unknown submission_id")
    return diagnostics.interpret(rec)


def _practice_response(rec):
    return recommendations.generate_practice_response(rec)


@app.get("/submissions/{submission_id}/practice")
@app.get("/api/submissions/{submission_id}/practice")
def submission_practice(submission_id: str,
                        current_user: Optional[dict] = Depends(get_current_user_optional)):
    """Return a student-safe follow-up without exposing research labels.
    
    Enforces privacy: students can only access practice follow-ups for their own submissions.
    """
    rec = store.load(submission_id)
    if rec is None:
        raise HTTPException(404, "unknown submission_id")

    if rec.get("user_id"):
        if not current_user:
            raise HTTPException(401, "Authentication required to view this submission")
        is_owner = current_user["user_id"] == rec["user_id"]
        is_researcher = current_user.get("role") in ("researcher", "admin")
        if not (is_owner or is_researcher):
            raise HTTPException(403, "Access to private submission denied")

    return _practice_response(rec)


@app.get("/submissions/{submission_id}/chain")
@app.get("/api/submissions/{submission_id}/chain")
def submission_chain(submission_id: str,
                     current_user: Optional[dict] = Depends(get_current_user_optional)):
    """Retrieve full sequence of related attempts (root + follow-ups)."""
    meta = store.get_submission_meta(submission_id)
    if meta is None:
        raise HTTPException(404, "unknown submission_id")

    if meta.get("user_id"):
        if not current_user:
            raise HTTPException(401, "Authentication required to view submission history")
        is_owner = current_user["user_id"] == meta["user_id"]
        is_researcher = current_user.get("role") in ("researcher", "admin")
        if not (is_owner or is_researcher):
            raise HTTPException(403, "Access to private submission chain denied")

    chain = store.get_submission_chain(submission_id)
    return {
        "submission_id": submission_id,
        "chain": chain,
        "total_attempts": len(chain)
    }


# --- Student Progress & History -------------------------------------------

@app.get("/api/student/profile")
def student_profile(user: dict = Depends(get_current_user)):
    return {
        "user_id": user["user_id"],
        "username": user["username"],
        "email": user["email"],
        "role": user["role"],
        "created_at": user.get("created_at"),
    }


@app.get("/api/student/history")
def student_history(user: dict = Depends(get_current_user)):
    subs = store.list_submissions(user_id=user["user_id"], limit=100)
    for s in subs:
        try:
            p = problems.get(s["problem_id"])
            s["title"] = p["title"]
            s["concept"] = p["concept"]
        except KeyError:
            s["title"] = s["problem_id"]
            s["concept"] = "General"

        # Determine explicit verdict based on real execution status & fingerprint
        if s["compile_status"] != "OK":
            s["verdict"] = "Compilation Error"
        elif s.get("fingerprint") and set(s["fingerprint"]) == {"P"}:
            s["verdict"] = "Accepted"
        elif s.get("fingerprint") and "R" in s["fingerprint"]:
            s["verdict"] = "Runtime Error / Timeout"
        elif s.get("fingerprint") and "F" in s["fingerprint"]:
            s["verdict"] = "Wrong Answer"
        else:
            s["verdict"] = "Evaluated"

    return {
        "user_id": user["user_id"],
        "total": len(subs),
        "submissions": subs
    }


@app.get("/api/student/progress")
def student_progress(user: dict = Depends(get_current_user)):
    subs = store.list_submissions(user_id=user["user_id"], limit=500)
    solved_problems = set()
    attempts_per_problem = {}

    for s in subs:
        pid = s["problem_id"]
        attempts_per_problem[pid] = attempts_per_problem.get(pid, 0) + 1
        if s["compile_status"] == "OK" and s["fingerprint"] and set(s["fingerprint"]) == {"P"}:
            solved_problems.add(pid)

    all_probs = [
        {"problem_id": p["problem_id"], "title": p["title"], "concept": p["concept"],
         "status": "solved" if p["problem_id"] in solved_problems else
                   ("attempted" if p["problem_id"] in attempts_per_problem else "unsolved"),
         "attempts": attempts_per_problem.get(p["problem_id"], 0)}
        for p in problems.PROBLEMS.values()
    ]

    return {
        "user_id": user["user_id"],
        "solved_count": len(solved_problems),
        "total_problems": len(problems.PROBLEMS),
        "problems": all_probs
    }


# --- Researcher Endpoints -------------------------------------------------

@app.get("/api/research/overview")
def research_overview(researcher: dict = Depends(require_researcher)):
    """Aggregate research telemetry, problem coverage, and missing data indicators."""
    return research.get_research_overview()


@app.get("/api/research/submissions")
def research_list_submissions(problem_id: Optional[str] = None,
                              compile_status: Optional[str] = None,
                              search: Optional[str] = None,
                              limit: int = 50, offset: int = 0,
                              researcher: dict = Depends(require_researcher)):
    """Search, filter, and page stored submissions."""
    total = store.count_submissions(problem_id=problem_id, compile_status=compile_status, search=search)
    subs = store.list_submissions(problem_id=problem_id, compile_status=compile_status,
                                  search=search, limit=limit, offset=offset)
    return {"total": total, "limit": limit, "offset": offset, "submissions": subs}


@app.get("/api/research/submissions/{submission_id}")
def research_submission_detail(submission_id: str,
                               researcher: dict = Depends(require_researcher)):
    """Inspect full verbatim execution record, classified failures, and per-test outcomes."""
    detail = research.get_submission_detail(submission_id)
    if detail is None:
        raise HTTPException(404, f"unknown submission_id {submission_id!r}")
    return detail


@app.get("/api/research/submissions/{submission_id}/decision-trace")
def research_decision_trace(submission_id: str,
                            researcher: dict = Depends(require_researcher)):
    """Inspect diagnostic decision trace, candidate rules, excluded UB cells, and abstentions."""
    trace = research.get_decision_trace(submission_id)
    if trace is None:
        raise HTTPException(404, f"unknown submission_id {submission_id!r}")
    return trace


@app.get("/api/research/evaluation")
def research_evaluation(researcher: dict = Depends(require_researcher)):
    """Evaluation metrics distinguishing synthetic benchmarks from unannotated student data."""
    return research.get_research_evaluation()


@app.get("/api/research/limitations")
def research_limitations(researcher: dict = Depends(require_researcher)):
    """Documented research divergences, UB probe caveats, and construct validity limits."""
    return research.get_instrument_limitations()


@app.get("/api/research/telemetry")
def research_telemetry(researcher: dict = Depends(require_researcher)):
    """Legacy telemetry endpoint for backward compatibility."""
    return research.get_research_overview()


@app.get("/api/research/problems/{problem_id}/matrices")
def research_problem_matrices(problem_id: str,
                              researcher: dict = Depends(require_researcher)):
    try:
        p = problems.get(problem_id)
        pid = p["problem_id"]
    except KeyError:
        raise HTTPException(404, f"unknown problem_id {problem_id!r}")

    short_id = diagnostics._alias(pid)
    return {
        "problem_id": pid,
        "concept": p["concept"],
        "reference": diagnostics.REFERENCE.get(short_id, {}),
        "ub_dependent_cells": [
            {"error": k[1], "cells": v}
            for k, v in diagnostics.UB_DEPENDENT_CELLS.items() if k[0] == short_id
        ],
        "known_collisions": diagnostics.KNOWN_COLLISIONS.get(short_id, []),
        "descriptions": diagnostics.DESCRIPTIONS.get(short_id, {})
    }


# --- Static Frontend Serving ---------------------------------------------

_STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.isdir(_STATIC):
    app.mount("/static", StaticFiles(directory=_STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(_STATIC, "index.html"))


@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)
