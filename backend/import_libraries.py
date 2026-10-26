"""Bengaluru Public Library Importer for PustakaMitra AI.

Parses local KML and CSV datasets:
- Data/40839757-9521-4766-b8c0-9309cd9da1b0.kml
- Data/ddf6ea7d-eea3-44bb-972e-0e5fa911b55c.csv

Features:
- XML/KML namespace parsing (http://www.opengis.net/kml/2.2)
- Point coordinate extraction: GeoJSON [longitude, latitude]
- Coordinate bounds validation for Bengaluru (lon 77.0-78.5, lat 12.0-14.0)
- Exact duplicate detection (Cottonpet placemark)
- Conservative CSV-to-KML matching for verified records with contact numbers
- Ambiguous record flagging
- Idempotent upserts via stable library_id
- Dry-run mode (--dry-run)
- MongoDB 2dsphere indexing on location
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv
from pymongo import MongoClient

# Load environment variables
_BACKEND_DIR = Path(__file__).resolve().parent
_PROJECT_DIR = _BACKEND_DIR.parent
load_dotenv(_BACKEND_DIR / ".env", override=False)

DEFAULT_KML = _PROJECT_DIR / "Data" / "40839757-9521-4766-b8c0-9309cd9da1b0.kml"
DEFAULT_CSV = _PROJECT_DIR / "Data" / "ddf6ea7d-eea3-44bb-972e-0e5fa911b55c.csv"

KML_NS = {"kml": "http://www.opengis.net/kml/2.2"}

# Known Bengaluru localities/areas for heuristics extraction from placemark names
KNOWN_AREAS = [
    "Koramangala", "Indiranagar", "Jayanagar", "Basavanagudi", "Basavagudi",
    "Malleswaram", "Malleshwaram", "Vijayanagar", "Vijaynagar", "BTM Layout",
    "HSR Layout", "HSR", "Whitefield", "Peenya", "Yelahanka", "Cottonpet",
    "Lakkasandra", "Magadi Road", "Cubbon Park", "Dasarahalli", "Kumbalagodu",
    "Dayanand Nagar", "Kengeri", "N R Colony", "Vinayaka Layout", "J K Puram",
    "Gayatri Nagar", "Hampinagar", "R.T. Nagar", "RT Nagar", "Anekal",
    "Attibele", "Chandapura", "Sarjapur", "Bommasandra", "Hebbagodi",
    "Sahakarnagar", "JP Nagar", "Vijaya Bank Layout", "Parangipalya",
    "Saraswathipuram", "Double Road", "Sampige Road", "South End",
]


def _clean_text(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    # Strip HTML tags
    clean = re.sub(r"<[^>]*>", " ", text)
    # Collapse whitespace
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean or None


def _extract_area(name: str) -> Optional[str]:
    """Extract locality name from library name or branch string."""
    name_clean = _clean_text(name) or ""
    # Check explicit delimiters first: "Public Library, Lakkasandra" -> "Lakkasandra"
    for delim in [",", "-", "–", "—"]:
        if delim in name_clean:
            parts = [p.strip() for p in name_clean.split(delim)]
            for part in reversed(parts):
                for area in KNOWN_AREAS:
                    if area.lower() == part.lower() or area.lower() in part.lower():
                        return area
    # General substring search
    for area in KNOWN_AREAS:
        pattern = r"\b" + re.escape(area) + r"\b"
        if re.search(pattern, name_clean, re.I):
            return area
    return None


def _extract_phone(address_raw: str) -> Tuple[Optional[str], str]:
    """Extract telephone number from address string and return (phone, cleaned_address)."""
    phone = None
    clean_addr = address_raw
    m = re.search(r"\(?\s*(?:TEL\s*NO:?|TEL:?)\s*([0-9\s\-]+)\)?", address_raw, re.I)
    if m:
        raw_digits = re.sub(r"[^\d]", "", m.group(1))
        if len(raw_digits) in (10, 11):
            phone = raw_digits
            clean_addr = re.sub(r"\(?\s*(?:TEL\s*NO:?|TEL:?)\s*([0-9\s\-]+)\)?", "", address_raw, flags=re.I).strip()
            clean_addr = re.sub(r",\s*$", "", clean_addr).strip()
    return phone, clean_addr


def _make_library_id(source: str, identifier: str) -> str:
    h = hashlib.sha1(f"{source}:{identifier}".encode("utf-8")).hexdigest()[:12]
    return f"lib_{source}_{h}"


def parse_kml_file(kml_path: Path) -> List[dict]:
    """Parse KML file and extract library placemarks."""
    if not kml_path.exists():
        raise FileNotFoundError(f"KML file not found: {kml_path}")

    tree = ET.parse(str(kml_path))
    root = tree.getroot()

    placemarks_data = []
    folders = root.findall(".//kml:Folder", KML_NS)

    folders_to_scan = folders if folders else [root]

    for folder in folders_to_scan:
        folder_name = "General"
        if folder != root:
            fn = folder.find("kml:name", KML_NS)
            if fn is not None and fn.text:
                folder_name = fn.text.strip()

        for pm in folder.findall(".//kml:Placemark", KML_NS):
            name_elem = pm.find("kml:name", KML_NS)
            name = _clean_text(name_elem.text if name_elem is not None else "")
            if not name:
                continue

            desc_elem = pm.find("kml:description", KML_NS)
            desc = _clean_text(desc_elem.text if desc_elem is not None else "")

            point_elem = pm.find(".//kml:Point", KML_NS)
            if point_elem is None:
                continue

            coords_elem = point_elem.find("kml:coordinates", KML_NS)
            if coords_elem is None or not coords_elem.text:
                continue

            coords_raw = coords_elem.text.strip().split(",")
            if len(coords_raw) < 2:
                continue

            try:
                lon = float(coords_raw[0].strip())
                lat = float(coords_raw[1].strip())
            except ValueError:
                continue

            # Validate coordinate ranges: lon [-180, 180], lat [-90, 90]
            # Validate Bengaluru bounds (lon 77.0-78.5, lat 12.0-14.0)
            if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
                continue
            if not (77.0 <= lon <= 78.5 and 12.0 <= lat <= 14.0):
                continue

            area = _extract_area(name)
            placemarks_data.append({
                "name": name,
                "category": folder_name,
                "description": desc,
                "longitude": lon,
                "latitude": lat,
                "area": area,
                "source_file": kml_path.name,
            })

    return placemarks_data


def parse_csv_file(csv_path: Path) -> List[dict]:
    """Parse accompanying CSV dataset."""
    if not csv_path.exists():
        return []

    records = []
    with open(csv_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sl_no = (row.get("Sl. No") or "").strip()
            category = (row.get("Category") or "").strip()
            address_raw = (row.get("Address") or "").strip()
            if not address_raw:
                continue

            phone, clean_addr = _extract_phone(address_raw)
            area = _extract_area(clean_addr)
            records.append({
                "sl_no": sl_no,
                "category": category,
                "address": clean_addr,
                "raw_address": address_raw,
                "phone": phone,
                "area": area,
                "source_file": csv_path.name,
            })
    return records


def match_and_normalize(
    kml_records: List[dict], csv_records: List[dict]
) -> Tuple[List[dict], dict]:
    """Match CSV and KML records conservatively, deduplicate, and normalize."""
    stats = {
        "kml_scanned": len(kml_records),
        "csv_scanned": len(csv_records),
        "kml_duplicates_skipped": 0,
        "csv_confident_matches": 0,
        "csv_unmatched": 0,
        "csv_ambiguous": 0,
        "total_unique_libraries": 0,
    }

    # 1. Deduplicate KML records on exact (name, lon, lat)
    unique_kml = []
    seen_coords_name = set()

    for r in kml_records:
        key = (r["name"].lower(), round(r["longitude"], 6), round(r["latitude"], 6))
        if key in seen_coords_name:
            stats["kml_duplicates_skipped"] += 1
            continue
        seen_coords_name.add(key)
        unique_kml.append(r)

    # 2. Confident cross-referencing between CSV and KML
    csv_to_kml = {}
    matched_kml_indices = set()

    for csv_idx, c in enumerate(csv_records):
        addr_lower = c["address"].lower()
        sl = c["sl_no"]

        candidates = []
        if sl == "1" or "sheshadri" in addr_lower:
            for k_idx, k in enumerate(unique_kml):
                if "sheshadri" in k["name"].lower():
                    candidates.append(k_idx)
        elif sl == "2" or ("south zone" in addr_lower and "south end" in addr_lower):
            for k_idx, k in enumerate(unique_kml):
                if "south zone" in k["name"].lower() and "hsr" not in k["name"].lower():
                    if abs(k["latitude"] - 12.935664) < 0.01:
                        candidates.append(k_idx)
        elif sl == "4" or ("north zone" in addr_lower and "malleswaram" in addr_lower):
            for k_idx, k in enumerate(unique_kml):
                if "north zone" in k["name"].lower():
                    candidates.append(k_idx)
        elif sl == "6" or ("west zone" in addr_lower and "hampinagar" in addr_lower):
            for k_idx, k in enumerate(unique_kml):
                if "west zone" in k["name"].lower() and abs(k["latitude"] - 12.960197) < 0.01:
                    candidates.append(k_idx)
        elif sl == "7" or "vijaynagar" in addr_lower:
            for k_idx, k in enumerate(unique_kml):
                if "vijayanagar central library" in k["name"].lower():
                    candidates.append(k_idx)

        if len(candidates) == 1:
            k_idx = candidates[0]
            if k_idx not in matched_kml_indices:
                csv_to_kml[csv_idx] = k_idx
                matched_kml_indices.add(k_idx)
                stats["csv_confident_matches"] += 1
            else:
                stats["csv_ambiguous"] += 1
        elif len(candidates) > 1:
            stats["csv_ambiguous"] += 1
        else:
            stats["csv_unmatched"] += 1

    # 3. Assemble normalized records
    now_iso = datetime.now(timezone.utc).isoformat()
    normalized_docs = []

    # Process KML records (with merged CSV data where matched)
    for k_idx, k in enumerate(unique_kml):
        lon, lat = k["longitude"], k["latitude"]
        coord_key = f"{round(lon, 6)}_{round(lat, 6)}_{k['name'].lower()}"
        lib_id = _make_library_id("kml", coord_key)

        matched_csv = None
        for csv_idx, target_k_idx in csv_to_kml.items():
            if target_k_idx == k_idx:
                matched_csv = csv_records[csv_idx]
                break

        category = k["category"]
        address = None
        phone = None
        source = "kml"
        verification_status = "verified_location"

        if matched_csv:
            source = "kml+csv"
            verification_status = "verified_location_and_contact"
            address = matched_csv["address"]
            phone = matched_csv["phone"]
            if matched_csv["category"] and matched_csv["category"] != "City Central Library":
                category = f"{category} ({matched_csv['category']})"

        if not address and k["area"]:
            address = f"{k['area']}, Bengaluru, Karnataka"
        elif not address:
            address = "Bengaluru, Karnataka"

        doc = {
            "library_id": lib_id,
            "name": k["name"],
            "category": category,
            "branch": k["name"] if "Library" not in k["name"] else None,
            "address": address,
            "area": k["area"] or (matched_csv["area"] if matched_csv else None),
            "pincode": None,
            "phone": phone,
            "location": {
                "type": "Point",
                "coordinates": [lon, lat],  # GeoJSON: [longitude, latitude]
            },
            "latitude": lat,
            "longitude": lon,
            "source": source,
            "source_file": k["source_file"],
            "source_record_id": f"{k['name']}@{lon},{lat}",
            "catalogue_url": None,
            "verification_status": verification_status,
            "imported_at": now_iso,
        }
        normalized_docs.append(doc)

    # Process unmatched CSV records
    for csv_idx, c in enumerate(csv_records):
        if csv_idx in csv_to_kml:
            continue

        sl = c["sl_no"]
        lib_id = _make_library_id("csv", f"sl_{sl}")
        doc = {
            "library_id": lib_id,
            "name": f"{c['category']} - {c['address'].split(',')[0]}",
            "category": c["category"],
            "branch": c["address"].split(",")[0].strip(),
            "address": c["address"],
            "area": c["area"],
            "pincode": None,
            "phone": c["phone"],
            "location": None,
            "latitude": None,
            "longitude": None,
            "source": "csv",
            "source_file": c["source_file"],
            "source_record_id": f"csv_sl_{sl}",
            "catalogue_url": None,
            "verification_status": "unverified_coordinates",
            "imported_at": now_iso,
        }
        normalized_docs.append(doc)

    stats["total_unique_libraries"] = len(normalized_docs)
    return normalized_docs, stats


def import_to_mongodb(
    docs: List[dict], dry_run: bool = False, mongo_uri: str = None, mongo_db: str = None
) -> dict:
    """Import normalized documents into MongoDB libraries collection."""
    uri = mongo_uri or os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    db_name = mongo_db or os.environ.get("MONGO_DB", "pustakamitra")

    if dry_run:
        return {
            "dry_run": True,
            "total_to_import": len(docs),
            "with_coordinates": sum(1 for d in docs if d["location"] is not None),
            "with_phone": sum(1 for d in docs if d.get("phone")),
            "target_database": db_name,
            "target_collection": "libraries",
        }

    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    db = client[db_name]
    coll = db["libraries"]

    coll.create_index([("library_id", 1)], unique=True, name="uq_library_id")
    coll.create_index([("name", "text"), ("area", "text"), ("address", "text")], name="tx_library_search")
    coll.create_index([("area", 1)], name="ix_area")
    coll.create_index([("location", "2dsphere")], name="geo_location")

    inserted = 0
    updated = 0

    for doc in docs:
        res = coll.replace_one(
            {"library_id": doc["library_id"]},
            doc,
            upsert=True,
        )
        if res.upserted_id is not None:
            inserted += 1
        else:
            updated += 1

    total_in_db = coll.count_documents({})
    return {
        "dry_run": False,
        "inserted": inserted,
        "updated": updated,
        "total_in_db": total_in_db,
        "target_database": db_name,
        "target_collection": "libraries",
    }


def run_importer(kml_path: Path, csv_path: Path, dry_run: bool = False) -> None:
    print(f"=== PustakaMitra AI Library Dataset Importer ===")
    print(f"KML Source: {kml_path}")
    print(f"CSV Source: {csv_path}")
    print(f"Mode: {'DRY RUN (no database changes)' if dry_run else 'LIVE IMPORT'}\n")

    kml_records = parse_kml_file(kml_path)
    csv_records = parse_csv_file(csv_path)

    docs, stats = match_and_normalize(kml_records, csv_records)

    print("--- Parsing & Normalization Summary ---")
    print(f"KML Placemarks Read:           {stats['kml_scanned']}")
    print(f"KML Duplicate Placemarks:      {stats['kml_duplicates_skipped']}")
    print(f"CSV Records Read:              {stats['csv_scanned']}")
    print(f"CSV Confident Matches to KML:  {stats['csv_confident_matches']}")
    print(f"CSV Standalone Records:        {stats['csv_unmatched']}")
    print(f"CSV Ambiguous Records Flagged: {stats['csv_ambiguous']}")
    print(f"Total Unique Library Records:  {stats['total_unique_libraries']}")
    coords_count = sum(1 for d in docs if d["location"] is not None)
    phones_count = sum(1 for d in docs if d.get("phone"))
    print(f"Records with Geo Coordinates:  {coords_count}")
    print(f"Records with Phone Numbers:    {phones_count}\n")

    db_res = import_to_mongodb(docs, dry_run=dry_run)

    if dry_run:
        print("--- Dry-Run Result ---")
        print(f"Simulation completed successfully.")
        print(f"Records prepared for upsert:   {db_res['total_to_import']}")
        print(f"Target Collection:             {db_res['target_database']}.{db_res['target_collection']}")
    else:
        print("--- MongoDB Import Result ---")
        print(f"Inserted:                      {db_res['inserted']}")
        print(f"Updated / Refreshed:           {db_res['updated']}")
        print(f"Total Library Records in DB:   {db_res['total_in_db']}")
        print(f"Database Collection:           {db_res['target_database']}.{db_res['target_collection']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import Bengaluru libraries into MongoDB")
    parser.add_argument("--dry-run", action="store_true", help="Simulate import without modifying MongoDB")
    parser.add_argument("--kml", type=Path, default=DEFAULT_KML, help="Path to KML file")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="Path to CSV file")
    args = parser.parse_args()

    run_importer(args.kml, args.csv, dry_run=args.dry_run)
