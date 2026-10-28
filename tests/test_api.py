"""annie_api: the router mounted under /api/v1 as ddp_api would include it, and the development app."""

import json
import sqlite3

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

import annie_api
from annie_core import llm

BODY = "Artolff von Lewbnegk übergibt der Liebfrauenkirche zu Gmünd ein Gut zu Gmünd."
FIRST, SECOND = BODY.find("Gmünd"), BODY.rfind("Gmünd")


@pytest.fixture
def client(monkeypatch):
    for variable in annie_api.KEY_VARIABLES.values():
        monkeypatch.delenv(variable, raising=False)
    app = FastAPI()
    v1 = APIRouter(prefix="/api/v1")
    v1.include_router(annie_api.router)
    app.include_router(v1)
    return TestClient(app)


def test_providers_report_which_keys_the_server_holds(client, monkeypatch):
    monkeypatch.setenv("DDP_ANNIE_OPENAI_KEY", "secret")
    body = client.get("/api/v1/annie/providers").json()
    assert {(p["id"], p["configured"]) for p in body["data"]} == {
        ("anthropic", False), ("openai", True), ("together", False), ("huggingface", False), ("dhinfra", False)}
    assert "secret" not in json.dumps(body)


def test_propagate_per_text(client):
    texts = [{"id": "a:abstract", "body": BODY, "entities": [{"start": FIRST, "end": FIRST + 5, "tag": "LOC", "text": "Gmünd"}]},
             {"id": "b:tenor", "body": "nichts"}]
    body = client.post("/api/v1/annie/propagate", json={"texts": texts, "terms": {"Gmünd": "LOC"}}).json()
    assert body == {"data": [{"text_id": "a:abstract", "entities": [{"start": SECOND, "end": SECOND + 5, "tag": "LOC", "text": "Gmünd"}]},
                             {"text_id": "b:tenor", "entities": []}]}


def test_suggest_without_key_is_unavailable(client):
    response = client.post("/api/v1/annie/suggest", json={"text": {"id": "a", "body": BODY}, "tags": ["LOC"]})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "unavailable" and "DDP_ANNIE_ANTHROPIC_KEY" in response.json()["error"]["message"]


def test_suggest_marks_the_source(client, monkeypatch):
    monkeypatch.setenv("DDP_ANNIE_ANTHROPIC_KEY", "k")
    requested = {}
    monkeypatch.setattr(llm, "complete", lambda provider, model, text, key: requested.update(model=model) or
                        '[{"text": "Artolff von Lewbnegk", "tag": "PER"}]')
    examples = [{"id": "x", "body": "zu Gmünd", "entities": [{"start": 3, "end": 8, "tag": "LOC", "text": "Gmünd"}]}]
    body = client.post("/api/v1/annie/suggest", json={"text": {"id": "a", "body": BODY}, "examples": examples, "tags": ["LOC", "PER"]}).json()
    assert [(s["text"], s["tag"], s["source"]) for s in body["data"]] == [
        ("Gmünd", "LOC", "memory"), ("Gmünd", "LOC", "memory"), ("Artolff von Lewbnegk", "PER", "llm")]
    assert requested["model"] == "claude-opus-5-5"


def test_provider_failure_is_unavailable(client, monkeypatch):
    monkeypatch.setenv("DDP_ANNIE_OPENAI_KEY", "k")

    def fail(provider, model, text, key):
        raise llm.ProviderError("openai answered 401: bad key")
    monkeypatch.setattr(llm, "complete", fail)
    response = client.post("/api/v1/annie/suggest", json={"text": {"id": "a", "body": BODY}, "tags": ["LOC"], "provider": "openai"})
    assert response.status_code == 503 and response.json()["error"]["message"] == "openai answered 401: bad key"


def test_unknown_provider_is_rejected(client):
    response = client.post("/api/v1/annie/suggest", json={"text": {"id": "a", "body": BODY}, "tags": ["LOC"], "provider": "gpt"})
    assert response.status_code == 422


def test_dev_app_serves_documents_of_a_browse_file(monkeypatch, tmp_path):
    browse = tmp_path / "browse.sqlite"
    with sqlite3.connect(browse) as connection:
        connection.execute("CREATE TABLE documents (id TEXT PRIMARY KEY, identifier TEXT)")
        connection.execute("CREATE TABLE document_records (id TEXT PRIMARY KEY, record TEXT NOT NULL)")
        for document_id, texts in (("a", [{"id": "a:abstract", "body": BODY}]), ("b", [])):
            connection.execute("INSERT INTO documents VALUES (?, ?)", (document_id, f"No. {document_id}"))
            connection.execute("INSERT INTO document_records VALUES (?, ?)", (document_id, json.dumps({"id": document_id, "texts": texts})))
    monkeypatch.setenv("DDP_BROWSE_FILE", str(browse))
    from annie_api.dev import app
    client = TestClient(app)
    assert client.get("/api/v1/documents").json() == [{"id": "a", "identifier": "No. a"}]
    assert client.get("/api/v1/documents/a").json()["texts"][0]["body"] == BODY
    assert client.get("/api/v1/documents/c").status_code == 404
    assert client.get("/api/v1/annie/providers").status_code == 200
