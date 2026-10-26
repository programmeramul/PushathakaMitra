import csv
import hashlib
import logging
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from pymongo import MongoClient, errors

# Configuration
KML_FILE = "/home/amul/Desktop/PusathakaMitra/Data/40839757-9521-4766-b8c0-9309cd9da1b0.kml"
CSV_FILE = "/home/amul/Desktop/PusathakaMitra/Data/ddf6ea7d-eea3-44bb-972e-0e5fa911b55c.csv"
MONGO_URI = "mongodb://localhost:27017"
MONGO_DB = "pustakamitra"

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("importer")

def get_stable_id(name: str, lon: float, lat: float) -> str:
    """Create a stable unique ID based on name and coordinates to ensure idempotency."""
    seed = f"{name.strip().lower()}|{lon:.6f}|{lat:.6f}"
    return f"lib_{hashlib.sha256(seed.encode()).hexdigest()[:16]}"

def parse_kml(file_path: str) -> List[Dict]:
    """Parse KML and extract library placemarks with coordinates."""
    libraries = []
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()

        # KML namespaces can be tricky; find the actual namespace used in the file
        ns = {'kml': root.tag.split('}')[0].strip('{')} if '}' in root.tag else {}

        # Find all Placemarks
        # If namespace is present, use it; otherwise, search globally
        placemarks = root.findall(".//{http://www.opengis.net/kml/2.2}Placemark") if ns else root.findall(".//Placemark")
        if not placemarks:
            # Try again with a generic search if the specific namespace failed
            placemarks = root.findall(".//{*}Placemark")

        for pm in placemarks:
            name_node = pm.find("{http://www.opengis.net/kml/2.2}name") if ns else pm.find("name")
            name = name_node.text.strip() if name_node is not None and name_node.text else "Unknown Library"

            coord_node = pm.find(".//{http://www.opengis.net/kml/2.2}coordinates") if ns else pm.find(".//coordinates")
            if coord_node is not None and coord_node.text:
                coords_text = coord_node.text.strip()
                # KML format: longitude,latitude,altitude
                try:
                    parts = coords_text.split(',')
                    lon = float(parts[0])
                    lat = float(parts[1])

                    # Bengaluru bounds validation (Roughly 12.5-13.5 N, 77.2-78.0 E)
                    if not (12.0 <= lat <= 14.0 and 77.0 <= lon <= 79.0):
                        logger.warning(f"Skipping {name}: Coordinates ({lat}, {lon}) outside Bengaluru region.")
                        continue

                    libraries.append({
                        "name": name,
                        "longitude": lon,
                        "latitude": lat,
                        "location": {"type": "Point", "coordinates": [lon, lat]},
                        "source_file": Path(file_path).name,
                        "source": "KML"
                    })
                except (ValueError, IndexError) as e:
                    logger.error(f"Failed to parse coordinates for {name}: {e}")

        return libraries
    except Exception as e:
        logger.error(f"Error parsing KML file {file_path}: {e}")
        return []

def parse_csv(file_path: str) -> Dict[str, Dict]:
    """Parse CSV and return a mapping of library name -> details."""
    library_details = {}
    try:
        with open(file_path, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # CSV Fields: Sl. No, Category, Address
                # We try to extract a 'name' from the address or use a heuristic
                address = row.get("Address", "").strip()
                if not address:
                    continue

                # Many entries have the name at the start of the address (e.g., "State Central Library...")
                # We'll store the whole address and use it for joining later
                # To match KML, we need a way to key this.
                # Since CSV doesn't have a 'name' column, we'll use the full address as a potential match key
                # or extract the first part before a comma/dash.
                name_heuristic = address.split(',')[0].split('-')[0].strip()

                library_details[name_heuristic.lower()] = {
                    "address": address,
                    "category": row.get("Category", "Public Library"),
                    "phone": None,
                    "source_file": Path(file_path).name,
                    "source": "CSV"
                }

                # Extract phone number if present (e.g., 08022212128)
                import re
                phone_match = re.search(r"(\d{10})", address)
                if phone_match:
                    library_details[name_heuristic.lower()]["phone"] = phone_match.group(1)

        return library_details
    except Exception as e:
        logger.error(f"Error parsing CSV file {file_path}: {e}")
        return {}

def import_data(dry_run: bool = False):
    """Main import loop: KML -> CSV Join -> MongoDB."""
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    coll = db.libraries

    logger.info(f"Starting import. Dry-run: {dry_run}")

    kml_libs = parse_kml(KML_FILE)
    csv_details = parse_csv(CSV_FILE)

    logger.info(f"Found {len(kml_libs)} placemarks in KML.")
    logger.info(f"Found {len(csv_details)} records in CSV.")

    imported_count = 0
    updated_count = 0
    skipped_count = 0

    for lib in kml_libs:
        name = lib["name"]
        lon = lib["longitude"]
        lat = lib["latitude"]

        # Create stable ID
        lib_id = get_stable_id(name, lon, lat)

        # Try to join with CSV data
        # Match by name (lowercase)
        details = csv_details.get(name.lower(), {})

        # If no exact match, try partial match
        if not details:
            for csv_name, csv_val in csv_details.items():
                if csv_name in name.lower() or name.lower() in csv_name:
                    details = csv_val
                    break

        # Prepare final document
        doc = {
            "library_id": lib_id,
            "name": name,
            "longitude": lon,
            "latitude": lat,
            "location": lib["location"],
            "address": details.get("address", "Address not available"),
            "category": details.get("category", "Public Library"),
            "phone": details.get("phone"),
            "source": lib["source"],
            "source_file": lib["source_file"],
            "verification_status": "verified_location"
        }

        # Heuristic for 'area' from the address
        addr = doc["address"]
        # Common Bengaluru localities might be after a comma or in the address
        # For now, we'll try to extract it from the CSV address if possible
        # This is a simplification; in a real app, we might use a geocoding API.
        if "," in addr:
            doc["area"] = addr.split(",")[-2].strip() if len(addr.split(",")) > 1 else "Bengaluru"
        else:
            doc["area"] = "Bengaluru"

        if dry_run:
            logger.info(f"[Dry-Run] Would upsert: {name} ({lib_id}) - Area: {doc['area']}")
            imported_count += 1
            continue

        try:
            # Upsert based on library_id
            result = coll.update_one(
                {"library_id": lib_id},
                {"$set": doc},
                upsert=True
            )
            if result.upserted_id:
                imported_count += 1
            else:
                updated_count += 1
        except errors.PyMongoError as e:
            logger.error(f"MongoDB error for {name}: {e}")
            skipped_count += 1

    logger.info(f"Import complete. Inserted: {imported_count}, Updated: {updated_count}, Skipped: {skipped_count}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import Bengaluru Library data into PustakaMitra MongoDB.")
    parser.add_argument("--dry-run", action="store_true", help="Validate data without writing to MongoDB.")
    args = parser.parse_args()

    import_data(dry_run=args.dry_run)
