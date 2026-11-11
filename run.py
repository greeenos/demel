import os
from pathlib import Path
import uvicorn

for line in Path(".env").read_text().splitlines():
    if line and not line.startswith("#"):
        key, value = line.split("=", 1)
        os.environ.setdefault(key, value)
uvicorn.run("backend.main:app", host="127.0.0.1", port=int(os.environ.get("PORT", "8198")), proxy_headers=False)
