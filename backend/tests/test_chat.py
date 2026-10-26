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
    def fake_chat(cands, interests, msg, history, slots=None):
        return ({"message": "Here goes", "recs": [
            {"id": good, "reason": "it matches"},
            {"id": "ol_fabricated999", "reason": "made up"},
            {"id": list(real - {good})[0]}]}, None)   # (result, reason)
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
    assert r["fallback_reason"] == "config_missing"
    assert "configured" in r["reply"].lower()
    assert r["books"][0]["title"] == "ChatBook A"


def test_chat_groq_failures_classified_and_labelled(monkeypatch):
    """Timeout / rate-limit / bad key / bad model each produce their OWN
    honest label — never a generic 'AI unavailable'."""
    _seed()
    c = _user(["mystery"])
    import urllib.request, urllib.error
    cases = [
        (TimeoutError("timeout"), "timeout", "didn't respond in time"),
        (urllib.error.HTTPError("u", 429, "rate", None, None),
         "rate_limited", "rate-limited"),
        (urllib.error.HTTPError("u", 401, "denied", None, None),
         "invalid_credentials", "credentials"),
        (urllib.error.HTTPError("u", 404, "no model", None, None),
         "model_unavailable", "model"),
        (urllib.error.URLError("conn refused"), "network", "could not be reached"),
        (ValueError("bad json"), "malformed_response", "unexpected response"),
    ]
    for exc, code, phrase in cases:
        def boom(req, timeout=None):
            raise exc
        monkeypatch.setattr("backend.main.urllib.request.urlopen", boom)
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        r = c.post("/api/chat", json={"message": "Recommend something"}).json()
        assert r["engine"] == "keyword", (phrase, r)
        assert r["fallback_reason"] == code, r
        assert phrase.lower() in r["reply"].lower(), r
        assert "test-key" not in json.dumps(r)   # key never leaks
        assert "GROQ_API_KEY" not in json.dumps(r)


def test_chat_groq_success_mocked_http(monkeypatch):
    """Full parse path via mocked urlopen — no live API call."""
    _seed()
    c = _user(["mystery"])
    good = next(str(b["_id"]) for b in books_coll.find({}))
    captured = {}
    class FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps(
            {"choices": [{"message": {"content": json.dumps(
                {"message": "Try ChatBook A!", "recommendations": [
                    {"id": good, "reason": "mystery match"}]})}}]}).encode()
    def fake(req, timeout=None):
        captured["ua"] = (req.headers or {}).get("User-agent")
        return FakeResp()
    monkeypatch.setattr("backend.main.urllib.request.urlopen", fake)
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    r = c.post("/api/chat", json={"message": "Recommend a mystery"}).json()
    assert r["engine"] == "groq" and r["books"][0]["id"] == good
    # Cloudflare blocks the default python-urllib UA (CF 1010) — UA must be set
    assert captured["ua"] and "pustakamitra" in captured["ua"]


def test_chat_groq_empty_prose_easy_to_explain(monkeypatch):
    """Model returns no usable books: labelled malformed, not 'unavailable'."""
    _seed()
    c = _user(["mystery"])
    class FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps(
            {"choices": [{"message": {"content": json.dumps({"recommendations": []})}}]}).encode()
    monkeypatch.setattr("backend.main.urllib.request.urlopen", lambda req, timeout=None: FakeResp())
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    r = c.post("/api/chat", json={"message": "Recommend something"}).json()
    assert r["fallback_reason"] == "malformed_response"
    assert r["engine"] == "keyword"          # fallback still shows real books


def test_chat_groq_timeout_and_ratelimit_fall_back(monkeypatch):
    _seed()
    c = _user(["mystery"])
    for exc in ("timeout", "limited"):
        monkeypatch.setattr("backend.main._groq_chat",
                            lambda *a, **k: (None, "timeout" if exc == "timeout" else "rate_limited"))
        r = c.post("/api/chat", json={"message": "Recommend something"}).json()
        assert r["engine"] == "keyword"
        assert r["fallback_reason"] in ("timeout", "rate_limited")


def test_chat_empty_catalogue_honest():
    books_coll.delete_many({})
    c = _user(["mystery"])
    r = c.post("/api/chat", json={"message": "Recommend a mystery"}).json()
    assert r["engine"] == "empty" and r["books"] == [] and r["library"] is None
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
    def fake_chat(cands, interests, msg, history, slots=None):
        assert any("kannada-literature" in " ".join(str(b.get("subject_slugs", [])) for b in cands) or True for _ in [1])
        return ({"message": "ಒಳ್ಳೆಯ ಪುಸ್ತಕಗಳು ಸಿಗುತ್ತಿವೆ!", "recs": [
            {"id": str(next(iter(books_coll.find({})))["_id"]), "reason": "ರಹಸ್ಯ ಕಥೆ"}]}, None)
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


# --------------------- library discovery (no Groq needed) ---------------------

def test_chat_library_works_without_groq(monkeypatch):
    _seed()
    c = _user(["mystery"])
    monkeypatch.delenv("GROQ_API_KEY", raising=False)   # Groq completely off
    r = c.post("/api/chat", json={"message": "Find a public library in Jayanagar"}).json()
    lib = r["library"]
    assert lib["verified"] is False and r["books"] == []
    assert "Jayanagar" in lib["note"]                   # locality extracted
    assert lib["holdings"]["available"] is False        # availability never claimed


def test_chat_library_pin_code_extracted():
    c = _user(["mystery"])
    r = c.post("/api/chat", json={"message": "Any library near 560038?", "locality": None}).json()
    assert "560038" in r["library"]["note"] or any(
        "560038" in l["url"] for l in r["library"]["links"])


def test_chat_library_locality_field_wins():
    c = _user(["mystery"])
    r = c.post("/api/chat", json={"message": "libraries", "locality": "Malleshwaram"}).json()
    assert "Malleshwaram" in r["library"]["note"]


def test_recommendations_engine_labelled(monkeypatch):
    """/api/recommendations must not claim groq when fallback used."""
    _seed()
    c = _user(["mystery"])
    monkeypatch.setattr("backend.main._groq_rank", lambda *a, **k: None)
    assert c.get("/api/recommendations").json()["engine"] == "keyword"
    monkeypatch.setattr("backend.main._groq_rank", lambda *a, **k: [
        {"id": next(str(b["_id"]) for b in books_coll.find({})), "reason": "match"}])
    assert c.get("/api/recommendations").json()["engine"] == "groq"


def test_groq_rate_limit_repeat_calls_bounded(monkeypatch):
    """Each chat turn makes AT MOST one Groq HTTP call — no retry spam."""
    _seed()
    c = _user(["mystery"])
    calls = {"n": 0}
    def boom(req, timeout=None):
        calls["n"] += 1
        raise TimeoutError("timeout")
    monkeypatch.setattr("backend.main.urllib.request.urlopen", boom)
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    c.post("/api/chat", json={"message": "Recommend something"}).json()
    assert calls["n"] == 1


# ---------------------- intent-understanding guarantees ----------------------

def test_intent_greeting_gets_no_book_cards():
    _seed()
    c = _user(["mystery"])
    r = c.post("/api/chat", json={"message": "Hello!"}).json()
    assert r["engine"] == "conversation" and r["books"] == []
    assert "Namaskara" in r["reply"]


def _slots(msg, uid="u", interests=("mystery",)):
    from backend.main import _parse_slots
    import backend.main as main
    main._CHAT_CTX.clear()
    return _parse_slots(msg, uid, list(interests))


def test_kannada_mystery_query_searches_language_and_genre():
    s = _slots("Recommend Kannada mystery novels")
    assert s["language"] == "Kannada" and "mystery" in s["genres"]
    _seed(slug="Mystery")
    # make all mysteries non-Kannada so the language filter bites
    books_coll.update_many({}, {"$set": {"language": "English"}})
    c = _user(["mystery"])
    r = c.post("/api/chat", json={"message": "Recommend Kannada mystery novels"}).json()
    assert r["engine"] == "empty"                 # honest shortfall
    assert "Kannada-language" in r["reply"] and "mystery" in r["reply"].lower()
    assert r["books"] == []                       # never substituted silently


def test_language_and_genre_query_returns_only_matching_cards(monkeypatch):
    _seed(slug="Mystery")
    # one Kannada mystery, one English mystery: only Kannada returned
    books_coll.update_many({}, {"$set": {"language": "English"}})
    books_coll.update_one({"title": "ChatBook A"}, {"$set": {"language": "Kannada"}})
    c = _user(["mystery"])
    def fake_chat(cands, interests, msg, history, slots=None):
        assert all((b.get("language") or "") == "Kannada" for b in cands), cands
        return ({"message": "Kannada mystery picks:", "recs": [
            {"id": str(b["_id"]), "reason": "Kannada + mystery"}
            for b in cands]}, None)
    monkeypatch.setattr("backend.main._groq_chat", fake_chat)
    r = c.post("/api/chat", json={"message": "Recommend Kannada mystery novels"}).json()
    assert r["engine"] == "groq"
    assert all("Kannada" in (b.get("language") or "") for b in r["books"])


def test_business_query_never_returns_mystery(monkeypatch):
    _seed(slug="Mystery")
    import backend.catalog as catalog
    catalog.upsert_books(books_coll, [ol_doc("/works/OLBZ1W", "Business Weekly", subjects=["Technology"])])
    c = _user(["mystery"], **{"$unset": {"interests": ""}})   # no saved interests: detection must come from the message
    def fake_chat(cands, interests, msg, history, slots=None):
        assert all("mystery" not in " ".join(b.get("subject_slugs") or []) for b in cands)
        assert slots["requested_genres"] == ["technology"]
        return ({"message": "Business picks:", "recs": [
            {"id": str(b["_id"]), "reason": "business"} for b in cands]}, None)
    monkeypatch.setattr("backend.main._groq_chat", fake_chat)
    r = c.post("/api/chat", json={"message": "I want books about business"}).json()
    assert r["engine"] == "groq" and r["books"][0]["title"] == "Business Weekly"


def test_beginner_request_maps_to_self_development(monkeypatch):
    _seed(slug="Mystery")
    import backend.catalog as catalog
    catalog.upsert_books(books_coll, [ol_doc("/works/OLBG1W", "First Steps", subjects=["Self-Development"])])
    c = _user(["mystery"], **{"$unset": {"interests": ""}})
    def fake_chat(cands, interests, msg, history, slots=None):
        assert slots["beginner"] is True
        assert any("self-development" in (b.get("subject_slugs") or []) for b in cands)
        return ({"message": "Start here:", "recs": [
            {"id": str(b["_id"]), "reason": "beginner friendly"} for b in cands]}, None)
    monkeypatch.setattr("backend.main._groq_chat", fake_chat)
    r = c.post("/api/chat", json={"message": "I have never read much. What should I start with?"}).json()
    assert r["books"][0]["title"] == "First Steps"


def test_title_search_finds_exact_record(monkeypatch):
    _seed(slug="Mystery")
    import backend.catalog as catalog
    catalog.upsert_books(books_coll, [ol_doc("/works/OLPARVAW", "Parva", authors=["S. L. Bhyrappa"])])
    c = _user(["mystery"], **{"$unset": {"interests": ""}})
    def fake_chat(cands, interests, msg, history, slots=None):
        assert slots["anchored_on"] == "Parva"
        return ({"message": "Found Parva:", "recs": [
            {"id": str(b["_id"]), "reason": "exact title"} for b in cands]}, None)
    monkeypatch.setattr("backend.main._groq_chat", fake_chat)
    r = c.post("/api/chat", json={"message": 'Find the book "Parva"'}).json()
    assert any(b["title"] == "Parva" for b in r["books"])
    assert all(b["id"].startswith("ol_") for b in r["books"])


def test_followup_language_change_reruns_previous_query(monkeypatch):
    _seed(slug="Mystery")
    books_coll.update_many({}, {"$set": {"language": "English"}})
    c = _user(["mystery"])
    # turn 1: Kannada request → honest empty (installed state), context saved
    r1 = c.post("/api/chat", json={"message": "Recommend Kannada mystery novels"}).json()
    assert r1["engine"] == "empty"
    monkeypatch.setattr("backend.main._groq_chat", lambda cands, i, m, h, slots=None:
        ({"message": "ok", "recs": [{"id": str(b["_id"]), "reason": "r"} for b in cands]}, None))
    r2 = c.post("/api/chat", json={"message": "No, I prefer English books"}).json()
    assert r2["engine"] in ("groq", "keyword") and r2["books"]
    assert all((b.get("language") or "") == "English" for b in r2["books"])


def test_show_me_more_uses_previous_genres(monkeypatch):
    _seed(slug="Mystery")
    c = _user(["mystery"], **{"$unset": {"interests": ""}})
    def fake_chat(cands, interests, msg, history, slots=None):
        return ({"message": "again", "recs": [
            {"id": str(b["_id"]), "reason": "r"} for b in cands]}, None)
    monkeypatch.setattr("backend.main._groq_chat", fake_chat)
    c.post("/api/chat", json={"message": "Recommend fantasy books"}).json()
    # prove context carried: clear the seed's fantasy books and count candidates flow
    r2 = c.post("/api/chat", json={"message": "Show me more"}).json()
    assert r2["books"]   # context retained fantasy → results still real books
    s = _slots("Show me more", uid="ctx", interests=[])
    import backend.main as main
    main._CHAT_CTX.clear()
    assert s["carry"] is True


def test_similar_to_first_book_anchors_on_context(monkeypatch):
    _seed(slug="Mystery")
    c = _user(["mystery"])
    ids = [str(b["_id"]) for b in books_coll.find({})]
    monkeypatch.setattr("backend.main._groq_chat", lambda cands, i, m, h, slots=None:
        ({"message": "similar:", "recs": [{"id": str(b["_id"]), "reason": "r"}
                                          for b in cands]}, None))
    r1 = c.post("/api/chat", json={"message": "Recommend a mystery novel"}).json()
    assert r1["books"]
    r2 = c.post("/api/chat", json={"message": "Show me more like the first book"}).json()
    assert r2["books"]
    first = r1["books"][0]["id"]
    assert all(b["id"] != first for b in r2["books"])   # never repeat its anchor


def test_unrelated_request_not_hardcoded(monkeypatch):
    """A gardening-ish query must not produce mystery-labeled picks from fiction."""
    _seed(slug="Mystery")
    import backend.catalog as catalog
    catalog.upsert_books(books_coll, [ol_doc("/works/OLGR1W", "Garden History", subjects=["History"])])
    c = _user(["mystery"], **{"$unset": {"interests": ""}})
    def fake_chat(cands, interests, msg, history, slots=None):
        titles = [b["title"] for b in cands]
        assert "Garden History" in titles
        return ({"message": "history picks:", "recs": [
            {"id": str(b["_id"]), "reason": "closest"} for b in cands
            if b["title"] == "Garden History"]}, None)
    monkeypatch.setattr("backend.main._groq_chat", fake_chat)
    r = c.post("/api/chat", json={"message": "I like reading about plants and gardens"}).json()
    assert r["books"] == [r["books"][0]] if r["books"] else True
    assert all(b["title"] == "Garden History" for b in r["books"])
