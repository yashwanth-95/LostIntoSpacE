<![CDATA[# AI Module — `ai/`

## Owner: P4 (AI / Search / Data / Integration)

## Purpose
LLM provider abstraction for tutoring, failure explanation, recommendations, and semantic search. AI explains deterministic results — it never invents physics.

## Structure
- `providers/` — Provider abstraction (OpenAI, Gemini, local)
- `prompts/` — System prompts and prompt templates
- `tools/` — Tool definitions for function calling
- `grounding/` — Context retrieval from DB/search/simulation
- `safety/` — Output validation, prompt injection defense
- `tests/` — AI response quality tests

## Critical Rule
> AI is the EXPLANATION layer. The simulation engine is the TRUTH layer.
> AI receives simulation results and explains them. AI never generates simulation results.

## Provider Interface
```python
class AIProvider(Protocol):
    async def complete(self, messages: list, tools: list = None) -> AIResponse: ...
    async def embed(self, text: str) -> list[float]: ...
```
]]>
