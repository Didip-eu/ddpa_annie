"""Pre-annotation by a language model: few-shot examples chosen by TF-IDF similarity, the prompt, the call, the reply."""

import json
import math
import re
import urllib.error
import urllib.request
from collections import Counter

import anthropic

from annie_core.propagation import Entity, propagate, remembered

DEFAULT_MODELS = {
    "anthropic": "claude-opus-5-5",
    "openai": "gpt-4o-mini",
    "together": "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
    "huggingface": "HuggingFaceH4/zephyr-7b-alpha",
    "dhinfra": "deepseek-v4.1-flash",
}
CHAT_COMPLETIONS = {
    "openai": "https://api.openai.com/v1/chat/completions",
    "together": "https://api.together.xyz/v1/chat/completions",
    "huggingface": "https://router.huggingface.co/v1/chat/completions",
    "dhinfra": "https://api.dhinfra.uni-graz.at/v1/chat/completions",
}
# The DH infrastructure's models reason by default and spend all of MAX_TOKENS on a charter before they answer.
REQUEST_OPTIONS = {"dhinfra": {"reasoning_effort": "none"}}
MAX_TOKENS = 16000
TIMEOUT_SECONDS = 300
WORD = re.compile(r"\w+")


class ProviderError(Exception):
    """The provider could not be reached, refused, or answered something that is not a list of entities."""


def similar(body: str, examples: list[tuple[str, list[Entity]]], count: int) -> list[tuple[str, list[Entity]]]:
    """The examples most similar to the text by TF-IDF cosine, most similar first."""
    query = WORD.findall(body.lower())
    if not query:
        return examples[:count]
    corpus = [WORD.findall(text.lower()) for text, _ in examples]
    frequency = Counter(word for words in corpus for word in set(words))
    unseen = math.log(1 + len(corpus)) + 1
    idf = {word: math.log((1 + len(corpus)) / (1 + documents)) + 1 for word, documents in frequency.items()}

    def vector(words: list[str]) -> dict[str, float]:
        return {word: n / len(words) * idf.get(word, unseen) for word, n in Counter(words).items()}

    def cosine(left: dict[str, float], right: dict[str, float]) -> float:
        norms = math.sqrt(sum(v * v for v in left.values())) * math.sqrt(sum(v * v for v in right.values()))
        return sum(left[word] * right[word] for word in left.keys() & right.keys()) / norms if norms else 0.0

    target = vector(query)
    scores = [cosine(target, vector(words)) if words else 0.0 for words in corpus]
    ranked = sorted(range(len(examples)), key=lambda position: -scores[position])
    return [examples[position] for position in ranked[:count]]


def prompt(body: str, tags: list[str], examples: list[tuple[str, list[Entity]]]) -> str:
    """The few-shot prompt: the task, each example with its entities of the given tags, then the text."""
    parts = [f"You are an expert medieval archivist performing Named Entity Recognition (NER). "
             f"Extract entities strictly belonging to these tags: {', '.join(tags)}.\n"
             f"Return ONLY a valid JSON array of objects with 'text' and 'tag' keys. Do not write markdown, "
             f"explanations, or introductory text. Just the JSON array starting with [ and ending with ].\n\n"]
    for number, (text, entities) in enumerate(examples, 1):
        shown = [{"text": entity.text, "tag": entity.tag} for entity in entities if entity.tag in tags]
        if shown:
            parts.append(f"### Example {number}\nInput:\n{text}\nOutput:\n{json.dumps(shown, ensure_ascii=False)}\n\n")
    parts.append(f"### Target Task\nInput:\n{body}\nOutput:\n")
    return "".join(parts)


def terms(reply: str) -> dict[str, str]:
    """Text to tag from the reply's JSON array; a list cut off after its last complete object is closed."""
    start = reply.find("[")
    if start == -1:
        raise ProviderError(f"The model did not answer with a JSON list: {reply[:200]}")
    listed = reply[start:]
    try:
        items = json.loads(listed)
    except json.JSONDecodeError:
        try:
            items = json.loads(listed[:listed.rfind("}") + 1] + "]")
        except json.JSONDecodeError as error:
            raise ProviderError(f"The model's JSON list cannot be read: {error}") from error
    return {item["text"].strip(): item["tag"] for item in items
            if isinstance(item, dict) and isinstance(item.get("text"), str) and item["text"].strip() and "tag" in item}


def suggest(body: str, existing: list[Entity], examples: list[tuple[str, list[Entity]]], tags: list[str],
            provider: str, model: str, key: str, example_count: int, allow_overlap: bool) -> tuple[list[Entity], list[Entity]]:
    """The entities remembered from the examples, and those the model proposes where no other entity is."""
    memory = propagate(body, remembered([entities for _, entities in examples], set(tags)), existing, allow_overlap)
    shots = similar(body, examples, example_count) if example_count else []
    proposed = {text: tag for text, tag in terms(complete(provider, model, prompt(body, tags, shots), key)).items() if tag in tags}
    return memory, propagate(body, proposed, existing + memory, allow_overlap=False)


def complete(provider: str, model: str, text: str, key: str) -> str:
    """The provider's answer to one user message."""
    if provider == "anthropic":
        return complete_anthropic(model, text, key)
    request = urllib.request.Request(
        CHAT_COMPLETIONS[provider],
        data=json.dumps({"model": model, "messages": [{"role": "user", "content": text}], "max_tokens": MAX_TOKENS,
                         **REQUEST_OPTIONS.get(provider, {})}).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.load(response)["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as error:
        raise ProviderError(f"{provider} answered {error.code}: {error.read()[:300].decode(errors='replace')}") from error
    except urllib.error.URLError as error:
        raise ProviderError(f"{provider} cannot be reached: {error.reason}") from error


def complete_anthropic(model: str, text: str, key: str) -> str:
    """Claude's answer to one user message; a refusal falls back server-side to the model the API picks."""
    client = anthropic.Anthropic(api_key=key, timeout=TIMEOUT_SECONDS)
    try:
        message = client.beta.messages.create(
            model=model, max_tokens=MAX_TOKENS, messages=[{"role": "user", "content": text}],
            betas=["server-side-fallback-2026-07-01"], fallbacks="default")
    except anthropic.APIStatusError as error:
        raise ProviderError(f"anthropic answered {error.status_code}: {error.message}") from error
    except anthropic.APIConnectionError as error:
        raise ProviderError(f"anthropic cannot be reached: {error}") from error
    if message.stop_reason == "refusal":
        raise ProviderError("Claude declined to annotate this text.")
    return "".join(block.text for block in message.content if block.type == "text")
