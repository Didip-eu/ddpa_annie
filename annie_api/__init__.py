"""The ANNIE routes, an APIRouter to include under /api/v1: propagation and model suggestions over texts the client sends."""

import os
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from annie_core import llm
from annie_core.propagation import Entity, propagate

type Provider = Literal["anthropic", "openai", "together", "huggingface", "dhinfra"]
KEY_VARIABLES = {provider: f"DDP_ANNIE_{provider.upper()}_KEY" for provider in llm.DEFAULT_MODELS}
UNAVAILABLE = {503: {"description": "The provider has no key on this server, cannot be reached, or answered no entity list"}}

router = APIRouter(prefix="/annie", tags=["annie"])


class Span(BaseModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    tag: str
    text: str


class Text(BaseModel):
    id: str
    body: str
    entities: list[Span] = []


class TextSpans(BaseModel):
    text_id: str
    entities: list[Span]


class PropagationRequest(BaseModel):
    texts: list[Text]
    terms: dict[str, str] = Field(description="the tag of each term to find")
    allow_overlap: bool = True


class PropagationResult(BaseModel):
    data: list[TextSpans]


class SuggestionRequest(BaseModel):
    text: Text
    examples: list[Text] = Field([], description="annotated texts: the session memory and the pool of few-shot examples")
    tags: list[str]
    provider: Provider = "anthropic"
    model: str | None = Field(None, description="the provider's default model when not given")
    example_count: int = Field(3, ge=0, le=20)
    allow_overlap: bool = True


class Suggestion(Span):
    source: Literal["memory", "llm"]


class SuggestionResult(BaseModel):
    data: list[Suggestion]


class ProviderState(BaseModel):
    id: Provider
    default_model: str
    configured: bool


class ProviderList(BaseModel):
    data: list[ProviderState]


def entities(spans: list[Span]) -> list[Entity]:
    return [Entity(span.start, span.end, span.tag, span.text) for span in spans]


def spans(found: list[Entity]) -> list[Span]:
    return [Span(start=entity.start, end=entity.end, tag=entity.tag, text=entity.text) for entity in found]


def unavailable(request: Request, message: str) -> JSONResponse:
    """503 in the error shape of ddp_api, with the request id it assigns."""
    detail = {"code": "unavailable", "message": message, "request_id": getattr(request.state, "request_id", None)}
    return JSONResponse(status_code=503, content={"error": detail})


@router.get("/providers")
def providers() -> ProviderList:
    """The language model providers, their default model, and whether this server holds a key for them."""
    return ProviderList(data=[ProviderState(id=provider, default_model=model, configured=bool(os.environ.get(KEY_VARIABLES[provider])))
                              for provider, model in llm.DEFAULT_MODELS.items()])


@router.post("/propagate")
def propagation(body: PropagationRequest) -> PropagationResult:
    """The entities the terms add to each text, without repeating a span and tag a text already has."""
    return PropagationResult(data=[TextSpans(text_id=text.id, entities=spans(propagate(text.body, body.terms, entities(text.entities), body.allow_overlap)))
                                   for text in body.texts])


@router.post("/suggest", responses=UNAVAILABLE)
def suggestion(body: SuggestionRequest, request: Request) -> SuggestionResult:
    """Entities for one text: those its examples already hold (memory) and those the language model proposes (llm)."""
    key = os.environ.get(KEY_VARIABLES[body.provider])
    if not key:
        return unavailable(request, f"This server holds no key for {body.provider} ({KEY_VARIABLES[body.provider]}).")
    examples = [(example.body, entities(example.entities)) for example in body.examples if example.entities]
    try:
        memory, proposed = llm.suggest(body.text.body, entities(body.text.entities), examples, body.tags, body.provider,
                                       body.model or llm.DEFAULT_MODELS[body.provider], key, body.example_count, body.allow_overlap)
    except llm.ProviderError as error:
        return unavailable(request, str(error))
    return SuggestionResult(data=[Suggestion(**span.model_dump(), source="memory") for span in spans(memory)]
                            + [Suggestion(**span.model_dump(), source="llm") for span in spans(proposed)])
