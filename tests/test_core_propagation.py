"""annie_core.propagation: the same entities as the desktop app, in character offsets."""

from pathlib import Path

import pytest

from annie_core.propagation import Entity, propagate, remembered
from conftest import entity, open_session

TERMS = {"Gmünd": "LOC", "Papst": "TITLE", "Anselm Vieweger": "PER", "zu Gmünd": "LOC", "Liebfrauenkirche zu Gmünd": "INS"}


def legacy_offsets(app, path):
    """The desktop app's entities of one file as (start, end, tag, text)."""
    content = Path(path).read_text(encoding="utf-8")
    return sorted((app._tkinter_index_to_char_offset(content, e["start_line"], e["start_char"]),
                   app._tkinter_index_to_char_offset(content, e["end_line"], e["end_char"]), e["tag"], e["text"])
                  for e in app.annotations[path]["entities"])


@pytest.mark.parametrize("allow_overlap", [True, False])
def test_same_entities_as_the_desktop_app(app, charter_texts, allow_overlap):
    open_session(app, charter_texts)
    app.allow_multilabel_overlap.set(allow_overlap)
    app._perform_propagation(TERMS, "Current File Propagation")
    for path in charter_texts:
        found = propagate(Path(path).read_text(encoding="utf-8"), TERMS, [], allow_overlap)
        assert sorted((e.start, e.end, e.tag, e.text) for e in found) == legacy_offsets(app, path)


def test_existing_spans_are_kept_and_not_repeated(app, charter_texts):
    body = Path(charter_texts[0]).read_text(encoding="utf-8")
    start = body.find("Gmünd")
    existing = [Entity(start, start + 5, "LOC", "Gmünd")]
    found = propagate(body, {"Gmünd": "LOC"}, existing, allow_overlap=True)
    assert len(found) == 3 and existing[0] not in found


def test_term_ending_in_punctuation_matches():
    body = "Papst Nikolaus IV. bestätigt. Papst Nikolaus IV.,"
    assert [e.start for e in propagate(body, {"Papst Nikolaus IV.": "PER"}, [], True)] == [0, 30]


def test_multiword_term_across_whitespace():
    (found,) = propagate("iussu\npredicti   iudicis", {"iussu predicti iudicis": "LEG"}, [], True)
    assert (found.start, found.end, found.text) == (0, 24, "iussu predicti iudicis")


def test_longest_term_wins_without_overlap():
    found = propagate("Peter in der Aw", {"Peter": "PER", "Peter in der Aw": "LOC"}, [], allow_overlap=False)
    assert [(e.tag, e.text) for e in found] == [("LOC", "Peter in der Aw")]


def test_remembered_takes_the_majority_tag_of_active_tags():
    annotated = [[Entity(0, 5, "LOC", "Gmünd")], [Entity(3, 8, "LOC", "gmünd")], [Entity(0, 5, "INS", "Gmünd"), Entity(0, 1, "PER", "A")]]
    assert remembered(annotated, {"LOC", "INS", "PER"}) == {"gmünd": "LOC"}
    assert remembered(annotated, {"INS"}) == {}


def test_remembered_matches_the_desktop_memory(app, charter_texts):
    paths = charter_texts
    anns = {}
    for path, items in ((paths[0], [("Gmünd", "LOC"), ("Ulrich Froner", "PER")]), (paths[1], [("Papst", "TITLE")])):
        content = Path(path).read_text(encoding="utf-8")
        anns[path] = {"entities": [entity(app, path, content.find(t), content.find(t) + len(t), g) for t, g in items], "relations": []}
    open_session(app, paths, anns)
    app.load_file(2)
    target = Path(paths[2]).read_text(encoding="utf-8")
    legacy = sorted((e["text"], e["tag"]) for e in app._get_memory_predictions(target))
    examples = [[Entity(0, 0, e["tag"], e["text"]) for e in anns[path]["entities"]] for path in paths[:2]]
    found = propagate(target, remembered(examples, set(app.get_active_tags())), [], True)
    assert sorted((e.text, e.tag) for e in found) == legacy
