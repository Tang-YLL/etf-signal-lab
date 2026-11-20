import secrets
import hashlib
from fastapi import HTTPException, Request
from sqlalchemy.orm import Session
from .models import Setting

def encode_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260000)
    return salt.hex()+":"+digest.hex()

def verify_password(password: str, stored: str) -> bool:
    try:
        a,b=stored.split(":",1)
        digest=hashlib.pbkdf2_hmac("sha256",password.encode(),bytes.fromhex(a),260000)
        return secrets.compare_digest(digest,bytes.fromhex(b))
    except (ValueError, TypeError):
        return False

def init_admin(db: Session):
    if db.get(Setting, "password_hash") is None:
        password = secrets.token_urlsafe(15)
        db.add(Setting(key="password_hash",value=encode_password(password)))
        db.commit()
        print("FIRST RUN ADMIN LOGIN: username=admin password="+password,flush=True)
        print("Change this password after login. Only readable from local backend logs.",flush=True)

def ensure_login(request: Request):
    if request.session.get("user") != "admin":
        raise HTTPException(401,"Login required")
    # JSON-only mutations + required custom header prevent simple cross-origin form CSRF.
    if request.method not in ("GET","HEAD","OPTIONS"):
        if request.headers.get("X-Requested-With") != "ETFSignalLab":
            raise HTTPException(403,"Missing CSRF header")
    return True
