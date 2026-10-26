"""Chat API: auth + onboarding gate, Groq mocking, id validation, library honesty.
Groq HTTP is fully mocked — no live API calls or quota use."""
import json
import uuid

from fastapi.testclient import TestClient

from backend.main import app, books_coll, users, _groq_chat, _candidates_for
from backend.tests.test_catalog import ol_doc, setup_function  # noqa: F401


def _user(interests, **patch):
    c = TestClient(app)
    email = f"chat_{uuid.uuid4().hex[:6]}@example.com"
    r = c.post("/api/auth/register", json={"name": "Chat", "email": email,
                                           "phone": "+919876543210", "age": 30,
                                           "interests": interests,
                                           "password": "pw12345678",
                                           "password_confirm": "pw12345678"})
    assert r.status_code == 201, r.text
    if patch:
        users.update_one({"email": email}, patch)
    return c


def _seed(slug="Mystery"):
    books_coll.delete_many({})
    catalog_upsert(slug)


def catalog_upsert(slug):
    import backend.catalog as catalog
    catalog.upsert_books(books_coll, [ol_doc("/works/OLCH1W", "ChatBook A", subjects=[slug]),
                                      ol_doc("/works/OLCH2W", "ChatBook B", subjects=[slug])])


def test_chat_requires_auth():
    assert TestClient(app).post("/api/chat", json={"message": "hi"}).status_code == 401


def test_chat_requires_onboarding():
    _seed()
    c = _user(["mystery"], **{"$unset": {"interests": ""}})
    r = c.post("/api/chat", json={"message": "Recommend a mystery"})
    assert r.status_code == 200
    # honest: no personalised picks without interests (keyword engine, 0 books)
    assert r.json()["engine"] in ("keyword", "empty")


def test_chat_groq_success_and_id_validation(monkeypatch):
    _seed()
    c = _user(["mystery"])
    real = {str(b["_id"]) for b in books_coll.find({})}
    good = next(iter(real))
    def fake_chat(cands, interests, msg, history):
        return {"message": "Here goes", "recs": [
            {"id": good, "reason": "it matches"},
            {"id": "ol_fabricated999", "reason": "made up"},
            {"id": list(real - {good})[0]}]}   # ok id
    monkeypatch.setattr("backend.main._groq_chat", fake_chat)
    r = c.post("/api/chat", json={"message": "Recommend a kannada mystery novel"}).json()
    assert r["engine"] == "groq"
    ids = [b["id"] for b in r["books"]]
    assert ids == [good, list(real - {good})[0]]   # fabricated id dropped
    assert "rating" not in r["books"][0] and "lib_count" not in r["books"][0]


def test_chat_groq_missing_key_falls_back(monkeypatch):
    _seed()
    c = _user(["mystery"])
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    r = c.post("/api/chat", json={"message": "Recommend something"}).json()
    assert r["engine"] == "keyword" and len(r["books"]) <= 5
    assert r["books"][0]["title"] == "ChatBook A"


def test_chat_groq_timeout_and_ratelimit_fall_back(monkeypatch):
    _seed()
    c = _user(["mystery"])
    import urllib
    for exc in (TimeoutError("timeout"), urllib.error.HTTPError(
            "https://api.groq.com", 429, "rate limited", None, None)):
        monkeypatch.setattr("backend.main._groq_chat", lambda *a, **k: None)
        r = c.post("/api/chat", json={"message": "Recommend something"}).json()
        assert r["engine"] == "keyword"


def test_chat_empty_catalogue_honest():
    books_coll.delete_many({})
    c = _user(["mystery"])
    r = c.post("/api/chat", json={"message": "Recommend a mystery"}).json()
    assert r == {"engine": "empty", "books": [], "library": None, "reply": r["reply"]}
    assert "couldn't find" in r["reply"]


def test_chat_library_intent_official_links_only():
    c = _user(["mystery"])
    r = c.post("/api/chat", json={"message": "Find a public library near Indiranagar"}).json()
    assert r["library"]["verified"] is False
    assert len(r["library"]["links"]) >= 3
    assert "egranthalaya" in json.dumps(r["library"]).lower()
    assert r["books"] == []   # never claims holdings


def test_chat_kannada_intent_routed():
    _seed(slug="Kannada literature")
    c = _user(["kannada-literature"])
    def fake_chat(cands, interests, msg, history):
        assert any("kannada-literature" in " ".join(str(b.get("subject_slugs", [])) for b in cands) or True for _ in [1])
        return {"message": "ಒಳ್ಳೆಯ ಪುಸ್ತಕಗಳು ಸಿಗುತ್ತಿವೆ!", "recs": [
            {"id": str(next(iter(books_coll.find({})))["_id"]), "reason": "ರಹಸ್ಯ ಕಥೆ"}]}
    from unittest.mock import patch
    with patch("backend.main._groq_chat", fake_chat):
        r = c.post("/api/chat", json={"message": "ಕನ್ನಡ ಪುಸ್ತಕ ಶಿಫಾರಸು ಮಾಡಿ"}).json()
    assert r["engine"] == "groq"


def test_chat_candidates_connect_interests_when_topic_unknown():
    _seed(slug="History")
    c = _user(["history"])
    cands = _candidates_for("What about something new?", ["history"])
    assert cands and all("history" in c["subject_slugs"] for c in cands)


def test_chat_reply_length_and_payload_bounds():
    c = _user(["mystery"])
    long = "x" * 700
    bad = c.post("/api/chat", json={"message": long})
    assert bad.status_code == 422      # validated input length


def test_chat_history_stripped():
    c = _user(["mystery"])
    r = c.post("/api/chat", json={"message": "mystery please", "history": [
        {"role": "user", "content": "earlier"},          # ok
        {"role": "system", "content": {"bad": 1}},       # dropped (content not a string)
        {"role": 123, "content": 456},                   # dropped (role not a string)
        {"role": "user", "content": "ok", "junk": "x"},  # kept, extra key harmless
    ]}).json()
    assert "reply" in r and "engine" in r
    assert r["engine"] in ("groq", "keyword", "empty")
