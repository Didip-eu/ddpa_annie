# -*- coding: utf-8 -*-
"""Whole-corpus characterization over example_data/ (skipped if absent).

Parses every CH.cei.xml with the real import parser and pins aggregate
statistics plus a hash of all produced documents, so any change in text
extraction or auto-annotation anywhere in the corpus is detected."""
import collections
import hashlib
import json
import time

import pytest

from conftest import EXAMPLE_DATA, assert_golden

pytestmark = pytest.mark.corpus


@pytest.fixture(scope="module")
def charter_files():
    if not EXAMPLE_DATA.exists():
        pytest.skip("example_data/ not present")
    return sorted(p for p in EXAMPLE_DATA.rglob("CH.cei.xml"))


def test_corpus_import(app, dialogs, charter_files):
    empty = [p for p in charter_files if p.stat().st_size == 0]
    tag_counts = collections.Counter()
    text_lengths = []
    digest = hashlib.sha256()
    ids = collections.Counter()
    t0 = time.perf_counter()
    for p in charter_files:
        if p.stat().st_size == 0:
            continue
        docs, tags = app._parse_cei_xml_into_documents(str(p))
        assert len(docs) == 1, p
        doc = docs[0]
        ids[doc["source_id"]] += 1
        text_lengths.append(len(doc["text"]))
        for a in doc["annotations"]:
            tag_counts[a["tag"]] += 1
            assert 0 <= a["start"] < a["end"] <= len(doc["text"]), p
        digest.update(json.dumps([doc["source_id"], doc["text"], sorted(
            (a["start"], a["end"], a["tag"]) for a in doc["annotations"])], ensure_ascii=False).encode())
    elapsed = time.perf_counter() - t0

    assert not [t for t in dialogs.calls if t[0].startswith("show")], "parser raised dialogs"
    assert max(ids.values()) == 1, "duplicate atom ids"
    assert elapsed < 30
    text_lengths.sort()
    assert_golden("corpus__stats", {
        "charter_files": len(charter_files),
        "empty_files": len(empty),
        "parsed": len(text_lengths),
        "tag_counts": dict(sorted(tag_counts.items())),
        "text_length_min_median_max": [text_lengths[0], text_lengths[len(text_lengths) // 2], text_lengths[-1]],
        "sha256": digest.hexdigest(),
    })


def test_quirk_empty_charter_files_raise_error_dialog(app, dialogs, charter_files):
    """A 0-byte CH.cei.xml produces an 'XML Parse Error' dialog and no document."""
    empty = next((p for p in charter_files if p.stat().st_size == 0), None)
    if empty is None:
        pytest.skip("no empty files in corpus")
    docs, tags = app._parse_cei_xml_into_documents(str(empty))
    assert docs == [] and dialogs.titles("showerror") == ["XML Parse Error"]
