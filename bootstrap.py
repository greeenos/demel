"""Create private runtime configuration once without printing credentials."""
import hashlib
import os
import secrets
from pathlib import Path
from cryptography.fernet import Fernet

root = Path(__file__).resolve().parent
config = root / ".env"
if config.exists():
    raise SystemExit("Configuration already exists; it was preserved.")
password = secrets.token_urlsafe(18)
salt = secrets.token_hex(16)
digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600000).hex()
url = os.environ.get("VITAL_URL", "http://127.0.0.1:8198")
config.write_text(f"APP_URL={url}\nAPP_PASSWORD_HASH={salt}:{digest}\nENCRYPTION_KEY={Fernet.generate_key().decode()}\nDATA_DIR=data\n")
config.chmod(0o600)
access = root / "ACCESS.txt"
access.write_text(f"Demel\nURL: {url}\nPassword: {password}\n\nChange the password in settings after you log in. Keep this file private.\n")
access.chmod(0o600)
print("Private configuration created; access details are in ACCESS.txt.")
