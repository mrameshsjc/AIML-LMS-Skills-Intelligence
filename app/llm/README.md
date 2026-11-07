# app/llm – language model providers

**Filled in:** Phase 11.

| File | Purpose |
| --- | --- |
| `base.py` | `LLMProvider` interface (`generate`, `status`), `LLMRequest` (instruction + facts), `LLMResult` |
| `ollama_provider.py` | Local Ollama over HTTP (`/api/tags`, `/api/chat`); local hosts only unless approved |
| `fallback_provider.py` | No model: lists the facts, always labelled "Fallback - no LLM" |
| `factory.py` | `LLM_PROVIDER` (auto / ollama / fallback) → provider; `AutoProvider` falls back when Ollama cannot answer |
| `prompts.py` | The system prompt (rules) and how facts are wrapped |
| `guardrails.py` | `redact()` before sending; `check_grounding()` after answering |

A hosted provider for the public demo comes in Phase 19. The provider is chosen in `.env`, so changing the model needs no code change. Guide: [`docs/LLM_RAG_GUIDE.md`](../../docs/LLM_RAG_GUIDE.md).
