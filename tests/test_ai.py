# -*- coding: utf-8 -*-
"""AI pre-annotation: session memory, TF-IDF retrieval (RAG), few-shot prompt,
LLM response handling per provider, and the HF-pipeline chunking logic.
No network and no torch: HTTP and pipelines are faked."""
import json
from pathlib import Path
from unittest import mock

import pytest

import annie_legacy.ai.llm as llm_mod
from conftest import assert_golden, entity, open_session


def _ents(app, path):
    return app.annotations[path]["entities"]


@pytest.fixture
def memory_session(app, charter_texts):
    """P0306 + P1303 annotated, P2335 is the target file (index 2)."""
    anns = {}
    for path, items in ((charter_texts[0], [("Gmünd", "LOC"), ("Ulrich Froner", "PER")]),
                        (charter_texts[1], [("Papst", "TITLE"), ("Salzburg", "LOC")])):
        content = Path(path).read_text(encoding="utf-8")
        anns[path] = {"entities": [entity(app, path, content.find(t), content.find(t) + len(t), g)
                                   for t, g in items], "relations": []}
    open_session(app, charter_texts, anns)
    app.load_file(2)
    return charter_texts


class SyncThread:
    def __init__(self, target=None, daemon=None, **kw):
        self._target = target

    def start(self):
        self._target()


@pytest.fixture
def sync_llm(app, monkeypatch):
    monkeypatch.setattr(llm_mod.threading, "Thread", SyncThread)
    app.root.after = lambda ms, fn, *args: fn(*args)
    posted = []

    def install(reply_text, provider="Anthropic (Claude)"):
        app.llm_provider = provider
        app.llm_model = app.llm_models[provider]
        resp = mock.MagicMock()
        if provider == "Anthropic (Claude)":
            resp.json.return_value = {"content": [{"text": reply_text}]}
        else:
            resp.json.return_value = {"choices": [{"message": {"content": reply_text}}]}

        def post(url, headers=None, json=None, timeout=None):
            posted.append({"url": url, "headers": headers, "json": json})
            return resp
        monkeypatch.setattr(llm_mod.requests, "post", post)
        return posted
    return install


# session memory

def test_memory_predictions_use_other_files(app, memory_session):
    preds = app._get_memory_predictions(Path(memory_session[2]).read_text(encoding="utf-8"))
    assert sorted((p["text"], p["tag"]) for p in preds) == [("Gmünd", "LOC"), ("Papst", "TITLE")]
    assert all(p["source"] == "memory" for p in preds)


def test_memory_majority_vote_and_inactive_tags(app, tmp_path):
    files = []
    for i, tag in enumerate(["LOC", "LOC", "INS"]):
        f = tmp_path / f"{i}.txt"
        f.write_text("Gmünd", encoding="utf-8")
        files.append(str(f))
    target = tmp_path / "t.txt"
    target.write_text("in Gmünd", encoding="utf-8")
    anns = {p: {"entities": [entity(app, p, 0, 5, t)], "relations": []}
            for p, t in zip(files, ["LOC", "LOC", "INS"])}
    open_session(app, files + [str(target)], anns)
    app.load_file(3)
    assert [p["tag"] for p in app._get_memory_predictions("in Gmünd")] == ["LOC"]
    app.tag_active_states["LOC"] = False
    assert app._get_memory_predictions("in Gmünd") == []


# RAG retrieval & prompt

def test_tfidf_retrieval_ranks_similar_charters(app, memory_session):
    query = "Papst Benedikt beauftragt den Erzbischof von Salzburg"
    ranked = app._retrieve_similar_examples(query, top_k=2)
    assert ranked[0][0].startswith("ADG_Urk_P1303")
    assert len(ranked) == 2
    assert all(text != Path(memory_session[2]).read_text(encoding="utf-8") for text, _ in ranked)


def test_few_shot_prompt_golden(app, memory_session):
    prompt = app._build_few_shot_prompt(Path(memory_session[2]).read_text(encoding="utf-8"))
    assert prompt.startswith("You are an expert medieval archivist")
    assert prompt.count("### Example") == 2
    assert_golden("llm__few_shot_prompt", prompt.split("\n"))


def test_few_shot_count_zero_means_zero_shot(app, memory_session):
    app.llm_few_shot_count = 0
    assert "### Example" not in app._build_few_shot_prompt("x")


# LLM agent end-to-end (HTTP mocked)

@pytest.mark.parametrize("provider,url", [
    ("Anthropic (Claude)", "https://api.anthropic.com/v1/messages"),
    ("OpenAI", "https://api.openai.com/v1/chat/completions"),
    ("Together AI", "https://api.together.xyz/v1/chat/completions"),
    ("Hugging Face", "https://router.huggingface.co/v1/chat/completions"),
])
def test_llm_agent_providers(app, memory_session, sync_llm, provider, url):
    posted = sync_llm('[{"text": "Anselm Vieweger", "tag": "PER"}, {"text": "Weißbriach", "tag": "LOC"}]', provider)
    app._start_llm_agent()
    assert posted[0]["url"] == url
    assert posted[0]["json"]["temperature"] == 0.1
    got = sorted((e["text"], e["tag"], e.get("source", "llm")) for e in _ents(app, memory_session[2]))
    assert got == [("Anselm Vieweger", "PER", "llm"), ("Gmünd", "LOC", "memory"),
                   ("Papst", "TITLE", "memory"), ("Weißbriach", "LOC", "llm")]


def test_llm_reply_with_prose_and_truncated_json_is_repaired(app, memory_session, sync_llm):
    sync_llm('Sure! Here you go:\n[{"text": "Anselm Vieweger", "tag": "PER"}, {"text": "Dorothea von Weiß')
    app._start_llm_agent()
    assert ("Anselm Vieweger", "PER") in {(e["text"], e["tag"]) for e in _ents(app, memory_session[2])}


def test_llm_reply_without_json_reports_error(app, memory_session, sync_llm):
    sync_llm("I cannot help with that.")
    app._start_llm_agent()
    status = app.ai_status_queue.get_nowait()
    while not status.startswith("DONE|"):
        status = app.ai_status_queue.get_nowait()
    assert "did not generate a JSON list" in status
    assert {e.get("source") for e in _ents(app, memory_session[2])} == set()  # nothing applied


def test_quirk_llm_spans_are_matched_everywhere(app, memory_session, sync_llm):
    """The LLM returns only text+tag; ANNIE regex-matches each text (case-insensitive,
    \\b-bounded) and tags EVERY occurrence. Memory hits win over overlapping LLM hits."""
    sync_llm('[{"text": "gmünd", "tag": "INS"}, {"text": "Papst Nikolaus IV.", "tag": "PER"}]')
    app._start_llm_agent()
    got = {(e["text"], e["tag"]) for e in _ents(app, memory_session[2])}
    assert ("Gmünd", "LOC") in got and ("Gmünd", "INS") not in got
    # trailing '.' + \\b: 'IV.' is never matched by r'\\bPapst Nikolaus IV\\.\\b'
    assert not any(t == "PER" and "Nikolaus" in x for x, t in got)


# HF ensemble: chunking + label mapping (pipeline faked)

def test_ai_prediction_chunking_and_mapping(app, tmp_path):
    words = [f"w{i}" for i in range(400)]
    words[10] = "Gmünd"
    words[300] = "Salzburg"
    text = " ".join(words)
    calls = []

    def fake_pipeline(chunk):
        calls.append(chunk.split()[0])
        out = []
        for name, label, score in (("Gmünd", "B-LOC", 0.95), ("Salzburg", "I-LOC", 0.5)):
            i = chunk.find(name)
            if i >= 0:
                out.append({"entity_group": label, "start": i, "end": i + len(name), "score": score})
        return out

    app.extend_to_word.set(False)
    res = app._get_ai_predictions(text, [fake_pipeline], {"LOC": "LOC"}, 0.9, 1.0)
    assert calls == ["w0", "w110", "w220", "w330"]  # 150-word chunks, 40-word overlap
    assert [(r["text"], r["tag"], r["score"]) for r in res] == [("Gmünd", "LOC", 0.95)]  # Salzburg < min_conf


def test_ai_prediction_extend_to_word_and_ignore(app):
    text = "Liebfrauenkirche zu Gmünd"

    def fake_pipeline(chunk):
        return [{"entity": "B-ORG", "start": 2, "end": 8, "score": 0.99},
                {"entity": "B-MISC", "start": 20, "end": 25, "score": 0.99}]
    app.extend_to_word.set(True)
    res = app._get_ai_predictions(text, [fake_pipeline], {"ORG": "INS", "*": "-- Ignore --"}, 0.5, 1.0)
    assert [(r["text"], r["tag"]) for r in res] == [("Liebfrauenkirche", "INS")]


def test_ensemble_memory_has_priority_over_ai(app, tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("zu Gmünd", encoding="utf-8")
    open_session(app, [str(f)])
    mem = [entity(app, str(f), 3, 8, "LOC", source="memory")]
    ai = [entity(app, str(f), 3, 8, "INS"), entity(app, str(f), 0, 2, "DAT")]
    app._apply_ensemble_to_ui(mem, ai)
    assert sorted(e["tag"] for e in _ents(app, str(f))) == ["DAT", "LOC"]
