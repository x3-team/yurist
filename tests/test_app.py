"""API сервиса с подменённым ИИ."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from yurist import parser, render, templater
from yurist.models import AnnexInput, Task

from test_pipeline import MARKUP, doc_text  # noqa: F401
from make_sample_annex import build


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(templater, "ask_markup", lambda text: MARKUP)
    monkeypatch.setattr(parser, "parse_text", lambda text, c: AnnexInput(
        start_date=date(2026, 11, 5), end_date=date(2026, 12, 25),
        tasks=[Task(name="Доработка отчётов", cost=95000)]))
    from yurist.app import app
    return TestClient(app)


def test_flow(client, tmp_path):
    sample = build(tmp_path / "s.docx").read_bytes()
    r = client.post("/api/clients", data={"title": "РАТЕП"},
                    files={"file": ("Приложение 7.docx", sample)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["client"]["id"] == "ratep"
    assert body["client"]["next_annex_number"] == "8"

    assert [c["title"] for c in client.get("/api/clients").json()] == ["РАТЕП"]

    annex = client.post("/api/clients/ratep/parse", json={"text": "отчёты 95к"}).json()
    assert annex["tasks"][0]["cost"] == 95000

    r = client.post("/api/clients/ratep/generate", json=annex)
    assert r.status_code == 200
    assert "Приложение № 8" in doc_text(r.content)
    assert client.get("/api/clients").json()[0]["next_annex_number"] == "9"

    r = client.patch("/api/clients/ratep", json={"vat_mode": "included", "vat_rate": 20})
    assert r.json()["vat_mode"] == "included"
    assert client.get("/api/clients/ratep/template").status_code == 200


def test_rejects_non_docx(client):
    r = client.post("/api/clients", files={"file": ("a.pdf", b"x")})
    assert r.status_code == 400
