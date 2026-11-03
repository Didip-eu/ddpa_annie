/** The shapes ANNIE works with: a text of a ddp_api document, its entities and relations, the tag schema. */

/** A text as ddp_api's Document serves it: body, content hash and the mentions the source already marks. */
export type Text = {
	id: string;
	kind: string;
	language: string | null;
	body: string;
	hash: string;
	mentions: { kind: string; surface: string; start: number | null; end: number | null }[];
};

export type Source = 'manual' | 'mention' | 'propagation' | 'dictionary' | 'memory' | 'llm';

/** A tagged span of a text body; mentions merged into one entity share a group. */
export type Entity = { id: string; group: string; start: number; end: number; tag: string; text: string; source: Source };

/** A directed relation between two entity groups. */
export type Relation = { id: string; type: string; head: string; tail: string };

/** The annotations of one text, with the hash of the body they were made on. */
export type TextAnnotations = { hash: string; entities: Entity[]; relations: Relation[] };

export type Schema = { layers: Record<string, string[]>; relations: string[] };

export type Settings = {
	selection: 'word' | 'char';
	allowOverlap: boolean;
	provider: string;
	model: string;
	exampleCount: number;
};

export type Span = { start: number; end: number; tag: string; text: string };
