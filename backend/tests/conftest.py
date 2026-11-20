import os
import tempfile
from pathlib import Path
TEST_DATA=Path(tempfile.mkdtemp(prefix="etf-signal-test-"))
os.environ["DATA_DIR"]=str(TEST_DATA)
os.environ["DATABASE_URL"]="sqlite:///"+str(TEST_DATA/"test.db")
import pytest
from fastapi.testclient import TestClient
from app.db import Base,engine,SessionLocal
from app.main import app
from app.models import Setting
from app.security import encode_password

@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as client:
        with SessionLocal() as db:
            row=db.get(Setting,"password_hash")
            row.value=encode_password("test_password_1234")
            db.commit()
        yield client

@pytest.fixture
def logged_client(client):
    response=client.post("/api/v1/auth/login",json={"username":"admin","password":"test_password_1234"},headers={"X-Requested-With":"ETFSignalLab"})
    assert response.status_code==200
    return client
