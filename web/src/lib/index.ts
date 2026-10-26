/** ANNIE for the Monasterium NG web client: the annotator component, its store and the client of the ANNIE routes. */
export { default as Annotator } from './Annotator.svelte';
export { AnnieStore, DEFAULT_SCHEMA, MENTION_TAGS } from './annotations.svelte';
export { annieApi, AnnieError, type AnnieApi, type Provider, type Suggestion } from './api';
export { readDictionary, writeDictionary } from './dictionary';
export type { Entity, Relation, Schema, Settings, Source, Span, Text, TextAnnotations } from './types';
