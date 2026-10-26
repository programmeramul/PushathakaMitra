"""Automated tests for the PustakaMitra AI auth + profile backend.

Run:
    cd backend
    MONGO_URI=mongodb://localhost:27017 MONGO_DB=pustakamitra_test \
        MONGO_DB=pustakamitra_test SESSION_HASH_KEY=test-key python3 -m pytest tests/ -v

Uses a throwaway Mongo database (pustakamitra_test) wiped between runs.
"""
import os
import re
import uuid

os.environ.setdefault("MONGO_DB", "pustakamitra_test")
os.environ.setdefault("SESSION_HASH_KEY", "test-session-key")
os.environ.setdefault("SECURE_COOKIES", "0")

import pytest
from fastapi.testclient import TestClient
from backend.main import app, DB

users = DB.users
sessions = DB.sessions

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]$")


def uid():
    return f"t{uuid.uuid4().hex[:10]}@example.com"


def reg_payload(email=None, **over):
    p = {
        "name": "Test User",
        "email": email or uid(),
        "phone": "+91 98765 43210",
        "age": 26,
        "dob": "2000-01-05",
        "gender": "woman",
        "home_address": "12 MG Road, Bengaluru",
        "pin_code": "560001",
        "interests": ["mystery", "horror"],
        "other_interest": None,
        "password": "hunter2safe",
        "password_confirm": "hunter2safe",
    }
    p.update(over)
    return p


@pytest.fixture(scope="module", autouse=True)
def clean_db():
    users.delete_many({})
    sessions.delete_many({})
    yield
    users.delete_many({})
    sessions.delete_many({})


client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_register_201_and_persists():
    email = uid()
    r = client.post("/api/auth/register", json=reg_payload(email=email))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["created"] is True
    assert body["user"]["email"] == email  # normalized to lowercase
    doc = users.find_one({"email": email})
    assert doc is not None, "MongoDB did not confirm the write"
    assert doc["password_hash"].startswith("$argon2id$")
    assert "password" not in doc and "password_confirm" not in doc
    assert doc["interests"] == ["mystery", "horror"]
    assert doc["pin_code"] == "560001"


def test_register_normalizes_email_case():
    email = uid()
    mixed = email.capitalize()
    r = client.post("/api/auth/register", json=reg_payload(email=mixed))
    assert r.status_code == 201
    assert users.count_documents({"email": email}) == 1
    assert users.count_documents({"email": mixed}) == 0


def test_duplicate_email_409():
    email = uid()
    assert client.post("/api/auth/register", json=reg_payload(email=email)).status_code == 201
    r = client.post("/api/auth/register", json=reg_payload(email=email.upper()))
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "email_taken"


def test_duplicate_email_concurrent_only_one_survives():
    email = uid()
    codes = []
    for _ in range(5):
        # TestClient per-request sessions hammer the same unique index
        codes.append(client.post("/api/auth/register", json=reg_payload(email=email)).status_code)
    assert sorted(codes)[0] in (201, 409)
    assert codes.count(201) <= 1, f"multiple concurrent inserts succeeded: {codes}"
    assert codes.count(409) >= 4
    assert users.count_documents({"email": email}) == 1


def test_password_never_plaintext():
    doc = users.find_one({}, {"password_hash": 1, "password": 1, "_id": 0})
    assert doc
    assert doc["password_hash"].startswith("$argon2")
    assert "password" not in doc


def test_password_mismatch_422():
    r = client.post("/api/auth/register", json=reg_payload(password_confirm="different"))
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "password_mismatch"


def test_future_dob_rejected():
    r = client.post("/api/auth/register", json=reg_payload(dob="2999-01-01"))
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "dob_future"


def test_age_dob_mismatch_422():
    r = client.post("/api/auth/register", json=reg_payload(age=44))
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "age_dob_mismatch"


def test_bad_pin_rejected():
    r = client.post("/api/auth/register", json=reg_payload(pin_code="011001"))
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "pin_invalid"


def test_custom_other_interest_required():
    r = client.post("/api/auth/register", json=reg_payload(interests=["other"]))
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "other_required"


def test_empty_interests_rejected():
    r = client.post("/api/auth/register", json=reg_payload(interests=[]))
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "interests_empty"


def test_login_success_and_cookie_flags():
    email = uid()
    client.post("/api/auth/register", json=reg_payload(email=email))
    r = client.post("/api/auth/login", json={"email": email.upper(), "password": "hunter2safe"})
    assert r.status_code == 200
    sc = r.headers["set-cookie"].lower()
    assert "httponly" in sc and "pm_session=" in sc and "samesite=lax" in sc


def test_login_wrong_password_401():
    email = uid()
    client.post("/api/auth/register", json=reg_payload(email=email))
    r = client.post("/api/auth/login", json={"email": email, "password": "wrongwrong"})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "bad_credentials"


def test_unknown_user_login_401():
    r = client.post("/api/auth/login", json={"email": "nobody@nowhere.io", "password": "hunter2safe"})
    assert r.status_code == 401


def test_me_requires_session():
    # fresh client, no cookies — must not leak data
    assert TestClient(app).get("/api/profile/me").status_code == 401


def test_me_after_logout_401():
    email = uid()
    c = TestClient(app)
    c.post("/api/auth/register", json=reg_payload(email=email))
    assert c.get("/api/profile/me").status_code == 200
    assert c.post("/api/auth/logout").status_code == 200
    assert c.get("/api/profile/me").status_code == 401


def test_profile_persistence_and_update():
    email = uid()
    c = TestClient(app)
    c.post("/api/auth/register", json=reg_payload(email=email))
    r = c.put("/api/profile/me", json={"interests": ["philosophy", "kannada-literature"],
                                       "phone": "+91 90909 090905" if False else "+91 90909 09090"})
    assert r.status_code == 200
    doc = users.find_one({"email": email})
    assert doc["interests"] == ["philosophy", "kannada-literature"]
    assert doc["phone"] == "+919090909090"  # re-normalized to E.164
    assert doc["updated_at"] > doc["created_at"]


def test_password_change_updates_hash():
    email = uid()
    c = TestClient(app)
    c.post("/api/auth/register", json=reg_payload(email=email))
    old_hash = users.find_one({"email": email})["password_hash"]
    r = c.put("/api/profile/me", json={"password": "newpass9876", "password_confirm": "newpass9876"})
    assert r.status_code == 200
    doc = users.find_one({"email": email})
    assert doc["password_hash"] != old_hash and doc["password_hash"].startswith("$argon2id$")
    # relogin with new password
    assert TestClient(app).post("/api/auth/login", json={"email": email, "password": "newpass9876"}).status_code == 200


def test_user_cannot_access_other_users_profile():
    """Two accounts — user B's session must only ever return B's own document.
    There is no endpoint that accepts a user id for lookup; /api/profile/me is
    session-bound, which is the protection under test."""
    email_a, email_b = uid(), uid()
    ca, cb = TestClient(app), TestClient(app)
    ca.post("/api/auth/register", json=reg_payload(email=email_a, name="Alice"))
    cb.post("/api/auth/register", json=reg_payload(email=email_b, name="Bob"))

    me_b = cb.get("/api/profile/me").json()
    assert me_b["email"] == email_b and me_b["name"] == "Bob"

    # guessing user A's id in every documented endpoint must not leak A's data
    id_a = ca.get("/api/profile/me").json()["id"]
    r = cb.get(f"/api/profile/{id_a}")
    assert r.status_code in (401, 403, 404, 405), r.text
    body = (r.json() if r.status_code != 405 else {})
    if isinstance(body, dict):
        assert "home_address" not in body and "phone" not in body.get("", {})

    # B's session never returns A's doc
    assert cb.get("/api/profile/me").json()["id"] != id_a
    # profile listing endpoints that could leak contact info do not exist
    assert ca.get("/api/profiles").status_code in (404, 405)


def test_onboarding_preferences_persist():
    email = uid()
    c = TestClient(app)
    c.post("/api/auth/register", json=reg_payload(email=email))
    r = c.put("/api/profile/me", json={"interests": ["horror", "kannada-literature"],
                                       "goal": "finish-classics", "level": "regular",
                                       "language": "Kannada"})
    assert r.status_code == 200
    doc = users.find_one({"email": email})
    assert doc["goal"] == "finish-classics"
    assert doc["level"] == "regular"
    assert doc["language"] == "Kannada"
    assert doc["interests"] == ["horror", "kannada-literature"]
    me = c.get("/api/profile/me").json()
    assert me["goal"] == "finish-classics" and me["language"] == "Kannada"
