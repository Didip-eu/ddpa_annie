<!-- The entities and relations of one text: select, delete, merge and demerge entities; add, flip and delete relations. -->
<script lang="ts">
	import type { Entity, Relation } from './types';

	type Props = {
		entities: Entity[];
		relations: Relation[];
		relationTypes: string[];
		selected: string[];
		color: (tag: string) => string;
		onremove: (ids: string[]) => void;
		onmerge: (ids: string[]) => void;
		ondemerge: (id: string) => void;
		onrelate: (head: string, tail: string, type: string) => void;
		onflip: (id: string) => void;
		onunrelate: (id: string) => void;
	};
	let { entities, relations, relationTypes, selected = $bindable(), color, onremove, onmerge, ondemerge, onrelate, onflip, onunrelate }: Props = $props();

	// undefined lets the bound select take its first option
	let relationType = $state<string>();
	const chosen = $derived(selected.map((id) => entities.find((entity) => entity.id === id)).filter((entity) => entity !== undefined));
	const groupSize = $derived(new Map(Object.entries(Object.groupBy(entities, (entity) => entity.group)).map(([group, members]) => [group, members!.length])));
	const label = (group: string) => entities.filter((entity) => entity.group === group).map((entity) => entity.text)[0] ?? '?';

	function toggle(id: string) {
		selected = selected.includes(id) ? selected.filter((other) => other !== id) : [...selected, id];
	}
</script>

<section>
	<h3>Entities ({entities.length})</h3>
	<div class="actions">
		<button disabled={!chosen.length} onclick={() => { onremove(selected); selected = []; }}>Delete</button>
		<button disabled={chosen.length < 2} onclick={() => onmerge(selected)}>Merge</button>
		<button disabled={chosen.length !== 1 || groupSize.get(chosen[0].group) === 1} onclick={() => ondemerge(selected[0])}>Demerge</button>
	</div>
	<ul class="entities">
		{#each entities as entity (entity.id)}
			<li>
				<label class:selected={selected.includes(entity.id)}>
					<input type="checkbox" checked={selected.includes(entity.id)} onchange={() => toggle(entity.id)} />
					<span class="tag" style:background={color(entity.tag)}>{entity.tag}</span>
					<span class="surface">{entity.text}</span>
					{#if (groupSize.get(entity.group) ?? 1) > 1}<span class="note" title="merged mentions">×{groupSize.get(entity.group)}</span>{/if}
					{#if entity.source !== 'manual'}<span class="note">{entity.source}</span>{/if}
				</label>
			</li>
		{/each}
	</ul>

	<h3>Relations ({relations.length})</h3>
	<div class="actions">
		<select bind:value={relationType} aria-label="Relation type">
			{#each relationTypes as type (type)}<option value={type}>{type}</option>{/each}
		</select>
		<button disabled={chosen.length !== 2 || !relationType} onclick={() => onrelate(chosen[0].group, chosen[1].group, relationType!)}
			title="From the entity selected first to the one selected second">Relate</button>
	</div>
	<ul class="relations">
		{#each relations as relation (relation.id)}
			<li>
				<span>{label(relation.head)} <em>{relation.type}</em> {label(relation.tail)}</span>
				<button onclick={() => onflip(relation.id)} title="Swap head and tail">Flip</button>
				<button onclick={() => onunrelate(relation.id)}>Delete</button>
			</li>
		{/each}
	</ul>
</section>

<style>
	ul {
		list-style: none;
		margin: 0 0 var(--space-4, 1rem);
		padding: 0;
		max-height: 24rem;
		overflow-y: auto;
	}
	li {
		display: flex;
		gap: var(--space-2, 0.5rem);
		align-items: baseline;
		padding: var(--space-1, 0.25rem) 0;
		border-bottom: 1px solid var(--color-border, #dddbd3);
	}
	label {
		display: flex;
		gap: var(--space-2, 0.5rem);
		align-items: baseline;
		width: 100%;
		cursor: pointer;
	}
	label.selected {
		font-weight: 600;
	}
	.tag {
		color: #1d1d1b;
		font-size: var(--text-xs, 0.8125rem);
		padding: 0 var(--space-1, 0.25rem);
		border-radius: var(--radius, 2px);
	}
	.surface {
		flex: 1;
	}
	.note {
		color: var(--color-muted, #5f5f5a);
		font-size: var(--text-xs, 0.8125rem);
	}
	.actions {
		display: flex;
		gap: var(--space-2, 0.5rem);
		margin-bottom: var(--space-2, 0.5rem);
	}
	h3 {
		font-size: var(--text-ui, 0.9375rem);
		margin: var(--space-3, 0.75rem) 0 var(--space-2, 0.5rem);
	}
</style>
