# -*- coding: utf-8 -*-
"""
ANNIE: Annotation Interface for Named-entity & Information Extraction.
Includes Hierarchical Tagging, Hybrid Ensemble AI (Session Memory + HF Models),
Sentence-level conversion, and Global Search.

Thin launcher — the application lives in the `annie_legacy/` package.
Run with:  python annie.py   (or:  python -m annie_legacy)
"""
from annie_legacy.app import main

if __name__ == "__main__":
    main()