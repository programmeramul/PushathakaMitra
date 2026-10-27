# PustakaMitra AI — Full Installation Guide

Step-by-step setup instructions for the PustakaMitra AI application on Windows, macOS, and Linux. This guide covers the Python/FastAPI backend, MongoDB, the static HTML/CSS/JavaScript frontend, configuration, testing, and troubleshooting.

> **Before you begin:** Commands and configuration below are preserved from the supplied guide and have not been independently tested. Check them against the current repository before running them, especially database installation and data-import commands.

## Table of Contents

- [1. Clone the Repository](#1-clone-the-repository)
- [2. Install Prerequisites](#2-install-prerequisites)
  - [2.1 Python](#21-python-310)
  - [2.2 MongoDB](#22-mongodb-60)
  - [2.3 Node.js (Optional)](#23-nodejs-optional)
- [3. Platform-Specific Setup](#3-platform-specific-setup)
  - [3.1 Windows](#31-windows)
  - [3.2 macOS](#32-macos)
  - [3.3 Linux](#33-linux)
- [4. Backend Setup](#4-backend-setup)
  - [4.1 Configure Environment Variables](#41-configure-environment-variables)
  - [4.2 Install Python Dependencies](#42-install-python-dependencies)
  - [4.3 Import Library Data](#43-import-library-data)
  - [4.4 Start the Backend Server](#44-start-the-backend-server)
- [5. Frontend Setup](#5-frontend-setup)
  - [5.1 Open the Frontend](#51-open-the-frontend)
- [6. Testing the Application](#6-testing-the-application)
  - [6.1 Backend API](#61-backend-api)
  - [6.2 Frontend](#62-frontend)
  - [6.3 User Flow](#63-user-flow)
- [7. Troubleshooting](#7-troubleshooting)
- [8. Running Tests](#8-running-tests)
- [9. Summary of Commands](#9-summary-of-commands)
- [10. Final Notes](#10-final-notes)
- [11. Presentation Tips](#11-presentation-tips)

---

## Project Overview

**PustakaMitra AI** is an intelligent reading companion designed to connect digital book discovery with real-world library access. According to the supplied guide, its key areas include AI-based book recommendations, Bengaluru library discovery, and Kannada/English reader support.

---

## 1. Clone the Repository
Open a terminal (or Git Bash on Windows) and run:
```bash
git clone https://github.com/programmeramul/PusathakaMitra.git
cd PusathakaMitra
```

---

## 2. Install Prerequisites
### 2.1 Python (3.10+)
**Python is required for the backend (FastAPI).**

- **Windows**:
  - Download from [python.org](https://www.python.org/downloads/).
  - **Check "Add Python to PATH"** during installation.
  - Verify:
    ```bash
    python --version
    pip --version
    ```

- **macOS**:
  - Use **Homebrew**:
    ```bash
    brew install python
    ```
  - Verify:
    ```bash
    python3 --version
    pip3 --version
    ```

- **Linux (Ubuntu/Debian)**:
  - Install Python:
    ```bash
    sudo apt update
    sudo apt install python3 python3-pip python3-venv -y
    ```
  - Verify:
    ```bash
    python3 --version
    pip3 --version
    ```

---

### 2.2 MongoDB (6.0+)
**MongoDB is required for storing library and user data.**

- **Windows**:
  - Download **MongoDB Community Server** from [MongoDB's official site](https://www.mongodb.com/try/download/community).
  - Install and start MongoDB:
    ```bash
    mongod
    ```
  - To run MongoDB as a service:
    ```bash
    net start MongoDB
    ```

- **macOS**:
  - Use **Homebrew**:
    ```bash
    brew tap mongodb/brew
    brew install mongodb-community
    brew services start mongodb-community
    ```

- **Linux (Ubuntu/Debian)**:
  - Install MongoDB:
    ```bash
    sudo apt update
    sudo apt install mongodb -y
    ```
  - Start MongoDB:
    ```bash
    sudo systemctl start mongod
    sudo systemctl enable mongod  # Enable MongoDB to start on boot
    ```

**Verify MongoDB is running**:
```bash
mongo --eval "db.runCommand({ connectionStatus: 1 })"
```

---

### 2.3 Node.js (Optional)
If you plan to modify the frontend (JavaScript/CSS), install **Node.js** (version 14+):
- Download from [Node.js official site](https://nodejs.org/).
- Verify:
  ```bash
  node --version
  npm --version
  ```

---

## 3. Platform-Specific Setup
### 3.1 Windows
- Use **Git Bash**, **WSL (Windows Subsystem for Linux)**, or **Command Prompt**.
- Install **VS Code** (optional but recommended for editing code).
- If you encounter **port conflicts** (e.g., `8001` or `27017`):
  ```bash
  # Find the process using the port
  lsof -i :8001
  # Kill the process (replace <PID> with the actual process ID)
  taskkill /PID <PID> /F
  ```

### 3.2 macOS
- Use the **Terminal** for all commands.
- Install **VS Code** or **iTerm2** (optional).
- If you encounter **permission issues**, grant full disk access to Terminal:
  ```bash
  sudo chown -R $(whoami) /usr/local/mongodb
  ```

### 3.3 Linux
- Use the **Terminal** for all commands.
- Install **VS Code** or **Sublime Text** (optional).
- If MongoDB is not accessible, allow the port:
  ```bash
  sudo ufw allow 27017
  ```

---

## 4. Backend Setup
### 4.1 Configure Environment Variables
1. Navigate to the `backend` folder:
   ```bash
   cd PusathakaMitra/backend
   ```
2. Copy the example `.env` file:
   ```bash
   cp .env.example .env
   ```
3. Edit `.env` and add your **Groq API key** and other variables:
   ```env
   MONGO_URI=mongodb://localhost:27017
   MONGO_DB=pustakamitra
   GROQ_API_KEY=your_groq_api_key_here
   SESSION_HASH_KEY=some_random_secret_string
   ```
   - Replace `your_groq_api_key_here` with your actual **Groq API key** (sign up at [Groq](https://groq.com/)).
   - Generate a **random `SESSION_HASH_KEY`**:
     ```bash
     python3 -c "import secrets; print(secrets.token_urlsafe(32))"
     ```

### 4.2 Install Python Dependencies
Create and activate a **virtual environment** (recommended):
```bash
python3 -m venv .venv
```
- **Activate the virtual environment**:
  - **Windows (Git Bash/WSL)**:
    ```bash
    source .venv/bin/activate
    ```
  - **macOS/Linux**:
    ```bash
    source .venv/bin/activate
    ```
- Install dependencies:
  ```bash
  pip install -r ../requirements.txt
  ```

### 4.3 Import Library Data
Import the **Bengaluru library dataset** into MongoDB:
```bash
python3 import_libraries.py
```
- To **test without modifying the database**, use dry-run mode:
  ```bash
  python3 import_libraries.py --dry-run
  ```

### 4.4 Start the Backend Server
Start the **FastAPI server**:
```bash
python3 main.py
```
- For better performance (recommended for development):
  ```bash
  uvicorn main:app --host 127.0.0.1 --port 8001 --reload
  ```
  - The `--reload` flag enables **auto-reload** during development.

The backend should now be running at: [http://127.0.0.1:8001](http://127.0.0.1:8001).

---

## 5. Frontend Setup
The frontend is a **static HTML/JS/CSS** application. To run it:

### 5.1 Open the Frontend
- **Method 1: Directly Open in Browser**
  ```bash
  # Navigate to the project root
  cd /path/to/PusathakaMitra

  # Open index.html in your default browser
  start index.html  # Windows
  open index.html   # macOS
  xdg-open index.html # Linux
  ```

- **Method 2: Use a Local Server (Recommended for Development)**
  Install **Python’s built-in HTTP server**:
  ```bash
  python3 -m http.server 8000
  ```
  - Open [http://localhost:8000](http://localhost:8000) in your browser.

- **Method 3: Use Live Server (VS Code Extension)**
  - Install the **Live Server** extension in VS Code.
  - Right-click on `index.html` and select **"Open with Live Server"**.

---

## 6. Testing the Application
### 6.1 Backend API
Test the backend API at:
[http://127.0.0.1:8001/api/health](http://127.0.0.1:8001/api/health)
You should see:
```json
{"status":"ok"}
```

### 6.2 Frontend
- Navigate to the **Discover Books** page.
- Search for books or explore recommendations.
- Test the **Library Finder** to locate libraries in Bengaluru.

### 6.3 User Flow
1. Register a new user (or log in if you already have an account).
2. Complete the **onboarding process** to set your reading preferences.
3. View **AI-driven book recommendations** on your dashboard.

---

## 7. Troubleshooting
| Issue                          | Solution                                                                 |
|--------------------------------|--------------------------------------------------------------------------|
| **Backend Server Not Starting** | Ensure MongoDB is running and the `.env` file is correctly configured.   |
| **Port 8001 Already in Use**   | Kill the process using the port (`lsof -i :8001` → `kill -9 <PID>`).      |
| **MongoDB Connection Failed**  | Verify MongoDB is running (`sudo systemctl start mongod` on Linux).      |
| **Groq API Key Missing**       | Set `GROQ_API_KEY` in `.env` file.                                        |
| **Python Version Issues**      | Use a virtual environment: `python3 -m venv .venv` and activate it.       |
| **Frontend Not Loading**       | Open `index.html` using a local server (e.g., `python3 -m http.server`). |
| **KML/CSV Parsing Errors**     | Run in dry-run mode: `python3 backend/import_libraries.py --dry-run`.   |

### Debugging Tips
- **Check MongoDB Logs** (Linux/macOS):
  ```bash
  journalctl -u mongod -f
  ```
- **Test Backend API Manually**:
  ```bash
  curl http://127.0.0.1:8001/api/health
  ```
- **Verify Environment Variables**:
  ```bash
  python3 -c "import os; print(os.environ.get('MONGO_URI'))"
  ```

---

## 8. Running Tests
To ensure the backend is working correctly, run the automated tests:
```bash
cd backend
python3 -m pytest tests/ -v
```
- Tests use a **throwaway MongoDB database** (`pustakamitra_test`) to avoid modifying your production data.

---

## 9. Summary of Commands
| Task                          | Command                                                                 |
|-------------------------------|--------------------------------------------------------------------------|
| Clone Repository              | `git clone https://github.com/programmeramul/PusathakaMitra.git`          |
| Install Python                 | `sudo apt install python3` (Linux) or `brew install python` (macOS)       |
| Install MongoDB                | `brew install mongodb-community` (macOS) or `sudo apt install mongodb` (Linux) |
| Start MongoDB                  | `mongod` (Windows) or `sudo systemctl start mongod` (Linux)             |
| Create Virtual Environment     | `python3 -m venv .venv`                                                 |
| Activate Virtual Environment   | `source .venv/bin/activate` (Linux/macOS) or `.\\.venv\\Scripts\\activate` (Windows) |
| Install Dependencies            | `pip install -r requirements.txt`                                        |
| Import Library Data            | `python3 backend/import_libraries.py`                                    |
| Start Backend Server           | `uvicorn backend.main:app --host 127.0.0.1 --port 8001 --reload`       |
| Open Frontend                  | `python3 -m http.server 8000` (then open [http://localhost:8000](http://localhost:8000)) |
| Run Tests                      | `python3 -m pytest backend/tests/ -v`                                    |

---

## 10. Final Notes
- **For Production**:
  - Use **Uvicorn with Gunicorn** for better performance:
    ```bash
    pip install gunicorn
    gunicorn -w 4 -k uvicorn.workers.UvicornWorker backend.main:app
    ```
  - Set `SECURE_COOKIES=1` in `.env` if using HTTPS.

- **For Development**:
  - Use `--reload` in Uvicorn for auto-reloading.
  - Use **VS Code Live Server** for frontend development.

- **Security**:
  - Never commit `.env` files to version control.
  - Use `.gitignore` to exclude sensitive files.

---

## 11. Presentation Tips
When presenting **PustakaMitra AI**, highlight:
1. **Problem Solved**: Bridging digital book discovery with real-world library access.
2. **Key Features**: AI recommendations, spatial search, and honest data labeling.
3. **Tech Stack**: FastAPI, MongoDB, Groq AI, and vanilla JavaScript.
4. **Cross-Platform Support**: Works seamlessly on **Windows, macOS, and Linux**.
5. **User Flow**: From registration to book recommendations and library discovery.

Use this guide to **demonstrate the installation process** live during your presentation!
