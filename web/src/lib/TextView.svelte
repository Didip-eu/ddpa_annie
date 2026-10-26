<!-- A text body with its entities highlighted; reports a selection as character offsets and a click on an entity. -->
<script lang="ts">
	import { segments } from './spans';
	import type { Entity } from './types';

	type Props = {
		body: string;
		language?: string | null;
		entities: Entity[];
		selected: string[];
		pending: [number, number] | null;
		color: (tag: string) => string;
		onselect: (start: number, end: number) => void;
		onpick: (entity: Entity, additive: boolean) => void;
	};
	let { body, language = null, entities, selected, pending, color, onselect, onpick }: Props = $props();

	let container: HTMLElement;
	// The selection waiting for a tag is drawn as an entity without id.
	const marked = $derived<Entity[]>(pending ? [...entities, { id: '', group: '', start: pending[0], end: pending[1], tag: '', text: '', source: 'manual' }] : entities);
	const pieces = $derived(segments(body, marked));

	/** The offset in the body of a DOM position inside the container. */
	function offsetOf(node: Node, offset: number): number {
		if (node === container) {
			const child = container.childNodes[offset] as HTMLElement | undefined;
			return child?.dataset?.start ? Number(child.dataset.start) : body.length;
		}
		const element = (node.nodeType === Node.TEXT_NODE ? node.parentElement : node) as HTMLElement;
		return Number(element.closest<HTMLElement>('[data-start]')!.dataset.start) + offset;
	}

	function pick(event: MouseEvent | KeyboardEvent, shown: Entity[]) {
		if (event instanceof KeyboardEvent && event.key !== 'Enter') return;
		if (shown.length && !window.getSelection()?.toString()) onpick(shown[0], event.shiftKey || event.ctrlKey || event.metaKey);
	}

	function selectionEnd() {
		const selection = window.getSelection();
		if (!selection || selection.isCollapsed || !container.contains(selection.anchorNode) || !container.contains(selection.focusNode)) return;
		const range = selection.getRangeAt(0);
		onselect(offsetOf(range.startContainer, range.startOffset), offsetOf(range.endContainer, range.endOffset));
		selection.removeAllRanges();
	}
</script>

<!-- svelte-ignore a11y_no_noninteractive_element_interactions (selecting text with the mouse is the interaction) -->
<div class="text" bind:this={container} lang={language ?? undefined} onmouseup={selectionEnd} role="document">{#each pieces as piece (piece.start)}{@const shown = piece.entities.filter((entity) => entity.id)}{#if piece.entities.length}<span
				class="entity"
				data-start={piece.start}
				class:pending={shown.length < piece.entities.length}
				class:selected={shown.some((entity) => selected.includes(entity.id))}
				class:stacked={shown.length > 1}
				style:background={shown.length ? color(shown[0].tag) : undefined}
				title={shown.map((entity) => entity.tag).join(', ')}
				role="button"
				tabindex={shown.length ? 0 : -1}
				onclick={(event) => pick(event, shown)}
				onkeydown={(event) => pick(event, shown)}
				>{body.slice(piece.start, piece.end)}</span
			>{:else}<span data-start={piece.start}>{body.slice(piece.start, piece.end)}</span>{/if}{/each}</div>

<style>
	.text {
		white-space: pre-wrap;
		font-family: var(--font-body, Georgia, serif);
		font-size: var(--text-base, 1.0625rem);
		line-height: 1.8;
		max-width: var(--measure, 68ch);
	}
	.entity {
		color: #1d1d1b;
		border-radius: var(--radius, 2px);
		cursor: pointer;
	}
	.entity.stacked {
		box-shadow: inset 0 -3px 0 var(--color-accent, #7a2e1f);
	}
	.entity.selected {
		outline: 2px solid var(--color-accent, #7a2e1f);
	}
	.entity.pending {
		outline: 2px dashed var(--color-machine, #1f5a7a);
	}
	.entity.pending:not([style]) {
		background: var(--color-machine-surface, #e7f0f4);
	}
</style>
