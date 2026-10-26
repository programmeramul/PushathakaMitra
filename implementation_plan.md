# Implementation Plan — Integrate Bengaluru Public Libraries & KML Dataset

Integrate actual local Bengaluru library datasets (`Data/40839757-9521-4766-b8c0-9309cd9da1b0.kml` and `Data/ddf6ea7d-eea3-44bb-972e-0e5fa911b55c.csv`) into the PustakaMitra AI platform.

## Inspection & Discovery Findings (Step 1)

1. **Discovered Files**:
   - `Data/40839757-9521-4766-b8c0-9309cd9da1b0.kml` (KML dataset of Bengaluru libraries)
   - `Data/ddf6ea7d-eea3-44bb-972e-0e5fa911b55c.csv` (Karnataka Public Library directory dataset)

2. **KML Contents & Analysis**:
   - **Placemark Count**: 115 placemarks across 3 Folders:
     - Government Libraries: 80 placemarks
     - Privately Run: 19 placemarks
     - Miscellaneous: 16 placemarks
   - **Available Fields**: `<name>`, `<Point><coordinates>` (format: `longitude,latitude,altitude`).
   - **Fields Absent in KML**: `<description>` (empty), `<ExtendedData>` (none), contact details, PIN codes, catalogue URLs.
   - **Duplicates**: Exactly one duplicate placemark with identical coordinates (`77.570328,12.97145,0`) and name ("City Central Library, Cottonpet"). Several branches share the generic name "City Central Library" or "Public Library" but have distinct coordinates and localities.
   - **Coordinate Range**: All coordinates are valid Bengaluru geographical coordinates (`longitude ~ 77.44 to 77.75`, `latitude ~ 12.81 to 13.14`).

3. **CSV Contents & Analysis**:
   - **Total Records**: 50 records.
   - **Available Fields**: `Sl. No`, `Category`, `Address`.
   - **Contact Details**: 5 entries contain telephone numbers in the address field (e.g., State Central Library Cubbon Park: `08022212128`, Vijaynagar District Central: `08023159289`, and 3 Gram Panchayati libraries).
   - **Localities**: South Zone (Jayanagar), Central Zone (Double Road), North Zone (Malleswaram), East Zone (R.T. Nagar), West Zone (Hampinagar), Vijaynagar, etc.
   - **Catalogue Information**: No book holdings or catalogue URLs are present in the CSV or KML.

4. **Matching & Provenance**:
   - High-confidence cross-referencing between KML placemarks and CSV records exists for major central libraries (e.g., Sheshadri Iyer Memorial Hall in Cubbon Park, City Central Library South Zone, North Zone, West Zone, and Vijayanagar Central Library).
   - The importer will conservatively join matching records, preserve provenance (`source_file`, `source_record_id`), and flag any ambiguous matches without silently mangling data.

---

## User Review Required

> [!IMPORTANT]
> - **Book Holdings & Availability**: Neither the KML nor the CSV dataset contains shelf availability or catalog holdings for individual books. As required by the honest architecture of PustakaMitra AI, the UI and API will clearly state that book holdings are unverified, while offering verified library coordinates, directions, and official catalogue portals (e-Granthalaya, Karnataka Public Library Directory, WorldCat).
> - **MongoDB Port & Access**: In the local sandboxed environment, MongoDB runs on the host system at `mongodb://localhost:27017` (`pustakamitra` database with 778 existing book records). Test executions and imports will run against host MongoDB.

---

## Proposed Changes

### Backend Component

#### [NEW] [import_libraries.py](file:///home/amul/Desktop/PusathakaMitra/backend/import_libraries.py)
Create a robust, idempotent KML/CSV parsing and importing CLI tool:
- Parse KML namespace `http://www.opengis.net/kml/2.2` safely using standard XML parsing.
- Extract Point coordinates formatted strictly as GeoJSON `[longitude, latitude]`.
- Validate coordinates (Bengaluru bounds: lat 12.5-13.5, lon 77.2-78.0).
- Extract locality heuristics and branch names from placemark names.
- Join CSV records where unambiguous matches exist (e.g., State Central Library Cubbon Park telephone and address).
- Implement `--dry-run` flag: outputs exact counts of placemarks scanned, valid libraries, skipped/rejected duplicates, and records ready to insert/update, without modifying MongoDB.
- Upsert using stable unique ID (`lib_<hash>`) ensuring idempotency.
- Ensure 2dsphere index on `location`.

#### [MODIFY] [backend/main.py](file:///home/amul/Desktop/PusathakaMitra/backend/main.py)
Extend FastAPI application:
- Add `libraries` collection handle and ensure indexes (`2dsphere` on `location`, unique on `library_id`, index on `name`, `area`, `pincode`).
- Implement `GET /api/libraries`:
  - Query parameters: `q` (name/text search), `area` (locality filter), `pincode` (PIN filter), `page` (int >= 1), `page_size` (int, 1-100).
  - Sanitized case-insensitive regex searches.
- Implement `GET /api/libraries/nearby`:
  - Query parameters: `lat` (float), `lon` (float), `radius_km` (float, 0.1 to 50.0), `page`, `page_size`.
  - MongoDB `$geoNear` aggregation pipeline returning actual distance in kilometres.
- Implement `GET /api/libraries/{library_id}`:
  - Returns detailed record for a specific library or 404.
- Update `/api/chat`:
  - When `s["mode"] == "library"` or library intent detected:
    - Extract requested locality / PIN or coordinates.
    - Query real `libraries` collection deterministically in MongoDB.
    - Return matching real library records (`libraries: [...]`) with name, address, area, coordinates, directions link, and honest unverified holdings disclaimer.
    - Works even if Groq API key is not configured.
- Update `/api/chat/status`:
  - Report `"library_dataset_imported": True` when `libraries.count_documents({}) > 0`.

---

### Frontend Component

#### [MODIFY] [js/services/api.js](file:///home/amul/Desktop/PusathakaMitra/js/services/api.js)
- Extend `libraryService`:
  - `search({ q, area, pincode, page, page_size })`
  - `nearby({ lat, lon, radius_km, page, page_size })`
  - `getLibrary(library_id)`

#### [MODIFY] [pages/libraries.html](file:///home/amul/Desktop/PusathakaMitra/pages/libraries.html) & [js/pages/libraries.js](file:///home/amul/Desktop/PusathakaMitra/js/pages/libraries.js)
- Connect real library endpoints:
  - Search input (library name / keyword).
  - Locality filter and PIN code filter.
  - "Near Me" button with browser Geolocation API (`navigator.geolocation.getCurrentPosition`), prompting user permission.
  - Grid of library cards showing:
    - Library name and category badge (Government, Private, etc.).
    - Address and locality.
    - Distance (km) when nearby search is active.
    - Contact phone if available from CSV join.
    - "Get Directions" link (`https://www.google.com/maps/dir/?api=1&destination=lat,lon`).
    - Honest badge: "Holdings unverified".
  - Pagination bar.
  - Loading spinner, empty state, and error handling.
  - Responsive design matching PustakaMitra cream & forest-green palette.

#### [MODIFY] [js/chatbot.js](file:///home/amul/Desktop/PusathakaMitra/js/chatbot.js)
- Update chatbot UI rendering:
  - Support structured library cards returned by `/api/chat` with directions link, address, locality, and distance.
  - Support manual locality / PIN input or "Use my location" button.

---

### Tests Component

#### [NEW] [backend/tests/test_libraries.py](file:///home/amul/Desktop/PusathakaMitra/backend/tests/test_libraries.py)
Add comprehensive automated test suite covering:
- KML parsing and namespace handling.
- Coordinate extraction and validation (GeoJSON `[lon, lat]` ordering).
- Coordinate range validation & invalid coordinate rejection.
- Duplicate record handling and idempotency.
- Importer dry-run vs live import.
- MongoDB 2dsphere index and `$geoNear` spatial queries.
- Locality, PIN-code, and text search queries.
- Pagination controls.
- Chatbot library intent parsing and deterministic database fallback without Groq.
- Safe rendering (no scripts/XSS in descriptions or URLs).
- Preserving existing book and authentication features.

---

## Verification Plan

### Automated Tests
- Run existing suite to ensure no regressions:
  ```bash
  python3 -m pytest backend/tests/test_auth.py backend/tests/test_catalog.py backend/tests/test_chat.py -v
  ```
- Run new library test suite:
  ```bash
  python3 -m pytest backend/tests/test_libraries.py -v
  ```
- Run full combined test suite:
  ```bash
  python3 -m pytest backend/tests -v
  ```

### Importer Verification
- Test importer in dry-run mode:
  ```bash
  python3 backend/import_libraries.py --dry-run
  ```
- Run live import into MongoDB:
  ```bash
  python3 backend/import_libraries.py
  ```
- Verify idempotency by running again:
  ```bash
  python3 backend/import_libraries.py
  ```
- Verify document count and 2dsphere index in MongoDB `libraries` collection.

### Manual / Browser Verification
- Start backend server on `127.0.0.1:8001`.
- Verify `GET /api/libraries`, `GET /api/libraries/nearby`, `GET /api/libraries/{id}` using curl / http client.
- Test frontend `pages/libraries.html` search, filtering, and "Near Me" geolocation.
- Test chatbot library queries in chat panel ("Find public libraries in Bengaluru", "Show libraries near Indiranagar", "Find libraries near PIN code 560011").
