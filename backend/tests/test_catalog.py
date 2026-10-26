"""Catalogue (Open Library import), books endpoints and Groq recommendations.

External HTTP is mocked — no live Open Library / Groq calls in tests.
"""
import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.main import app, books_coll
import backend.catalog as catalog


def setup_function():
    books_coll.delete_many({})


def ol_doc(key, title, **kw):
    d = {"key": key, "title": title, "author_name": kw.get("authors", ["Some Author"]),
         "language": kw.get("language", ["kan"]), "subject": kw.get("subjects", []),
         "cover_i": kw.get("cover_i"), "first_publish_year": kw.get("year", 2001),
         "isbn": kw.get("isbn", ["9780306406157"])}
    for k in ("cover_i",):
        if d[k] is None:
            d.pop(k)
    if "description" in kw:
        d["description"] = kw["description"]
    return d


def test_normalize_full_record():
    b = catalog.normalize_ol_doc(ol_doc("/works/OL1W", "  Mooksṇa   Peak  ",
                                        cover_i=123, year=1998, description="A trek tale. ",
                                        subjects=["Kannada fiction", "Mystery"]))
    assert b["title"].startswith("Mooksṇa") and not b["title"].endswith(" ")
    assert b["source"] == "openlibrary" and b["work_id"] == "OL1W"
    assert b["year"] == 1998 and b["language"] == "Kannada"
    assert b["cover_url"].endswith("-M.jpg") and "covers.openlibrary.org" in b["cover_url"]
    assert b["description"] == "A trek tale."
    assert "kannada-literature" in b["subject_slugs"] and "mystery" in b["subject_slugs"]
    assert b["imported_at"] and b["source_id"] == "/works/OL1W"


def test_normalize_missing_fields_never_invented():
    b = catalog.normalize_ol_doc({"key": "/works/OL2W", "title": "Bare Record"})
    assert b["authors"] == [] and b["year"] is None
    assert b["cover_url"] is None and b["description"] is None
    assert b["isbn"] is None and b["language"] is None and b["subject_slugs"] == []


def test_normalize_rejects_bad_source_records():
    assert catalog.normalize_ol_doc({"title": "no key"}) is None
    assert catalog.normalize_ol_doc({"key": "/works/OL3W", "title": ""}) is None


def test_upsert_dedupes_on_source_id():
    r = catalog.upsert_books(books_coll, [ol_doc("/works/OL4W", "Dup A"),
                                          ol_doc("/works/OL4W", "Dup A 2nd ed")])
    assert r["inserted"] == 1 and r["updated"] == 1 and r["rejected"] == 0
    assert books_coll.count_documents({"source_id": "/works/OL4W"}) == 1


def test_normalize_dict_description():
    b = catalog.normalize_ol_doc(ol_doc("/works/OL5W", "Dict Desc",
                                        description={"type": "/type/text", "value": "v"}))
    assert b["description"] == "v"


def test_books_list_search_filter_pagination():
    for i in range(3):
        catalog.upsert_books(books_coll, [ol_doc(f"/works/OLM{i}W", f"T{i}",
                                                 subjects=["Mystery"] if i < 2 else [])])
    c = TestClient(app)
    r = c.get("/api/books?page_size=2")
    assert r.json()["total"] == 3 and len(r.json()["items"]) == 2 and r.json()["page"] == 1
    r = c.get("/api/books?page=2&page_size=2")
    assert len(r.json()["items"]) == 1
    r = c.get("/api/books?genre=mystery")
    assert r.json()["total"] == 2
    r = c.get("/api/books?q=t1")
    assert r.json()["total"] == 1 and r.json()["items"][0]["title"] == "T1"


def test_pub_book_has_no_fabricated_fields():
    catalog.upsert_books(books_coll, [ol_doc("/works/OL6W", "Provenance")])
    b = TestClient(app).get("/api/books").json()["items"][0]
    assert "rating" not in b and "ratings_count" not in b and "lib_count" not in b
    assert b["source"] == "openlibrary" and b["source_id"] == "/works/OL6W"


def test_book_detail_404_and_similar():
    catalog.upsert_books(books_coll, [ol_doc("/works/OLA", "A", subjects=["Mystery"]),
                                      ol_doc("/works/OLB", "B", subjects=["Mystery"]),
                                      ol_doc("/works/OLC", "C", subjects=["History"])])
    c = TestClient(app)
    a = c.get("/api/books")
    id_a = next(i["id"] for i in a.json()["items"] if i["title"] == "A")
    d = c.get(f"/api/books/{id_a}").json()
    assert d["similar"] and {s["title"] for s in d["similar"]} == {"B"}
    assert c.get("/api/books/nonexistent-id").status_code == 404


def test_sync_requires_token(monkeypatch):
    monkeypatch.delenv("CATALOG_SYNC_TOKEN", raising=False)
    import backend.main as main
    main.SYNC_TOKEN = None
    c = TestClient(app)
    assert c.post("/api/catalog/sync").status_code == 503
    main.SYNC_TOKEN = "secret"
    assert c.post("/api/catalog/sync", headers={"X-Admin-Token": "wrong"}).status_code == 401


def test_sync_imports_with_mocked_ol(monkeypatch):
    import backend.main as main
    monkeypatch.setattr(main, "SYNC_TOKEN", "secret")
    monkeypatch.setattr(catalog, "fetch_books",
                        lambda q, limit=100: [ol_doc(f"/works/OLS{i}W", f"S{i}") for i in range(2)])
    monkeypatch.setattr(json, "load", lambda *a, **k: [{"q": "kannada", "limit": 2}])
    r = TestClient(app).post("/api/catalog/sync", headers={"X-Admin-Token": "secret"})
    assert r.status_code == 200 and r.json()["counts"]["inserted"] == 2

# --------------------------- recommendations ---------------------------

def _mk_user(interests):
    c = TestClient(app)
    email = f"rec_{uuid.uuid4().hex[:6]}@example.com"
    r = c.post("/api/auth/register", json={"name": "Rec", "email": email,
                                           "phone": "+919876543211", "age": 30,
                                           "interests": interests,
                                           "password": "pw12345678",
                                           "password_confirm": "pw12345678"})
    assert r.status_code == 201, r.text
    return c


def test_recommendations_empty_catalogue():
    c = _mk_user(["mystery"])
    r = c.get("/api/recommendations")
    assert r.status_code == 200 and r.json() == {"engine": "empty", "items": []}


def test_recommendations_keyword_fallback_engine_labeled():
    catalog.upsert_books(books_coll, [ol_doc("/works/OLK1W", "Match",
                                             subjects=["Mystery", "Kannada fiction"]),
                                      ol_doc("/works/OLK2W", "Unmatch", subjects=["History"])])
    c = _mk_user(["mystery", "kannada-literature"])
    r = c.get("/api/recommendations").json()
    assert r["engine"] == "keyword"          # no GROQ_API_KEY in tests
    assert len(r["items"]) <= 6
    assert r["items"][0]["title"] == "Match" and "reason" in r["items"][0]
    assert "rating" not in r["items"][0]


def test_recommendations_groq_ids_validated(monkeypatch):
    catalog.upsert_books(books_coll, [ol_doc("/works/OLG1W", "Real1", subjects=["Mystery"]),
                                      ol_doc("/works/OLG2W", "Real2", subjects=["Mystery"])])
    c = _mk_user(["mystery"])
    real = {str(b["_id"]) for b in books_coll.find({})}
    good = next(iter(real))

    def fake_groq(cands, interests):
        # 1 valid id, 1 fabricated id, 1 missing reason — only valid survives
        return [{"id": good, "reason": "it matches"},
                {"id": "ol_fabricated999", "reason": "made up"},
                {"id": list(real - {good})[0]}]
    monkeypatch.setattr("backend.main._groq_rank", fake_groq)
    r = c.get("/api/recommendations").json()
    assert r["engine"] == "groq" and [i["id"] for i in r["items"]] == [good]


def test_recommendations_groq_failure_falls_back(monkeypatch):
    catalog.upsert_books(books_coll, [ol_doc("/works/OLF1W", "Failmatch",
                                             subjects=["Mystery"])])
    c = _mk_user(["mystery"])
    monkeypatch.setattr("backend.main._groq_rank", lambda c, i: None)
    r = c.get("/api/recommendations").json()
    assert r["engine"] == "keyword" and len(r["items"]) == 1


def test_groq_rank_sends_no_pii(monkeypatch):
    """Groq payload contains book metadata + interests, never the user's PII."""
    captured = {}
    class FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self):
            return json.dumps({"choices": [{"message": {"content":
                json.dumps({"recommendations": []})}}]}).encode()
    def fake_urlopen(req, timeout=None):
        captured["body"] = req.data
        return FakeResp()
    monkeypatch.setattr("backend.main.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    books_coll.insert_one(catalog.normalize_ol_doc(ol_doc("/works/OLP1W", "P1")))
    out = catalog.__dict__  # noqa
    import backend.main as main
    r = main._groq_rank(list(books_coll.find({})), ["mystery"])
    assert r == [] or r is None or r == []  # tolerated empty result
    body = json.loads(captured["body"].decode())
    text = json.dumps(body["messages"])
    for pii in ("home_address", "phone", "email", "gender", "dob"):
        assert f'"{pii}' not in text and pii not in json.dumps(body["messages"][1]["content"])
    assert body["messages"][1]["content"].count("candidates")

def test_groq_rank_requires_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    import backend.main as main
    assert main._groq_rank([{"_id": "x"}], []) is None


def test_recommendations_no_interests_honest_engine():
    """Signed-in user with NO interests gets engine 'no_interests', no blanket picks."""
    c = _mk_user(["mystery"])
    import uuid as _u
    email = "noint_" + _u.uuid4().hex[:5] + "@example.com"
    r = c.post("/api/auth/register", json={"name": "NoI", "email": email,
                                           "phone": "+919876543210", "age": 35,
                                           "interests": ["mystery"],
                                           "password": "pw12345678",
                                           "password_confirm": "pw12345678"})
    assert r.status_code == 201
    import backend.main as main
    main.users.update_one({"email": email}, {"$unset": {"interests": "", "other_interest": ""}})
    catalog.upsert_books(books_coll, [ol_doc("/works/OLNIW", "AnonPick", subjects=["History"])])
    body = c.get("/api/recommendations").json()
    assert body == {"engine": "no_interests", "items": []}


def test_recommendations_require_session():
    assert TestClient(app).get("/api/recommendations").status_code == 401


def test_frontend_genres_have_ids_and_labels(node=None):
    """The canonical GENRES list renders valid id/en/kn — no undefined chips."""
    import subprocess, textwrap, sys
    script = textwrap.dedent("""
        import { GENRES } from "/home/amul/Desktop/PusathakaMitra/js/services/api.js";
        const valid = new Set(["horror","supernatural","spirituality","mystery","thriller",
            "fantasy","romance","science-fiction","technology","self-development",
            "biography","history","philosophy","kannada-literature"]);
        // required by onboarding render (g.id/g.en/g.kn):
        for (const g of GENRES) {
            if (!g || typeof g.id !== "string" || !g.id) throw new Error("CHIP id bad: " + JSON.stringify(g));
            if (!g.en || !g.kn) throw new Error("CHIP label undefined: " + JSON.stringify(g));
            if (!valid.has(g.id)) throw new Error("CHIP not backend-valid: " + g.id);
        }
        // source files must read canonical properties, never g[0]/g[1]/g[2]
        const fs = await import("fs");
        for (const f of ["landing", "discover", "onboarding"]) {
            const src = fs.readFileSync(`/home/amul/Desktop/PusathakaMitra/js/pages/${f}.js`, "utf8");
            if (/\bg\[\d\]/.test(src)) throw new Error(f + " still indexes genres positionally");
            if (/g\.en|g\.kn|g\.id/.test(src)) { /* good */ }
        }
        // onboarding markup builds labelled buttons, never "undefined":
        const onb = fs.readFileSync("/home/amul/Desktop/PusathakaMitra/js/pages/onboarding.js", "utf8");
        const chip = onb.match(/bookService\.genres\.map\(\(g\) =>[\s\S]*?\)/)[0];
        const html = `(button ${chip.replace(/\\$\{g\.en\}/, "Horror").replace(/\\$\{g\.kn\}/, "ಭಯ").replace(/\\$\{g\.id\}/, "horror")})`;
        if (html.includes("undefined") || html.includes("null")) throw new Error("onboarding chip renders undefined/null");
        console.log("GENRES-OK");
    """)
    r = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True)
    assert r.returncode == 0, f"frontend genre check failed: {r.stderr}"
    assert "GENRES-OK" in r.stdout

def test_groq_model_env_override(monkeypatch):
    """GROQ_MODEL (env or backend/.env) reaches the Groq request body."""
    import backend.main as main
    monkeypatch.setattr(main, "GROQ_MODEL", "llama-test-model")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    captured = {}
    class FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps({"choices": [{"message": {"content": "{}"}}]}).encode()
    def fake_urlopen(req, timeout=None):
        captured["body"] = json.loads(req.data.decode())
        return FakeResp()
    monkeypatch.setattr("backend.main.urllib.request.urlopen", fake_urlopen)
    r = main._groq_rank([{"_id": "x", "title": "T", "authors": [], "subject_slugs": []}], [])
    assert captured["body"]["model"] == "llama-test-model"


def test_backend_env_file_not_tracked():
    import subprocess
    r = subprocess.run(["git", "check-ignore", "-v", "backend/.env"], capture_output=True, text=True)
    assert r.returncode == 0, "backend/.env must stay ignored by Git"
