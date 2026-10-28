import { beforeEach, describe, expect, it } from 'vitest';
import { AnnieStore } from '$lib/annie/annotations.svelte';
import type { Text } from '$lib/annie/types';

class MemoryStorage {
	items = new Map<string, string>();
	getItem = (key: string) => this.items.get(key) ?? null;
	setItem = (key: string, value: string) => void this.items.set(key, value);
}

const BODY = 'Artolff von Lewbnegk übergibt der Liebfrauenkirche zu Gmünd ein Gut.';
const text = (body = BODY, hash = 'h1'): Text => ({
	id: 'doc:abstract', kind: 'abstract', language: null, body, hash,
	mentions: [
		{ kind: 'person', surface: 'Artolff von Lewbnegk', start: 0, end: 20 },
		{ kind: 'concept', surface: 'Gut', start: 64, end: 67 },
		{ kind: 'location', surface: 'Gmünd', start: null, end: null }
	]
});
const GMUEND = BODY.indexOf('Gmünd');
const INS = BODY.indexOf('Liebfrauenkirche');

let storage: MemoryStorage;
let store: AnnieStore;
beforeEach(() => {
	storage = new MemoryStorage();
	store = new AnnieStore(storage as unknown as Storage);
});

describe('AnnieStore', () => {
	it('keeps annotations and the pool across instances', () => {
		store.open(text());
		store.add(text(), 0, 20, 'PER');
		store.setPool([text()]);
		const reopened = new AnnieStore(storage as unknown as Storage);
		expect(reopened.entities(text()).map((e) => [e.text, e.tag])).toEqual([['Artolff von Lewbnegk', 'PER']]);
		expect(reopened.pool).toEqual([text()]);
	});

	it('rejects an exact duplicate and, when set, an overlap', () => {
		store.add(text(), GMUEND, GMUEND + 5, 'LOC');
		expect(store.add(text(), GMUEND, GMUEND + 5, 'LOC')).toMatch(/already exists/);
		expect(store.add(text(), INS, GMUEND + 5, 'INS')).toBeNull();
		store.setSettings({ allowOverlap: false });
		expect(store.add(text(), GMUEND - 3, GMUEND + 5, 'LOC')).toMatch(/overlaps/);
	});

	it('accepts the mentions of kinds that have a tag and a span', () => {
		expect(store.acceptMentions(text())).toBe(1);
		expect(store.entities(text())[0]).toMatchObject({ tag: 'PER', source: 'mention', text: 'Artolff von Lewbnegk' });
	});

	it('merges into the first group, collapsing duplicate relations, and demerges', () => {
		store.add(text(), 0, 7, 'PER');
		store.add(text(), 12, 20, 'PER');
		store.add(text(), GMUEND, GMUEND + 5, 'LOC');
		const [first, second, place] = store.entities(text());
		store.addRelation(text(), first.group, place.group, 'located_in');
		store.addRelation(text(), second.group, place.group, 'located_in');
		store.merge(text(), [second.id, first.id]);
		expect(second.group).toBe(first.group);
		expect(store.relations(text())).toHaveLength(1);
		store.demerge(text(), first.id);
		expect(first.group).not.toBe(second.group);
		expect(store.relations(text())[0].head).toBe(second.group);
		const lone = place.group;
		store.demerge(text(), place.id);
		expect(place.group).toBe(lone);
	});

	it('removes relations that lose an end', () => {
		store.add(text(), 0, 7, 'PER');
		store.add(text(), GMUEND, GMUEND + 5, 'LOC');
		const [person, place] = store.entities(text());
		store.addRelation(text(), person.group, place.group, 'located_in');
		store.flipRelation(text(), store.relations(text())[0].id);
		expect(store.relations(text())[0]).toMatchObject({ head: place.group, tail: person.group });
		store.remove(text(), [place.id]);
		expect(store.relations(text())).toEqual([]);
	});

	it('moves annotations onto a changed body and reports what is lost', () => {
		store.open(text());
		store.add(text(), GMUEND, GMUEND + 5, 'LOC');
		store.add(text(), 0, 7, 'PER');
		const changed = text(`Ein Regest: ${BODY.replace('Artolff', 'Artolf')}`, 'h2');
		const lost = store.open(changed);
		expect(lost.map((e) => e.text)).toEqual(['Artolff']);
		expect(store.entities(changed).map((e) => changed.body.slice(e.start, e.end))).toEqual(['Gmünd']);
		expect(store.texts['doc:abstract'].hash).toBe('h2');
	});

	it('adds tags and relation types once', () => {
		store.addTag('Custom', 'ARCH');
		store.addTag('Custom', 'ARCH');
		store.addTag('Custom', 'PER');
		store.addRelationType('witness_of');
		expect(store.schema.layers.Custom).toEqual(['ARCH']);
		expect(store.tags).toContain('ARCH');
		expect(store.schema.relations.at(-1)).toBe('witness_of');
	});
});
