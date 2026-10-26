"""Safe backend-only diagnostic utility for Groq credentials and model availability.

This script never reveals, logs, or hashes the Groq API key.
Run locally via:
    python3 backend/diagnostic.py
"""
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path
from dotenv import load_dotenv

GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_UA = "pustakamitra-backend/0.3"


def run_diagnostic():
    print("=" * 60)
    print("PustakaMitra AI — Safe Groq Diagnostics")
    print("=" * 60)

    # 1. Trace configuration file
    env_backend = Path(__file__).resolve().parent / ".env"
    env_root = Path(__file__).resolve().parent.parent / ".env"

    if env_backend.is_file():
        config_path = env_backend
        print(f"[✓] Configuration source found: backend/.env")
    elif env_root.is_file():
        config_path = env_root
        print(f"[✓] Configuration source found: .env (project root)")
    else:
        config_path = None
        print(f"[!] Warning: No .env file found at backend/.env or project root")

    if config_path:
        # override=True ensures newly edited file values supersede stale shell variables
        load_dotenv(config_path, override=True)

    # 2. Key presence and whitespace check (NEVER printing the key)
    raw_key = os.environ.get("GROQ_API_KEY")
    if raw_key is None:
        print("[✗] GROQ_API_KEY is not set in environment or configuration file.")
        return False
    elif not raw_key.strip():
        print("[✗] GROQ_API_KEY is present but empty.")
        return False
    else:
        print("[✓] GROQ_API_KEY is present and non-empty.")

    has_leading = len(raw_key) > len(raw_key.lstrip())
    has_trailing = len(raw_key) > len(raw_key.rstrip())
    if has_leading or has_trailing:
        print(f"[!] Warning: GROQ_API_KEY contains accidental whitespace "
              f"(leading={has_leading}, trailing={has_trailing}). It will be trimmed automatically.")
    else:
        print("[✓] No leading or trailing whitespace detected around GROQ_API_KEY.")

    clean_key = raw_key.strip()

    # 3. Model check
    model = (os.environ.get("GROQ_MODEL") or "llama-3.3-70b-versatile").strip()
    print(f"[*] Configured GROQ_MODEL: {model}")

    # 4. Groq authentication & model list check
    req = urllib.request.Request(
        GROQ_MODELS_URL,
        headers={
            "Authorization": f"Bearer {clean_key}",
            "User-Agent": GROQ_UA,
        }
    )

    auth_success = False
    available_models = []
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.load(resp)
            auth_success = True
            available_models = [m.get("id") for m in data.get("data", []) if m.get("id")]
            print(f"[✓] Groq authentication: SUCCESS (HTTP 200 OK)")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            print(f"[✗] Groq authentication FAILED: HTTP {e.code} (invalid_credentials).")
            print("    Please verify your key in Groq Console (https://console.groq.com/keys).")
        else:
            print(f"[✗] Groq models check failed: HTTP {e.code} ({e.reason}).")
        return False
    except urllib.error.URLError as e:
        print(f"[✗] Network error reaching Groq: {e.reason}")
        return False
    except Exception as e:
        print(f"[✗] Unexpected error reaching Groq: {type(e).__name__}")
        return False

    # 5. Model availability check
    if model in available_models:
        print(f"[✓] Configured model '{model}' is ACTIVE and available on this key.")
    else:
        print(f"[✗] Configured model '{model}' was NOT found in the available models list.")
        relevant = [m for m in available_models if any(k in m.lower() for k in ["llama", "qwen", "mixtral", "gemma"])]
        print(f"    Available chat models: {relevant}")
        return False

    # 6. Minimal chat-completion check
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "user", "content": "Respond with JSON: {\"status\": \"ok\"}"}
        ],
        "temperature": 0.2,
        "max_tokens": 50,
        "response_format": {"type": "json_object"},
    }).encode()

    chat_req = urllib.request.Request(
        GROQ_CHAT_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {clean_key}",
            "Content-Type": "application/json",
            "User-Agent": GROQ_UA,
        }
    )

    try:
        with urllib.request.urlopen(chat_req, timeout=12) as resp:
            chat_data = json.load(resp)
            choices = chat_data.get("choices", [])
            if choices and choices[0].get("message", {}).get("content"):
                print("[✓] Live chat-completion test: SUCCESS.")
            else:
                print("[!] Live chat test returned unexpected structure.")
    except urllib.error.HTTPError as e:
        print(f"[✗] Live chat test failed: HTTP {e.code} ({e.reason})")
        return False
    except Exception as e:
        print(f"[✗] Live chat test failed: {type(e).__name__}")
        return False

    print("=" * 60)
    print("All diagnostic checks PASSED successfully.")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = run_diagnostic()
    sys.exit(0 if success else 1)
