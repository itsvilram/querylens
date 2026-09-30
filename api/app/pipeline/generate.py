"""Generate: ask the LLM for SQL and read its JSON answer."""

import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from app.llm.base import LLMClient, Message, Usage


class GeneratedAnswer(BaseModel):
    # extra="forbid" puts "additionalProperties": false in the JSON schema,
    # which strict structured output requires.
    model_config = ConfigDict(extra="forbid")

    sql: str  # "" when the model declines (off-topic question, prompt injection, ...)
    explanation: str
    chart_hint: Literal["line", "bar", "number", "table"]


ANSWER_SCHEMA = GeneratedAnswer.model_json_schema()

# Without structured output, models often wrap JSON in a Markdown code fence.
_CODE_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


def _strip_code_fence(text: str) -> str:
    match = _CODE_FENCE.match(text)
    return match.group(1) if match else text


@dataclass(frozen=True)
class Generation:
    answer: GeneratedAnswer
    usage: Usage
    model: str


class GenerationError(Exception):
    """The model's reply was not the JSON we asked for.

    It keeps the token usage (those tokens were spent and count against the
    budget) and the raw reply (the correction step shows it back to the model).
    """

    code = "bad_json"

    def __init__(self, detail: str, usage: Usage, text: str = "") -> None:
        super().__init__(detail)
        self.detail = detail
        self.usage = usage
        self.text = text


async def generate_sql(llm: LLMClient, messages: list[Message]) -> Generation:
    completion = await llm.complete(messages, json_schema=ANSWER_SCHEMA, schema_name="sql_answer")
    try:
        answer = GeneratedAnswer.model_validate_json(_strip_code_fence(completion.text))
    except ValidationError as error:
        problems = "; ".join(
            f"{'.'.join(map(str, e['loc'])) or 'reply'}: {e['msg']}" for e in error.errors()
        )
        raise GenerationError(
            f"The reply was not valid JSON for the answer format: {problems}",
            completion.usage,
            completion.text,
        ) from error
    return Generation(answer=answer, usage=completion.usage, model=completion.model)
