"""PustakaMitra AI backend — FastAPI + MongoDB.

Registration/login/profile endpoints with:
- Argon2id password hashing (argon2-cffi); plaintext never stored
- unique normalized (lowercased) email via a MongoDB unique index;
  duplicateDoc KeyErrors — including concurrent inserts — mapped to a 409
- server-managed sessions in Mongo (TTL index) behind HTTP-only cookies;
  cookie value is opaque; Mongo stores only a keyed SHA-256 of it
- profile edits allowed after registration; email immutably keys the account
- privacy: GET endpoints return the caller's own doc only; no endpoint ever
  returns any other user's phone/address/PIN

Kept out of the frontend: Mongo credentials and hashing/session secrets come
from environment variables only.
"""
import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import uvicorn
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from pymongo import MongoClient, errors

SESSION_COOKIE = "pm_session"
SESSION_TTL_MIN = int(os.environ.get("SESSION_TTL_MIN", "180"))
SESSION_HASH_KEY = os.environ.get("SESSION_HASH_KEY", "dev-only-session-key")
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.environ.get("MONGO_DB", "pustakamitra")  # tests override to pustakamitra_test
SECURE_COOKIES = os.environ.get("SECURE_COOKIES") == "1"

ph = PasswordHasher()

DB = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)[MONGO_DB]
users = DB.users
sessions = DB.sessions


def _ensure_indexes() -> None:
    users.create_index([("email", 1)], unique=True, name="uq_email")
    users.create_index([("interests", 1)], name="ix_interests")
    sessions.create_index([("sid", 1)], unique=True, name="uq_sid")
    # TTL index: Mongo autoremoves expired session docs
    sessions.create_index([("expires_at", 1)], name="ttl_sessions",
                          expireAfterSeconds=0)


_ensure_indexes()


def _fail(status: int, code: str, msg: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": msg})


def _keyed(sid: str) -> str:
    return hashlib.sha256((SESSION_HASH_KEY + sid).encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------- validation -------------------------------
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PIN_RE = re.compile(r"^[1-9][0-9]{5}$")

CANON_CLASSES = {
    "IN": {"country": "+91", "digits": 10, "first": (6, 9)},  # 10-digit mobile, first digit 6-9
    "US": {"country": "+1", "digits": 10, "first": (2, 9)},
    "GB": {"country": "+44", "digits": 10, "first": (1, 9)},
}

GENRES = {
    "horror", "supernatural", "spirituality", "mystery", "thriller", "fantasy",
    "romance", "science-fiction", "technology", "self-development",
    "biography", "history", "philosophy", "kannada-literature", "other",
}
GENDERS = {"man", "woman", "non-binary", "prefer-to-self-describe", "prefer-not-to-say"}


def _validate_phone(raw: str, country: str = "IN") -> str:
    """Validate loosely but persistently: strip separators, keep E.164 output.
    Per-country digit rules instead of a universal 'exactly 10 digits'."""
    rule = CANON_CLASSES.get(country.upper())
    if not rule:
        raise _fail(422, "phone_country", "Unsupported country code")
    digits = re.sub(r"[^0-9]", "", raw)
    if digits.startswith("0"):
        digits = digits.lstrip("0")
    if digits.startswith(rule["country"].lstrip("+")) and len(digits) > rule["digits"]:
        digits = digits[len(rule["country"].lstrip("+")):]
    if len(digits) != rule["digits"] or not digits[0].isdigit() or not (int(rule["first"][0]) <= int(digits[0]) <= int(rule["first"][1])):
        raise _fail(422, "phone_invalid",
                    f"Enter a valid {country} mobile number ({rule['digits']} digits)")
    return rule["country"] + digits


def _validate_register(d: dict) -> dict:
    email = (d.get("email") or "").strip().lower()
    if not _EMAIL_RE.fullmatch(email):
        raise _fail(422, "email_invalid", "Enter a valid email address.")

    pw, pwc = d.get("password") or "", d.get("password_confirm") or ""
    if pw != pwc:
        raise _fail(422, "password_mismatch", "Passwords do not match.")
    if len(pw) < 8:
        raise _fail(422, "password_weak", "Password must be at least 8 characters.")

    phone = _validate_phone(d.get("phone") or "", "IN")

    age = d.get("age")
    if age is None or not isinstance(age, int) or not (5 <= age <= 120):
        raise _fail(422, "age_invalid", "Age must be between 5 and 120.")

    dob_raw = d.get("dob") or None
    if dob_raw:
        try:
            dob = datetime.strptime(dob_raw, "%Y-%m-%d").date()
        except ValueError:
            raise _fail(422, "dob_invalid", "Date of birth must be YYYY-MM-DD.")
        if dob > _now().date():
            raise _fail(422, "dob_future", "Date of birth cannot be in the future.")
        today = _now().date()
        computed = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        if computed != age:
            raise _fail(422, "age_dob_mismatch",
                        "Age and date of birth do not match.")

    gender = d.get("gender") or "prefer-not-to-say"
    if gender not in GENDERS:
        raise _fail(422, "gender_invalid", "Choose a listed gender option.")

    address = (d.get("home_address") or "").strip() or None
    pin = (d.get("pin_code") or "").replace(" ", "") or None
    if pin and not _PIN_RE.fullmatch(pin):
        raise _fail(422, "pin_invalid", "PIN code must be six digits.")

    interests = d.get("interests") or []
    unknown = [g for g in interests if g not in GENRES]
    if unknown:
        raise _fail(422, "genre_invalid", f"Unknown genre: {unknown[0]}")
    if not interests:
        raise _fail(422, "interests_empty", "Pick at least one book interest.")
    other_interest = (d.get("other_interest") or "").strip() or None
    if "other" in interests and not other_interest:
        raise _fail(422, "other_required", "Describe your custom interest for Other.")
    if "other" not in interests:
        other_interest = None

    name = (d.get("name") or "").strip()
    if not (2 <= len(name) <= 80):
        raise _fail(422, "name_invalid", "Name must be 2–80 characters.")

    return dict(name=name, email=email, phone=phone, age=age, dob=dob_raw,
                gender=gender, home_address=address, pin_code=pin,
                interests=interests, other_interest=other_interest,
                password=pw)


# --------------------------------- models ---------------------------------
class RegisterIn(BaseModel):
    name: str
    email: str
    phone: str
    age: int
    dob: Optional[str] = None
    gender: Optional[str] = None
    home_address: Optional[str] = Field(default=None, max_length=320)
    pin_code: Optional[str] = None
    interests: List[str]
    other_interest: Optional[str] = None
    password: str
    password_confirm: str


class LoginIn(BaseModel):
    email: str
    password: str


class ProfileIn(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    age: Optional[int] = None
    dob: Optional[str] = None
    gender: Optional[str] = None
    home_address: Optional[str] = None
    pin_code: Optional[str] = None
    interests: Optional[List[str]] = None
    other_interest: Optional[str] = None
    goal: Optional[str] = None          # onboarding reading goal id
    level: Optional[str] = None         # onboarding reading level id
    language: Optional[str] = None      # preferred reading language
    password: Optional[str] = None
    password_confirm: Optional[str] = None


# --------------------------------- app ---------------------------------
app = FastAPI(title="PustakaMitra AI API", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in os.environ.get(
        "CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",") if o],
    allow_credentials=True,
    allow_methods=["*"], allow_headers=["Content-Type"],
)


def _self_doc(user: dict) -> dict:
    """Everything the OWNER may see (own phone/address). Never used for others."""
    return {
        "id": str(user["_id"]), "name": user["name"], "email": user["email"],
        "phone": user["phone"], "age": user["age"], "dob": user["dob"],
        "gender": user["gender"], "home_address": user.get("home_address"),
        "pin_code": user.get("pin_code"),
        "interests": user["interests"], "other_interest": user.get("other_interest"),
        "goal": user.get("goal"), "level": user.get("level"), "language": user.get("language"),
        "created_at": user["created_at"].isoformat(),
        "updated_at": user["updated_at"].isoformat(),
    }


def _start_session(resp: Response, user_id: ObjectId) -> None:
    sid = secrets.token_urlsafe(32)
    sessions.insert_one({"sid": _keyed(sid), "user_id": str(user_id),
                         "created_at": _now(),
                         "expires_at": _now() + timedelta(minutes=SESSION_TTL_MIN)})
    resp.set_cookie(SESSION_COOKIE, sid,
                    max_age=SESSION_TTL_MIN * 60, path="/",
                    httponly=True, samesite="lax", secure=SECURE_COOKIES)


def _current_user(pm_session: Optional[str] = Cookie(default=None)) -> dict:
    if not pm_session:
        raise _fail(401, "no_session", "Not signed in.")
    rec = sessions.find_one({"sid": _keyed(pm_session)})
    if not rec or rec["expires_at"].replace(tzinfo=timezone.utc) < _now():
        raise _fail(401, "session_expired", "Session expired — log in again.")
    user = users.find_one({"_id": ObjectId(rec["user_id"])})
    if not user:
        raise _fail(401, "user_gone", "Account no longer exists.")
    return user


@app.get("/api/health")
def health():
    DB.command("ping")
    return {"ok": True}


@app.post("/api/auth/register", status_code=201)
def register(data: RegisterIn, response: Response):
    try:
        v = _validate_register(data.model_dump())
    except HTTPException:
        raise

    doc = {**v, "password_hash": ph.hash(v["password"]), "created_at": _now(),
           "updated_at": _now()}
    doc.pop("password")
    try:
        user_id = users.insert_one(doc).inserted_id
    except errors.DuplicateKeyError:
        # unique index catches both existing and concurrent duplicate emails
        raise _fail(409, "email_taken", "An account with this email already exists.")

    _start_session(response, user_id)
    return {"created": True, "user": _self_doc(users.find_one({"_id": user_id}))}


@app.post("/api/auth/login")
def login(data: LoginIn, response: Response):
    user = users.find_one({"email": (data.email or "").strip().lower()})
    if not user:
        raise _fail(401, "bad_credentials", "Email or password is incorrect.")
    try:
        ph.verify(user["password_hash"], data.password)
    except (VerifyMismatchError, InvalidHashError):
        raise _fail(401, "bad_credentials", "Email or password is incorrect.")
    # transparent rehash on Argon2 parameter changes
    if ph.check_needs_rehash(user["password_hash"]):
        users.update_one({"_id": user["_id"]},
                         {"$set": {"password_hash": ph.hash(data.password)}})
    _start_session(response, user["_id"])
    return {"ok": True, "user": _self_doc(user)}


@app.post("/api/auth/logout")
def logout(response: Response, pm_session: Optional[str] = Cookie(default=None)):
    if pm_session:
        sessions.delete_one({"sid": _keyed(pm_session)})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@app.get("/api/profile/me")
def get_me(user: dict = Depends(_current_user)):
    return _self_doc(user)


@app.put("/api/profile/me")
def update_me(data: ProfileIn, user: dict = Depends(_current_user)):
    upd: dict = {"updated_at": _now()}
    d = data.model_dump(exclude_unset=True)

    interests = d.get("interests")
    if interests is not None:
        unknown = [g for g in interests if g not in GENRES]
        if not interests or unknown:
            raise _fail(422, "genre_invalid", "Invalid or empty interests list.")
        upd.update(interests=interests, other_interest=d.get("other_interest") or None)

    if d.get("password"):
        if d["password"] != (d.get("password_confirm") or ""):
            raise _fail(422, "password_mismatch", "Passwords do not match.")
        if len(d["password"]) < 8:
            raise _fail(422, "password_weak", "Password must be at least 8 characters.")
        upd["password_hash"] = ph.hash(d["password"])

    if d.get("pin_code"):
        pin = d["pin_code"].replace(" ", "")
        if not _PIN_RE.fullmatch(pin):
            raise _fail(422, "pin_invalid", "PIN code must be six digits.")
        upd["pin_code"] = pin
    if "pin_code" in d and not d.get("pin_code"):
        upd["pin_code"] = None

    for k in ("name", "home_address", "gender", "dob", "phone", "age", "goal", "level", "language"):
        if k in d:
            upd[k] = d[k]
    if upd.get("phone"):
        upd["phone"] = _validate_phone(upd["phone"])
    if upd.get("age") is not None and not (5 <= upd["age"] <= 120):
        raise _fail(422, "age_invalid", "Age must be between 5 and 120.")
    if upd.get("dob"):
        try:
            dd = datetime.strptime(upd["dob"], "%Y-%m-%d").date()
        except ValueError:
            raise _fail(422, "dob_invalid", "Date of birth must be YYYY-MM-DD.")
        if dd > _now().date():
            raise _fail(422, "dob_future", "Date of birth cannot be in the future.")

    users.update_one({"_id": user["_id"]}, {"$set": upd})
    return _self_doc(users.find_one({"_id": user["_id"]}))


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8001)
