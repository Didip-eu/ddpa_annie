<!-- ANNIE in the browser: annotate the texts of a working set with entities and relations, propagate them, pre-annotate with a language model. -->
<script lang="ts">
	import { onMount, untrack } from 'svelte';
	import { AnnieStore } from './annotations.svelte';
	import { annieApi, type AnnieApi, type Provider } from './api';
	import { readDictionary, writeDictionary } from './dictionary';
	import EntityPanel from './EntityPanel.svelte';
	import { snap } from './spans';
	import TextView from './TextView.svelte';
	import type { Text } from './types';

	type Props = { texts: Text[]; api?: AnnieApi; store?: AnnieStore };
	let { texts, api = annieApi(), store = new AnnieStore() }: Props = $props();

	const PALETTE = ['#ffcccc', '#ccccff', '#ccffcc', '#ffffcc', '#ccffff', '#e6e6fa', '#ffe4e1', '#f0fff0', '#fffacd', '#add8e6',
		'#f5f5dc', '#d3ffd3', '#fafad2', '#ffebcd', '#e0ffff'];
	const color = (tag: string) => PALETTE[Math.max(0, store.tags.indexOf(tag)) % PALETTE.length];

	let currentId = $state<string>();
	const current = $derived(texts.find((text) => text.id === currentId) ?? texts[0]);
	let tag = $state<string>();
	const activeTag = $derived(tag && store.tags.includes(tag) ? tag : store.tags[0]);
	let selected = $state<string[]>([]);
	let pending = $state<[number, number] | null>(null);
	let scope = $state<'text' | 'all'>('all');
	let notice = $state('');
	let busy = $state(false);
	let providers = $state<Provider[]>([]);
	let newTag = $state('');
	let newRelationType = $state('');

	const entities = $derived(current ? store.entities(current) : []);
	const relations = $derived(current ? store.relations(current) : []);
	const mentionCount = $derived(current?.mentions.filter((mention) => mention.start !== null).length ?? 0);

	$effect(() => {
		const text = current;
		if (!text) return;
		untrack(() => {
			const lost = store.open(text);
			selected = [];
			pending = null;
			notice = lost.length ? `The text changed since it was annotated; ${lost.length} entities could not be found again: ${lost.map((entity) => entity.text).join('; ')}` : '';
		});
	});

	onMount(async () => {
		providers = await api.providers().catch(() => []);
	});

	/** Runs an action that calls the server, showing its error instead of its result when it fails. */
	async function run(action: () => Promise<string>) {
		busy = true;
		try {
			notice = await action();
		} catch (error) {
			notice = (error as Error).message;
		} finally {
			busy = false;
		}
	}

	function selectSpan(start: number, end: number) {
		pending = snap(current.body, Math.min(start, end), Math.max(start, end), store.settings.selection);
	}

	function annotate(chosen: string) {
		tag = chosen;
		if (!pending) return;
		notice = store.add(current, pending[0], pending[1], chosen) ?? '';
		pending = null;
	}

	/** Term to tag from the current text's entities; a text annotated twice keeps its later tag, as in the desktop app. */
	const currentTerms = () => Object.fromEntries(entities.map((entity) => [entity.text.trim(), entity.tag]));

	/** Adds what the terms find in the targets; returns how many entities that is. */
	async function propagateTo(targets: Text[], terms: Record<string, string>, allowOverlap: boolean, source: 'propagation' | 'dictionary') {
		const found = await api.propagate(targets.map((text) => ({ text, entities: store.entities(text) })), terms, allowOverlap);
		let added = 0;
		for (const text of targets) {
			const spans = found.get(text.id) ?? [];
			store.addSpans(text, spans, source);
			added += spans.length;
		}
		return added;
	}

	const propagate = () => run(async () => {
		const targets = scope === 'text' ? [current] : texts;
		const added = await propagateTo(targets, currentTerms(), store.settings.allowOverlap, 'propagation');
		return `Propagation added ${added} entities to ${targets.length} texts.`;
	});

	const importDictionary = (event: Event) => run(async () => {
		const input = event.currentTarget as HTMLInputElement;
		const terms = readDictionary(await input.files![0].text());
		input.value = '';
		for (const dictionaryTag of new Set(Object.values(terms))) store.addTag('Dictionary Layer', dictionaryTag);
		// the desktop app lets a dictionary overlap existing entities whatever the setting
		const added = await propagateTo(texts, terms, true, 'dictionary');
		return `The dictionary's ${Object.keys(terms).length} terms added ${added} entities to ${texts.length} texts.`;
	});

	function exportDictionary() {
		const link = document.createElement('a');
		link.href = URL.createObjectURL(new Blob([writeDictionary(store.allEntities())], { type: 'text/plain' }));
		link.download = 'dictionary.txt';
		link.click();
		URL.revokeObjectURL(link.href);
	}

	const suggest = () => run(async () => {
		const examples = texts.filter((text) => text.id !== current.id && store.entities(text).length).map((text) => ({ text, entities: store.entities(text) }));
		const suggestions = await api.suggest(current, entities, examples, store.tags, store.settings);
		store.addSpans(current, suggestions.filter((span) => span.source === 'memory'), 'memory');
		store.addSpans(current, suggestions.filter((span) => span.source === 'llm'), 'llm');
		const fromMemory = suggestions.filter((span) => span.source === 'memory').length;
		return `Added ${fromMemory} entities from the session memory and ${suggestions.length - fromMemory} from the language model.`;
	});
</script>

<div class="annotator">
	<nav aria-label="Texts">
		<h3>Texts ({texts.length})</h3>
		<ul>
			{#each texts as text (text.id)}
				<li>
					<button class:current={text.id === current?.id} onclick={() => (currentId = text.id)}>
						{text.id.split(':')[0].slice(0, 8)} <span class="note">{text.kind} · {store.entities(text).length}</span>
					</button>
				</li>
			{/each}
		</ul>
	</nav>

	<main>
		{#if current}
			<div class="tags" role="toolbar" aria-label="Tags">
				{#each Object.entries(store.schema.layers) as [layer, layerTags] (layer)}
					<div class="layer">
						<span class="note">{layer}</span>
						{#each layerTags as layerTag (layerTag)}
							<button class:active={layerTag === activeTag} style:background={color(layerTag)} onclick={() => annotate(layerTag)}>{layerTag}</button>
						{/each}
					</div>
				{/each}
			</div>
			<p class="note">Select text, then pick its tag. {#if pending}Selected: “{current.body.slice(...pending)}” <button onclick={() => (pending = null)}>Cancel</button>{/if}</p>
			<TextView body={current.body} language={current.language} {entities} {selected} {pending} {color} onselect={selectSpan}
				onpick={(entity, additive) => (selected = additive ? [...new Set([...selected, entity.id])] : [entity.id])} />
			{#if notice}<p class="notice" role="status">{notice}</p>{/if}
		{:else}
			<p>No text to annotate.</p>
		{/if}
	</main>

	{#if current}
		<aside>
			<section class="actions">
				<h3>Propagate</h3>
				<select bind:value={scope} aria-label="Scope">
					<option value="all">to all texts</option>
					<option value="text">within this text</option>
				</select>
				<button disabled={busy || !entities.length} onclick={propagate}>Propagate this text's entities</button>
				{#if mentionCount}<button onclick={() => (notice = `Accepted ${store.acceptMentions(current)} mentions of the source.`)}>Accept the source's {mentionCount} mentions</button>{/if}

				<h3>Dictionary</h3>
				<label class="file">Import and propagate <input type="file" accept=".txt,.tsv,text/plain" disabled={busy} onchange={importDictionary} /></label>
				<button onclick={exportDictionary}>Export all entities as a dictionary</button>

				<h3>Language model</h3>
				<select value={store.settings.provider} onchange={(event) => store.setSettings({ provider: event.currentTarget.value, model: '' })} aria-label="Provider">
					{#each providers as provider (provider.id)}
						<option value={provider.id} disabled={!provider.configured}>{provider.id}{provider.configured ? '' : ' (no key)'}</option>
					{/each}
				</select>
				<input value={store.settings.model} placeholder={providers.find((provider) => provider.id === store.settings.provider)?.default_model ?? 'model'}
					onchange={(event) => store.setSettings({ model: event.currentTarget.value })} aria-label="Model" />
				<label>Examples <input type="number" min="0" max="20" value={store.settings.exampleCount}
					onchange={(event) => store.setSettings({ exampleCount: Number(event.currentTarget.value) })} /></label>
				<button disabled={busy} onclick={suggest}>Pre-annotate this text</button>
			</section>

			<EntityPanel {entities} {relations} relationTypes={store.schema.relations} bind:selected {color}
				onremove={(ids) => store.remove(current, ids)}
				onmerge={(ids) => store.merge(current, ids)}
				ondemerge={(id) => store.demerge(current, id)}
				onrelate={(head, tail, type) => store.addRelation(current, head, tail, type)}
				onflip={(id) => store.flipRelation(current, id)}
				onunrelate={(id) => store.removeRelation(current, id)} />

			<section class="actions">
				<h3>Settings</h3>
				<label><input type="checkbox" checked={store.settings.selection === 'word'}
					onchange={(event) => store.setSettings({ selection: event.currentTarget.checked ? 'word' : 'char' })} /> Extend a selection to whole words</label>
				<label><input type="checkbox" checked={store.settings.allowOverlap}
					onchange={(event) => store.setSettings({ allowOverlap: event.currentTarget.checked })} /> Allow overlapping entities</label>
				<form onsubmit={(event) => { event.preventDefault(); store.addTag('Custom Layer', newTag.trim()); newTag = ''; }}>
					<input bind:value={newTag} placeholder="New tag" required aria-label="New tag" /> <button>Add tag</button>
				</form>
				<form onsubmit={(event) => { event.preventDefault(); store.addRelationType(newRelationType.trim()); newRelationType = ''; }}>
					<input bind:value={newRelationType} placeholder="New relation type" required aria-label="New relation type" /> <button>Add relation type</button>
				</form>
			</section>
		</aside>
	{/if}
</div>

<style>
	.annotator {
		display: grid;
		grid-template-columns: 12rem minmax(0, 1fr) 22rem;
		gap: var(--space-5, 1.5rem);
		font-family: var(--font-ui, system-ui, sans-serif);
		font-size: var(--text-ui, 0.9375rem);
		color: var(--color-text, #1d1d1b);
	}
	nav ul {
		list-style: none;
		margin: 0;
		padding: 0;
		max-height: 80vh;
		overflow-y: auto;
	}
	nav button {
		width: 100%;
		text-align: left;
		background: none;
		border: 0;
		padding: var(--space-1, 0.25rem);
		cursor: pointer;
		color: inherit;
		font-family: ui-monospace, monospace;
	}
	nav button.current {
		background: var(--color-accent-surface, #f3e3dc);
	}
	.tags {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-3, 0.75rem);
		margin-bottom: var(--space-3, 0.75rem);
	}
	.layer {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-1, 0.25rem);
		align-items: center;
	}
	.tags button {
		color: #1d1d1b;
		border: 1px solid var(--color-border, #dddbd3);
		border-radius: var(--radius, 2px);
		cursor: pointer;
	}
	.tags button.active {
		outline: 2px solid var(--color-accent, #7a2e1f);
	}
	.actions {
		display: flex;
		flex-direction: column;
		gap: var(--space-2, 0.5rem);
	}
	h3 {
		font-size: var(--text-ui, 0.9375rem);
		margin: var(--space-3, 0.75rem) 0 0;
	}
	.note {
		color: var(--color-muted, #5f5f5a);
		font-size: var(--text-xs, 0.8125rem);
	}
	.notice {
		padding: var(--space-2, 0.5rem);
		background: var(--color-absent-surface, #faf2dc);
		color: var(--color-absent, #75591a);
	}
	@media (max-width: 64rem) {
		.annotator {
			grid-template-columns: 1fr;
		}
	}
</style>
