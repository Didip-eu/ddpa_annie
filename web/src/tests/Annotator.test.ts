// @vitest-environment jsdom
import { flushSync, mount, unmount } from 'svelte';
import { SvelteMap } from 'svelte/reactivity';
import { afterEach, describe, expect, it } from 'vitest';
import { AnnieStore } from '$lib/annotations.svelte';
import type { AnnieApi } from '$lib/api';
import Annotator from '$lib/Annotator.svelte';
import type { Text } from '$lib/types';

class MemoryStorage {
	items = new Map<string, string>();
	getItem = (key: string) => this.items.get(key) ?? null;
	setItem = (key: string, value: string) => void this.items.set(key, value);
}

const FIRST: Text = { id: 'a:abstract', kind: 'abstract', language: 'de', hash: 'h', mentions: [],
	body: 'Artolff von Lewbnegk übergibt der Liebfrauenkirche zu Gmünd ein Gut.' };
const SECOND: Text = { id: 'b:abstract', kind: 'abstract', language: 'de', hash: 'h', mentions: [], body: 'Bürger zu Gmünd.' };

const fakeApi = (calls: unknown[]): AnnieApi => ({
	providers: async () => [{ id: 'anthropic', default_model: 'claude-opus-5-5', configured: true }],
	propagate: async (texts, terms) => {
		calls.push({ texts: texts.map((item) => item.text.id), terms });
		return new Map([['b:abstract', [{ start: 10, end: 15, tag: 'LOC', text: 'Gmünd' }]]]);
	},
	suggest: async () => []
});

let component: ReturnType<typeof mount> | undefined;
afterEach(() => component && unmount(component));

function render(calls: unknown[] = [], texts: () => Text[] = () => [FIRST, SECOND]) {
	const store = new AnnieStore(new MemoryStorage() as unknown as Storage);
	component = mount(Annotator, { target: document.body, props: { get texts() { return texts(); }, api: fakeApi(calls), store } });
	flushSync();
	return store;
}

/** Selects characters start..end of the rendered body as a user would with the mouse. */
function selectText(start: number, end: number) {
	const container = document.querySelector('.text')!;
	const node = container.firstElementChild!.firstChild!;
	const range = document.createRange();
	range.setStart(node, start);
	range.setEnd(node, end);
	window.getSelection()!.removeAllRanges();
	window.getSelection()!.addRange(range);
	container.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
	flushSync();
}

const button = (label: string) => [...document.querySelectorAll('button')].find((candidate) => candidate.textContent?.trim() === label)!;

describe('Annotator', () => {
	it('annotates a selection with the tag picked after it, widened to whole words', () => {
		const store = render();
		selectText(2, 10);
		button('PER').click();
		flushSync();
		expect(store.entities(FIRST).map((entity) => [entity.text, entity.tag])).toEqual([['Artolff von', 'PER']]);
		expect(document.querySelector('.entity')!.textContent).toBe('Artolff von');
	});

	it('propagates the entities of the current text to its document and the documents of the pool', async () => {
		const calls: unknown[] = [];
		const shown = new SvelteMap([['texts', [SECOND]]]);
		const store = render(calls, () => shown.get('texts')!);
		button('Add this document to the propagation pool').click();
		flushSync();
		expect(button('Remove this document from the propagation pool')).toBeDefined();
		shown.set('texts', [FIRST]);
		flushSync();
		const start = FIRST.body.indexOf('Gmünd');
		selectText(start, start + 5);
		button('LOC').click();
		const scope = document.querySelector<HTMLSelectElement>('[aria-label="Scope"]')!;
		scope.value = 'all';
		scope.dispatchEvent(new Event('change'));
		flushSync();
		button("Propagate this text's entities").click();
		await new Promise((resolve) => setTimeout(resolve));
		flushSync();
		expect(calls).toEqual([{ texts: ['a:abstract', 'b:abstract'], terms: { 'Gmünd': 'LOC' } }]);
		expect(store.entities(SECOND)).toMatchObject([{ text: 'Gmünd', tag: 'LOC', source: 'propagation' }]);
		expect(document.querySelector('[role="status"]')!.textContent).toBe('Propagation added 1 entities to 2 texts.');
	});
});
