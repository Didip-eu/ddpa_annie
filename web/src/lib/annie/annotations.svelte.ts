/** The annotations of the texts a user works on, the tag schema, the settings and the propagation pool, kept in the browser's localStorage. */
import { overlaps, reanchor } from './spans';
import type { Entity, Relation, Schema, Settings, Source, Span, Text, TextAnnotations } from './types';

export const DEFAULT_SCHEMA: Schema = {
	layers: {
		'CORE Layer': ['PER', 'LOC', 'INS', 'DAT', 'TIM'],
		'ANALYTICAL Layer': ['TITLE', 'REL', 'TAX', 'MEA', 'COM', 'EST', 'MON', 'NUM', 'LEG', 'NAT'],
		'SPAN Layer': ['ACTOR', 'PROP', 'TRANS']
	},
	relations: ['spouse_of', 'works_at', 'located_in', 'born_on', 'produces']
};
const DEFAULT_SETTINGS: Settings = { selection: 'word', allowOverlap: true, provider: 'anthropic', model: '', exampleCount: 3 };
// The tag a mention of the platform's source data becomes when accepted, by the mention's kind.
export const MENTION_TAGS: Record<string, string> = { person: 'PER', location: 'LOC', group: 'INS' };

const empty = (text: Text): TextAnnotations => ({ hash: text.hash, entities: [], relations: [] });

/** The relations whose head and tail are both groups of the entities. */
const connected = (relations: Relation[], entities: Entity[]) => {
	const groups = new Set(entities.map((entity) => entity.group));
	return relations.filter((relation) => groups.has(relation.head) && groups.has(relation.tail));
};

export class AnnieStore {
	schema = $state<Schema>(structuredClone(DEFAULT_SCHEMA));
	settings = $state<Settings>({ ...DEFAULT_SETTINGS });
	texts = $state<Record<string, TextAnnotations>>({});
	pool = $state<Text[]>([]);
	tags = $derived(Object.values(this.schema.layers).flat());

	constructor(private storage: Storage = localStorage, private key = 'annie') {
		const stored = storage.getItem(key);
		if (!stored) return;
		const { schema, settings, texts, pool } = JSON.parse(stored);
		this.schema = schema;
		this.settings = { ...DEFAULT_SETTINGS, ...settings };
		this.texts = texts;
		this.pool = pool ?? [];
	}

	private save() {
		this.storage.setItem(this.key, JSON.stringify({ schema: this.schema, settings: this.settings, texts: this.texts, pool: this.pool }));
	}

	/** The annotations of a text, moved onto its body when the body changed since; returns the entities that could not be moved. */
	open(text: Text): Entity[] {
		const stored = this.texts[text.id];
		if (!stored) {
			this.texts[text.id] = empty(text);
			this.save();
			return [];
		}
		if (stored.hash === text.hash) return [];
		const { kept, lost } = reanchor(text.body, stored.entities);
		this.texts[text.id] = { hash: text.hash, entities: kept, relations: connected(stored.relations, kept) };
		this.save();
		return lost;
	}

	entities(text: Text): Entity[] {
		return this.texts[text.id]?.entities ?? [];
	}

	relations(text: Text): Relation[] {
		return this.texts[text.id]?.relations ?? [];
	}

	/** Adds one entity; returns why it was not added, or null. */
	add(text: Text, start: number, end: number, tag: string, source: Source = 'manual'): string | null {
		const entities = (this.texts[text.id] ??= empty(text)).entities;
		if (entities.some((entity) => entity.start === start && entity.end === end && entity.tag === tag)) return 'This exact annotation already exists.';
		if (!this.settings.allowOverlap && overlaps(start, end, entities)) return 'The annotation overlaps an existing one.';
		const id = crypto.randomUUID();
		entities.push({ id, group: id, start, end, tag, text: text.body.slice(start, end), source });
		entities.sort((a, b) => a.start - b.start || a.end - b.end);
		this.save();
		return null;
	}

	/** Adds the spans the server found, which it already checked against the text's entities. */
	addSpans(text: Text, spans: Span[], source: Source) {
		const annotations = (this.texts[text.id] ??= empty(text));
		for (const span of spans) {
			const id = crypto.randomUUID();
			annotations.entities.push({ id, group: id, start: span.start, end: span.end, tag: span.tag, text: text.body.slice(span.start, span.end), source });
		}
		annotations.entities.sort((a, b) => a.start - b.start || a.end - b.end);
		this.save();
	}

	/** Turns the platform's own mentions of the text into entities, those of a kind without a tag left out. */
	acceptMentions(text: Text): number {
		const before = this.entities(text).length;
		for (const mention of text.mentions) {
			const tag = MENTION_TAGS[mention.kind];
			if (tag && mention.start !== null && mention.end !== null) this.add(text, mention.start, mention.end, tag, 'mention');
		}
		return this.entities(text).length - before;
	}

	/** Removes entities and the relations that lose their head or tail. */
	remove(text: Text, ids: string[]) {
		const annotations = this.texts[text.id];
		annotations.entities = annotations.entities.filter((entity) => !ids.includes(entity.id));
		annotations.relations = connected(annotations.relations, annotations.entities);
		this.save();
	}

	/** Merges entities into the group of the first by position, their relations with them; duplicates collapse. */
	merge(text: Text, ids: string[]) {
		const annotations = this.texts[text.id];
		const merged = annotations.entities.filter((entity) => ids.includes(entity.id));
		if (merged.length < 2) return;
		const canonical = merged[0].group;
		const groups = new Set(merged.map((entity) => entity.group));
		for (const entity of merged) entity.group = canonical;
		const relations = new Map<string, Relation>();
		for (const relation of annotations.relations) {
			if (groups.has(relation.head)) relation.head = canonical;
			if (groups.has(relation.tail)) relation.tail = canonical;
			relations.set(`${relation.head}|${relation.type}|${relation.tail}`, relation);
		}
		annotations.relations = [...relations.values()];
		this.save();
	}

	/** Takes one entity out of the group it shares with others; the group's relations stay with the others. */
	demerge(text: Text, id: string) {
		const entities = this.texts[text.id].entities;
		const entity = entities.find((candidate) => candidate.id === id);
		if (!entity || !entities.some((other) => other !== entity && other.group === entity.group)) return;
		entity.group = crypto.randomUUID();
		this.save();
	}

	addRelation(text: Text, head: string, tail: string, type: string) {
		const relations = this.texts[text.id].relations;
		if (relations.some((relation) => relation.head === head && relation.tail === tail && relation.type === type)) return;
		relations.push({ id: crypto.randomUUID(), type, head, tail });
		this.save();
	}

	flipRelation(text: Text, id: string) {
		const relation = this.texts[text.id].relations.find((candidate) => candidate.id === id);
		if (!relation) return;
		[relation.head, relation.tail] = [relation.tail, relation.head];
		this.save();
	}

	removeRelation(text: Text, id: string) {
		this.texts[text.id].relations = this.texts[text.id].relations.filter((relation) => relation.id !== id);
		this.save();
	}

	addTag(layer: string, tag: string) {
		if (this.tags.includes(tag)) return;
		(this.schema.layers[layer] ??= []).push(tag);
		this.save();
	}

	addRelationType(type: string) {
		if (this.schema.relations.includes(type)) return;
		this.schema.relations.push(type);
		this.save();
	}

	setSettings(settings: Partial<Settings>) {
		Object.assign(this.settings, settings);
		this.save();
	}

	/** Replaces the texts of other documents that propagation reaches besides the working set. */
	setPool(pool: Text[]) {
		this.pool = pool;
		this.save();
	}

	/** Every entity of every stored text. */
	allEntities(): Entity[] {
		return Object.values(this.texts).flatMap((annotations) => annotations.entities);
	}
}
