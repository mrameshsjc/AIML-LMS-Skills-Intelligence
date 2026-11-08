"""AI learning assistant: chat with LMS data and approved documents, with sources (API 5)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from app.api.dependencies import get_chat_service, get_llm_provider  # noqa: E402
from dashboard.components import data, ui  # noqa: E402

ui.setup_page(
    "AI learning assistant",
    "Ask about skills, roles, courses, your learning path or the learning policies. Answers use LMS data and "
    "approved documents only, and list their sources.",
    "💬",
)
repo = ui.repository()
employee_id = ui.employee_picker(repo)
about_me = st.sidebar.toggle("Answer about the selected employee", value=True)
if st.sidebar.button("New conversation"):
    st.session_state["chat"] = []
messages: list[dict] = st.session_state.setdefault("chat", [])

EXAMPLES = [
    "What are my current skill gaps?",
    "Which courses should I complete next?",
    "Which skills are required for an AI Engineer?",
    "How many learning hours do I have per year?",
]


def show(message: dict) -> None:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        answer = message.get("answer")
        if answer is None:
            return
        st.caption(
            f"{answer.provider} {answer.model} · {answer.duration_ms / 1000:.1f} s · "
            f"understood as: {', '.join(answer.intents) or '–'}"
        )
        if answer.is_fallback:  # never let a fallback look like an LLM answer
            st.info(
                "Fallback mode - no language model is available right now. This answer lists the "
                "matching LMS facts and document passages; it was not written by an AI model.",
                icon="ℹ️",
            )
        for warning in answer.grounding_warnings:
            st.warning(warning)
        if answer.sources:
            with st.expander(f"Sources ({len(answer.sources)})"):
                st.dataframe(data.sources_table(answer), hide_index=True)
                for s in answer.sources:
                    st.markdown(f"**[{s.label}] {s.source}** – {s.section}  \n{s.text[:400]}")
        for note in answer.notes:
            st.caption(f"ⓘ {note[:200]}")


if not messages:
    st.markdown("**Try:**")
    for column, example in zip(st.columns(len(EXAMPLES)), EXAMPLES, strict=True):
        if column.button(example):
            st.session_state["pending"] = example
for message in messages:
    show(message)

question = st.chat_input("Ask a question") or st.session_state.pop("pending", None)
if question and ui.chat_allowed():
    history = [(m["role"], m["content"]) for m in messages]
    messages.append({"role": "user", "content": question})
    show(messages[-1])
    with st.spinner("Thinking ..."):
        answer = ui.safe(
            get_chat_service(repo, get_llm_provider()).ask,
            question,
            employee_id if about_me else None,
            history,
        )
    if answer is not None:
        messages.append({"role": "assistant", "content": answer.answer, "answer": answer})
        show(messages[-1])
