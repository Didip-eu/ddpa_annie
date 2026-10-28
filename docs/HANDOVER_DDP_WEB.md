# Handover: the ANNIE annotator into ddp_web

How to move the Svelte part of ANNIE from `ddpa_annie/web/` into `ddp_web`. Checked against `ddp_web`
0.4.5 and `ddpa_annie` on branch `feat/web-annotator`, 2026-10-28. Background: `SPECIFICATION.md`,
sections 7 (API), 8 (component contract) and 9 (integration).

## 1. Before: ddp_api must serve the ANNIE routes

The annotator calls `GET /api/v1/annie/providers`, `POST /api/v1/annie/propagate` and
`POST /api/v1/annie/suggest`. `ddp_api` does not include them yet. Do `SPECIFICATION.md` 9.1 first:

1. Add `ddpa_annie` as a git dependency of `ddp_api`, pinned to a tag, as `ddp-lib` is.
2. `v1.include_router(annie_api.router)` in `ddp_api/app.py`.
3. Regenerate `openapi.json` (`uv run python -m ddp_api.openapi`), then `npm run types` in `ddp_web`.
4. Set the provider keys (`DDP_ANNIE_*_KEY`) in the deployment.

Check: `curl localhost:8000/api/v1/annie/providers` answers `{"data": [...]}`.

## 2. What to copy

| From `ddpa_annie/web/src/` | To `ddp_web/src/` |
|---|---|
| `lib/annie/` (`annotations.svelte.ts`, `api.ts`, `dictionary.ts`, `spans.ts`, `types.ts`) | `lib/annie/` |
| `lib/components/annie/` (`Annotator.svelte`, `EntityPanel.svelte`, `TextView.svelte`) | `lib/components/annie/` |

The components import the modules by relative path (`../../annie/...`), so both folders must land at
these paths.

Do not copy:

- `routes/annotator/`: the development page, it lists the documents of `annie_api.dev`.
- `package.json`, `vite.config.ts`, `tsconfig.json`: `ddp_web` already has what the annotator needs.

## 3. What already fits

- Dependencies: none beyond `svelte`; `svelte`, `@sveltejs/kit`, `vite` and TypeScript are the same
  versions in both. `ddp_web` forces runes mode, which the components use.
- Styles: every token the components use (`--color-*`, `--space-*`, `--text-*`, `--font-*`,
  `--measure`, `--radius`) is defined in `ddp_web/src/app.css`, dark variant included.
- API: `annieApi()` calls `/api/v1/annie/...` with the browser's `fetch`. `ddp_web`'s
  `/api/v1/[...path]` server route forwards GET and POST and passes errors through unchanged.
- Storage: everything is under `localStorage["annie"]`. `ddp_web` uses `ddp-baskets` and
  `ddp-preferences`, so there is no clash.
- Types: ANNIE's `Text` is a subset of the generated `components["schemas"]["Text"]`, so a
  document's `texts` from `document()` can be passed to `<Annotator>` without conversion.

## 4. Putting it on a page

`<Annotator texts={Text[]} />` takes the working set: the texts that propagation "to all" reaches. It
needs `localStorage` when it is created, so its page must not render on the server. A route of its
own with `ssr = false` is the simplest way. The routes below are examples; where the annotator lives
is still open (`SPECIFICATION.md` 12).

One document, `src/routes/documents/[id]/annotate/+page.ts`:

```ts
import { document } from '$lib/api';
import type { PageLoad } from './$types';

// The annotator keeps its data in localStorage, which only the browser has.
export const ssr = false;

export const load: PageLoad = async ({ params, url, fetch }) => ({
	record: await document(params.id, { fetch, origin: url.origin })
});
```

`src/routes/documents/[id]/annotate/+page.svelte`:

```svelte
<script lang="ts">
	import Annotator from '$lib/components/annie/Annotator.svelte';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();
</script>

<Annotator texts={data.record.texts} />
```

The documents of a basket as the working set, which makes propagation across documents useful: load
each item with `document(item.id, ...)` and pass `records.flatMap((record) => record.texts)`. Items
without a text (`hasText === false`) can be skipped before loading. Documents outside the working
set can still be added to the propagation pool inside the annotator.

## 5. Later, to match ddp_web

None of this is needed for it to work.

- Strings are English and inline. Move them into `lib/i18n/locales/en.json` and read them with
  `uiText`.
- Replace ANNIE's `Text` with the generated type, and once the types hold the ANNIE routes, consider
  calling them through `openapi-fetch` as `lib/api` does.
- `ddp_web` writes imports as `$lib/...` with a `.js` extension (`basketStore.svelte.js`); the copied
  files use relative paths without one. Both resolve.

## 6. Tests

`ddp_web` has no test runner. The tests in `ddpa_annie/web/src/tests/` (spans, dictionary, store, and
the mounted `Annotator` in jsdom) already import `$lib/annie/...` and `$lib/components/annie/...`, so
they run unchanged once `ddp_web` has:

- dev dependencies `vitest` and `jsdom`, and a script `"test": "vitest run"`;
- in `vite.config.ts`: `defineConfig` from `vitest/config`,
  `resolve: mode === 'test' ? { conditions: ['browser'] } : {}` (the components mount, so they need
  Svelte's browser build) and `test: { include: ['src/**/*.test.ts'] }`.

## 7. Limits that come along

- Offsets: the server counts code points, the browser UTF-16 units; a character outside the Basic
  Multilingual Plane before a span shifts it (`SPECIFICATION.md` 10).
- `localStorage` holds about 5 MB per origin, now shared with the baskets and preferences; there is
  no export of annotations yet.
- A suggestion from a language model can take tens of seconds; a reverse proxy in the deployment
  with a short read timeout cuts it off.
