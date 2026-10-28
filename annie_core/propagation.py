"""Tag every occurrence of known terms in a text: propagation, dictionaries and session memory."""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class Entity:
    start: int
    end: int
    tag: str
    text: str


def pattern(term: str) -> re.Pattern:
    """The pattern that finds a term in any case, with any whitespace between its words."""
    words = r"\s+".join(map(re.escape, term.split()))
    # \b only at an end that is a word character: '(S)' never matches between ')' and a space
    start = r"\b" if term[:1].isalnum() else ""
    end = r"\b" if term[-1:].isalnum() else ""
    return re.compile(start + words + end, re.IGNORECASE)


def overlaps(start: int, end: int, entities: list[Entity]) -> bool:
    """True when the span shares at least one character with one of the entities."""
    return any(start < entity.end and entity.start < end for entity in entities)


def propagate(body: str, terms: dict[str, str], existing: list[Entity], allow_overlap: bool) -> list[Entity]:
    """The entities the terms add to a text, longest term first, without repeating an existing span and tag."""
    taken = {(entity.start, entity.end, entity.tag) for entity in existing}
    entities = list(existing)
    added = []
    for term, tag in sorted(terms.items(), key=lambda item: -len(item[0])):
        for match in pattern(term).finditer(body):
            start, end = match.span()
            if (start, end, tag) in taken or (not allow_overlap and overlaps(start, end, entities)):
                continue
            entity = Entity(start, end, tag, " ".join(match.group().split()))
            taken.add((start, end, tag))
            entities.append(entity)
            added.append(entity)
    return added


def remembered(annotated: list[list[Entity]], tags: set[str]) -> dict[str, str]:
    """Each surface annotated elsewhere, in lower case, with the tag given to it most often."""
    counts: dict[str, Counter] = defaultdict(Counter)
    for entities in annotated:
        for entity in entities:
            surface = entity.text.strip().lower()
            if len(surface) >= 2:
                counts[surface][entity.tag] += 1
    best = {surface: tag_counts.most_common(1)[0][0] for surface, tag_counts in counts.items()}
    return {surface: tag for surface, tag in best.items() if tag in tags}
