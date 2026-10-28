# Changelog

## 0.1.0

### Added

- `scripts/profile_corpus.py`: a profile of the texts and markup of an FSDB build, with its report on the full build of 2026-10-22.
- `annie_core`: propagation, dictionaries, session memory and language model pre-annotation without a GUI, in character offsets.
- `annie_api`: the routes `/annie/providers`, `/annie/propagate` and `/annie/suggest` as an `APIRouter` for `ddp_api`, and a development app.
- `annie_core`, `annie_api`: the provider `dhinfra`, the self-hosted models of the University of Graz, default `deepseek-v4.1-flash`.
- `web/`: the Svelte 5 annotator for `ddp_web`: entities, merge, relations, propagation, dictionaries and pre-annotation, kept in `localStorage`.
- `web/`: a propagation pool: documents added to it receive the propagation of a text's entities besides its own document, kept in `localStorage`.

### Changed

- The desktop application is legacy: its package `annie/` is now `annie_legacy/` (`python -m annie_legacy`); `python annie.py` still starts it.
