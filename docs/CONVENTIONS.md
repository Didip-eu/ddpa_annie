# Code

- No emojis anywhere in code or config files.
- ASCII in code, comments, config and repository text: `...`, `->`, straight quotes, a plain hyphen. Another character stands only where the content is that character: a name, a quoted source, text shown to a reader.
- No file-header comments unless required by a license; in TypeScript and Svelte a module may open with what it is.
- Keep inline comments rare. A comment states what the code cannot; everything else goes into the name. A review note goes into the pull request or an issue, not into the code.
- Names are words: `doc`, `row`, `response`, `position`, not `d`, `r`, `neigh`. No one-letter names outside an index or a comprehension. A parameter is named for what it means at the call site. A loop pair reads as a phrase: `for position, doc in enumerate(docs)`.
- Every public function has a one-line docstring that says what it does, not how. A docstring never states what other code or data guarantees; such claims drift.
- A block that can carry a name and a one-line docstring becomes a function: a closure, a chain of `if ...: continue` filters, a repeated comprehension, a nested conditional expression.
- Early returns over nested conditionals. Compute a value once and name it.
- Fail loudly: catch the exceptions the code expects, never everything; no silent skip. A tool that deliberately keeps going after an error says so and reports at the end.
- Strings a person reads (messages, prompts, keys) use the same plain language as the docs; a key names what the value is.
- KISS: the simplest design that meets the requirement wins.
- DRY: factor on the third occurrence, not the second.
- Follow idiomatic patterns for the language and tool in use.
- Prefer local helpers and existing package boundaries over new abstractions. What several repositories need lives once, in ddp_lib (the FSDB folder rule and walk, file names, the layout record, the page image, Monasterium identifiers).
- Speed and efficiency first: the fast version wins when it stays readable.
- Every line we do not ship is a line we do not maintain. Little redundancy, ideally none, but not at every cost: the aim is a code and doc base that stays small. Before adding, ask whether something already does this; before keeping, ask who will read it.

# Python

- Use a `.venv`, preferably using uv. Python 3.12 or later.
- Current syntax (`match`, unions with `|`) is welcome where it reads better than the old form.

# TypeScript and Svelte

- A doc comment is one line, `/** ... */`. It says what the thing does or is, never how, and it does not repeat the name, the types or the body.
- It stands on every exported function of a module that other modules call, and a module or a component may open with one or two lines that say what it is. A private helper gets a name and no comment.
- An inline comment states a fact the code cannot: a spec, a constant, what the caller must guarantee. A name is tried first.
- Types are TypeScript's. No `@param`, no `@returns`, no types in prose.

# Running and checking

- Prefer standard project commands over one-off shell gymnastics: `npm run lint`, `npm run build`, uv (`uv pip install -r ...` / `make install`) then `python ...` with a named script or module checked into the repo.
- A heredoc (`python <<'PY' ...`) is fine for a one-off, read-only survey. Anything that may be repeated, that matters, or that writes files becomes a script under `scripts/` or a test, and is run by name; ask before running it.
- For HTTP checks, prefer `curl` against a running server, or a small committed script under `scripts/`, rather than embedding request logic only in chat or CI logs.
- A command that writes data supports `--dry-run`, and what it changed goes to a log outside the repository.

# Commits

Messages follow [Conventional Commits 1.0](https://www.conventionalcommits.org/en/v1.0.0/): `type(scope): summary`.

- type: `feat` (a user sees something new), `fix` (a user sees a bug gone), `perf`, `refactor`, `docs`, `test`, `build`, `chore`, `revert`.
- scope: the part of the code base, by its name in the code: a module, a directory, a job, a component (`search`, `proxy`, `images`, `basket`).
- summary: a verb for the action, then the object by its name, then the purpose in a few words where it helps: `add year filter to search`, `replace per-endpoint routes with one /api/v1 catch-all`, `fix 502 body when the API is unreachable`. Lower case, no full stop, at most 72 characters.
- From the subject alone, a reader names the kind of change and where it is.
- body: only for a reason the diff does not show, in one to three lines.
- breaking change: `!` after the scope and a `BREAKING CHANGE:` footer that says what a client must change.
- References: an issue of the same repository (`(#12)`); nothing that points outside the repository.
- A commit is one coherent change: a feature, a fix, a refactor of one thing, a documentation pass over one area. Edits for the same purpose go together across files; edits for different issues or packages are separate commits. Its tests, its changelog line and the files it regenerates go in the same commit.
- A commit that only improves language or legibility is a valid commit on its own.
- A legibility pass: snapshot the outputs of fixed inputs first, one module per commit, wording after names.

# Changelogs and releases

- Versions follow [Semantic Versioning](https://semver.org). Before 1.0, a minor version marks a change a client must follow; a patch marks additions and fixes.
- `CHANGELOG.md` has one line per change a user notices, under `Unreleased` in the commit of the change, grouped as Added, Changed, Fixed, Removed ([Keep a Changelog](https://keepachangelog.com/en/1.1.0/)).
- A release is one commit, `chore(release): 0.3.3`, with the version in the package file and the `Unreleased` lines moved under the new heading, and an annotated tag `v0.3.3` on it.
