/** Offsets in a text body: snapping a selection, segments to render overlapping entities, re-anchoring after the body changed. */
import type { Entity } from './types';

// Tk's text widget, whose behaviour users of the desktop app know: a word is a run of letters, digits and
// underscores, any other character is a word of its own.
const WORD_CHARACTER = /[\p{L}\p{N}_]/u;

const isWord = (character: string | undefined) => character !== undefined && WORD_CHARACTER.test(character);

/** The span to annotate for a selection: widened to whole words in word mode, without surrounding whitespace; null when empty. */
export function snap(body: string, start: number, end: number, mode: 'word' | 'char'): [number, number] | null {
	if (mode === 'word' && end > start) {
		if (isWord(body[start])) while (start > 0 && isWord(body[start - 1])) start--;
		if (isWord(body[end - 1])) while (end < body.length && isWord(body[end])) end++;
	}
	while (start < end && /\s/.test(body[start])) start++;
	while (end > start && /\s/.test(body[end - 1])) end--;
	return end > start ? [start, end] : null;
}

/** True when the span shares at least one character with one of the entities. */
export function overlaps(start: number, end: number, entities: Entity[]): boolean {
	return entities.some((entity) => start < entity.end && entity.start < end);
}

export type Segment = { start: number; end: number; entities: Entity[] };

/** The body cut at every entity boundary, each piece with the entities that cover it, shortest first. */
export function segments(body: string, entities: Entity[]): Segment[] {
	const cuts = [...new Set([0, body.length, ...entities.flatMap((entity) => [entity.start, entity.end])])].sort((a, b) => a - b);
	return cuts.slice(0, -1).map((start, position) => {
		const end = cuts[position + 1];
		const covering = entities.filter((entity) => entity.start <= start && end <= entity.end);
		return { start, end, entities: covering.sort((a, b) => a.end - a.start - (b.end - b.start)) };
	});
}

const nearest = (body: string, text: string, around: number): number => {
	let best = -1;
	for (let found = body.indexOf(text); found !== -1; found = body.indexOf(text, found + 1)) {
		if (best === -1 || Math.abs(found - around) < Math.abs(best - around)) best = found;
	}
	return best;
};

/** The entities moved onto a changed body, each to the occurrence of its text nearest its old start; those whose text is gone are lost. */
export function reanchor(body: string, entities: Entity[]): { kept: Entity[]; lost: Entity[] } {
	const kept: Entity[] = [];
	const lost: Entity[] = [];
	for (const entity of entities) {
		if (body.slice(entity.start, entity.end) === entity.text) {
			kept.push(entity);
			continue;
		}
		const start = nearest(body, entity.text, entity.start);
		if (start === -1) lost.push(entity);
		else kept.push({ ...entity, start, end: start + entity.text.length });
	}
	return { kept, lost };
}
