<!-- The development page: pick a document of the development API and annotate its texts. -->
<script lang="ts">
	import { onMount } from 'svelte';
	import Annotator from '$lib/components/annie/Annotator.svelte';
	import type { Text } from '$lib/annie/types';

	const CURRENT_DOCUMENT = 'annie-demo-document';
	let listed = $state<{ id: string; identifier: string | null }[]>([]);
	let currentId = $state(localStorage.getItem(CURRENT_DOCUMENT));
	let texts = $state<Text[]>([]);
	let error = $state('');

	async function json<T>(path: string): Promise<T> {
		const response = await fetch(`/api/v1/${path}`);
		if (!response.ok) throw new Error(`${path}: ${response.status}`);
		return response.json();
	}

	async function open(id: string) {
		currentId = id;
		localStorage.setItem(CURRENT_DOCUMENT, id);
		const document = await json<{ texts: Text[] }>(`documents/${id}`);
		// a document clicked while this one loaded wins
		if (id === currentId) texts = document.texts;
	}

	onMount(() => {
		json<typeof listed>('documents?limit=200')
			.then((documents) => {
				listed = documents;
				return open(currentId ?? documents[0].id);
			})
			.catch((failure) => (error = `${failure.message}. Is the development API running (see README)?`));
	});
</script>

<svelte:head><title>ANNIE</title></svelte:head>

<div class="page">
	<nav aria-label="Documents">
		<h3>Documents ({listed.length})</h3>
		{#if error}<p role="alert">{error}</p>{/if}
		<ul>
			{#each listed as document (document.id)}
				<li>
					<button class:current={document.id === currentId} onclick={() => open(document.id)}>
						{document.id.slice(0, 8)} <span class="note">{document.identifier}</span>
					</button>
				</li>
			{/each}
		</ul>
	</nav>

	<Annotator {texts} />
</div>

<style>
	:global(body) {
		margin: 1rem;
		background: #fdfdfb;
	}
	.page {
		display: grid;
		grid-template-columns: 12rem minmax(0, 1fr);
		gap: var(--space-5, 1.5rem);
		font-family: var(--font-ui, system-ui, sans-serif);
		font-size: var(--text-ui, 0.9375rem);
		color: var(--color-text, #1d1d1b);
	}
	h3 {
		font-size: var(--text-ui, 0.9375rem);
		margin: var(--space-3, 0.75rem) 0 0;
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
	.note {
		color: var(--color-muted, #5f5f5a);
		font-size: var(--text-xs, 0.8125rem);
	}
	@media (max-width: 64rem) {
		.page {
			grid-template-columns: 1fr;
		}
	}
</style>
