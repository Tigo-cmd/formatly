import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "engine" / "tests"))  # sample builders

from formatly_server.config import Settings  # noqa: E402
from formatly_server.main import create_app  # noqa: E402


@pytest.fixture
def settings(tmp_path):
    return Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", storage_dir=tmp_path / "files",
                    secret_key="test-secret-0123456789abcdef0123456789", free_credits=2, fix_cost=1, admin_emails=["admin@formatly.test"])


@pytest.fixture
def client(settings):
    return TestClient(create_app(settings))


def signup(client, email="ada@example.com", password="correct horse", name="Ada"):
    r = client.post("/api/auth/register", json={"email": email, "password": password, "name": name})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
def auth(client):
    return signup(client)
