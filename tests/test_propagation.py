# -*- coding: utf-8 -*-
"""Annotation propagation (session-wide and from a dictionary file) and
corpus-wide deletion, run on the real charter texts."""
from pathlib import Path

from conftest import assert_golden, entity, open_session, relativize, strip_ids


def ents(app, path):
    return app.annotations.get(path, {}).get("entities", [])


def summary(app, paths, base):
    return relativize({p: sorted((e["tag"], e["start_line"], e["start_char"], e["end_line"],
                                  e["end_char"], e["text"], e.get("propagated", False))
                                 for e in ents(app, p)) for p in paths}, base)


def test_propagate_place_and_person_across_charters(app, charter_texts, tmp_path):
    open_session(app, charter_texts)
    app._perform_propagation({"Gmünd": "LOC", "Papst": "TITLE", "Anselm Vieweger": "PER"},
                             "Current File Propagation")
    result = summary(app, charter_texts, tmp_path)
    assert_golden("propagation__charters", result)
    p0306, p1303, p2335 = charter_texts
    assert [e["text"] for e in ents(app, p0306) if e["tag"] == "LOC"] == ["Gmünd"] * 4
    assert [e["text"] for e in ents(app, p1303) if e["tag"] == "TITLE"] == ["Papst", "Papst"]
    assert all(e["propagated"] for p in charter_texts for e in ents(app, p))


def test_case_insensitive_and_text_taken_from_target(app, charter_texts):
    open_session(app, charter_texts)
    app._perform_propagation({"papst": "TITLE"}, "Current File Propagation", target_files=[charter_texts[1]])
    assert {e["text"] for e in ents(app, charter_texts[1])} == {"Papst"}


def test_word_boundaries(app, tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("Gmünder Gmünd. (Gmünd) Ego notarius interfui. (S) Ego notarius interfui. (S)x", encoding="utf-8")
    open_session(app, [str(f)])
    app._perform_propagation({"Gmünd": "LOC", "interfui. (S)": "COM"}, "Dictionary Propagation")
    got = sorted((e["tag"], e["start_char"], e["text"]) for e in ents(app, str(f)))
    # 'Gmünder' is not matched; text ending in ')' has no trailing \b, so '(S)x' also matches
    assert got == [("COM", 36, "interfui. (S)"), ("COM", 63, "interfui. (S)"),
                   ("LOC", 8, "Gmünd"), ("LOC", 16, "Gmünd")]


def test_multiword_terms_match_across_line_breaks(app, tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("iussu\npredicti   iudicis et cetera", encoding="utf-8")
    open_session(app, [str(f)])
    app._perform_propagation({"iussu predicti iudicis": "LEG"}, "Dictionary Propagation")
    (e,) = ents(app, str(f))
    assert (e["start_line"], e["start_char"], e["end_line"], e["end_char"]) == (1, 0, 2, 18)
    assert e["text"] == "iussu predicti iudicis"  # stored text is whitespace-normalised


def test_existing_identical_span_not_duplicated(app, charter_texts):
    path = charter_texts[0]
    content = Path(path).read_text(encoding="utf-8")
    start = content.find("Gmünd")
    open_session(app, charter_texts, {path: {"entities": [entity(app, path, start, start + 5, "LOC")], "relations": []}})
    app._perform_propagation({"Gmünd": "LOC"}, "Current File Propagation", target_files=[path])
    assert len([e for e in ents(app, path) if e["tag"] == "LOC"]) == 4  # 4 occurrences, 1 pre-existing


def test_overlap_setting_respected_for_session_propagation(app, charter_texts):
    path = charter_texts[0]
    content = Path(path).read_text(encoding="utf-8")
    start = content.find("Liebfrauenkirche zu Gmünd")
    open_session(app, charter_texts, {path: {"entities": [entity(app, path, start, start + 25, "INS")], "relations": []}})
    app.allow_multilabel_overlap.set(False)
    app._perform_propagation({"Gmünd": "LOC"}, "Current File Propagation", target_files=[path])
    assert len([e for e in ents(app, path) if e["tag"] == "LOC"]) == 3  # first of 4 overlaps INS


def test_quirk_dictionary_propagation_always_allows_overlap(app, charter_texts):
    """allow_overlap is forced to True whenever 'Dictionary' is in the description string."""
    path = charter_texts[0]
    content = Path(path).read_text(encoding="utf-8")
    start = content.find("Liebfrauenkirche zu Gmünd")
    open_session(app, charter_texts, {path: {"entities": [entity(app, path, start, start + 25, "INS")], "relations": []}})
    app.allow_multilabel_overlap.set(False)
    app._perform_propagation({"Gmünd": "LOC"}, "Dictionary Propagation", target_files=[path])
    assert len([e for e in ents(app, path) if e["tag"] == "LOC"]) == 4


def test_longer_terms_are_applied_first(app, tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("Peter in der Aw", encoding="utf-8")
    open_session(app, [str(f)])
    app.allow_multilabel_overlap.set(False)
    app._perform_propagation({"Peter": "PER", "Peter in der Aw": "LOC"}, "Current File Propagation")
    assert [(e["tag"], e["text"]) for e in ents(app, str(f))] == [("LOC", "Peter in der Aw")]


def test_propagate_annotations_uses_propagation_states(app, charter_texts):
    """propagate_annotations collects text->tag from the current file (only tags
    with propagation enabled) and hands it to the scope dialog."""
    path = charter_texts[0]
    content = Path(path).read_text(encoding="utf-8")
    s1, s2 = content.find("Gmünd"), content.find("Ulrich Froner")
    open_session(app, charter_texts, {path: {"entities": [
        entity(app, path, s1, s1 + 5, "LOC"), entity(app, path, s2, s2 + 13, "PER")], "relations": []}})
    app.tag_propagation_states["PER"] = False
    captured = {}
    app._show_propagation_scope_dialog = lambda mapping: captured.update(mapping)
    app.propagate_annotations()
    assert captured == {"Gmünd": "LOC"}


def test_quirk_same_text_different_tags_last_wins(app, tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("Gmünd und Gmünd", encoding="utf-8")
    open_session(app, [str(f)], {str(f): {"entities": [
        entity(app, str(f), 0, 5, "LOC"), entity(app, str(f), 10, 15, "INS")], "relations": []}})
    captured = {}
    app._show_propagation_scope_dialog = lambda mapping: captured.update(mapping)
    app.propagate_annotations()
    assert captured == {"Gmünd": "INS"}


def test_dictionary_file_parsing(app, dialogs, charter_texts, tmp_path):
    d = tmp_path / "dict.tsv"
    d.write_text("# comment\nGmünd\tLOC\nAnselm Vieweger PER\nPA Keutschach ARCH\nbroken\n", encoding="utf-8")
    open_session(app, charter_texts)
    dialogs.script(askopenfilename=[str(d)], askyesno=[True])
    captured = {}
    app._show_dictionary_propagation_dialog = lambda mapping: captured.update(mapping)
    app.load_and_propagate_from_dictionary()
    assert captured == {"Gmünd": "LOC", "Anselm Vieweger": "PER", "PA Keutschach": "ARCH"}
    assert app.tag_hierarchy["Dictionary Layer"] == ["ARCH"]


def test_corpus_wide_delete_removes_entities_and_dangling_relations(app, dialogs, charter_texts):
    open_session(app, charter_texts)
    app._perform_propagation({"Gmünd": "LOC", "Ulrich Froner": "PER"}, "Current File Propagation")
    p = charter_texts[0]
    loc = next(e for e in ents(app, p) if e["tag"] == "LOC")
    per = next(e for e in ents(app, p) if e["tag"] == "PER")
    app.annotations[p]["relations"] = [{"id": "r1", "type": "located_in", "head_id": per["id"], "tail_id": loc["id"]}]
    app._remove_text_tag_from_corpus(" gmünd ", "LOC")
    assert not [e for p in charter_texts for e in ents(app, p) if e["tag"] == "LOC"]
    assert app.annotations[p]["relations"] == []
    assert dialogs.titles("askokcancel") == ["Permanent Deletion"]
