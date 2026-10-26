# -*- coding: utf-8 -*-
"""'Extract diplomatic parts' feature: discovery in CEI files and applying the
parts as annotations to matching session TXT files."""
import shutil
import xml.etree.ElementTree as ET

from conftest import REAL_CHARTERS, SYNTH_CHARTER, assert_golden, cei_path, strip_ids

NS = {"cei": "http://www.monasterium.net/NS/cei"}


def discover(app, name):
    root = ET.parse(cei_path(name)).getroot()
    return app._discover_diplomatic_parts(root, NS, str(cei_path(name)))


def test_discover_parts_golden(app):
    assert_golden("diplomatic_discover", {
        name: [{"label": p["label"], "text": p["text"]} for p in discover(app, name)]
        for name in REAL_CHARTERS + [SYNTH_CHARTER]})


def test_real_charters_only_offer_the_regest(app):
    for name in REAL_CHARTERS:
        assert [p["label"] for p in discover(app, name)] == ["abstract / regest"]


def test_synthetic_charter_offers_all_parts(app):
    labels = [p["label"] for p in discover(app, SYNTH_CHARTER)]
    assert labels == ["invocatio", "intitulatio", "narratio", "dispositio", "corroboratio",
                      "tenor (main text)", "abstract / regest", "datation"]


def test_label_to_tag(app):
    f = app._diplomatic_label_to_tag
    assert f("tenor (main text)") == "tenor"
    assert f("abstract / regest") == "abstract"
    assert f("authentication formula") == "authentication_formula"
    assert f("publicatio / promulgatio") == "publicatio"
    assert f("datation") == "datation"


def _parts(app, name, stem, labels=None):
    return [(f"{name}.cei.xml", str(cei_path(name)), p["label"], p["text"], stem)
            for p in discover(app, name) if labels is None or p["label"] in labels]


def test_apply_parts_to_matching_session_file(app, tmp_path):
    """Session file is matched to the XML by file stem, then each part's text is
    searched in the file content."""
    synth_txt = tmp_path / f"{SYNTH_CHARTER}.txt"
    docs, _ = app._parse_cei_xml_into_documents(str(cei_path(SYNTH_CHARTER)))
    synth_txt.write_text(docs[0]["text"], encoding="utf-8")
    app.files_list = [str(synth_txt)]
    app.annotations = {}
    n = app._apply_diplomatic_annotations(_parts(app, SYNTH_CHARTER, SYNTH_CHARTER), {SYNTH_CHARTER})
    ents = app.annotations[str(synth_txt)]["entities"]
    assert n == len(ents)
    assert_golden("diplomatic_apply__synth", strip_ids(sorted(
        ents, key=lambda e: (e["start_line"], e["start_char"], e["tag"]))))
    tags = {e["tag"] for e in ents}
    assert {"protocol", "tenor", "eschatocol"} <= tags  # macro spans are added
    assert "Diplomatic" in app.tag_hierarchy


def test_apply_regest_to_real_charter_txt(app, tmp_path):
    out = tmp_path / "txt"
    out.mkdir()
    txt = app._convert_cei_xml_to_txt(str(cei_path("ADG_Urk_P2335")), str(out))
    app.files_list = [txt]
    app.annotations = {}
    n = app._apply_diplomatic_annotations(_parts(app, "ADG_Urk_P2335", "ADG_Urk_P2335"), {"ADG_Urk_P2335"})
    ents = app.annotations[txt]["entities"]
    assert n == 1 and ents[0]["tag"] == "abstract"
    assert (ents[0]["start_line"], ents[0]["start_char"]) == (1, 0)


def test_quirk_stem_matching_is_substring_based(app, tmp_path):
    """If no exact stem matches, the FIRST session file whose stem is a substring
    of the XML stem (or vice versa) is used: 'CH' matches everything."""
    a = tmp_path / "CH.txt"
    a.write_text("unrelated text", encoding="utf-8")
    b = tmp_path / "ADG_Urk_P2335.txt"
    b.write_text(discover(app, "ADG_Urk_P2335")[0]["text"], encoding="utf-8")
    app.files_list = [str(a), str(b)]
    app.annotations = {}
    n = app._apply_diplomatic_annotations(_parts(app, "ADG_Urk_P2335", "CH_ADG_Urk_P2335"), {"CH", "ADG_Urk_P2335"})
    # 'CH' is tried first, its content does not contain the regest -> part skipped
    assert n == 0


def test_quirk_extract_dialog_scans_only_one_flat_directory(app, dialogs, tmp_path):
    """extract_diplomatic_parts lists *.xml in ONE directory (no recursion), so the
    Monasterium layout <fond>/<hash>/CH.cei.xml finds nothing at the fond level."""
    fond = tmp_path / "fond"
    for name in REAL_CHARTERS:
        d = fond / name
        d.mkdir(parents=True)
        shutil.copy(cei_path(name), d / "CH.cei.xml")
    dialogs.script(askdirectory=[str(tmp_path / "session"), str(fond)])
    app.files_list = []
    app.extract_diplomatic_parts()
    assert dialogs.titles("showinfo") == ["No XML Files"]


def test_quirk_two_different_tenor_spans(app, tmp_path):
    """'tenor (main text)' (the whole cei:tenor element, protocol..eschatocol) and
    the Tenor *macro* (narratio..corroboratio) both become tag 'tenor', so the
    extraction path yields two overlapping 'tenor' spans with different extents.
    The import path only produces the macro span."""
    synth_txt = tmp_path / f"{SYNTH_CHARTER}.txt"
    docs, _ = app._parse_cei_xml_into_documents(str(cei_path(SYNTH_CHARTER)))
    synth_txt.write_text(docs[0]["text"], encoding="utf-8")
    app.files_list = [str(synth_txt)]
    app.annotations = {}
    app._apply_diplomatic_annotations(_parts(app, SYNTH_CHARTER, SYNTH_CHARTER), {SYNTH_CHARTER})
    tenors = [e for e in app.annotations[str(synth_txt)]["entities"] if e["tag"] == "tenor"]
    assert len(tenors) == 2
    assert {e["text"].split()[0] for e in tenors} == {"In", "notum"}
    assert len([a for a in docs[0]["annotations"] if a["tag"] == "tenor"]) == 1
