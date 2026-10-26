# -*- coding: utf-8 -*-
"""Characterization-test harness for ANNIE.

These tests pin down the CURRENT behaviour of the Tkinter application so the
logic can be extracted into a GUI-free ``annie_core`` package without silent
drift. They deliberately also pin quirks (see tests named ``test_quirk_*``);
when a quirk is intentionally fixed during the refactor, update that test.

The ``app`` fixture builds a real ``TextAnnotator`` with all Tk widgets and
dialogs replaced by fakes, so it runs without a display. Tests that need real
Tk text-index semantics use the ``tk_app`` fixture (marker ``tk``) and are
skipped when no display is available.

Golden files live in tests/golden/. Regenerate with ``UPDATE_GOLDEN=1``.
"""
import json
import os
import re
import shutil
import sys
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# annie/ai/ensemble.py does a top-level ``import torch`` although the README
# calls torch optional. Stub it so the logic can be tested without PyTorch.
try:
    import torch  # noqa: F401
    TORCH_STUBBED = False
except ImportError:
    _torch = mock.MagicMock(name="torch-stub")
    _torch.cuda.is_available.return_value = False
    sys.modules["torch"] = _torch
    TORCH_STUBBED = True

FIXTURES = ROOT / "tests" / "fixtures"
CEI_DIR = FIXTURES / "cei"
GOLDEN_DIR = ROOT / "tests" / "golden"
EXAMPLE_DATA = ROOT / "example_data"

REAL_CHARTERS = ["ADG_Urk_P0306", "ADG_Urk_P1303", "ADG_Urk_P2335"]
SYNTH_CHARTER = "SYNTH_full_tenor"

DIALOG_MODULES = [
    "annie.io.import_parser", "annie.io.files", "annie.io.session",
    "annie.io.export", "annie.annotation.core", "annie.annotation.propagation",
    "annie.annotation.manage", "annie.ai.llm", "annie.ai.ensemble", "annie.search",
]


# Tk stand-ins

class Var:
    """Stand-in for tk.StringVar / tk.BooleanVar."""

    def __init__(self, master=None, value=None, **kwargs):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value


class FakeListbox:
    def __init__(self):
        self.items = []

    def delete(self, first, last=None):
        self.items = []

    def insert(self, index, item):
        self.items.append(item)

    def __getattr__(self, name):  # selection_set, see, activate, ...
        return lambda *a, **k: None


class FakeText:
    """Only what the logic paths read back: the full text."""

    def __init__(self):
        self.content = ""

    def insert(self, index, text):
        self.content += text

    def delete(self, *args):
        self.content = ""

    def get(self, start="1.0", end=None):
        return self.content + "\n"  # Tk always appends a trailing newline

    def cget(self, key):
        return "disabled"

    def winfo_exists(self):
        return True

    def __getattr__(self, name):  # config, tag_remove, edit_reset, ...
        return lambda *a, **k: None


class Dialogs:
    """Records every messagebox / filedialog call and returns scripted answers.

    ``dialogs.script(askyesno=[True, False], askdirectory=["/tmp/x"])`` queues
    answers per function name. Unscripted confirmations answer True; unscripted
    file dialogs answer "" (i.e. the user cancelled).
    """

    CONFIRM = {"askyesno", "askokcancel", "askyesnocancel", "askquestion", "askretrycancel"}

    def __init__(self):
        self.calls = []
        self._answers = {}

    def script(self, **answers):
        for name, values in answers.items():
            self._answers.setdefault(name, []).extend(values)

    def titles(self, kind=None):
        return [title for name, title in self.calls if kind is None or name == kind]

    def _fn(self, name):
        def fn(*args, **kwargs):
            title = args[0] if args else kwargs.get("title", "")
            self.calls.append((name, title))
            queue = self._answers.get(name)
            if queue:
                return queue.pop(0)
            return True if name in self.CONFIRM else ""
        return fn

    def module(self):
        names = ["showinfo", "showwarning", "showerror", "askyesno", "askokcancel",
                 "askyesnocancel", "askquestion", "askretrycancel", "askopenfilename",
                 "askopenfilenames", "asksaveasfilename", "askdirectory"]
        ns = mock.MagicMock()
        for n in names:
            setattr(ns, n, self._fn(n))
        return ns


# App fixtures

UI_NOOPS = [
    "create_menu", "_update_entity_tag_combobox", "_update_relation_type_combobox",
    "_configure_text_tags", "_configure_treeview_tags", "_update_button_states",
    "apply_annotations_to_text", "update_entities_list", "update_relations_list",
    "clear_views", "_process_queue",
]


def _make_headless_class():
    from annie.app import TextAnnotator

    def create_layout(self):
        self.text_area = FakeText()
        self.files_listbox = FakeListbox()
        self.entities_tree = mock.MagicMock()
        self.relations_tree = mock.MagicMock()

    def _load_api_keys(self):
        # Never read the developer's real .env during tests.
        self.hf_api_key = self.claude_api_key = ""
        self.openai_api_key = self.together_api_key = ""

    attrs = {name: (lambda self, *a, **k: None) for name in UI_NOOPS}
    attrs["create_layout"] = create_layout
    attrs["_load_api_keys"] = _load_api_keys
    return type("HeadlessAnnotator", (TextAnnotator,), attrs)


@pytest.fixture
def dialogs(monkeypatch):
    d = Dialogs()
    fake = d.module()
    import importlib
    for modname in DIALOG_MODULES:
        mod = importlib.import_module(modname)
        for attr in ("messagebox", "filedialog", "simpledialog"):
            if hasattr(mod, attr):
                monkeypatch.setattr(mod, attr, fake)
    return d


@pytest.fixture
def app(monkeypatch, tmp_path, dialogs):
    import annie.app as app_mod
    fake_tk = mock.MagicMock()
    fake_tk.StringVar = Var
    fake_tk.BooleanVar = Var
    monkeypatch.setattr(app_mod, "tk", fake_tk)
    monkeypatch.setattr(app_mod, "ttk", mock.MagicMock())
    monkeypatch.chdir(tmp_path)
    cls = _make_headless_class()
    return cls(mock.MagicMock(name="root"))


def _has_display():
    try:
        import tkinter as tk
        r = tk.Tk()
        r.destroy()
        return True
    except Exception:
        return False


@pytest.fixture
def tk_app(monkeypatch, tmp_path, dialogs):
    if not _has_display():
        pytest.skip("no display available for real Tk widgets")
    import tkinter as tk
    from annie.app import TextAnnotator
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(TextAnnotator, "_load_api_keys",
                        lambda self: [setattr(self, k, "") for k in
                                      ("hf_api_key", "claude_api_key", "openai_api_key", "together_api_key")])
    root = tk.Tk()
    root.withdraw()
    instance = TextAnnotator(root)
    yield instance
    root.destroy()


# Data helpers

def cei_path(name):
    return CEI_DIR / f"{name}.cei.xml"


@pytest.fixture
def charter_texts(app, tmp_path):
    """The three real charters imported as TXT session files (via the real parser)."""
    out = tmp_path / "session"
    out.mkdir()
    paths = []
    for name in REAL_CHARTERS:
        docs, _ = app._parse_cei_xml_into_documents(str(cei_path(name)))
        p = out / f"{name}.txt"
        p.write_text(docs[0]["text"], encoding="utf-8")
        paths.append(str(p))
    return paths


def open_session(app, paths, annotations=None):
    app.files_list = list(paths)
    app.annotations = annotations or {}
    app.current_file_index = -1
    app.load_file(0)


def entity(app, path, start, end, tag, **extra):
    """Build an entity dict from absolute char offsets, the way ANNIE stores it."""
    content = Path(path).read_text(encoding="utf-8")
    line_starts = [0] + [i + 1 for i, c in enumerate(content) if c == "\n"] + [len(content) + 1]
    sl, sc = map(int, app._char_offset_to_tkinter_index_from_offsets(line_starts, start).split("."))
    el, ec = map(int, app._char_offset_to_tkinter_index_from_offsets(line_starts, end).split("."))
    ent = {"id": f"e{start}_{end}_{tag}", "start_line": sl, "start_char": sc,
           "end_line": el, "end_char": ec, "text": content[start:end], "tag": tag}
    ent.update(extra)
    return ent


def strip_ids(obj):
    """Replace random uuid4 hex ids so outputs are comparable."""
    if isinstance(obj, dict):
        return {k: ("<id>" if k in ("id", "head_id", "tail_id") and isinstance(v, str) else strip_ids(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [strip_ids(x) for x in obj]
    return obj


def relativize(obj, base):
    """Make absolute tmp paths stable inside golden data."""
    base = str(base)
    if isinstance(obj, dict):
        return {relativize(k, base): relativize(v, base) for k, v in obj.items()}
    if isinstance(obj, list):
        return [relativize(x, base) for x in obj]
    if isinstance(obj, str):
        return obj.replace(base, "<tmp>")
    return obj


def assert_golden(name, data):
    path = GOLDEN_DIR / f"{name}.json"
    rendered = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if os.environ.get("UPDATE_GOLDEN") == "1" or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
        if os.environ.get("UPDATE_GOLDEN") != "1":
            pytest.fail(f"golden file {path.name} did not exist and was created; re-run")
        return
    expected = path.read_text(encoding="utf-8")
    assert rendered == expected, f"output differs from golden {path.name} (UPDATE_GOLDEN=1 to accept)"


def spans_with_text(text, annotations):
    """Annotation list with the covered substring, for readable goldens."""
    return [{"tag": a["tag"], "start": a["start"], "end": a["end"], "covered": text[a["start"]:a["end"]]}
            for a in sorted(annotations, key=lambda a: (a["start"], a["end"], a["tag"]))]
