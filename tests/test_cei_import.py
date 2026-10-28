# -*- coding: utf-8 -*-
"""CEI XML -> ANNIE documents: text extraction and automatic annotations."""
import os
import shutil
import xml.etree.ElementTree as ET

import pytest

from conftest import (REAL_CHARTERS, SYNTH_CHARTER, assert_golden, cei_path,
                      relativize, spans_with_text, strip_ids)

CEI_NS = "http://www.monasterium.net/NS/cei"


def parse(app, name):
    docs, tags = app._parse_cei_xml_into_documents(str(cei_path(name)))
    assert len(docs) == 1
    return docs[0], tags


@pytest.mark.parametrize("name", REAL_CHARTERS + [SYNTH_CHARTER])
def test_parse_cei_golden(app, name):
    doc, tags = parse(app, name)
    assert_golden(f"cei_parse__{name}", {
        "text": doc["text"],
        "source_id": doc["source_id"],
        "tags": sorted(tags),
        "annotations": spans_with_text(doc["text"], doc["annotations"]),
    })


def test_source_id_is_atom_id(app):
    doc, _ = parse(app, "ADG_Urk_P0306")
    assert doc["source_id"] == "tag:www.monasterium.net,2011:/charter/AT-ADG/PA/ADG_Urk_P0306"


def test_regest_charter_gets_abstract_span(app):
    doc, tags = parse(app, "ADG_Urk_P0306")
    abstract = [a for a in doc["annotations"] if a["tag"] == "abstract"]
    assert len(abstract) == 1
    covered = doc["text"][abstract[0]["start"]:abstract[0]["end"]]
    assert covered.startswith("Artolff von Lewbnegk übergibt")
    assert covered.endswith("(Michel Haunsmid).")


def test_daterange_becomes_DAT(app):
    doc, tags = parse(app, "ADG_Urk_P1303")
    dat = [a for a in doc["annotations"] if a["tag"] == "DAT"]
    assert [doc["text"][a["start"]:a["end"]] for a in dat] == ["174.(radiert), Rom (vor 1741 Jänner 22)"]


def test_quirk_cei_date_is_not_tagged(app):
    """Only cei:dateRange yields DAT; the far more common cei:date (571/577 example charters) does not."""
    doc, tags = parse(app, "ADG_Urk_P0306")
    assert "1448 Juli 16" in doc["text"]
    assert "DAT" not in tags


def test_quirk_metadata_is_mixed_into_document_text(app):
    """Because cei:abstract counts as a 'diplomatic' part, the WHOLE cei:text is
    flattened: idno, date, seal description, archive fond, material and
    cei:back witnesses all end up in one line of annotatable text."""
    doc, _ = parse(app, "ADG_Urk_P0306")
    for fragment in ("ADG_Urk_P0306", "2 Sig. pend. fehlen", "PA Gmünd", "Orig. Perg.",
                     "Hans Huber, Niclas Kopauner"):
        assert fragment in doc["text"]
    assert "\n" not in doc["text"]


def test_quirk_persname_is_not_tagged(app):
    doc, tags = parse(app, "ADG_Urk_P0306")
    assert "PER" not in tags


def test_quirk_place_names_tagged_by_first_occurrence_only(app):
    """placeName text is located with str.find: one LOC per placeName element,
    at its FIRST textual occurrence (which may be in the abstract, not where the
    element actually is)."""
    doc, _ = parse(app, SYNTH_CHARTER)
    locs = [(doc["text"][a["start"]:a["end"]], a["start"]) for a in doc["annotations"] if a["tag"] == "LOC"]
    first_gmuend = doc["text"].find("Gmünd")
    assert ("Gmünd", first_gmuend) in locs
    assert first_gmuend < doc["text"].find("1305 März 12")  # i.e. inside the abstract


def test_synthetic_diplomatic_structure(app):
    doc, tags = parse(app, SYNTH_CHARTER)
    by_tag = {}
    for a in doc["annotations"]:
        by_tag.setdefault(a["tag"], []).append(doc["text"][a["start"]:a["end"]])
    assert {"protocol", "tenor", "eschatocol", "invocatio", "intitulatio", "narratio",
            "dispositio", "corroboratio", "datation", "abstract"} <= tags
    assert by_tag["protocol"] == ["In nomine sancte et individue trinitatis.\nNos Heinricus deigratia episcopus"]
    assert by_tag["tenor"][0].startswith("notum facimus") and by_tag["tenor"][0].endswith("appendimus.")
    assert by_tag["eschatocol"][0].startswith("Datum anno domini")
    # sub-parts nest inside their macro span
    assert by_tag["invocatio"][0] in by_tag["protocol"][0]
    assert by_tag["corroboratio"][0] in by_tag["tenor"][0]


def test_quirk_datatio_tag_is_named_datation(app, dialogs, tmp_path):
    """cei:datatio is labelled 'datation', but DIPLOMATIC_TAGS lists 'datatio',
    so on import the tag lands in 'Imported Tags' instead of the Diplomatic layer."""
    dialogs.script(askopenfilename=[str(cei_path(SYNTH_CHARTER))])
    app._ask_for_save_directory = lambda initial: str(tmp_path / "out")
    app.import_annotations()
    assert "datation" in app.tag_hierarchy["Imported Tags"]
    assert "datation" not in app.tag_hierarchy["Diplomatic"]
    assert "eschatocol" in app.tag_hierarchy["Diplomatic"]


def test_quirk_date_and_place_spans_include_element_tail(app):
    """_get_element_text returns text + tail, so 'IIII idus marcii' followed by
    '.' in the XML becomes a DAT span 'IIII idus marcii .'."""
    doc, _ = parse(app, SYNTH_CHARTER)
    dats = [doc["text"][a["start"]:a["end"]] for a in doc["annotations"] if a["tag"] == "DAT"]
    assert "IIII idus marcii ." in dats


def test_quirk_abbr_expansion_merges_with_next_word(app):
    """The expansion is appended without a separator and the tail's leading
    space is stripped: '<abbr expan="dei">dei</abbr> gratia' -> 'deigratia'."""
    assert app._extract_text_from_cei_element(_el('<cei:abbr expan="domini">dni</cei:abbr> nostri')) == "domininostri"
    doc, _ = parse(app, SYNTH_CHARTER)
    assert "Nos Heinricus deigratia episcopus" in doc["text"]


def test_import_text_differs_from_convert_to_txt(app, tmp_path):
    """_convert_cei_xml_to_txt (used for 'open XML as TXT') extracts only the
    tenor/abstract, while import extracts the full cei:text. The two paths
    therefore produce different documents for the same charter."""
    out = app._convert_cei_xml_to_txt(str(cei_path("ADG_Urk_P0306")), output_dir=str(tmp_path))
    converted = open(out, encoding="utf-8").read()
    doc, _ = parse(app, "ADG_Urk_P0306")
    assert os.path.basename(out) == "ADG_Urk_P0306.txt"
    assert converted.startswith("Artolff von Lewbnegk") and converted.endswith("(Michel Haunsmid).")
    assert converted != doc["text"] and converted in doc["text"]


# _extract_text_from_cei_element: markup handling

def _el(xml):
    return ET.fromstring(f'<cei:x xmlns:cei="{CEI_NS}">{xml}</cei:x>')


@pytest.mark.parametrize("xml,expected", [
    ("plain text", "plain text"),
    ("a<cei:lb/>b", "a\nb"),
    ("<cei:abbr>dni</cei:abbr> nostri", "dni nostri"),
    ("<cei:app><cei:lem>Gemunde</cei:lem><cei:rdg>Gmunde</cei:rdg></cei:app>", "Gemunde"),
    ("<cei:app><cei:rdg>Gmunde</cei:rdg></cei:app>", "Gmunde"),
    ("dixit <cei:quote>fiat</cei:quote> et", 'dixit "fiat" et'),
    ("M<cei:sup>o</cei:sup>CCC", "M o CCC"),
    ("text<cei:note>skip me</cei:note> more", "text more"),
    ("a<cei:del>gone</cei:del>b", "a b"),
    ("<cei:placeName>Gmünd</cei:placeName>, am", "Gmünd , am"),
    ("line one\n      line two", "line one\nline two"),
    ("a<cei:lb/><cei:lb/><cei:lb/><cei:lb/>b", "a\n\nb"),
])
def test_extract_text_markup(app, xml, expected):
    assert app._extract_text_from_cei_element(_el(xml)) == expected


def test_quirk_element_boundaries_insert_spaces(app):
    """Non-whitespace text before/after child elements gets a trailing space,
    so markup inside a word splits it ('M<sup>o</sup>' -> 'M o')."""
    assert app._extract_text_from_cei_element(_el("Gmü<cei:hi>n</cei:hi>d")) == "Gmü n d"


# import_annotations end-to-end (file dialogs scripted)

def test_import_annotations_creates_txt_and_session_entries(app, dialogs, tmp_path):
    save_dir = tmp_path / "imported"
    dialogs.script(askopenfilename=[str(cei_path("ADG_Urk_P1303"))])
    app._ask_for_save_directory = lambda initial: str(save_dir)
    app.import_annotations()

    created = save_dir / "ADG_Urk_P1303_1.txt"
    assert created.exists()
    assert app.files_list == [str(created)]
    ents = app.annotations[str(created)]["entities"]
    assert {e["tag"] for e in ents} == {"abstract", "DAT"}
    assert "New Tags Found" in dialogs.titles("askyesno")
    assert app.tag_hierarchy["Diplomatic"] == ["abstract"]
    assert "Imported Tags" not in app.tag_hierarchy  # DAT already exists in CORE Layer
    assert_golden("import_annotations__P1303", relativize(strip_ids({
        "entities": ents, "tag_hierarchy": app.tag_hierarchy}), tmp_path))


def test_import_rejecting_new_tags_drops_their_annotations(app, dialogs, tmp_path):
    dialogs.script(askopenfilename=[str(cei_path("ADG_Urk_P1303"))], askyesno=[False])
    app._ask_for_save_directory = lambda initial: str(tmp_path / "out")
    app.import_annotations()
    ents = app.annotations[app.files_list[0]]["entities"]
    assert {e["tag"] for e in ents} == {"DAT"}  # DAT is a default tag, 'abstract' is new


def test_quirk_real_corpus_filenames_collide(app, dialogs, tmp_path):
    """Monasterium dumps store every charter as <hash>/CH.cei.xml. Importing two
    of them into the same folder writes CH_1.txt twice: the second import
    silently overwrites the first file, and files_list holds the path twice."""
    out = tmp_path / "out"
    for name in ("ADG_Urk_P0306", "ADG_Urk_P1303"):
        d = tmp_path / name
        d.mkdir()
        shutil.copy(cei_path(name), d / "CH.cei.xml")
        dialogs.script(askopenfilename=[str(d / "CH.cei.xml")], askyesno=[True, False])
        app._ask_for_save_directory = lambda initial: str(out)
        app.import_annotations()
    assert os.listdir(out) == ["CH_1.txt"]
    assert app.files_list == [str(out / "CH_1.txt")] * 2
    assert "ADG_Urk_P1303" in (out / "CH_1.txt").read_text(encoding="utf-8")


def test_import_cei_annotate_existing_files(app, dialogs, tmp_path):
    """Second import path: annotate already-open session files whose content matches."""
    doc, _ = parse(app, "ADG_Urk_P0306")
    session_file = tmp_path / "existing.txt"
    session_file.write_text("Header line\n" + doc["text"], encoding="utf-8")
    app.files_list = [str(session_file)]
    app.annotations = {str(session_file): {"entities": [], "relations": []}}

    dialogs.script(askopenfilename=[str(cei_path("ADG_Urk_P0306"))], askyesno=[True, True])
    app.import_annotations()
    ents = app.annotations[str(session_file)]["entities"]
    assert [(e["tag"], e["start_line"]) for e in ents] == [("abstract", 2)]
    assert ents[0]["text"].startswith("Artolff")
    assert dialogs.titles("showinfo")[-1] == "Import Complete"
