"""Rewrite: turn a follow-up into one standalone question, using the chat history.

"Only for store 2" means nothing alone. After "Which film categories made the
most money in 2024?", it means "Which film categories made the most money in
2024 at store 2?". Everything after this step (retrieval, SQL, later the
answer cache) then works on a complete question, exactly as for a first one.

No history means no rewrite and no LLM call. The API returns the rewritten
question, so the UI can show "Understood as: ..." and a wrong guess is easy to spot.
"""

from pydantic import BaseModel, ConfigDict, ValidationError

from app.llm.base import LLMClient, Usage
from app.llm.prompts import REWRITE_SCHEMA_NAME, build_rewrite_messages
from app.pipeline.generate import strip_code_fence


class RewriteAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")  # strict structured output needs it

    question: str


REWRITE_SCHEMA = RewriteAnswer.model_json_schema()


async def rewrite_question(llm: LLMClient, earlier: list[str], follow_up: str) -> tuple[str, Usage]:
    """The standalone question, and the tokens spent getting it."""
    if not earlier:
        return follow_up, Usage(0, 0, 0)
    completion = await llm.complete(
        build_rewrite_messages(earlier, follow_up),
        json_schema=REWRITE_SCHEMA,
        schema_name=REWRITE_SCHEMA_NAME,
    )
    try:
        text = strip_code_fence(completion.text)
        question = RewriteAnswer.model_validate_json(text).question.strip()
    except ValidationError:
        question = ""
    # An unreadable rewrite is not worth failing the request for: fall back to
    # the follow-up as typed. The SQL step then asks for more detail if needed.
    return question or follow_up, completion.usage
