# PustakaMitra AI 📚📍

PustakaMitra AI is an intelligent reading companion designed for Kannada and English readers in Bengaluru. It bridges the gap between digital book discovery and physical library access by integrating real-world spatial data with AI-driven recommendations.

## ✨ Key Features

- **AI Book Recommendations**: Personalized suggestions based on user interests, reading level, and language preference (Kannada/English).
- **Bengaluru Library Finder**:
  - Integrated a dataset of **115+ public libraries** across Bengaluru.
  - **Spatial Search**: Find libraries "Near Me" using browser geolocation.
  - **Locality Filters**: Search by area (e.g., Jayanagar, Malleswaram, Koramangala) or PIN code.
  - **Verified Data**: Real-world coordinates and contact details merged from KML and CSV datasets.
- **Honest Architecture**: Clear labeling of verified locations vs. unverified book holdings, ensuring users have realistic expectations.
- **Direct Navigation**: Integrated "Get Directions" links via Google Maps for every library.

## 🛠️ Tech Stack

- **Backend**: FastAPI (Python)
- **Database**: MongoDB (with `2dsphere` indexing for spatial queries)
- **AI Engine**: Groq API (Qwen/Llama models) for intent parsing and ranking
- **Frontend**: Modern HTML5, CSS3, and Vanilla JavaScript (ES6 Modules)
- **Data Sources**: Bengaluru Public Library KML and CSV datasets

## 🚀 Getting Started

### Prerequisites

- **Python 3.10+**
- **MongoDB** (running locally on `mongodb://localhost:27017`)
- **Node.js** (optional, for frontend development)

For **detailed platform-specific instructions**, refer to the **[Full Installation Guide](FULL_INSTALLATION_GUIDE.md)**.

### Quick Installation Overview

#### 1. Clone the Repository

```
git clone https://github.com/programmeramul/PusathakaMitra.git
cd PusathakaMitra
```

#### 2. Set Up Environment

Create a `.env` file in the `backend` folder:

```
cd backend
cp .env.example .env
```

Edit the `.env` file and add your **Groq API key** and other required variables:

```
MONGO_URI=mongodb://localhost:27017
MONGO_DB=pustakamitra
GROQ_API_KEY=your_groq_api_key_here
SESSION_HASH_KEY=some_random_secret_string
```

#### 3. Install Dependencies

```
bash
pip install -r requirements.txt
```

#### 4. Import Library Data

Run the importer to populate the database with the Bengaluru library dataset:

```
bash
python3 backend/import_libraries.py
```

To test without modifying the database, use the dry-run mode:

```
bash
python3 backend/import_libraries.py --dry-run
```

#### 5. Run the Server

Start the FastAPI server:

```
bash
uvicorn backend.main:app --host 127.0.0.1 --port 8001 --reload
```

#### 6. Open the App

Open `index.html` in your browser or use a local live server:

```
bash
python3 -m http.server 8000
```

Then open [http://localhost:8000](http://localhost:8000) in your browser.


## 🗺️ Data Integration Details

The library discovery system is powered by a merged dataset:
- **Spatial Data**: KML files providing precise `longitude` and `latitude`.
- **Directory Data**: CSV files providing administrative categories and telephone contacts.
- **Join Logic**: A custom idempotent importer joins these sources using name-based heuristics and validates all coordinates within the Bengaluru city bounds.

## 📚 Full Installation Guide

For **detailed platform-specific instructions** (Windows, macOS, Linux), including troubleshooting and testing, refer to the **[Full Installation Guide](FULL_INSTALLATION_GUIDE_STYLED.md)**.

## 🧪 Running Tests

To ensure the backend is working correctly, run the automated tests:
```bash
cd backend
python3 -m pytest tests/ -v
```

Tests use a **throwaway MongoDB database** (`pustakamitra_test`) to avoid modifying your production data.

## 📜 License

Refer to the [LICENSE](LICENSE) file for more details.
