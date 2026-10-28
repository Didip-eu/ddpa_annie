/** Dictionary files: one term and its tag per line, the tag last; the format the desktop app reads and writes. */
import type { Entity } from './types';

/** Term to tag from a dictionary file; blank lines and lines starting with # are skipped. */
export function readDictionary(content: string): Record<string, string> {
	const terms: Record<string, string> = {};
	for (const line of content.split(/\r?\n/)) {
		const match = line.trim().match(/^(.+?)\s+(\S+)$/);
		if (match && !line.startsWith('#')) terms[match[1].trim()] = match[2];
	}
	return terms;
}

/** A dictionary file of every distinct entity text and tag, sorted by tag, then text. */
export function writeDictionary(entities: Entity[]): string {
	const lines = new Set(entities.map((entity) => `${entity.text.replace(/\s+/g, ' ').trim()}\t${entity.tag}`));
	// tag first, then the text in lower case, compared by code point as the desktop app does; a tab sorts before any tag character
	const key = (line: string) => {
		const [text, tag] = line.split('\t');
		return `${tag}\t${text.toLowerCase()}`;
	};
	const compare = (a: string, b: string) => (key(a) < key(b) ? -1 : key(a) > key(b) ? 1 : 0);
	return [...lines].sort(compare).map((line) => `${line}\n`).join('');
}
