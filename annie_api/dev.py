"""A stand-in for ddp_api during development: the ANNIE routes and the documents of a browse file, under /api/v1.

    DDP_BROWSE_FILE=../ddp_etl/fsdb-builds/sample-store/browse.sqlite uv run uvicorn annie_api.dev:app
"""

import json
import os
import sqlite3

from fastapi import APIRouter, FastAPI, HTTPException

from annie_api import router

app = FastAPI(title="ANNIE development API")
v1 = APIRouter(prefix="/api/v1")
v1.include_router(router)


def browse() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{os.environ['DDP_BROWSE_FILE']}?mode=ro", uri=True)


@v1.get("/documents")
def documents(limit: int = 50) -> list[dict]:
    """The first documents of the browse file that have a text, with their identifier."""
    with browse() as connection:
        rows = connection.execute("SELECT documents.id, identifier FROM documents JOIN document_records USING (id)"
                                  " WHERE json_array_length(record, '$.texts') > 0 ORDER BY documents.id LIMIT ?",
                                  (limit,)).fetchall()
    return [{"id": document_id, "identifier": identifier} for document_id, identifier in rows]


@v1.get("/documents/{document_id}")
def document(document_id: str) -> dict:
    """One document record as ddp_api serves it."""
    with browse() as connection:
        row = connection.execute("SELECT record FROM document_records WHERE id = ?", (document_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"No record with id {document_id}.")
    return json.loads(row[0])


app.include_router(v1)
