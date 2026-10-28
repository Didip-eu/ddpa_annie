# ANNIE for Monasterium NG - Specification

A living document: what ANNIE in Monasterium NG is, what it does, how it fits into the platform, and
what is decided and still open. Change it in the same commit as the change it describes.

State: 2026-10-26, branch `feat/web-annotator`; checked against `ddp_api` 0.7.0
(<https://github.com/Didip-eu/ddp_api>), `ddp_web` 0.3.3 (<https://github.com/Didip-eu/ddp_web>),
`ddp_etl` and `ddp_lib` 0.3.2.

## 1. Purpose

ANNIE annotates the texts of medieval charters with named entities (persons, places, institutions,
dates, ...) and directed relations between them, by hand and with help: propagation of known terms,
dictionaries, a session memory and a language model. It started as a Tkinter desktop application
(`annie_legacy/`, `annie.py`). This repository now also holds its logic as importable Python modules,
API routes for `ddp_api`, and a Svelte component library for `ddp_web`, so that ANNIE runs inside the
web platform of Monasterium NG as a single-user tool.

## 2. The platform around it

```
monasterium.net backup
  -> ddp_etl fsdb        FSDB: one folder per charter (CH.cei.xml, sidecars, images, layer files)
  -> ddp_etl browse      browse.sqlite (document records), analytics.duckdb
  -> ddp_etl index       search index (alias "documents")
  -> ddp_api             FastAPI under /api/v1, read-only, contract in openapi.json
  -> ddp_web             SvelteKit client; its /api/v1 server route forwards to ddp_api
```

- `ddp_lib` holds what several repositories need: the FSDB folder rule, file names (`names`), images.
- `ddp_api` serves every response as a typed pydantic model and every error as
  `{"error": {"code", "message", "request_id"}}`. It has no authentication and, until ANNIE, no route
  that computes on data a client sends.
- `ddp_web` is Svelte 5 (runes) and TypeScript; its API types are generated from `openapi.json`
  (`npm run types`). Its CSS defines design tokens (`--color-*`, `--space-*`, `--text-*`,
  `--font-*`) with a dark variant, and it keeps baskets of documents in the browser.

## 3. The data

### 3.1 The corpus

Measured on the full FSDB build of 2026-10-22 (`scripts/profile_corpus.py`, report in
`reports/profile_full/`):

| | Charters | Share |
|---|---|---|
| All, all CEI files parse, atom ids unique | 793,176 | 100% |
| With a regest (`cei:abstract`) | 675,666 | 85% |
| With a transcription (`cei:tenor`) | 77,515 | 9.8% |
| Regest only | 611,146 | 77% |
| Regest with names marked up (mostly `cei:issuer`) | 235,263 | 30% |
| Tenor with diplomatic parts marked up | 200 | 0.03% |
| No text | 104,515 | 13% |

Text lengths: regest median 192 characters (p99 1,858, max 129,493); tenor median 1,667 (p99 15,754,
max 215,907). Tenors come from 265 archives; the twelve largest hold a third of them. Inline markup in
texts is mostly `sup`, `hi`, `lb`, `ref`, names and `foreign`; `abbr` is rare.

### 3.2 What ANNIE annotates: the texts of a document

ANNIE does not read CEI. It annotates the texts `ddp_etl` extracts and `ddp_api` serves in
`GET /api/v1/documents/{id}`:

```
Document.texts[]: { id: "<document id>:<kind>", kind: "abstract" | "tenor", language, body, hash,
                    mentions[]: { kind, surface, role, key, certainty, start, end, ... }, notes[] }
```

- `body` is plain text with whitespace collapsed; `hash` is the md5 of the body.
- `mentions` are the names the source already marks (`persName`, `placeName`, `orgName`, `geogName`,
  `issuer`, `recipient`, `testis`, `cei:index`), with spans where they stand in the text.
- An annotation is anchored to a text by its `id` and to its content by `hash`.

### 3.3 Known issues of the extracted texts (upstream, in ddp_etl)

- Markup inside a word splits it: `Chv<sup>e</sup>nrat` becomes `Chv e nrat` (about 40,000 texts).
- Diplomatic parts inside a tenor (`invocatio`, `dispositio`, ...) are not read.
- A hyphen at a line break stays: `fro-<lb/> wen` becomes `fro- wen`.

A fix there changes bodies and hashes; ANNIE then re-anchors its annotations (section 6.6).

## 4. Scope

### 4.1 In the first web version

- Core annotation: entity spans with a layered tag schema, overlapping and multi-label spans, merge and
  demerge of mentions (coreference), directed relations, accepting the source's mentions as entities.
- Propagation of a text's entities within the text, or to every text of the working set and of the
  documents added to the propagation pool; dictionaries: import (and propagate), export. TBD: dictionary
  import and the session memory of pre-annotation reach the working set only, not the pool.
- Pre-annotation of a text from the session memory and a language model with TF-IDF-selected
  few-shot examples; providers Anthropic, OpenAI, Together AI, Hugging Face, the DH infrastructure of the University of Graz.

### 4.2 Decided

| Question | Decision |
|---|---|
| Where annotations live | In the browser's `localStorage`, as JSON. Nothing is stored on the server. |
| Users | One user per browser, no authentication, no accounts. |
| What is annotated | `ddp_api` document texts, not CEI files (section 3.2). |
| Where the logic runs | In Python (`annie_core`), called through stateless routes; the client sends the texts. |
| Language model keys | On the server, in environment variables; never in the browser. |
| Claude | Through the official `anthropic` SDK, default `claude-opus-5-5`, server-side refusal fallback. |
| Other providers | Their OpenAI-style chat completion endpoints, through the standard library. |
| The desktop application | Legacy, in `annie_legacy/`: no longer developed, kept as it is; its behaviour is pinned by tests and is the reference. |

### 4.3 Not in the first web version

Training data export (spaCy JSONL, CoNLL), Hugging Face token-classification models, CoNLL/JSONL/CEI
import, sentence splitting, the diplomatic-part extraction from CEI, global search (the platform has
its own), keyboard shortcuts, import of desktop sessions, a server-side store.

## 5. Architecture

```
ddp_web page --(texts of the working set)--> web/ Annotator --localStorage (annotations, schema, settings)
                                                   |
                                    POST /api/v1/annie/... (texts + entities)
                                                   v
ddp_api  --include_router-->  annie_api.router  --calls-->  annie_core (propagation, llm)  --> providers
```

| Part | Path | Depends on | What it is |
|---|---|---|---|
| `annie_core` | `annie_core/` | `anthropic` | The logic, no GUI, no web framework; offsets are characters of a body. |
| `annie_api` | `annie_api/` | `fastapi`, `annie_core` | `router`, an `APIRouter` with prefix `/annie`; `annie_api.dev`, a development app. |
| web library | `web/src/lib/` | `svelte` (peer) | `Annotator` and its parts in `components/annie/`, the store and the API client in `annie/`; packaged by `svelte-package`. |
| demo page | `web/src/routes/annotator/` | the library | Lists the documents of the development app; the clicked one is the working set. Not shipped. |
| desktop app | `annie_legacy/`, `annie.py` | `tkinter`, `requests`, `torch` | The original application, legacy: kept as the reference of the characterization and parity tests. |

## 6. Behaviour

### 6.1 Entities, groups, relations

- An entity is `{id, group, start, end, tag, text, source}`; `text` is `body.slice(start, end)`;
  `source` is `manual`, `mention`, `propagation`, `dictionary`, `memory` or `llm`.
- Spans are half-open; two spans overlap when they share a character.
- The same span with the same tag exists once. With "allow overlap" off, a span that overlaps any
  entity is refused; with it on (the default), overlapping and nested spans of any tags are allowed.
- Merged mentions share a `group`; merging takes the group of the first selected entity by position.
  Demerging gives an entity a group of its own and is only possible for an entity that shares its group.
- A relation is `{id, type, head, tail}` between groups. Merging rewrites relations to the kept group
  and collapses duplicates. Removing entities removes the relations that lose their head or tail.

### 6.2 Selecting a span

In word mode (the default) a selection widens to whole words, a word being a run of letters, digits
and underscores and any other character a word of its own, as in Tk's text widget; in both modes
surrounding whitespace is cut. The user selects first and picks the tag after.

### 6.3 Propagation and dictionaries

- A term matches case-insensitively, with any whitespace between its words, and with a word boundary
  only at an end that is a word character (`interfui. (S)` and `Papst Nikolaus IV.` match).
- Longer terms are applied first; a match that repeats a span and tag is skipped; with overlap off a
  match that overlaps any entity, including one added in the same run, is skipped.
- Propagating a text uses its entities as terms; a text annotated with two tags keeps the later one.
- A dictionary file has one term per line with its tag last, separated by whitespace; blank lines and
  lines starting with `#` are skipped. Its tags are added to a "Dictionary Layer". Dictionary
  propagation always allows overlap, as in the desktop application.
- The dictionary export holds every distinct text and tag of all stored texts, tab-separated, sorted
  by tag, then text in lower case.

### 6.4 Pre-annotation

1. Session memory: every surface (two characters or more) annotated in the other texts of the
   working set, with its most frequent tag among the schema's tags, propagated into the text.
2. Few-shot examples: the annotated texts most similar to the text by TF-IDF cosine (`example_count`,
   default 3, 0 for zero-shot).
3. The prompt asks for a JSON array of `{text, tag}` restricted to the schema's tags; a reply cut
   off after its last complete object is closed and read.
4. The model's terms with a tag of the schema are propagated without overlap against the text's
   entities and the memory's; tags the model invents are dropped.

Results are added at once and marked by source; the user removes what is wrong.

### 6.5 Accepting the source's mentions

Mentions with a span become entities: `person` -> `PER`, `location` -> `LOC`, `group` -> `INS`;
concepts and mentions without a span are left out.

### 6.6 Re-anchoring

When a text is opened and its `hash` differs from the stored one, each entity whose text no longer
stands at its offsets moves to the occurrence of its text nearest its old start; an entity whose text
is gone is dropped, the user is told which, and relations that lose an end are dropped.

### 6.7 Stored state

`localStorage["annie"]` holds `{schema, settings, texts, pool}`:

- `schema`: `{layers: {name: [tags]}, relations: [types]}`; the default is the desktop app's
  (CORE, ANALYTICAL, SPAN layers; `spouse_of`, `works_at`, `located_in`, `born_on`, `produces`).
- `settings`: `{selection, allowOverlap, provider, model, exampleCount}`.
- `texts`: `{text id: {hash, entities, relations}}`.
- `pool`: the texts of the documents added to the propagation pool, bodies included.

## 7. API contract

Routes of `annie_api.router`, under `/api/v1` once included:

| Route | Request | Response |
|---|---|---|
| `GET /annie/providers` | | `{data: [{id, default_model, configured}]}` |
| `POST /annie/propagate` | `{texts: [{id, body, entities}], terms: {term: tag}, allow_overlap}` | `{data: [{text_id, entities}]}`, the new spans per text |
| `POST /annie/suggest` | `{text, examples, tags, provider, model?, example_count, allow_overlap}` | `{data: [{start, end, tag, text, source}]}`, `source` is `memory` or `llm` |

- A span is `{start, end, tag, text}`. Offsets count Python code points (section 10).
- `provider` is `anthropic` (default), `openai`, `together`, `huggingface` or `dhinfra`. Default
  models: `claude-opus-5-5`, `gpt-4o-mini`, `meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo`,
  `HuggingFaceH4/zephyr-7b-alpha`, `deepseek-v4.1-flash`. `dhinfra` is sent `reasoning_effort: none`:
  its model otherwise reasons through the whole token budget on a charter and answers nothing.
- Keys: `DDP_ANNIE_ANTHROPIC_KEY`, `DDP_ANNIE_OPENAI_KEY`, `DDP_ANNIE_TOGETHER_KEY`,
  `DDP_ANNIE_HUGGINGFACE_KEY`, `DDP_ANNIE_DHINFRA_KEY`. `providers` tells whether a key is set, never the key.
- Errors in `ddp_api`'s shape: a provider without a key, unreachable, refusing, or answering no
  readable list is 503 `unavailable`; a malformed request is 422 `invalid_request` (from `ddp_api`'s
  handler once included).

## 8. Frontend library contract

`import { Annotator, AnnieStore, annieApi, readDictionary, writeDictionary } from 'annie'` and the
types `Text`, `Entity`, `Relation`, `Schema`, `Settings`, `Span`.

- `<Annotator texts={Text[]} api? store? />`: `texts` is the working set; `api` defaults to
  `annieApi(fetch, '/api/v1')`; `store` defaults to a store on `localStorage`.
- It renders in the browser only (`localStorage`); a page sets `ssr = false` or guards it.
- It styles itself with `ddp_web`'s tokens and falls back to their light values without them.
- Strings are English and inline.

## 9. Integration into the platform

### 9.1 ddp_api

1. Add this repository as a dependency (git source, as for `ddp-lib`).
2. `v1.include_router(annie_api.router)` in `ddp_api/app.py`.
3. Regenerate `openapi.json` (`uv run python -m ddp_api.openapi`): the contract test fails until then,
   and `ddp_web` regenerates its types from it.
4. Set the provider keys in the deployment (`ddp_deploy`), as secrets.
5. Nothing else changes: CORS already allows POST, errors already use `unavailable`, and the request
   id middleware fills `request_id`. `ddp_api` requires Python 3.13; `annie_*` require 3.12 or later.

### 9.2 ddp_web

1. Add `web/` as a dependency once packaged (`npm run package`), or copy `web/src/lib/annie/` and
   `web/src/lib/components/annie/` to the same paths, keeping their relative imports.
2. Place `<Annotator>` on a page with a working set: the texts of one document
   (`routes/documents/[id]`), or of the documents of a basket, which makes propagation across them
   meaningful.
3. The `/api/v1/[...path]` server route already forwards GET and POST, so the routes need no change.
4. Later: move the strings into `src/lib/i18n`, and use the generated types for `Text`.

### 9.3 ddp_etl and ddp_lib

- The fixes of section 3.3 belong in `ddp_etl/cei/text.py`; ANNIE re-anchors after them.
- Should annotations ever be stored on the server, `ddp_lib.names` already names charter-level layer
  files: `CH.ner_annie.pred.json` for machine output and `CH.ner_<schema>.<campaign>.gt.json` for
  ground truth; `ddp_etl/layers.py` lists them as layers of a document.

## 10. Known limits and risks

- Offsets: Python counts code points, JavaScript counts UTF-16 code units. A character outside the
  Basic Multilingual Plane before a span shifts the offsets the server returns. MUFI characters are in
  the BMP; others are rare in the corpus but not measured.
- `localStorage` holds about 5 MB per origin; a large working set or pool of long tenors can reach it, and
  clearing the browser's data loses all annotations. There is no annotation export yet.
- A text of 200,000 characters is sent whole with every propagation and suggestion, and the session
  memory sends every annotated text of the working set.
- The desktop application's Claude provider sends `temperature`, which the Messages API rejects since
  2026-10-21; it fails until fixed there.
- The web interface is tested in jsdom, not yet in a real browser.

## 11. Development and tests

```
uv sync && uv run pytest                     # Python: desktop characterization, core parity, routes
DDP_BROWSE_FILE=../ddp_etl/fsdb-builds/sample-store/browse.sqlite uv run uvicorn annie_api.dev:app
cd web && npm install && npm test && npm run check && npm run dev
```

- `annie_api.dev` stands in for `ddp_api`: the ANNIE routes plus `GET /api/v1/documents` (documents
  with a text) and `GET /api/v1/documents/{id}` from a browse file. The demo page forwards `/api/v1`
  to it on port 8000.
- Characterization tests (`tests/test_*` except `test_core_*` and `test_api`) pin the desktop app,
  quirks included (`test_quirk_*`); golden files in `tests/golden/` (`UPDATE_GOLDEN=1` rewrites).
  `test_corpus` runs over `example_data/` when present.
- Parity tests (`tests/test_core_*`) run the desktop code and `annie_core` on the same charter texts
  and compare entities, retrieval ranking and prompt.
- Web tests (`web/src/tests/`): spans, dictionary, store, and the mounted `Annotator` in jsdom.
- `tests/fixtures/cei_real/` (not committed): 33 real charters stratified by the profile, for future
  tests.
- Code, commits and changelog follow `CONVENTIONS.md` of the Didip-eu home repository.

## 12. Open questions

- Export and import of the stored annotations (JSON), so that work survives a browser and can be shared.
- Training data export from the web version, and whether Hugging Face models come back as a service.
- Server-side storage as FSDB layer files (section 9.3), and with it users and campaigns.
- Where in `ddp_web` the annotator lives, and whether baskets are its working sets.
- Keyboard shortcuts for tags, as in the desktop application.
- Diplomatic parts as pre-annotations once `ddp_etl` reads them.
