import { describe, expect, it } from 'vitest';
import { readDictionary, writeDictionary } from '$lib/dictionary';
import { reanchor, segments, snap } from '$lib/spans';
import type { Entity } from '$lib/types';

const BODY = 'Artolff von Lewbnegk übergibt der Liebfrauenkirche zu Gmünd\nein Gut zu Plesnicz (Leucz Weczenpacher).';
const entity = (start: number, end: number, tag: string, body = BODY): Entity => ({
	id: `${start}-${end}-${tag}`, group: `${start}-${end}-${tag}`, start, end, tag, text: body.slice(start, end), source: 'manual'
});

describe('snap', () => {
	// The cases tests/test_tk_interaction.py pins in the desktop app's Tk text widget.
	it('widens a partial selection to whole words', () => {
		expect(snap(BODY, 2, 10, 'word')).toEqual([0, 11]);
	});
	it('keeps a character selection but strips whitespace', () => {
		const gmuend = BODY.indexOf('Gmünd');
		expect(snap(BODY, gmuend - 1, gmuend + 6, 'char')).toEqual([gmuend, gmuend + 5]);
	});
	it('takes punctuation as a word of its own', () => {
		const start = BODY.indexOf('Leucz');
		expect(BODY.slice(...snap(BODY, start + 1, start + 15, 'word')!)).toBe('Leucz Weczenpacher');
		expect(BODY.slice(...snap(BODY, start - 1, start + 2, 'word')!)).toBe('(Leucz');
	});
	it('counts letters with diacritics as word characters', () => {
		const start = BODY.indexOf('übergibt');
		expect(BODY.slice(...snap(BODY, start + 3, start + 4, 'word')!)).toBe('übergibt');
	});
	it('spans lines', () => {
		const start = BODY.indexOf('Gmünd');
		expect(BODY.slice(...snap(BODY, start, start + 8, 'word')!)).toBe('Gmünd\nein');
	});
	it('is null for whitespace only', () => {
		expect(snap(BODY, 7, 8, 'word')).toBeNull();
	});
});

describe('segments', () => {
	it('cuts at every boundary with the shortest covering entity first', () => {
		const ins = entity(34, 59, 'INS');
		const loc = entity(54, 59, 'LOC');
		const pieces = segments(BODY, [ins, loc]);
		expect(pieces.map((piece) => [piece.start, piece.end, piece.entities.map((e) => e.tag)])).toEqual([
			[0, 34, []], [34, 54, ['INS']], [54, 59, ['LOC', 'INS']], [59, BODY.length, []]
		]);
	});
	it('is the whole body without entities', () => {
		expect(segments('abc', [])).toEqual([{ start: 0, end: 3, entities: [] }]);
	});
});

describe('reanchor', () => {
	it('keeps entities whose text is still there and moves the others to the nearest occurrence', () => {
		const old = 'Chv e nrat und Gmünd, Gmünd';
		const changed = 'Chvenrat und Gmünd, Gmünd';
		const first = entity(15, 20, 'LOC', old);
		const second = entity(22, 27, 'LOC', old);
		const person = entity(0, 10, 'PER', old);
		const { kept, lost } = reanchor(changed, [first, second, person]);
		expect(kept.map((e) => [e.start, e.end])).toEqual([[13, 18], [20, 25]]);
		expect(lost).toEqual([person]);
	});
});

describe('dictionary', () => {
	it('reads term and tag, the tag last', () => {
		expect(readDictionary('# comment\nGmünd\tLOC\nAnselm Vieweger PER\nbroken\n\nPA Keutschach  ARCH\r\n')).toEqual({
			'Gmünd': 'LOC', 'Anselm Vieweger': 'PER', 'PA Keutschach': 'ARCH'
		});
	});
	it('writes each text and tag once, by tag then text', () => {
		const entities = [entity(54, 59, 'LOC'), entity(0, 20, 'PER'), entity(54, 59, 'LOC'), entity(34, 59, 'INS')];
		const written = writeDictionary(entities);
		expect(written).toBe('Liebfrauenkirche zu Gmünd\tINS\nGmünd\tLOC\nArtolff von Lewbnegk\tPER\n');
		expect(readDictionary(written)).toEqual({ 'Liebfrauenkirche zu Gmünd': 'INS', 'Gmünd': 'LOC', 'Artolff von Lewbnegk': 'PER' });
	});
});
