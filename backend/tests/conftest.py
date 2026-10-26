import os

# .env may hold a REAL GROQ_API_KEY on this machine — tests must never call the
# live API or spend quota, so blank it before anything imports backend.main.
# Individual tests opt into Groq paths with monkeypatch.setenv + mocked HTTP.
os.environ["GROQ_API_KEY"] = ""
