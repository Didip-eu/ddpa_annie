# -*- coding: utf-8 -*-
"""Interaction logic that only exists inside real Tk widgets / dialogs:
selection snapping, merge/demerge (coreference by shared id), relations, and
the dialog-bound dictionary export and propagation scope. A future web UI must
reproduce these semantics, so they are pinned with a real (hidden) Tk window."""
import tkinter as tk
from pathlib import Path

import pytest

from conftest import entity, open_session

pytestmark = pytest.mark.tk


def find_button(widget, text):
    for child in widget.winfo_children():
        if isinstance(child, tk.Button) and child.cget("text") == text:
            return child
        found = find_button(child, text)
        if found:
            return found
    return None


def toplevels(root):
    return [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]


def select(app, start, end):
    app.text_area.config(state=tk.NORMAL)
    app.text_area.tag_remove(tk.SEL, "1.0", tk.END)
    app.text_area.tag_add(tk.SEL, start, end)


def file_ents(app):
    return app.annotations[app.current_file_path]["entities"]


G = 54  # column of 'Gmünd' on line 1
L = 34  # column of 'Liebfrauenkirche'


@pytest.fixture
def charter(tk_app, tmp_path):
    f = tmp_path / "P0306.txt"
    f.write_text("Artolff von Lewbnegk übergibt der Liebfrauenkirche zu Gmünd\n"
                 "ein Gut gelegen zu Plesnicz (Leucz Weczenpacher).", encoding="utf-8")
    first_line = f.read_text(encoding="utf-8").split("\n")[0]
    assert first_line.find("Gmünd") == G and first_line.find("Liebfrauenkirche") == L
    open_session(tk_app, [str(f)])
    return str(f)


def test_word_mode_snaps_partial_selection_to_word(tk_app, charter):
    tk_app.selected_entity_tag.set("PER")
    select(tk_app, "1.2", "1.10")  # 'tolff v'
    tk_app.annotate_selection()
    (e,) = file_ents(tk_app)
    assert (e["text"], e["start_char"], e["end_char"]) == ("Artolff von", 0, 11)


def test_char_mode_keeps_selection_but_strips_whitespace(tk_app, charter):
    tk_app.selection_mode.set("char")
    tk_app.selected_entity_tag.set("LOC")
    select(tk_app, f"1.{G - 1}", "2.0")  # ' Gmünd\n'

    tk_app.annotate_selection()
    (e,) = file_ents(tk_app)
    assert e["text"] == "Gmünd" and (e["start_line"], e["start_char"], e["end_char"]) == (1, G, G + 5)


def test_word_mode_punctuation_is_its_own_word(tk_app, charter):
    tk_app.selected_entity_tag.set("PER")
    select(tk_app, "2.29", "2.46")  # 'Leucz Weczenpacher'
    tk_app.annotate_selection()
    assert file_ents(tk_app)[0]["text"] == "Leucz Weczenpacher"


def test_multiline_selection(tk_app, charter):
    tk_app.selected_entity_tag.set("LOC")
    select(tk_app, f"1.{G}", "2.3")
    tk_app.annotate_selection()
    (e,) = file_ents(tk_app)
    assert (e["start_line"], e["end_line"]) == (1, 2) and e["text"] == "Gmünd\nein"


def test_exact_duplicate_rejected_overlap_allowed(tk_app, charter):
    tk_app.selected_entity_tag.set("LOC")
    for _ in range(2):
        select(tk_app, f"1.{G}", f"1.{G + 5}")
        tk_app.annotate_selection()
    tk_app.selected_entity_tag.set("INS")
    select(tk_app, f"1.{L}", f"1.{G + 5}")
    tk_app.annotate_selection()
    assert sorted(e["tag"] for e in file_ents(tk_app)) == ["INS", "LOC"]


def test_overlap_rejected_when_multilabel_disabled(tk_app, dialogs, charter):
    tk_app.allow_multilabel_overlap.set(False)
    tk_app.selected_entity_tag.set("LOC")
    select(tk_app, f"1.{G}", f"1.{G + 5}")
    tk_app.annotate_selection()
    tk_app.selected_entity_tag.set("INS")
    select(tk_app, f"1.{L}", f"1.{G + 5}")
    tk_app.annotate_selection()
    assert [e["tag"] for e in file_ents(tk_app)] == ["LOC"]
    assert dialogs.titles("showwarning") == ["Overlap Detected"]


def test_merge_shares_id_and_rewrites_relations_demerge_splits(tk_app, charter):
    p = charter
    content = Path(p).read_text(encoding="utf-8")
    a = entity(tk_app, p, 0, 20, "PER")
    b = entity(tk_app, p, content.find("Leucz"), content.find("Leucz") + 18, "PER")
    c = entity(tk_app, p, content.find("Gmünd"), content.find("Gmünd") + 5, "LOC")
    tk_app.annotations[p] = {"entities": [a, b, c], "relations": [
        {"id": "r1", "type": "located_in", "head_id": a["id"], "tail_id": c["id"]},
        {"id": "r2", "type": "located_in", "head_id": b["id"], "tail_id": c["id"]}]}
    tk_app.current_file_index = -1
    tk_app.load_file(0)
    iids = [i for i in tk_app.entities_tree.get_children() if "|PER|" in i]
    tk_app.entities_tree.selection_set(iids)
    tk_app.merge_selected_entities()
    assert a["id"] == b["id"]
    rels = tk_app.annotations[p]["relations"]
    assert len(rels) == 1 and rels[0]["head_id"] == a["id"]  # duplicate relation collapsed
    tk_app.demerge_entity(b)
    assert a["id"] != b["id"]
    assert rels[0]["head_id"] == a["id"]  # relation stays with the first mention


def test_add_and_flip_relation(tk_app, charter):
    p = charter
    a = entity(tk_app, p, 0, 20, "PER")
    c = entity(tk_app, p, G, G + 5, "LOC")
    tk_app.annotations[p] = {"entities": [a, c], "relations": []}
    tk_app.current_file_index = -1
    tk_app.load_file(0)
    tk_app.selected_entity_ids_for_relation = [a["id"], c["id"]]
    tk_app.selected_relation_type.set("located_in")
    tk_app.add_relation()
    tk_app.add_relation()  # duplicate ignored
    rels = tk_app.annotations[p]["relations"]
    assert [(r["head_id"], r["tail_id"]) for r in rels] == [(a["id"], c["id"])]
    tk_app.relations_tree.selection_set(rels[0]["id"])
    tk_app.flip_selected_relation()
    assert (rels[0]["head_id"], rels[0]["tail_id"]) == (c["id"], a["id"])


def test_dictionary_export_dialog(tk_app, dialogs, charter, tmp_path):
    p = charter
    tk_app.annotations[p] = {"entities": [entity(tk_app, p, 0, 20, "PER"), entity(tk_app, p, G, G + 5, "LOC"),
                                          entity(tk_app, p, G, G + 5, "LOC")], "relations": []}
    out = tmp_path / "dict.txt"
    dialogs.script(asksaveasfilename=[str(out)])
    tk_app.export_dictionary()
    find_button(toplevels(tk_app.root)[-1], "Export").invoke()
    assert out.read_text(encoding="utf-8") == "Gmünd\tLOC\nArtolff von Lewbnegk\tPER\n"


def test_quirk_propagation_scope_all_files_label(tk_app, charter, tmp_path):
    """Choosing 'All Files' still reports 'Current File Propagation' in the status."""
    other = tmp_path / "other.txt"
    other.write_text("Gmünd", encoding="utf-8")
    tk_app.files_list.append(str(other))
    tk_app.annotations[charter] = {"entities": [entity(tk_app, charter, G, G + 5, "LOC")], "relations": []}
    tk_app.propagate_annotations()
    find_button(toplevels(tk_app.root)[-1], "All Files").invoke()
    assert [e["text"] for e in tk_app.annotations[str(other)]["entities"]] == ["Gmünd"]
    assert tk_app.status_var.get().startswith("Current File Propagation complete")
