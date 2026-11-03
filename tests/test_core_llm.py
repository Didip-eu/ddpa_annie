"""annie_core.llm: retrieval and prompt as in the desktop app, reply parsing, and the provider calls with HTTP faked."""

import io
import json
import urllib.error
from pathlib import Path

import pytest

from annie_core import llm
from annie_core.propagation import Entity
from conftest import entity, open_session


@pytest.fixture
def session(app, charter_texts):
    """P0306 and P1303 annotated in the desktop app; P2335 is the text to annotate."""
    anns = {}
    for path, items in ((charter_texts[0], [("Gmünd", "LOC"), ("Ulrich Froner", "PER")]),
                        (charter_texts[1], [("Papst", "TITLE"), ("Salzburg", "LOC")])):
        content = Path(path).read_text(encoding="utf-8")
        anns[path] = {"entities": [entity(app, path, content.find(t), content.find(t) + len(t), g) for t, g in items], "relations": []}
    open_session(app, charter_texts, anns)
    app.load_file(2)
    examples = [(Path(path).read_text(encoding="utf-8"), [Entity(0, 0, e["tag"], e["text"]) for e in anns[path]["entities"]])
                for path in charter_texts[:2]]
    return Path(charter_texts[2]).read_text(encoding="utf-8"), examples


def test_similar_ranks_as_the_desktop_app(app, session):
    target, examples = session
    for query in (target, "Papst Benedikt beauftragt den Erzbischof von Salzburg", ""):
        legacy = [text for text, _ in app._retrieve_similar_examples(query, top_k=2)]
        assert [text for text, _ in llm.similar(query, examples, 2)] == legacy


def test_prompt_is_the_desktop_prompt(app, session):
    target, examples = session
    tags = app.get_active_tags()
    assert llm.prompt(target, tags, llm.similar(target, examples, 3)) == app._build_few_shot_prompt(target)


@pytest.mark.parametrize("reply,expected", [
    ('[{"text": "Gmünd", "tag": "LOC"}]', {"Gmünd": "LOC"}),
    ('Here you go:\n[{"text": " Anselm ", "tag": "PER"}, {"text": "", "tag": "X"}, "junk"]', {"Anselm": "PER"}),
    ('[{"text": "Anselm", "tag": "PER"}, {"text": "Dorothea von Wei', {"Anselm": "PER"}),
])
def test_terms_from_the_reply(reply, expected):
    assert llm.terms(reply) == expected


@pytest.mark.parametrize("reply", ["I cannot help with that.", "[{broken"])
def test_unreadable_reply_is_a_provider_error(reply):
    with pytest.raises(llm.ProviderError):
        llm.terms(reply)


def test_suggest_puts_memory_before_the_model(monkeypatch, session):
    target, examples = session
    sent = []
    monkeypatch.setattr(llm, "complete", lambda provider, model, text, key: sent.append(text) or
                        '[{"text": "gmünd", "tag": "INS"}, {"text": "Anselm Vieweger", "tag": "PER"}, {"text": "Rom", "tag": "UNKNOWN"}]')
    memory, proposed = llm.suggest(target, [], examples, ["LOC", "PER", "TITLE", "INS"], "dhinfra", "m", "k", 2, True)
    assert sorted((e.text, e.tag) for e in memory) == [("Gmünd", "LOC"), ("Papst", "TITLE")]
    assert [(e.text, e.tag) for e in proposed] == [("Anselm Vieweger", "PER")]
    assert sent[0].count("### Example") == 2


def test_chat_completion(monkeypatch):
    calls = []

    def urlopen(request, timeout):
        calls.append((request.full_url, request.headers, json.loads(request.data)))
        return io.BytesIO(json.dumps({"choices": [{"message": {"content": "[]"}}]}).encode())
    monkeypatch.setattr(llm.urllib.request, "urlopen", urlopen)
    assert llm.complete("dhinfra", "model-x", "hello", "secret") == "[]"
    url, headers, payload = calls[0]
    assert url == "https://api.dhinfra.uni-graz.at/v1/chat/completions" and headers["Authorization"] == "Bearer secret"
    assert payload == {"model": "model-x", "messages": [{"role": "user", "content": "hello"}], "max_tokens": llm.MAX_TOKENS,
                       "reasoning_effort": "none"}


def test_chat_completion_http_error(monkeypatch):
    def urlopen(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, io.BytesIO(b'{"error": "bad key"}'))
    monkeypatch.setattr(llm.urllib.request, "urlopen", urlopen)
    with pytest.raises(llm.ProviderError, match="dhinfra answered 401"):
        llm.complete("dhinfra", "m", "hello", "k")

