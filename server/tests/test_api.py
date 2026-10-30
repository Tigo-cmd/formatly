import io

import docx

from conftest import signup
from samples import build_standard_project

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def upload(client, auth, data, rulebook="builtin:default", name="project.docx"):
    return client.post("/api/documents", headers=auth, data={"rulebook_ref": rulebook},
                       files={"file": (name, data, DOCX)})


# --- accounts ---------------------------------------------------------------

def test_register_login_and_me(client):
    auth = signup(client)
    me = client.get("/api/auth/me", headers=auth).json()
    assert me["email"] == "ada@example.com" and me["credits"] == 2
    r = client.post("/api/auth/login", json={"email": "ADA@example.com", "password": "correct horse"})
    assert r.status_code == 200
    assert client.post("/api/auth/login", json={"email": "ada@example.com", "password": "wrong"}).status_code == 401


def test_duplicate_email_and_weak_password(client):
    signup(client)
    r = client.post("/api/auth/register", json={"email": "ada@example.com", "password": "another one"})
    assert r.status_code == 409
    r = client.post("/api/auth/register", json={"email": "b@example.com", "password": "short"})
    assert r.status_code == 422


def test_signed_out_is_refused(client):
    assert client.get("/api/documents").status_code == 401
    assert client.get("/api/documents", headers={"Authorization": "Bearer nonsense"}).status_code == 401


# --- rulebooks --------------------------------------------------------------

def test_builtin_rulebooks_default_first(client):
    books = client.get("/api/rulebooks").json()
    assert books[0]["ref"] == "builtin:default"
    assert {"builtin:seminar", "builtin:postgraduate", "builtin:generic"} <= {b["ref"] for b in books}
    full = client.get("/api/rulebooks/builtin:seminar").json()
    assert full["rules"]["page"]["size"] == "Letter"


def test_custom_rulebook_extends_default(client, auth):
    r = client.post("/api/rulebooks", headers=auth, json={
        "name": "Dept X", "institution": "University X",
        "data": {"extends": "default", "body": {"line_spacing": 1.5}}})
    assert r.status_code == 201, r.text
    ref = r.json()["ref"]
    full = client.get(f"/api/rulebooks/{ref}", headers=auth).json()
    assert full["rules"]["body"]["line_spacing"]["value"] == 1.5
    assert full["rules"]["body"]["font"] == "Times New Roman"  # inherited


def test_invalid_rulebook_is_explained(client, auth):
    r = client.post("/api/rulebooks", headers=auth, json={"name": "x", "data": {"body": {"colour": "red"}}})
    assert r.status_code == 422
    assert "body.colour" in r.json()["detail"]


def test_extends_cannot_read_files_or_other_peoples_rulebooks(client, auth):
    r = client.post("/api/rulebooks", headers=auth, json={"name": "x", "data": {"extends": "/etc/passwd"}})
    assert r.status_code == 404
    other = signup(client, email="eve@example.com")
    r = client.post("/api/rulebooks", headers=other, json={"name": "secret", "data": {"extends": "default"}})
    secret = r.json()["ref"]
    r = client.post("/api/rulebooks", headers=auth, json={"name": "y", "data": {"extends": secret}})
    assert r.status_code == 404
    assert client.get(f"/api/rulebooks/{secret}", headers=auth).status_code == 404


def test_public_rulebooks_are_in_the_library(client, auth):
    client.post("/api/rulebooks", headers=auth, json={
        "name": "Computer Engineering Project 2026", "institution": "MOUAU", "visibility": "public",
        "data": {"extends": "default"}})
    client.post("/api/rulebooks", headers=auth, json={"name": "My private one", "data": {"extends": "default"}})
    found = client.get("/api/rulebooks/library", params={"q": "mouau computer"}).json()
    assert [b["name"] for b in found] == ["Computer Engineering Project 2026"]
    assert client.get("/api/rulebooks/library", params={"q": "private"}).json() == []


# --- documents --------------------------------------------------------------

def test_upload_checks_and_returns_comments(client, auth):
    r = upload(client, auth, build_standard_project(missing_scope=True))
    assert r.status_code == 201, r.text
    doc = r.json()
    v = doc["latest"]
    assert v["status"] == "done" and v["number"] == 1 and v["score"] < 100
    report = client.get(f"/api/versions/{v['id']}/report", headers=auth).json()["report"]
    assert any(i["rule"] == "structure.subsections" for i in report["issues"])
    assert all("excerpt" in i for i in report["issues"])
    commented = client.get(f"/api/versions/{v['id']}/download", headers=auth)
    assert commented.headers["content-type"] == DOCX
    comments = list(docx.Document(io.BytesIO(commented.content)).comments)
    assert any("1.5 Scope" in c.text for c in comments)


def test_wrong_files_are_refused_kindly(client, auth):
    r = upload(client, auth, b"%PDF-1.7 ...", name="project.pdf")
    assert r.status_code == 415 and "Word file" in r.json()["detail"]
    r = upload(client, auth, b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"0" * 100, name="project.doc")
    assert r.status_code == 415 and "Save As" in r.json()["detail"]
    r = upload(client, auth, b"hello", name="notes.docx")
    assert r.status_code == 415


def test_other_users_cannot_see_my_documents(client, auth):
    doc = upload(client, auth, build_standard_project()).json()
    eve = signup(client, email="eve@example.com")
    assert client.get(f"/api/documents/{doc['id']}", headers=eve).status_code == 404
    assert client.get(f"/api/versions/{doc['latest']['id']}/download", headers=eve).status_code == 404
    assert client.get("/api/documents", headers=eve).json() == []


def test_new_version_and_history(client, auth):
    doc = upload(client, auth, build_standard_project(missing_scope=True)).json()
    r = client.post(f"/api/documents/{doc['id']}/versions", headers=auth,
                    files={"file": ("project-v2.docx", build_standard_project(), DOCX)})
    assert r.status_code == 201
    versions = r.json()["versions"]
    assert [v["number"] for v in versions] == [1, 2]
    assert versions[1]["score"] == 100


def test_autofix_uses_a_credit_and_adds_a_version(client, auth):
    doc = upload(client, auth, build_standard_project(abstract_double=True, split_reference=True)).json()
    v1 = doc["latest"]
    assert v1["counts"]["fixable"] > 0
    r = client.post(f"/api/versions/{v1['id']}/fix", headers=auth)
    assert r.status_code == 201, r.text
    v2 = r.json()["latest"]
    assert v2["source"] == "autofix" and v2["number"] == 2 and v2["score"] == 100
    assert v2["fix_summary"]["from_version"] == 1
    assert client.get("/api/auth/me", headers=auth).json()["credits"] == 1
    fixed = client.get(f"/api/versions/{v2['id']}/download", headers=auth, params={"kind": "original"})
    assert fixed.status_code == 200
    history = client.get("/api/billing", headers=auth).json()["history"]
    assert [h["reason"] for h in history] == ["Auto-fix", "Welcome credits"]


def test_autofix_needs_credits(client, auth):
    for _ in range(2):
        doc = upload(client, auth, build_standard_project(abstract_double=True)).json()
        assert client.post(f"/api/versions/{doc['latest']['id']}/fix", headers=auth).status_code == 201
    doc = upload(client, auth, build_standard_project(abstract_double=True)).json()
    r = client.post(f"/api/versions/{doc['latest']['id']}/fix", headers=auth)
    assert r.status_code == 402
    assert client.get("/api/auth/me", headers=auth).json()["credits"] == 0


def test_autofix_refuses_when_nothing_is_fixable(client, auth):
    doc = upload(client, auth, build_standard_project()).json()
    assert client.post(f"/api/versions/{doc['latest']['id']}/fix", headers=auth).status_code == 409
    assert client.get("/api/auth/me", headers=auth).json()["credits"] == 2


def test_switching_rulebook_rechecks(client, auth):
    doc = upload(client, auth, build_standard_project(seminar=True)).json()
    assert doc["latest"]["score"] < 100  # a seminar against the project rulebook
    r = client.patch(f"/api/documents/{doc['id']}", headers=auth, json={"rulebook_ref": "builtin:seminar"})
    latest = r.json()["latest"]
    assert latest["rulebook_ref"] == "builtin:seminar" and latest["score"] == 100


def test_delete_removes_files(client, auth, settings):
    doc = upload(client, auth, build_standard_project()).json()
    files = list((settings.storage_dir).rglob("*.*"))
    assert files
    assert client.delete(f"/api/documents/{doc['id']}", headers=auth).status_code == 204
    assert list((settings.storage_dir).rglob("*.*")) == []
    assert client.get(f"/api/documents/{doc['id']}", headers=auth).status_code == 404


def test_server_delivers_the_website(tmp_path, settings):
    from fastapi.testclient import TestClient

    from formatly_server.main import create_app

    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<!doctype html><title>Formatly</title>")
    (web / "assets" / "app.js").write_text("console.log(1)")
    settings.web_dir = web
    c = TestClient(create_app(settings))
    assert "Formatly" in c.get("/").text
    assert "Formatly" in c.get("/documents/abc").text  # the app's own pages
    assert c.get("/assets/app.js").headers["cache-control"].startswith("public")
    assert c.get("/api/nope").status_code == 404
    assert c.get("/api/health").json() == {"ok": True}
    assert "Formatly" in c.get("/../../etc/passwd").text  # never a file outside the website
