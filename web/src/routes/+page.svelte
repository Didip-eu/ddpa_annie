<!-- The development page: pick documents of the development API as a working set and annotate their texts. -->
<script lang="ts">
	import { onMount } from 'svelte';
	import { Annotator, type Text } from '$lib';

	const WORKING_SET = 'annie-demo-documents';
	let listed = $state<{ id: string; identifier: string | null }[]>([]);
	const saved: string[] = JSON.parse(localStorage.getItem(WORKING_SET) ?? '[]');
	let chosen = $state(saved);
	let texts = $state<Text[]>([]);
	let error = $state('');

	async function json<T>(path: string): Promise<T> {
		const response = await fetch(`/api/v1/${path}`);
		if (!response.ok) throw new Error(`${path}: ${response.status}`);
		return response.json();
	}

	async function load() {
		localStorage.setItem(WORKING_SET, JSON.stringify(chosen));
		const documents = await Promise.all(chosen.map((id) => json<{ texts: Text[] }>(`documents/${id}`)));
		texts = documents.flatMap((document) => document.texts);
	}

	onMount(() => {
		json<typeof listed>('documents?limit=200')
			.then((documents) => (listed = documents))
			.then(load)
			.catch((failure) => (error = `${failure.message}. Is the development API running (see README)?`));
	});
</script>

<svelte:head><title>ANNIE</title></svelte:head>

<details open={!saved.length}>
	<summary>Working set: {chosen.length} documents, {texts.length} texts</summary>
	{#if error}<p role="alert">{error}</p>{/if}
	<select multiple size="12" bind:value={chosen} aria-label="Documents">
		{#each listed as document (document.id)}<option value={document.id}>{document.identifier ?? document.id}</option>{/each}
	</select>
	<button onclick={load}>Load</button>
</details>

<Annotator {texts} />

<style>
	:global(body) {
		margin: 1rem;
		background: #fdfdfb;
	}
	select {
		min-width: 20rem;
	}
</style>
