/** Calls to the ANNIE routes of ddp_api under /api/v1/annie. */
import type { Entity, Span, Text } from './types';

export type Provider = { id: string; default_model: string; configured: boolean };
export type Suggestion = Span & { source: 'memory' | 'llm' };
type Payload = { id: string; body: string; entities: Span[] };

export class AnnieError extends Error {}

const payload = (text: Text, entities: Entity[]): Payload => ({
	id: text.id,
	body: text.body,
	entities: entities.map(({ start, end, tag, text }) => ({ start, end, tag, text }))
});

/** The client of the ANNIE routes, sending its requests to base (by default the page's own /api/v1). */
export function annieApi(fetcher: typeof fetch = fetch, base = '/api/v1') {
	async function call<T>(path: string, body?: unknown): Promise<T> {
		const response = await fetcher(`${base}/annie/${path}`, body === undefined ? undefined : {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(body)
		});
		const json = await response.json();
		if (!response.ok) throw new AnnieError(json.error?.message ?? `${response.status} ${response.statusText}`);
		return json.data;
	}

	return {
		/** The language model providers and whether the server holds a key for them. */
		providers: () => call<Provider[]>('providers'),
		/** The spans the terms add to each text, by text id. */
		propagate: async (texts: { text: Text; entities: Entity[] }[], terms: Record<string, string>, allowOverlap: boolean) => {
			const result = await call<{ text_id: string; entities: Span[] }[]>('propagate', {
				texts: texts.map(({ text, entities }) => payload(text, entities)),
				terms,
				allow_overlap: allowOverlap
			});
			return new Map(result.map((item) => [item.text_id, item.entities]));
		},
		/** Spans for one text from the session memory and the language model. */
		suggest: (text: Text, entities: Entity[], examples: { text: Text; entities: Entity[] }[], tags: string[],
			options: { provider: string; model: string; exampleCount: number; allowOverlap: boolean }) =>
			call<Suggestion[]>('suggest', {
				text: payload(text, entities),
				examples: examples.map(({ text, entities }) => payload(text, entities)),
				tags,
				provider: options.provider,
				model: options.model || null,
				example_count: options.exampleCount,
				allow_overlap: options.allowOverlap
			})
	};
}

export type AnnieApi = ReturnType<typeof annieApi>;
