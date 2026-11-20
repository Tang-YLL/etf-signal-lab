"""Run in the backend container: python -m app.reset_admin"""
import secrets
from .db import SessionLocal
from .models import Setting
from .security import encode_password

def main():
    password=secrets.token_urlsafe(15)
    with SessionLocal() as db:
        record=db.get(Setting,"password_hash")
        if not record: record=Setting(key="password_hash",value="");db.add(record)
        record.value=encode_password(password)
        db.commit()
    print("New admin password: "+password,flush=True)

if __name__=="__main__":main()
