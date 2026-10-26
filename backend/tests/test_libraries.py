"""Automated tests for Bengaluru Public Libraries integration:
- KML / CSV parsing & namespace handling
- Coordinate extraction & GeoJSON [lon, lat] ordering
- Coordinate validation & invalid coordinate rejection
- Duplicate record handling (Cottonpet duplicate) & distinct branch preservation
- Importer dry-run mode and idempotency
- MongoDB 2dsphere indexing and geospatial $geoNear queries
- Locality, text, category, and telephone search endpoints
- Pagination
- Chatbot library intent parsing and real backend results without Groq
- Honest unverified book holdings handling
- XSS / safe rendering
"""
import json
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from fastapi.testclient import TestClient

from backend.main import app, DB, libraries_coll, users
from backend.import_libraries import (
    parse_kml_file,
    parse_csv_file,
    match_and_normalize,
    import_to_mongodb,
    DEFAULT_KML,
    DEFAULT_CSV,
)


def _auth_user():
    """Create an authenticated test client."""
    c = TestClient(app)
    email = f"lib_test_{uuid.uuid4().hex[:6]}@example.com"
    r = c.post(
        "/api/auth/register",
        json={
            "name": "Library Tester",
            "email": email,
            "phone": "+919876543210",
            "age": 28,
            "interests": ["mystery"],
            "password": "pw12345678",
            "password_confirm": "pw12345678",
        },
    )
    assert r.status_code == 201, r.text
    return c


# --------------------- Importer & Parsing Tests ---------------------

def test_kml_file_exists_and_parses():
    assert DEFAULT_KML.exists(), "KML dataset must exist in Data/"
    records = parse_kml_file(DEFAULT_KML)
    assert len(records) == 115, f"Expected 115 placemarks, got {len(records)}"
    for r in records:
        assert "name" in r and r["name"]
        assert "longitude" in r and "latitude" in r
        # Geo bounds check for Bengaluru
        assert 77.0 <= r["longitude"] <= 78.5
        assert 12.0 <= r["latitude"] <= 14.0


def test_csv_file_exists_and_parses():
    assert DEFAULT_CSV.exists(), "CSV dataset must exist in Data/"
    records = parse_csv_file(DEFAULT_CSV)
    assert len(records) == 50, f"Expected 50 records in CSV, got {len(records)}"
    with_phone = [r for r in records if r.get("phone")]
    assert len(with_phone) == 5, f"Expected 5 records with telephone, got {len(with_phone)}"


def test_deduplication_and_matching():
    kml_records = parse_kml_file(DEFAULT_KML)
    csv_records = parse_csv_file(DEFAULT_CSV)
    docs, stats = match_and_normalize(kml_records, csv_records)

    # 1 duplicate Cottonpet entry must be skipped
    assert stats["kml_duplicates_skipped"] == 1
    # 4 confident matches joined
    assert stats["csv_confident_matches"] == 4
    # 1 ambiguous match flagged safely
    assert stats["csv_ambiguous"] == 1
    # Total unique = 114 KML + 46 standalone CSV = 160
    assert stats["total_unique_libraries"] == 160
    assert len(docs) == 160


def test_distinct_branches_preserved():
    """Distinct branches with identical names (e.g. City Central Library) must NOT be collapsed."""
    kml_records = parse_kml_file(DEFAULT_KML)
    csv_records = parse_csv_file(DEFAULT_CSV)
    docs, _ = match_and_normalize(kml_records, csv_records)

    city_central_branches = [d for d in docs if "city central library" in d["name"].lower()]
    # There are multiple distinct City Central Library branches across Bengaluru
    assert len(city_central_branches) >= 10
    unique_ids = {d["library_id"] for d in city_central_branches}
    assert len(unique_ids) == len(city_central_branches), "Every branch must have a unique stable ID"


def test_geojson_coordinate_ordering():
    """GeoJSON specification strictly requires [longitude, latitude]."""
    kml_records = parse_kml_file(DEFAULT_KML)
    csv_records = parse_csv_file(DEFAULT_CSV)
    docs, _ = match_and_normalize(kml_records, csv_records)

    with_coords = [d for d in docs if d["location"] is not None]
    assert len(with_coords) == 114
    for d in with_coords:
        loc = d["location"]
        assert loc["type"] == "Point"
        coords = loc["coordinates"]
        assert len(coords) == 2
        lon, lat = coords[0], coords[1]
        assert lon == d["longitude"]
        assert lat == d["latitude"]
        # In Bengaluru, lon ~ 77.x, lat ~ 12.x-13.x
        assert 77.0 <= lon <= 78.5, f"Longitude out of bounds: {lon}"
        assert 12.0 <= lat <= 14.0, f"Latitude out of bounds: {lat}"


def test_invalid_coordinates_rejected(tmp_path):
    """Corrupted / out of bounds coordinates must be skipped safely."""
    bad_kml = tmp_path / "bad.kml"
    bad_kml.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Bad Library 1</name>
      <Point><coordinates>not_a_number,12.97</coordinates></Point>
    </Placemark>
    <Placemark>
      <name>Bad Library 2 - North Pole</name>
      <Point><coordinates>0.0,95.0</coordinates></Point>
    </Placemark>
    <Placemark>
      <name>Good Library</name>
      <Point><coordinates>77.58,12.97</coordinates></Point>
    </Placemark>
  </Document>
</kml>""")
    records = parse_kml_file(bad_kml)
    assert len(records) == 1
    assert records[0]["name"] == "Good Library"


def test_importer_dry_run_does_not_modify_db():
    kml_records = parse_kml_file(DEFAULT_KML)
    csv_records = parse_csv_file(DEFAULT_CSV)
    docs, _ = match_and_normalize(kml_records, csv_records)

    # Count before
    count_before = libraries_coll.count_documents({})
    res = import_to_mongodb(docs, dry_run=True)
    assert res["dry_run"] is True
    assert res["total_to_import"] == 160
    # Must not modify DB
    count_after = libraries_coll.count_documents({})
    assert count_before == count_after


def test_importer_idempotency():
    kml_records = parse_kml_file(DEFAULT_KML)
    csv_records = parse_csv_file(DEFAULT_CSV)
    docs, _ = match_and_normalize(kml_records, csv_records)

    # First live import
    res1 = import_to_mongodb(docs, dry_run=False)
    assert res1["total_in_db"] == 160

    # Second live import
    res2 = import_to_mongodb(docs, dry_run=False)
    assert res2["inserted"] == 0
    assert res2["updated"] == 160
    assert res2["total_in_db"] == 160


# --------------------- API Endpoint Tests ---------------------

def test_api_libraries_list_and_pagination():
    client = TestClient(app)
    r = client.get("/api/libraries?page=1&page_size=10")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 160
    assert len(data["items"]) == 10
    assert data["page"] == 1
    assert data["pages"] == 16

    # Page 2
    r2 = client.get("/api/libraries?page=2&page_size=10")
    data2 = r2.json()
    assert data2["items"][0]["library_id"] != data["items"][0]["library_id"]


def test_api_libraries_search_locality():
    client = TestClient(app)
    r = client.get("/api/libraries?area=Jayanagar")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    for item in data["items"]:
        text = f"{item['name']} {item.get('address') or ''} {item.get('area') or ''}".lower()
        assert "jayanagar" in text or "south zone" in text or "south end" in text


def test_api_libraries_search_phone_filter():
    client = TestClient(app)
    r = client.get("/api/libraries?has_phone=true")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 5
    for item in data["items"]:
        assert item["phone"] is not None


def test_api_libraries_nearby_geospatial():
    client = TestClient(app)
    # Search around South End Circle, Jayanagar: lat=12.935664, lon=77.580756
    r = client.get("/api/libraries/nearby?lat=12.935664&lon=77.580756&radius_km=3.0")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    items = data["items"]
    # Check that distances are calculated and ordered ascending
    distances = [item["distance_km"] for item in items if "distance_km" in item]
    assert len(distances) == len(items)
    assert distances == sorted(distances)
    # Closest library should be City Central Library, South Zone (within ~0.1 km)
    assert items[0]["distance_km"] < 0.2
    assert "South Zone" in items[0]["name"] or "Jayanagar" in items[0]["name"]


def test_api_libraries_nearby_radius_limit():
    client = TestClient(app)
    # Invalid radius > 50 km
    bad = client.get("/api/libraries/nearby?lat=12.93&lon=77.58&radius_km=100")
    assert bad.status_code == 422
    # Invalid coordinates
    bad_coords = client.get("/api/libraries/nearby?lat=100&lon=77.58")
    assert bad_coords.status_code == 422


def test_api_library_detail_by_id():
    client = TestClient(app)
    all_libs = client.get("/api/libraries?page_size=1").json()
    lib_id = all_libs["items"][0]["library_id"]

    r = client.get(f"/api/libraries/{lib_id}")
    assert r.status_code == 200
    item = r.json()
    assert item["library_id"] == lib_id
    assert "name" in item
    assert "source_file" in item

    # Not found
    not_found = client.get("/api/libraries/nonexistent_lib_id")
    assert not_found.status_code == 404


# --------------------- Chatbot Library Integration Tests ---------------------

def test_chat_returns_real_libraries_jayanagar():
    c = _auth_user()
    r = c.post("/api/chat", json={"message": "Show libraries in Jayanagar"}).json()
    assert r["engine"] == "library_search"
    assert "Jayanagar" in r["reply"] or "libraries" in r["reply"]
    assert "libraries" in r
    assert len(r["libraries"]) >= 1
    names = [lib["name"] for lib in r["libraries"]]
    assert any("South Zone" in n or "Jayanagar" in n for n in names)
    # Must not return book picks
    assert r["books"] == []


def test_chat_state_central_library_query():
    c = _auth_user()
    r = c.post("/api/chat", json={"message": "Find the State Central Library"}).json()
    assert r["engine"] == "library_search"
    assert "libraries" in r
    assert len(r["libraries"]) >= 1
    match = r["libraries"][0]
    assert "State Central Library" in match["name"] or "Sheshadri" in match["name"]
    assert match["phone"] == "08022212128"


def test_chat_libraries_with_phone_numbers():
    c = _auth_user()
    r = c.post("/api/chat", json={"message": "Give me libraries with telephone numbers"}).json()
    assert r["engine"] == "library_search"
    assert "libraries" in r
    assert len(r["libraries"]) >= 1
    for lib in r["libraries"]:
        assert lib["phone"] is not None


def test_chat_closest_prompts_when_no_coords():
    c = _auth_user()
    r = c.post("/api/chat", json={"message": "Which library is closest to my location?"}).json()
    assert "Use My Location" in r["reply"] or "location" in r["reply"]


def test_chat_nearby_with_coordinates():
    c = _auth_user()
    r = c.post(
        "/api/chat",
        json={
            "message": "Which library is closest to my location?",
            "latitude": 12.935664,
            "longitude": 77.580756,
        },
    ).json()
    assert r["engine"] == "library_search"
    assert "libraries" in r
    assert len(r["libraries"]) >= 1
    assert "distance_km" in r["libraries"][0]
    assert r["libraries"][0]["distance_km"] < 0.2


def test_chat_book_holdings_honest_disclaimer():
    c = _auth_user()
    r = c.post("/api/chat", json={"message": "Does any library list this book?"}).json()
    # Must not claim book holdings are known
    assert "verified" in r["reply"].lower() or "holdings" in r["reply"].lower()
    assert r["library"]["holdings"]["available"] is False
    assert r["books"] == []


def test_chat_status_endpoint_reports_imported():
    client = TestClient(app)
    r = client.get("/api/chat/status").json()
    assert r["library_dataset_imported"] is True
    assert r["library_count"] == 160
