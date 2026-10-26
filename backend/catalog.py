"""Catalogue import/normalization from the Open Library Search API.

Bibliographic metadata only — never claims about physical library holdings.
Every record carries its source id so provenance can be audited/refreshed.
Missing metadata stays missing (None/[]) — nothing is invented.
"""
import json
import re
import time
import urllib.request
from datetime import datetime, timezone

OL_SEARCH = "https://openlibrary.org/search.json"
OL_FIELDS = ("key,title,author_name,first_publish_year,language,"
             "subject,description,cover_i,isbn,lending_edition_s")

# allowed normalized category slugs (mirror the app's genre vocabulary)
SLUGS = {
    "horror", "supernatural", "spirituality", "mystery", "thriller", "fantasy",
    "romance", "science-fiction", "technology", "self-development",
    "biography", "history", "philosophy", "kannada-literature",
}

_KN_RE = re.compile(r"kannada|ಕನ್ನಡ", re.I)
_KN_LANG = {"kan", "kn"}
_LANG_LABEL = {"eng": "English", "en": "English", "kan": "Kannada", "kn": "Kannada",
               "hin": "Hindi", "tam": "Tamil", "tel": "Telugu", "mar": "Marathi",
               "ben": "Bengali", "mal": "Malayalam", "urd": "Urdu", "san": "Sanskrit"}


def _clean_title(t: str) -> str:
    # collapse whitespace; strip trailing pagination notes like "… Volume 2"
    t = re.sub(r"\s+", " ", t or "").strip()
    return re.sub(r"[\[\(].*?[\]\)]", "", t).strip() or (t or "")


def normalize_ol_doc(doc: dict) -> dict:
    """Open Library search doc → normalized book record. No invented values."""
    key = (doc.get("key") or "").strip()
    if not key:
        return None
    title = (doc.get("title") or "").strip()
    if not title:
        return None                                  # never store title-less records
    authors = [a.strip() for a in (doc.get("author_name") or []) if a and a.strip()]
    subjects = [s.strip() for s in (doc.get("subject") or []) if s and s.strip()][:12]

    description = doc.get("description")
    if isinstance(description, dict):                # {"type":..., "value": "..."}
        description = description.get("value")
    if description is not None:
        description = re.sub(r"\s+", " ", str(description)).strip() or None
        if not description:
            description = None

    langs = [l.strip() for l in (doc.get("language") or []) if l and l.strip()]
    isbns = [i for i in (doc.get("isbn") or []) if i and i.strip()][:5]

    slug_set = set()
    for s in subjects:
        sl = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
        for cand in (sl, ("kannada-literature" if _KN_RE.search(s) else sl)):
            if cand in SLUGS:
                slug_set.add(cand)

    cover_i = doc.get("cover_i")
    now = datetime.now(timezone.utc).isoformat()
    _has_kn = _KN_LANG & set(langs)
    _has_en = "en" in langs
    language = ("Bilingual" if _has_kn and _has_en
                else "Kannada" if _has_kn
                else "English" if _has_en
                else _LANG_LABEL.get(langs[0]) if langs else None)
    return {
        "_id": _stable_id(key),
        "source": "openlibrary",
        "source_id": key,                            # e.g. "/works/OL1168366W"
        "work_id": key.rsplit("/", 1)[-1],
        "edition_id": doc.get("lending_edition_s") or None,
        "title": _clean_title(title),
        "authors": authors,
        "year": int(doc["first_publish_year"]) if doc.get("first_publish_year") else None,
        "language_codes": langs,
        "language": language,
        "subject_slugs": sorted(slug_set),
        "subjects": subjects,
        "description": description,                  # None when source has none
        "isbn": isbns[0] if isbns else None,
        "cover_url": (f"https://covers.openlibrary.org/b/id/{cover_i}-M.jpg"
                      if cover_i else None),
        "imported_at": now,
        "updated_at": now,
    }


def _stable_id(source_id: str) -> str:
    import hashlib
    return "ol_" + hashlib.sha1(source_id.encode()).hexdigest()[:12]


def fetch_books(query: str, *, limit: int = 200, timeout: int = 15) -> list:
    """Controlled fetch from Open Library Search API. Raises on failure."""
    url = f"{OL_SEARCH}?q={urllib.request.quote(query)}&fields={OL_FIELDS}&limit={min(limit, 200)}"
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        docs = json.load(resp).get("docs", [])
    time.sleep(1.0)                                  # polite rate limit
    return docs


def upsert_books(books_coll, docs: list) -> dict:
    """Dedupe on source_id; normalize; upsert. Returns honest counts."""
    inserted = updated = rejected = 0
    for raw in docs:
        norm = normalize_ol_doc(raw)
        if norm is None:
            rejected += 1
            continue
        res = books_coll.update_one(
            {"source_id": norm["source_id"]},
            {"$set": norm, "$setOnInsert": {"created_at": norm["imported_at"]}},
            upsert=True)
        if res.upserted_id:
            inserted += 1
        else:
            updated += 1
    return {"inserted": inserted, "updated": updated, "rejected": rejected}


if __name__ == "__main__":
    # manual import:  python3 catalog.py import
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    import pymongo
    db = pymongo.MongoClient(os.environ.get("MONGO_URI", "mongodb://localhost:27017"))[
        os.environ.get("MONGO_DB", "pustakamitra")]
    books = db["books"]
    books.create_index("source_id", unique=True)
    queries = json.load(open(os.path.join(os.path.dirname(__file__),
                                          "catalog_queries.json")))
    totals = {"inserted": 0, "updated": 0, "rejected": 0}
    for q in queries:
        try:
            docs = fetch_books(q["q"], limit=q.get("limit", 100))
        except Exception as e:
            print(f"[warn] query failed: {q['q']}: {e}", file=sys.stderr)
            continue
        r = upsert_books(books, docs)
        for k in totals:
            totals[k] += r[k]
        print(f"({q['q']!r}): {r}", file=sys.stderr)
    print(totals, "total in db:", books.count_documents({}))
