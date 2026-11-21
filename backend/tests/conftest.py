import os
import tempfile
from pathlib import Path
TEST_DATA=Path(tempfile.mkdtemp(prefix="etf-signal-test-"))
os.environ["DATA_DIR"]=str(TEST_DATA)
os.environ["DATABASE_URL"]="sqlite:///"+str(TEST_DATA/"test.db")
import pytest
from fastapi.testclient import TestClient
from app.db import Base,engine
from app.main import app

@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as client:
        yield client
