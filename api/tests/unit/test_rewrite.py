"""The follow-up rewrite: its prompt, when it calls the model, and its fallbacks."""

import json

import pytest

from app.llm.fake import STORE_2_QUESTION, FakeLLM
from app.llm.prompts import FOLLOW_UP_MARKER, build_rewrite_messages
from app.pipeline.rewrite import REWRITE_SCHEMA, rewrite_question

pytestmark = pytest.mark.anyio

EARLIER = ["Which film categories made the most money in 2024?", "How many films are there?"]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def rewritten(question: str) -> str:
    return json.dumps({"question": question})


def test_rewrite_prompt_numbers_the_history_and_ends_with_the_follow_up() -> None:
    system, user = build_rewrite_messages(EARLIER, "Only for store 2")

    assert system.role == "system"
    assert "Never answer the question and never write SQL" in system.content
    assert user.content.startswith("Earlier questions (oldest first):\n1. Which film categories")
    assert "\n2. How many films are there?\n" in user.content
    assert user.content.endswith(f"{FOLLOW_UP_MARKER} Only for store 2")


async def test_first_question_of_a_chat_costs_no_llm_call() -> None:
    llm = FakeLLM()

    question, usage = await rewrite_question(llm, [], "Only for store 2")

    assert question == "Only for store 2"
    assert usage.total_tokens == 0
    assert llm.calls == []


async def test_follow_up_is_rewritten_by_the_model() -> None:
    llm = FakeLLM(replies=[rewritten("Which categories made the most in 2024 at store 2?")])

    question, usage = await rewrite_question(llm, EARLIER, "Only for store 2")

    assert question == "Which categories made the most in 2024 at store 2?"
    assert usage.total_tokens > 0
    assert len(llm.calls) == 1


@pytest.mark.parametrize(
    "reply",
    ["Sure, here it is: at store 2", rewritten("   "), json.dumps({"q": "wrong key"})],
)
async def test_unreadable_rewrite_falls_back_to_the_question_as_typed(reply: str) -> None:
    llm = FakeLLM(replies=[reply])

    question, usage = await rewrite_question(llm, EARLIER, "Only for store 2")

    assert question == "Only for store 2"
    assert usage.total_tokens > 0  # the tokens were spent anyway, so they still count


async def test_rewrite_in_a_code_fence_is_read() -> None:
    llm = FakeLLM(replies=[f"```json\n{rewritten('At store 2?')}\n```"])

    question, _ = await rewrite_question(llm, EARLIER, "Only for store 2")

    assert question == "At store 2?"


async def test_fake_llm_knows_the_demo_follow_up_and_echoes_others() -> None:
    llm = FakeLLM()

    demo, _ = await rewrite_question(llm, EARLIER, "only for store 2?")
    other, _ = await rewrite_question(llm, EARLIER, "How many actors are there?")

    assert demo == STORE_2_QUESTION
    assert other == "How many actors are there?"


def test_rewrite_schema_is_strict() -> None:
    assert REWRITE_SCHEMA["required"] == ["question"]
    assert REWRITE_SCHEMA["additionalProperties"] is False  # strict output needs it
