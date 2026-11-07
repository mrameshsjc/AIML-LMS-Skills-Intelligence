# app/llm – language model providers

**Filled in:** Phase 11.

| Planned file | Purpose |
| --- | --- |
| `base.py` | `LLMProvider` interface: `generate(prompt) -> text` |
| `ollama_provider.py` | Local Ollama (for example Llama 3.2 3B) |
| `hosted_provider.py` | A configured remote endpoint (for the public demo) |
| `fallback_provider.py` | Retrieval-only answers, always labelled "fallback – no LLM" |

The provider is chosen in `.env`, so changing the model needs no code change.
