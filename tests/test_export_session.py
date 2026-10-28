# -*- coding: utf-8 -*-
"""Training-data export (spaCy JSONL / CoNLL), re-import of those formats,
and the session JSON file format."""
import json
from pathlib import Path

import pytest

from conftest import assert_golden, entity, open_session, relativize, strip_ids


@pytest.fixture
def annotated(app, charter_texts):
    """The three charters with a handful of hand-made annotations + one relation."""
    anns = {}
    picks = {
        0: [("Artolff von Lewbnegk", "PER"), ("Liebfrauenkirche zu Gmünd", "INS"), ("Gmünd", "LOC"),
            ("1448 Juli 16", "DAT")],
        1: [("Papst Benedikt XIV.", "PER"), ("Erzbischof von Salzburg", "TITLE"), ("Salzburg", "LOC")],
        2: [("Anselm Vieweger", "PER"), ("(1442 Dezember 30)", "DAT")],
    }
    for i, items in picks.items():
        path = charter_texts[i]
        content = Path(path).read_text(encoding="utf-8")
        ents = []
        for text, tag in items:
            s = content.find(text)
            assert s >= 0, text
            ents.append(entity(app, path, s, s + len(text), tag))
        anns[path] = {"entities": ents, "relations": []}
    p0 = charter_texts[0]
    e = anns[p0]["entities"]
    anns[p0]["relations"] = [{"id": "r1", "type": "located_in", "head_id": e[1]["id"], "tail_id": e[2]["id"]}]
    open_session(app, charter_texts, anns)
    return charter_texts


def test_spacy_jsonl_export_golden(app, annotated, tmp_path):
    out = tmp_path / "train.jsonl"
    app._export_as_spacy_jsonl(str(out))
    rows = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 3
    for row in rows:
        for span in row["spans"]:
            assert row["text"][span["start"]:span["end"]].strip()
    assert_golden("export__spacy_jsonl", rows)


def test_conll_export_golden(app, annotated, tmp_path):
    out = tmp_path / "train.conll"
    app._export_as_conll(str(out))
    text = out.read_text(encoding="utf-8")
    assert "Artolff B-PER\nvon I-PER\nLewbnegk I-PER\n" in text
    assert_golden("export__conll", text.split("\n"))


def test_quirk_conll_nested_spans_last_writer_wins(app, annotated, tmp_path):
    """Overlapping spans are written sequentially: the LOC 'Gmünd' inside the
    INS 'Liebfrauenkirche zu Gmünd' overwrites I-INS with B-LOC."""
    out = tmp_path / "train.conll"
    app._export_as_conll(str(out))
    lines = out.read_text(encoding="utf-8").splitlines()
    i = lines.index("Liebfrauenkirche B-INS")
    assert lines[i + 1:i + 3] == ["zu I-INS", "Gmünd B-LOC"]


def test_quirk_relations_are_not_exported(app, annotated, tmp_path):
    out = tmp_path / "train.jsonl"
    app._export_as_spacy_jsonl(str(out))
    assert "located_in" not in out.read_text(encoding="utf-8")


def test_export_annotations_dispatches_on_extension(app, dialogs, annotated, tmp_path):
    dialogs.script(asksaveasfilename=[str(tmp_path / "a.conll"), str(tmp_path / "b.txt")])
    app.export_annotations()
    app.export_annotations()
    assert (tmp_path / "a.conll").exists() and not (tmp_path / "b.txt").exists()
    assert dialogs.titles("showwarning") == ["Unknown Format"]


def test_spacy_jsonl_roundtrip(app, annotated, tmp_path):
    out = tmp_path / "train.jsonl"
    app._export_as_spacy_jsonl(str(out))
    docs, tags = app._parse_jsonl_into_documents(str(out))
    rows = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    assert [d["text"] for d in docs] == [r["text"] for r in rows]
    assert [sorted((a["start"], a["end"], a["tag"]) for a in d["annotations"]) for d in docs] == \
           [sorted((s["start"], s["end"], s["label"]) for s in r["spans"]) for r in rows]
    assert tags == {"PER", "INS", "LOC", "DAT", "TITLE"}


def test_conll_roundtrip(app, annotated, tmp_path):
    out = tmp_path / "train.conll"
    app._export_as_conll(str(out))
    docs, tags = app._parse_conll_into_documents(str(out))
    assert len(docs) == 3
    assert_golden("import__conll_roundtrip", [
        {"text": d["text"], "spans": sorted([d["text"][a["start"]:a["end"]], a["tag"]] for a in d["annotations"])}
        for d in docs])


def test_quirk_conll_roundtrip_changes_text(app, annotated, tmp_path):
    """CoNLL is token-based: re-import rebuilds text with single spaces between
    tokens, so punctuation spacing differs from the source ('XIV .' etc.)."""
    out = tmp_path / "train.conll"
    app._export_as_conll(str(out))
    docs, _ = app._parse_conll_into_documents(str(out))
    original = Path(annotated[1]).read_text(encoding="utf-8")
    assert docs[1]["text"] != original


# Session file

def test_session_save_format(app, dialogs, annotated, tmp_path):
    target = tmp_path / "s.json"
    dialogs.script(asksaveasfilename=[str(target)])
    app.save_session()
    data = json.loads(target.read_text(encoding="utf-8"))
    assert sorted(data) == sorted([
        "version", "files_list", "current_file_index", "tag_hierarchy", "tag_active_states",
        "tag_propagation_states", "tag_visible_states", "selection_mode", "relation_types",
        "tag_colors", "annotations", "extend_to_word", "allow_multilabel_overlap",
        "last_used_ai_models", "current_ai_models", "ai_min_conf", "ai_max_conf",
        "ai_label_mapping", "llm_provider", "llm_models", "llm_model", "llm_few_shot_count"])
    assert all(Path(p).is_absolute() for p in data["files_list"])
    assert set(data["annotations"]) == set(data["files_list"])
    assert "api_key" not in target.read_text(encoding="utf-8")
    assert_golden("session__saved", relativize(strip_ids(data), tmp_path))


def test_session_roundtrip(app, dialogs, annotated, tmp_path):
    target = tmp_path / "s.json"
    dialogs.script(asksaveasfilename=[str(target)])
    app.save_session()
    before = json.loads(json.dumps(app.annotations))
    app.files_list, app.annotations = [], {}
    dialogs.script(askopenfilename=[str(target)])
    app.load_session()
    assert app.annotations == before
    assert app.files_list == annotated
    assert app.current_file_path == annotated[0]


def test_session_load_with_missing_text_file(app, dialogs, annotated, tmp_path):
    target = tmp_path / "s.json"
    dialogs.script(asksaveasfilename=[str(target)])
    app.save_session()
    Path(annotated[1]).unlink()
    app.files_list = []
    dialogs.script(askopenfilename=[str(target)], askyesno=[True])
    app.load_session()
    assert "Missing Files" in dialogs.titles("askyesno")
    assert app.files_listbox.items[1].endswith("[MISSING]")


def test_quirk_legacy_session_keys(app, dialogs, tmp_path):
    """Old sessions with a flat 'entity_tags' list load into a 'Custom Layer';
    API keys stored in a session file are still read on load."""
    f = tmp_path / "a.txt"
    f.write_text("x", encoding="utf-8")
    target = tmp_path / "old.json"
    target.write_text(json.dumps({"files_list": [str(f)], "annotations": {}, "relation_types": ["r"],
                                  "entity_tags": ["PER", "LOC"], "claude_api_key": "sk-old"}), encoding="utf-8")
    dialogs.script(askopenfilename=[str(target)])
    app.files_list = []
    app.load_session()
    assert app.tag_hierarchy == {"Custom Layer": ["PER", "LOC"]}
    assert app.claude_api_key == "sk-old"
    assert app.ai_min_conf == 0.60  # default on load differs from the 0.90 default at startup


def test_schema_save_and_load(app, dialogs, tmp_path):
    target = tmp_path / "schema.json"
    dialogs.script(asksaveasfilename=[str(target)])
    app.save_schema()
    data = json.loads(target.read_text(encoding="utf-8"))
    assert_golden("schema__default", data)
