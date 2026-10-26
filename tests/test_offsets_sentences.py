# -*- coding: utf-8 -*-
"""Position model (Tk 'line.char' indices <-> absolute offsets) and the
sentence-level conversion that re-bases annotations."""
import random
from pathlib import Path

from conftest import assert_golden, entity, open_session, relativize, strip_ids


def line_starts(text):
    return [0] + [i + 1 for i, c in enumerate(text) if c == "\n"] + [len(text) + 1]


def test_offset_index_roundtrip(app):
    """Both converters agree for every offset in a multi-line charter text."""
    text = "Datum anno domini\nM o CCC o V o ,\n\nIIII idus marcii .\nGmünd"
    ls = line_starts(text)
    for off in range(len(text) + 1):
        idx = app._char_offset_to_tkinter_index_from_offsets(ls, off)
        line, char = map(int, idx.split("."))
        assert app._tkinter_index_to_char_offset(text, line, char) == off


def test_lines_are_one_based_chars_zero_based(app):
    ls = line_starts("ab\ncd")
    assert app._char_offset_to_tkinter_index_from_offsets(ls, 0) == "1.0"
    assert app._char_offset_to_tkinter_index_from_offsets(ls, 3) == "2.0"
    assert app._char_offset_to_tkinter_index_from_offsets(ls, 5) == "2.2"


def test_overlap_is_half_open(app):
    assert not app._spans_overlap_numeric(1, 0, 1, 5, 1, 5, 1, 9)  # touching
    assert app._spans_overlap_numeric(1, 0, 1, 6, 1, 5, 1, 9)
    assert app._spans_overlap_numeric(1, 0, 3, 0, 2, 4, 2, 5)  # multi-line containment


def test_normalize_and_remap(app):
    text = "  Artolff \n\n von   Lewbnegk  "
    spans = [{"start": 2, "end": 9, "label": "PER"}, {"start": 13, "end": 27, "label": "X"}]
    norm, remapped = app._normalize_and_remap(text, spans)
    assert norm == "Artolff von Lewbnegk"
    assert [norm[s["start"]:s["end"]] for s in remapped] == ["Artolff", "von Lewbnegk"]


def test_sentence_conversion(app, dialogs, tmp_path):
    src = tmp_path / "charter.txt"
    src.write_text(
        "Artolff von Lewbnegk übergibt der Liebfrauenkirche zu Gmünd ein Gut gelegen zu Plesnicz. "
        "Die Zeugen sind Hans Huber, Niclas Kopauner, alle Bürger zu Gmünd usw. kurz.\n"
        "Orig. Perg. 2 Sig. pend. fehlen", encoding="utf-8")
    content = src.read_text(encoding="utf-8")
    a = content.find("Liebfrauenkirche zu Gmünd")
    b = content.find("Hans Huber")
    c = content.find("Plesnicz. Die")
    anns = {str(src): {"entities": [entity(app, str(src), a, a + 25, "INS"),
                                     entity(app, str(src), b, b + 10, "PER"),
                                     entity(app, str(src), c, c + 13, "LOC")],
                       "relations": [{"id": "r", "type": "x", "head_id": f"e{a}_{a + 25}_INS",
                                      "tail_id": f"e{b}_{b + 10}_PER"}]}}
    open_session(app, [str(src)], anns)
    out = tmp_path / "sent"
    dialogs.script(askdirectory=[str(out)])
    app.convert_session_to_sentences()

    files = sorted(p.name for p in out.iterdir())
    # quirk: the abbreviation 'usw.' ends a sentence once >= 8 words accumulated
    assert files == [f"charter_sent_000{i}.txt" for i in range(1, 5)]
    assert (out / "charter_sent_0003.txt").read_text(encoding="utf-8") == "kurz."
    result = {Path(p).name: {"text": Path(p).read_text(encoding="utf-8"),
                             "annotations": app.annotations[p]} for p in app.files_list}
    assert_golden("sentences__charter", relativize(result, tmp_path))
    # spans crossing a sentence boundary are dropped, relations across sentences too
    all_tags = [e["tag"] for p in app.files_list for e in app.annotations[p]["entities"]]
    assert sorted(all_tags) == ["INS", "PER"]
    assert all(not app.annotations[p]["relations"] for p in app.files_list)


def test_quirk_short_sentences_are_merged(app, dialogs, tmp_path):
    """A '.'-boundary only splits once the running chunk has >= 8 words of length > 1."""
    src = tmp_path / "c.txt"
    src.write_text("Sig. pend. fehlt. Orig. Perg. Ein langer Satz mit genug Worten für einen Split hier. Ende.",
                   encoding="utf-8")
    open_session(app, [str(src)])
    dialogs.script(askdirectory=[str(tmp_path / "s")])
    app.convert_session_to_sentences()
    texts = [Path(p).read_text(encoding="utf-8") for p in app.files_list]
    assert texts == ["Sig. pend. fehlt. Orig. Perg. Ein langer Satz mit genug Worten für einen Split hier.", "Ende."]
