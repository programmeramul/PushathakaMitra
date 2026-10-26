# PustakaMitra AI — backend

FastAPI + MongoDB. user data lives in the `pustakamitra` Mongo database.

## Run

```bash
cp .env.example .env          # fill SESSION_HASH_KEY (python3 -c "import secrets; print(secrets.token_urlsafe(32))")
export $(grep -v '^#' ../.env | xargs)   # or source it in your shell profile
python3 backend/main.py       # 127.0.0.1:8001
uvicorn backend.main:app --host 127.0.0.1 --port 8001   # alternative

# automated tests (use throwaway pustakamitra_test database)
pip3 install --user -r requirements.txt
python3 -m pytest backend/tests -v
```

Mongo connection default `mongodb://localhost:27017`, override with `MONGO_URI`.
Set `SECURE_COOKIES=1` when behind HTTPS (default: secure cookie flag off so
http:// works locally).
A real deployment must set `SESSION_HASH_KEY` (32+ random bytes, base64).

## Progress

- Argon2id password hashing (argon2-cffi)
- unique `email` index, normalized to lowercase; duplicates (existing OR
  concurrently inserted) → HTTP 409 email_taken
- sessions collection with TTL; `sid` stored as SHA-256 hash with env-secret; cookie
  is HTTP-only, SameSite=Lax
- password never logged; Mongo never returned in responses
- endpoints:
  - `POST /api/auth/register`
  - `POST /api/auth/login`
  - `POST /api/auth/logout`
  - `GET  /api/profile/me`
  - `PUT  /api/profile/me`
  - `GET  /api/health`

## Notes

- Email-language errors are structured JSON:
  `{"detail": {"code": ..., "message": ...}}`.
- HOME ADDRESS is optional; PIN code separate field.
- age/dob: dob validated; if both, must be consistent for the current date.
- phone: E.164 persisted (`+91` by default), country rules per CANON_CLASSES.
- No endpoint returns other users' phone/address/PIN (they never existed as
  endpoints) — only `/api/profile/me` returns them, session-gated.
- interests are recommendation signal only. No personality inference from
  age/gender/address/phone.
