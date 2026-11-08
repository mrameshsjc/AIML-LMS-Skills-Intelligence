# LMS Skills Intelligence Engine – public demo

AI engine for an enterprise learning management system (LMS), with **synthetic data only** (no real people).

**Try it, no account needed:**

1. Pick a sample employee in the sidebar (for example E1001).
2. **Skills analysis:** gaps against a target job role, with a gap score.
3. **Role matching:** which roles fit the employee's skills.
4. **Recommendations:** courses ranked by an explainable score (gap, importance, level, completion model).
5. **Learning path:** ordered steps with prerequisites and projected readiness.
6. **AI assistant:** ask "What are my current skill gaps?" or "How many learning hours do I have per year?". Answers cite the matching document passages (RAG).
7. **Documents / Model management:** the indexed documents, and the ML model's test metrics.

**Fallback mode:** without a language model the assistant answers in a clearly labelled *fallback* mode. It lists the matching facts and passages and never pretends to be an AI answer.

**Read-only for visitors.** Uploading documents, retraining the model and resetting the demo are for administrators. The data resets whenever the Space restarts.

- Source code: https://github.com/mrameshsjc/AIML-LMS-Skills-Intelligence
- API with Swagger UI: see the companion Space linked in the repository README
