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
import json
import logging
import os
import re
import secrets
import socket
from collections import Counter
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

import uvicorn
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from pymongo import MongoClient, errors

# backend/.env is loaded explicitly using a reliable path independent of CWD.
# Under live execution, override=True ensures updated keys in .env supersede stale shell variables.
# Under pytest, override=False respects test isolation defined by conftest.py.
import sys
from pathlib import Path as _Path
from dotenv import load_dotenv as _load_dotenv

_backend_env = _Path(__file__).resolve().parent / ".env"
_root_env = _Path(__file__).resolve().parent.parent / ".env"
_is_pytest = "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST") is not None

if _backend_env.is_file():
    _load_dotenv(_backend_env, override=not _is_pytest)
elif _root_env.is_file():
    _load_dotenv(_root_env, override=not _is_pytest)

SESSION_COOKIE = "pm_session"
SESSION_TTL_MIN = int(os.environ.get("SESSION_TTL_MIN", "180"))
SESSION_HASH_KEY = os.environ.get("SESSION_HASH_KEY", "dev-only-session-key")
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.environ.get("MONGO_DB", "pustakamitra")  # tests override to pustakamitra_test
SECURE_COOKIES = os.environ.get("SECURE_COOKIES") == "1"
GROQ_MODEL = (os.environ.get("GROQ_MODEL") or "qwen/qwen3.8-27b").strip()


def _get_groq_config():
    """Safely return sanitized (key, model) stripped of whitespace without leaking secrets."""
    key = (os.environ.get("GROQ_API_KEY") or "").strip()
    model = (GROQ_MODEL or os.environ.get("GROQ_MODEL") or "qwen/qwen3.8-27b").strip()
    return key, model


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
    libraries_coll = DB.libraries
    libraries_coll.create_index([("library_id", 1)], unique=True, name="uq_library_id")
    libraries_coll.create_index([("name", "text"), ("area", "text"), ("address", "text")], name="tx_library_search")
    libraries_coll.create_index([("area", 1)], name="ix_area")
    libraries_coll.create_index([("location", "2dsphere")], name="geo_location")


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
        "interests": user.get("interests", []), "other_interest": user.get("other_interest"),
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


def health():
    DB.command("ping")
    return {"status": "ok", "ok": True}

# one implementation, two paths: /health is the public probe (monitors, curl),
# /api/health is what the existing tests/clients already use. Both require a
# live MongoDB round-trip — never report ok without checking the DB.
app.add_api_route("/health", health, methods=["GET"])


@app.get("/api/health")
def health_api():
    return health()


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



# ------------------------------ catalogue ------------------------------
books_coll = DB["books"]
books_coll.create_index("source_id", unique=True)

libraries_coll = DB["libraries"]

SYNC_TOKEN = os.environ.get("CATALOG_SYNC_TOKEN")


def _pub_library(lib: dict, distance_km: Optional[float] = None) -> dict:
    """Public library shape — real fields from uploaded dataset, no fake holdings."""
    lat = lib.get("latitude")
    lon = lib.get("longitude")
    directions_url = None
    if lat is not None and lon is not None:
        directions_url = f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}"
    res = {
        "library_id": lib.get("library_id") or str(lib.get("_id")),
        "name": lib.get("name") or "",
        "category": lib.get("category"),
        "branch": lib.get("branch"),
        "address": lib.get("address"),
        "area": lib.get("area"),
        "pincode": lib.get("pincode"),
        "phone": lib.get("phone"),
        "latitude": lat,
        "longitude": lon,
        "location": lib.get("location"),
        "source": lib.get("source"),
        "source_file": lib.get("source_file"),
        "verification_status": lib.get("verification_status") or "verified_location",
        "directions_url": directions_url,
    }
    if distance_km is not None:
        res["distance_km"] = round(distance_km, 2)
    return res


@app.get("/api/libraries")
def search_libraries(
    q: str = "",
    area: str = "",
    pincode: str = "",
    category: str = "",
    has_phone: Optional[bool] = None,
    page: int = 1,
    page_size: int = 20,
):
    if page < 1:
        raise _fail(422, "page_invalid", "Page must be >= 1")
    page_size = max(1, min(100, page_size))

    query: dict = {}
    if q.strip():
        rx = {"$regex": re.escape(q.strip()), "$options": "i"}
        query["$or"] = [{"name": rx}, {"address": rx}, {"area": rx}, {"branch": rx}]
    if area.strip():
        query["area"] = {"$regex": re.escape(area.strip()), "$options": "i"}
    if pincode.strip():
        query["pincode"] = pincode.strip()
    if category.strip():
        query["category"] = {"$regex": re.escape(category.strip()), "$options": "i"}
    if has_phone is True:
        query["phone"] = {"$ne": None}
    elif has_phone is False:
        query["phone"] = None

    total = libraries_coll.count_documents(query)
    skip = (page - 1) * page_size
    docs = list(libraries_coll.find(query).skip(skip).limit(page_size))
    items = [_pub_library(d) for d in docs]
    import math
    pages = math.ceil(total / page_size) if total else 1
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
    }


@app.get("/api/libraries/nearby")
def nearby_libraries(
    lat: float,
    lon: float,
    radius_km: float = 5.0,
    q: str = "",
    category: str = "",
    page: int = 1,
    page_size: int = 20,
):
    if not (-90.0 <= lat <= 90.0):
        raise _fail(422, "lat_invalid", "Latitude must be between -90 and 90")
    if not (-180.0 <= lon <= 180.0):
        raise _fail(422, "lon_invalid", "Longitude must be between -180 and 180")
    if radius_km <= 0 or radius_km > 50.0:
        raise _fail(422, "radius_invalid", "Radius must be between 0.1 and 50 km")
    if page < 1:
        raise _fail(422, "page_invalid", "Page must be >= 1")
    page_size = max(1, min(100, page_size))

    geo_near = {
        "near": {"type": "Point", "coordinates": [lon, lat]},
        "distanceField": "distance_meters",
        "maxDistance": radius_km * 1000.0,
        "spherical": True,
    }
    match_stage: dict = {}
    if q.strip():
        rx = {"$regex": re.escape(q.strip()), "$options": "i"}
        match_stage["$or"] = [{"name": rx}, {"address": rx}, {"area": rx}, {"branch": rx}]
    if category.strip():
        match_stage["category"] = {"$regex": re.escape(category.strip()), "$options": "i"}

    pipeline = [{"$geoNear": geo_near}]
    if match_stage:
        pipeline.append({"$match": match_stage})

    count_pipeline = list(pipeline) + [{"$count": "total"}]
    count_res = list(libraries_coll.aggregate(count_pipeline))
    total = count_res[0]["total"] if count_res else 0

    skip = (page - 1) * page_size
    pipeline.append({"$skip": skip})
    pipeline.append({"$limit": page_size})

    docs = list(libraries_coll.aggregate(pipeline))
    items = []
    for d in docs:
        dist_km = d.get("distance_meters", 0.0) / 1000.0
        items.append(_pub_library(d, distance_km=dist_km))

    import math
    pages = math.ceil(total / page_size) if total else 1
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
        "radius_km": radius_km,
        "center": {"lat": lat, "lon": lon},
    }


@app.get("/api/libraries/{library_id}")
def get_library(library_id: str):
    doc = libraries_coll.find_one({"$or": [{"library_id": library_id}, {"_id": library_id}]})
    if not doc and ObjectId.is_valid(library_id):
        doc = libraries_coll.find_one({"_id": ObjectId(library_id)})
    if not doc:
        raise _fail(404, "library_not_found", "Library not found in uploaded dataset")
    return _pub_library(doc)


def _pub_book(b: dict) -> dict:
    """Public book shape — only sourced fields, no ratings, no holdings."""
    return {
        "id": str(b["_id"]), "title": b["title"], "authors": b.get("authors") or [],
        "year": b.get("year"), "language": b.get("language"),
        "subject_slugs": b.get("subject_slugs") or [],
        "description": b.get("description"),
        "cover_url": b.get("cover_url"),
        # provenance is public by design — traceability is the point
        "source": b.get("source"), "source_id": b.get("source_id"),
    }


@app.get("/api/books")
def list_books(q: str = "", genre: str = "", lang: str = "",
               page: int = 1, page_size: int = 24):
    cur: dict = {}
    if q.strip():
        rx = {"$regex": re.escape(q.strip()), "$options": "i"}
        cur["$or"] = [{"title": rx}, {"authors": rx}]
    if genre:
        cur["subject_slugs"] = genre
    if lang:
        cur["language"] = lang
    page, page_size = max(1, page), max(1, min(60, page_size))
    total = books_coll.count_documents(cur)
    docs = books_coll.find(cur, sort=[("year", -1), ("_id", 1)]
                           ).skip((page - 1) * page_size).limit(page_size)
    return {"total": total, "page": page, "page_size": page_size,
            "items": [_pub_book(b) for b in docs]}


@app.get("/api/books/{book_id}")
def get_book(book_id: str, response: Response):
    try:
        b = books_coll.find_one({"_id": book_id})
    except Exception:
        b = None
    if not b:
        raise _fail(404, "book_not_found", "No such book in the catalogue.")
    out = _pub_book(b)
    out["subjects"] = b.get("subjects") or []
    out["language_codes"] = b.get("language_codes") or []
    out["isbn"] = b.get("isbn")
    out["imported_at"] = b.get("imported_at")
    # similar = share a category slug; honest "None yet" when categories missing
    slugs = b.get("subject_slugs") or []
    out["similar"] = ([_pub_book(s) for s in books_coll.find(
        {"_id": {"$ne": b["_id"]}, "subject_slugs": {"$in": slugs}}).limit(6)]
        if slugs else [])
    return out


@app.post("/api/catalog/sync")
def catalog_sync(request: Request):
    # admin-only, token from env; 503 with a clear message when not configured
    if not SYNC_TOKEN:
        raise _fail(503, "sync_unconfigured",
                    "Set CATALOG_SYNC_TOKEN to enable catalogue sync.")
    if request.headers.get("X-Admin-Token") != SYNC_TOKEN:
        raise _fail(401, "bad_admin_token", "Invalid admin token.")
    from importlib import import_module
    catalog = import_module("catalog") if not __package__ else import_module("backend.catalog")
    fetch_books, upsert_books = catalog.fetch_books, catalog.upsert_books
    totals = {"inserted": 0, "updated": 0, "rejected": 0}
    for q in json.load(open(os.path.join(os.path.dirname(__file__),
                                         "catalog_queries.json"))):
        try:
            r = upsert_books(books_coll, fetch_books(q["q"], limit=q.get("limit", 100)))
        except Exception:
            continue                      # failed query: skip, never fabricate
        for k in totals:
            totals[k] += r[k]
    return {"ok": True, "counts": totals, "total_in_db": books_coll.count_documents({})}


# --------------------------- recommendations ---------------------------
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
# Cloudflare in front of Groq hard-blocks the default "Python-urllib" client
# (HTTP 403, CF error 1010) — a named UA is required for any production call.
GROQ_UA = "pustakamitra-backend/0.3"

# sanitized fallback explanations returned to the frontend (never contain the key)
_GROQ_REASONS = {
    "config_missing": "AI isn't configured on this server yet.",
    "invalid_credentials": "The AI service rejected its credentials — the maintainer should check the Groq key.",
    "rate_limited": "The AI service is rate-limited right now.",
    "timeout": "The AI service didn't respond in time.",
    "network": "The AI service could not be reached.",
    "model_unavailable": "The configured AI model isn't currently available.",
    "malformed_response": "The AI returned an unexpected response format.",
    "no_candidates": "The AI had no catalogue books to work from.",
}


def _classify_groq_failure(e: Exception) -> str:
    """Map a urllib exception to a safe reason code. Logs it without secrets."""
    if isinstance(e, urllib.error.HTTPError):
        detail = ""
        try:
            detail = e.read().decode()[:200]
        except Exception:
            pass
        logging.getLogger("pustakamitra.groq").warning(
            "Groq HTTP %s (%s) — detail: %s", e.code, e.reason, detail[:120])
        if e.code in (401, 403):
            return "invalid_credentials"
        if e.code == 404:
            return "model_unavailable"
        if e.code == 400:
            if any(term in detail.lower() for term in ("model", "not_found", "decommissioned")):
                return "model_unavailable"
            return "malformed_response"
        if e.code == 429:
            return "rate_limited"
        return "network"
    if isinstance(e, TimeoutError):
        return "timeout"
    if isinstance(e, socket.timeout):
        return "timeout"
    try:
        raise e                                 # re-raise to see the real type
    except (urllib.error.URLError, ConnectionError, OSError):
        return "network"
    except Exception:
        logging.getLogger("pustakamitra.groq").warning(
            "Groq failed: %s: %s", type(e).__name__, str(e)[:200])
        return "malformed_response"


def _keyword_rank(cands: list, interests: list, limit: int = 6) -> list:
    """Deterministic metadata-only fallback. Labels genre overlap; no ratings."""
    def score(b):
        return (-len(set(b.get("subject_slugs") or []) & set(interests)),
                -(b.get("year") or 0))
    out = sorted(cands, key=score)[:limit]
    return [{"id": str(b["_id"]),
             "reason": "Matches your interest" + ("s" if len(set(b.get("subject_slugs") or []) & set(interests)) > 1 else "") + ": " + ", ".join(
                 sorted(set(b.get("subject_slugs") or []) & set(interests)))
             if set(b.get("subject_slugs") or []) & set(interests)
             else "From the current catalogue"}
            for b in out]


def _groq_rank(cands: list, interests: list) -> Optional[list]:
    """Ask Groq to pick from candidates. Returns None on any failure."""
    key, model = _get_groq_config()
    if not key:
        return None    # only titles/authors/categories go out — never the user's PII
    payload_cands = [{"id": str(b["_id"]), "title": b["title"],
                      "authors": b.get("authors") or [], "year": b.get("year"),
                      "categories": b.get("subject_slugs") or []} for b in cands]
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content":
             "You recommend books for a reader. From the given candidates ONLY, "
             "pick the best matches for their reading interests. Respond with "
             "strict JSON: {\"recommendations\": [{\"id\": \"<candidate id>\", "
             "\"reason\": \"<one concise sentence, max 20 words, referencing "
             "only the candidate's own metadata>\"}]}. Use only candidate ids "
             "from the list. Never invent books, ratings or availability."},
            {"role": "user", "content": json.dumps(
                {"interests": interests, "candidates": payload_cands})},
        ],
        "temperature": 0.3, "max_tokens": 800,
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request(GROQ_URL, data=body, headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json",
        "User-Agent": GROQ_UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            content = json.load(resp)["choices"][0]["message"]["content"]
        recs = json.loads(content).get("recommendations") or []
    except Exception:
        return None
    # validate: keep only known candidate ids with a string reason
    valid = {str(b["_id"]) for b in cands}
    out = [{"id": r["id"], "reason": str(r.get("reason") or "")[:200]}
           for r in recs
           if isinstance(r, dict) and str(r.get("id")) in valid and r.get("reason")]
    return out[:6] or None


@app.get("/api/recommendations")
def recommendations(user: dict = Depends(_current_user)):
    interests = user.get("interests") or []
    # no interests yet: say so honestly instead of blanket-recommending
    if not interests:
        return {"engine": "no_interests", "items": []}
    cands = list(books_coll.find({"subject_slugs": {"$in": interests}}, limit=100))
    if not cands:
        return {"engine": "empty", "items": []}      # honest empty catalogue
    recs = _groq_rank(cands, interests)
    engine = "groq"
    if recs is None:
        recs, engine = _keyword_rank(cands, interests), "keyword"
    by_id = {str(b["_id"]): b for b in cands}
    return {"engine": engine,
            "items": [{**_pub_book(by_id[r["id"]]), "reason": r.get("reason", "")}
                      for r in recs if r["id"] in by_id and r.get("reason")][:6]}


# ------------------------------ chatbot ------------------------------
# AI reading companion over the REAL catalogue. Authenticated + onboarded only.
class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=600)
    history: List[dict] = Field(default_factory=list, max_length=10)
    locality: Optional[str] = Field(default=None, max_length=80)
    latitude: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(default=None, ge=-180.0, le=180.0)
    radius_km: Optional[float] = Field(default=None, gt=0, le=50.0)


_KN_HINTS = ("ಕನ್ನಡ", "ಓದು", "ಪುಸ್ತಕ")          # generic Kannada words (language only via _KANNADA_RE)
_LIBRARY_HINTS = ("library", "librar", "granthalaya", "ಗ್ರಂಥಾಲಯ", "ಪುಸ್ತಕಾಲಯ",
                  "ಗ್ರಂಥಾಲಯದ")
_GENRE_HINTS = {
    "mystery": ("mystery", "mysteries", "ರಹಸ್ಯ"),
    "horror": ("horror", "ಭಯ", "ಭೀತಿ"),
    "fantasy": ("fantasy", "ಕಲ್ಪನಾವಿಶ್ವ"),
    "romance": ("romance", "love story", "ಪ್ರೇಮ"),
    "thriller": ("thriller", "ಥ್ರಿಲ್ಲರ್"),
    "science-fiction": ("science fiction", "sci-fi", "ಸೈನ್ಸ್ ಫಿಕ್ಷನ್"),
    "spirituality": ("spiritual", "spirituality", "ಆಧ್ಯಾತ್ಮ"),
    "philosophy": ("philosophy", "ತತ್ವ", "ತತ್ವಶಾಸ್ತ್ರ"),
    "history": ("history", "ಇತಿಹಾಸ"),
    "technology": ("technology", "business", "econom", "management", "finance",
                   "ತಂತ್ರಜ್ಞಾನ"),
    "biography": ("biography", "leader", "leadership", "ಜೀವನಚರಿತ್ರೆ"),
    "self-development": ("self-help", "self development", "beginner", "start reading",
                         "ಸ್ವಯಂ"),
    "kannada-literature": ("kannada literature", "kannada novel", "ಕನ್ನಡ ಸಾಹಿತ್ಯ",
                           "parva", "parvœ"),
}


def _book_card(b: dict) -> dict:
    c = _pub_book(b)
    c.pop("description", None)                   # cards stay compact
    return c


# ------------------------- request understanding -------------------------
# Deterministic slot+intent parsing (language words, genres, difficulty,
# follow-ups). The Groq prompt receives these slots so its reply reflects what
# the user actually asked — never a canned recommendation.

_CHAT_CTX: dict = {}        # str(user_id) -> {"genres", "language", "last_cards"}; per-user, per-process

_GREET_RE = re.compile(
    r"^\s*(hi|hello|hey|namaskara|namaskaragalu|namaste|hai|thanks|thank you|"
    r"dhanyavadagalu|ಧನ್ಯವಾದ|ನಮಸ್ಕಾರ)\b[!.]?\s*[!.\s]*$", re.I)
_KANNADA_RE = re.compile(r"\b(kannada|ಕನ್ನಡ)\b", re.I)
_ENGLISH_RE = re.compile(r"\b(english|ಇಂಗ್ಲೀಷ್|ಇಂಗ್ಲಿಷ್)\b", re.I)
_BEGINNER_RE = re.compile(r"\b(beginner|beginners|new reader|new to reading|first book|"
                          r"start reading|start with|never read|easy height|easy read|just starting)\b", re.I)
_PREFER_RE = re.compile(r"^\s*(no|nope|not that|actually)\b", re.I)
_SELF_RE = r"\b(first book|previous pick|the first one|that book)\b"
_MORE_RE = re.compile(r"\b(more|another|other options|innu|ಇನ್ನೊಂದು)\b", re.I)
_SIMILAR_RE = re.compile(
    r"(?:similar to|like)\s+(?:the\s+|a\s+)?" +
    r"((?:first book|previous pick|the first one|that book)|[\"“']?[A-Za-z0-9\u0c80-\u0cde .'\-]{2,40})\b",
    re.I)
_TITLE_Q_RE = re.compile(r"[\"“']([A-Za-z0-9\u0c80-\u0cde][^\"”']{2,60})[\"”']")
_TITLE_HINT_RE = re.compile(
    r"\b(find|search|look up|do you have|show me)\s+(?:the\s+)?book\s+[\"“']?([A-Za-z0-9\u0c80-\u0cde .'\-]{2,60})\b",
    re.I)


def _parse_slots(msg: str, user_id: str, interests: list) -> dict:
    """Slots for THIS message only; carry-over from _CHAT_CTX for follow-ups
    ("show me more", "no, English instead"). No cross-user mixing."""
    m = msg.lower()
    ctx = _CHAT_CTX.get(user_id, {})
    s = {"mode": "recommend", "genres": set(), "language": None,
         "beginner": _BEGINNER_RE.search(msg) is not None,
         "similar_to": None, "title": None, "topics_detected": False,
         "carry": False}
    if _GREET_RE.match(msg):
        s["mode"] = "greet"
        return s
    if any(h in m for h in _LIBRARY_HINTS):
        s["mode"] = "library"
        return s
    if _KANNADA_RE.search(msg):
        s["language"] = "Kannada"
    elif _ENGLISH_RE.search(msg):
        s["language"] = "English"
    for slug, hints in _GENRE_HINTS.items():
        if any(h in m for h in hints):
            s["genres"].add(slug)
    if s["genres"]:
        s["topics_detected"] = True
    # similar-to: "Show me more like the first book" / "similar to Parva"
    sm = _SIMILAR_RE.search(msg)
    if sm:
        ref = (sm.group(1) or "").strip()
        s["mode"] = "similar"
        if re.search(_SELF_RE, ref, re.I) or "first book" in ref.lower():
            last = (ctx.get("last_cards") or [])
            s["similar_to"] = last[0] if last else None
            s["carry"] = True
        else:
            s["similar_to"] = ref.rstrip(".!") if ref.rstrip(".!") else None
        if not s["genres"]:
            s["topics_detected"] = True
    elif _MORE_RE.search(m) and not s["genres"]:
        # "Show me more" → continue the previous query
        s["carry"] = True
    elif _TITLE_Q_RE.search(msg) or _TITLE_HINT_RE.search(msg):
        q = _TITLE_Q_RE.search(msg)
        s["title"] = (q.group(1) if q else _TITLE_HINT_RE.search(msg).group(2)).strip()
        s["mode"] = "title"
    elif _PREFER_RE.match(msg) or (s["language"] and not s["genres"]):
        # follow-up correction: use previous topics with the new language
        s["carry"] = True
    # carry previous context for this turn when the user references it
    if s["carry"]:
        s["genres"] = s["genres"] or set(ctx.get("genres") or [])
        s["language"] = s["language"] or ctx.get("language")
        if s["language"]:
            s["topics_detected"] = True
    if s["beginner"] and not s["genres"]:
        s["genres"].add("self-development")
    # remember the language preference across turns ("no, I prefer English books")
    if s["language"]:
        ctx["language"] = s["language"]
        _CHAT_CTX[user_id] = ctx
    return s


def _topic_text_query(words: list, language: Optional[str]) -> dict:
    """Regex match over title/subjects/description; ANY topic word matches."""
    fields = ("title", "subjects", "description")
    ors = [{f: {"$regex": re.escape(w), "$options": "i"}}
           for w in words for f in fields]
    if language:
        return {"$and": [{"$or": ors}, {"language": language}]}
    return {"$or": ors}


def _find_candidates(s: dict, interests: list) -> tuple:
    """Real Mongo retrieval for the parsed slots. Returns (docs, note) where
    note explains any honest shortfall. Never substitutes unrelated books."""
    similar = s.get("similar_to")
    if s["mode"] == "similar" and similar:
        anchor = None
        if isinstance(similar, dict):          # "the first book" → previous card
            anchor = books_coll.find_one({"_id": similar["id"]}) if similar.get("id") is not None else None
        else:                                   # an actual title name
            anchor = _find_by_title(similar)
            anchor = anchor[0] if anchor else None
        if anchor:
            terms = [{"title": {"$regex": re.escape(anchor["title"]), "$options": "i"}},
                     {"authors": {"$regex": re.escape((anchor.get("authors") or [""])[0]),
                                  "$options": "i"}}]
            if anchor.get("subject_slugs"):
                terms.append({"subject_slugs": {"$in": sorted(anchor["subject_slugs"])}})
            docs = list(books_coll.find(
                {"_id": {"$ne": anchor["_id"]}, "$or": terms}, limit=40))
            if s["language"]:
                kn = [d for d in docs if (d.get("language") or "") == s["language"]]
                if kn:
                    docs = kn
            return docs, None
        return [], f"I couldn't find \"{similar}\" in the catalogue to anchor similar picks."
    if s["mode"] == "title" and s["title"]:
        docs = _find_by_title(s["title"])
        if docs:
            return docs, None
        return [], f"No record titled \"{s['title']}\" in the catalogue."
    # normal recommendation search: explicit topics win; else real saved interests
    want = set(s["genres"]) if s["genres"] else set(interests)
    q: dict = {}
    if want:
        q["subject_slugs"] = {"$in": sorted(want)}
    note = None
    if s["language"]:
        asked = ", ".join(sorted(s["genres"])) or "that topic"
        words = [h for slug in s["genres"] for h in _GENRE_HINTS[slug]
                 if h.isascii() and len(h) > 3]
        if q:
            docs = list(books_coll.find({**q, "language": s["language"]}, limit=60))
            if docs:
                return docs, None
            # slug query failed: try topic text search within the language
            text_docs = []
            if words:
                text_docs = list(books_coll.find(
                    _topic_text_query(words[:3], s["language"]), limit=60))
            if text_docs:
                return text_docs, None
            # honest shortfall: don't substitute other languages silently
            others = list(books_coll.find(q, limit=60))
            langs = Counter((d.get("language") or "unknown") for d in others).most_common(3)
            listing = ", ".join(f"{l} ({n})" for l, n in langs)
            hint = (f"that topic exists in: {listing}" if listing else
                    ("nothing matches it in the catalogue — try asking about "
                     f"'{sorted(s['genres'])[0].replace('-', ' ')}' "
                     "without the language filter" if s["genres"] else
                     "nothing matches it in the catalogue — try another topic"))
            kn_total = books_coll.count_documents({"language": s["language"]})
            extra = (f" The catalogue has {kn_total} {s['language']}-language "
                     "books in other topics — ask for one of those genres."
                     if kn_total else "")
            return [], (f"No {s['language']}-language {asked} books in the "
                        f"catalogue — {hint}.{extra}")
        docs = list(books_coll.find({"language": s["language"]}, limit=80))
        if docs:
            return docs, None
        return [], f"No {s['language']}-language books match right now."
    if q:
        docs = list(books_coll.find(q, limit=60))
        if docs:
            return docs, None
        # genre slugs with no exact hits: real text search over title/subjects/
        # description for that topic (slug coverage in the import is uneven)
        words = [h for slug in s["genres"] for h in _GENRE_HINTS[slug]
                 if h.isascii() and len(h) > 3]
        if words and not s["carry"]:
            docs = list(books_coll.find(_topic_text_query(words, None), limit=60))
            if docs:
                return docs, None
        return [], None
    # nothing actionable: a broad relevance slice of the real catalogue
    return list(books_coll.find({}, limit=40)), "no_topic"


def _find_by_title(title: str) -> list:
    t = title.strip().rstrip(".!")
    if not t:
        return []
    out = list(books_coll.find(
        {"title": {"$regex": re.escape(t), "$options": "i"}}, limit=5))
    if not out:                       # normalized-ish: first few significant words
        words = [w for w in re.split(r"[\s'.]+", t) if len(w) > 2][:3]
        if words:
            out = list(books_coll.find(
                {"$and": [{"title": {"$regex": re.escape(w), "$options": "i"}}
                          for w in words]}, limit=5))
    return out


def _candidates_for(message: str, interests: list) -> list:
    """Legacy helper kept for tests/topics NOTE ( replaced by _find_candidates)."""
    slugs = set(interests)
    for slug, hints in _GENRE_HINTS.items():
        if any(h in message.lower() for h in hints):
            slugs.add(slug)
    q = {"subject_slugs": {"$in": sorted(slugs)}} if slugs else {}
    if "kannada" in message.lower():
        kn = list(books_coll.find({**q, "language": "Kannada"}, limit=60))
        if kn:
            return kn
    return list(books_coll.find(q, limit=60))


def _groq_chat(cands: list, interests: list, message: str, history: list, slots=None):
    """Groq chat turn over candidates. Returns ({message, recs}|None, reason|None);
    reason is a safe code from _GROQ_REASONS when result is None."""
    key, model = _get_groq_config()
    if not key:
        return None, "config_missing"
    if not cands:
        return None, "no_candidates"
    slots = slots or {}
    payload = {"interests": interests, "candidates": [
        {"id": str(b["_id"]), "title": b["title"], "authors": b.get("authors") or [],
         "year": b.get("year"), "categories": b.get("subject_slugs") or [],
         "language": b.get("language")}
        for b in cands[:30]]}
    body = json.dumps({
        "model": model, "temperature": 0.4, "max_tokens": 500,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content":
             "You are PustakaMitra AI, a warm reading companion for Kannada and "
             "English readers in Bengaluru. Answer in the user's language "
             "(Kannada or English). The user's intent was parsed as: "
             + json.dumps(slots) +
             ". Recommend from the given candidates ONLY. Reply with strict "
             "JSON: {\"message\": \"<2-3 short sentences, on-topic, no filler "
             "greetings>\", \"recommendations\": [{\"id\": \"<candidate id>\", "
             "\"reason\": \"<one sentence explaining the match using only the "
             "candidate's own metadata>\"}]}. Use only candidate ids from the "
             "list. If no candidate fits what was asked, return few or zero "
             "recommendations and say so honestly. Never invent books, ratings, "
             "or library availability. Do not repeat books already given in the "
             "conversation history."},
            {"role": "user", "content": json.dumps(
                {"history": history[-6:], "message": message, "context": payload})},
        ],
    }).encode()
    req = urllib.request.Request(GROQ_URL, data=body, headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json",
        "User-Agent": GROQ_UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            content = json.load(resp)["choices"][0]["message"]["content"]
        out = json.loads(content)
    except Exception as e:
        return None, _classify_groq_failure(e)   # timeout/429/malformed → fallback
    msg = str(out.get("message") or "").strip() or None
    valid = {str(b["_id"]) for b in cands}
    recs = [{"id": str(r.get("id")), "reason": str(r.get("reason") or "")[:200]}
            for r in (out.get("recommendations") or [])
            if isinstance(r, dict) and str(r.get("id")) in valid and r.get("reason")]
    if msg is None and not recs:
        return None, "malformed_response"
    return {"message": msg, "recs": recs[:5]}, None


_PIN_RE = re.compile(r"\b([1-9][0-9]{5})\b")
_NEAR_RE = re.compile(r"(?:near|in|around|list|available)\s+([A-Za-z][A-Za-z .]{2,40}?)(?:\s*[?.!]|$|\s+library|\s+public)", re.I)

KNOWN_AREAS = [
    "Koramangala", "Indiranagar", "Jayanagar", "Basavanagudi", "Basavagudi",
    "Malleswaram", "Malleshwaram", "Vijayanagar", "Vijaynagar", "BTM Layout", "BTM",
    "HSR Layout", "HSR", "Whitefield", "Peenya", "Yelahanka", "Cottonpet",
    "Lakkasandra", "Magadi Road", "Cubbon Park", "Dasarahalli", "Kumbalagodu",
    "Dayanand Nagar", "Kengeri", "N R Colony", "Vinayaka Layout", "J K Puram",
    "Gayatri Nagar", "Hampinagar", "R.T. Nagar", "RT Nagar", "Anekal",
    "Attibele", "Chandapura", "Sarjapur", "Bommasandra", "Hebbagodi",
    "Sahakarnagar", "JP Nagar", "Vijaya Bank Layout", "Parangipalya",
    "Saraswathipuram", "Double Road", "Sampige Road", "South End",
]


def _search_libraries_for_chat(
    msg: str,
    locality: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius_km: Optional[float] = None,
) -> Tuple[List[dict], str]:
    m = msg.lower()

    # 1. Holdings question check
    if re.search(r"list this book|holdings|shelf availability|is this book|have this book|own this book|borrow this book", m):
        reply = (
            "PustakaMitra AI has verified library locations and contacts from the uploaded Bengaluru dataset, "
            "but individual book holdings and shelf borrowing availability have not been verified. "
            "You can search the official state catalogue on e-Granthalaya or WorldCat for specific title holdings."
        )
        return [], reply

    # 2. Check for explicit radius in message (e.g. "within 3 km")
    rad_match = re.search(r"(?:within|under|around)\s+(\d+(?:\.\d+)?)\s*km", m)
    if rad_match:
        radius_km = float(rad_match.group(1))
    radius = radius_km or 5.0

    # 3. Nearby query with coordinates
    if lat is not None and lon is not None:
        pipeline = [
            {
                "$geoNear": {
                    "near": {"type": "Point", "coordinates": [lon, lat]},
                    "distanceField": "distance_meters",
                    "maxDistance": radius * 1000.0,
                    "spherical": True,
                }
            },
            {"$limit": 8},
        ]
        docs = list(libraries_coll.aggregate(pipeline))
        items = [_pub_library(d, distance_km=d["distance_meters"] / 1000.0) for d in docs]
        if items:
            reply = f"Found {len(items)} public libraries near your location within {radius} km (ordered by distance):"
        else:
            reply = f"No libraries found within {radius} km of your location in the uploaded dataset."
        return items, reply

    # 4. Proximity requested but no coordinates and no locality provided
    is_proximity = bool(re.search(r"\b(?:closest|nearest|near me|my location|close to me)\b", m))

    # 5. Extract locality / PIN from locality param or message
    target_area = (locality or "").strip()
    if not target_area:
        for area in KNOWN_AREAS:
            if re.search(r"\b" + re.escape(area) + r"\b", msg, re.I):
                target_area = area
                break
    if not target_area:
        near_m = _NEAR_RE.search(msg)
        if near_m:
            target_area = near_m.group(1).strip()
    pin_m = _PIN_RE.search(msg)
    target_pin = pin_m.group(1) if pin_m else None

    # If asking for closest/near me without coordinates or locality:
    if is_proximity and not target_area and not target_pin:
        reply = (
            "To find the closest library, click 'Use My Location' or share your locality/PIN code "
            "(e.g., 'Indiranagar', 'Jayanagar', or '560011')."
        )
        return [], reply

    # 6. Filters for telephone, category, specific name
    query: dict = {}

    if re.search(r"\b(?:phone|telephone|contact|number|numbers)\b", m):
        query["phone"] = {"$ne": None}

    if re.search(r"\bgovernment\b", m):
        query["category"] = {"$regex": "government", "$options": "i"}
    elif re.search(r"\bprivate(?:ly)?\b", m):
        query["category"] = {"$regex": "private", "$options": "i"}

    if "state central library" in m:
        query["name"] = {"$regex": "State Central Library", "$options": "i"}
    elif target_area or target_pin:
        area_terms = []
        if target_area:
            rx = {"$regex": re.escape(target_area), "$options": "i"}
            area_terms.extend([{"area": rx}, {"name": rx}, {"address": rx}])
        if target_pin:
            area_terms.append({"pincode": target_pin})
            area_terms.append({"address": {"$regex": re.escape(target_pin)}})
        if area_terms:
            query["$or"] = area_terms

    if not query:
        query = {"location": {"$ne": None}}

    docs = list(libraries_coll.find(query).limit(8))
    items = [_pub_library(d) for d in docs]

    if items:
        if "state central library" in m:
            reply = f"Found '{items[0]['name']}' in the uploaded Bengaluru dataset:"
        elif query.get("phone"):
            reply = f"Found {len(items)} libraries with telephone numbers in the uploaded dataset:"
        elif target_area:
            reply = f"Found {len(items)} libraries in or near {target_area} from the uploaded dataset:"
        elif target_pin:
            reply = f"Found {len(items)} libraries near PIN code {target_pin} from the uploaded dataset:"
        elif query.get("category"):
            reply = f"Found {len(items)} matching libraries in the uploaded dataset:"
        else:
            reply = f"Here are public libraries in Bengaluru from the uploaded dataset:"
    else:
        searched_for = target_area or target_pin or msg
        reply = (
            f"I couldn't find any libraries matching '{searched_for}' in the uploaded Bengaluru dataset. "
            "Try searching for a prominent area like Jayanagar, Malleswaram, Cubbon Park, or Koramangala."
        )

    return items, reply


def _library_links(message: str, locality: Optional[str]) -> dict:
    """Bengaluru library discovery: links to official search portals.
    Location dataset is imported into libraries collection, but book shelf
    holdings and live borrowing availability are unverified."""
    loc_named = (locality or "").strip()
    if not loc_named:
        m = _NEAR_RE.search(message)
        if m:
            loc_named = m.group(1).strip()
    pin = _PIN_RE.search(message)
    if pin and not loc_named:
        loc_named = pin.group(1)
    q = loc_named[:80] or "Bengaluru"
    loc = urllib.request.quote(q)
    holdings_note = ("No live catalogue integration exists, so shelf/borrowing "
                     "availability is UNVERIFIED for every book.")
    return {
        "verified": False,
        "note": ("Library locations and contacts below come from the uploaded "
                 "Bengaluru dataset, but individual book holdings and borrowing "
                 "availability are unverified. These official pages are the "
                 "reliable starting point for " + q + ":"),
        "links": [
            {"label": "City Central Library — State Library Directory",
             "url": "https://karnataka.gov.in/newpage/Public%20Libraries.aspx"},
            {"label": "e-Granthalaya catalogue (participating libraries)",
             "url": "https://egranthalaya.nic.in/"},
            {"label": f"Map search: public libraries near {q}",
             "url": f"https://www.google.com/maps/search/public+library+{loc}+Bengaluru"},
            {"label": "WorldCat — search library holdings for a book",
             "url": "https://search.worldcat.org/"},
        ],
        "holdings": {"available": False, "note": holdings_note},
    }


@app.post("/api/chat")
def chat(data: ChatIn, user: dict = Depends(_current_user)):
    msg = data.message.strip()
    user_id = str(user["_id"])
    interests = [i for i in (user.get("interests") or []) if i]
    history = [h for h in data.history if
               isinstance(h, dict) and isinstance(h.get("role"), str)
               and isinstance(h.get("content"), str)
               and h["role"] in ("user", "bot")][:10]
    s = _parse_slots(msg, user_id, interests)

    ctx = _CHAT_CTX.setdefault(user_id, {})

    if s["mode"] == "greet":
        # greetings get a greeting — never a wall of book cards
        return {"engine": "conversation", "reply":
                "Namaskara! What would you love to read today?" if not history
                else "Namaskara! What can I find for you next?",
                "books": [], "library": None}

    if s["mode"] == "library":
        lib_results, reply_text = _search_libraries_for_chat(
            msg=msg,
            locality=data.locality,
            lat=data.latitude,
            lon=data.longitude,
            radius_km=data.radius_km,
        )
        return {
            "engine": "library_search",
            "reply": reply_text,
            "books": [],
            "library": _library_links(msg, data.locality),
            "libraries": lib_results,
        }

    cands, note = _find_candidates(s, interests)

    if not cands:
        # honest: nothing matches this exact request — no substitution
        return {"engine": "empty", "reply":
                (note or "I couldn't find anything matching that in the real "
                 "Open Library catalogue yet — try another topic or genre and "
                 "I'll look again."),
                "books": [], "library": None,
                "suggested_genres": sorted(set(interests))[:4] or ["mystery",
                "history", "kannada-literature", "self-development"]}

    def _cards(picks):
        by_id = {str(b["_id"]): b for b in cands}
        return [_book_card(by_id[r["id"]]) for r in picks if r["id"] in by_id]

    def _remember(ids):
        # carry genre/language context and last-answer cards for follow-ups
        if s["genres"]:
            ctx["genres"] = sorted(s["genres"])
        elif s["carry"]:
            ctx.setdefault("genres", [])
        if s["language"]:
            ctx["language"] = s["language"]
        ctx["last_cards"] = [{"id": bid, "title": by["title"]}
                             for bid, by in ((str(b["_id"]), b) for b in cands)
                             if bid in ids][:6]
        _CHAT_CTX[user_id] = ctx

    groq, groq_err = _groq_chat(cands, interests, msg, history, slots={
        "intent": s["mode"],
        "requested_genres": sorted(s["genres"]) or None,
        "requested_language": s["language"],
        "beginner": s["beginner"],
        "anchored_on": (s["similar_to"]["title"] if isinstance(s["similar_to"], dict)
                        else s["similar_to"] if s["similar_to"] else s["title"]) or None,
    })
    if groq and groq["recs"]:
        books = _cards([{**r} for r in groq["recs"]])
        if books:
            _remember({b["id"] for b in books})
            return {"engine": "groq", "reply": groq["message"] or
                    "Here are the best matches from the real catalogue:",
                    "books": books, "library": None}
    # deterministic fallback / model-returned-nothing — labelled, real cause
    reason = groq_err or "model_no_picks"
    by_id = {str(b["_id"]): b for b in cands}
    ranked = _keyword_rank(cands, interests, limit=4)
    books = [{**_book_card(by_id[r["id"]]), "reason": r["reason"]}
             for r in ranked if r["id"] in by_id]
    explain = _GROQ_REASONS.get(reason)
    prefix = f"({explain}) " if explain else ""
    _remember({b["id"] for b in books})
    if reason == "model_no_picks" and groq and groq["message"]:
        reply = groq["message"]                # Groq worked; no books fit — use its words
    elif reason == "model_no_picks":
        reply = ("I couldn't pick a confident match from the real catalogue "
                 "for that — here are the closest real records:")
    else:
        reply = f"{prefix}Genre-matched picks from the real catalogue:"
    return {"engine": "keyword", "fallback_reason": reason, "reply": reply,
            "books": books, "library": None}


@app.get("/api/chat/status")
def chat_status():
    """Frontend can probe availability without calling Groq."""
    key, model = _get_groq_config()
    lib_count = libraries_coll.count_documents({})
    return {
        "groq_configured": bool(key),
        "model": model,
        "library_dataset_imported": lib_count > 0,
        "library_count": lib_count,
    }


if __name__ == "__main__":
    backend_dir = str(_Path(__file__).resolve().parent)
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
    uvicorn.run("main:app", host="127.0.0.1", port=8001, app_dir=backend_dir)
