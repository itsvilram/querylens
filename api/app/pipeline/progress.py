"""Progress: which stage a question is in, so the UI can show live progress.

The pipeline calls `progress(stage)` as it goes; the streaming endpoint turns
each call into an SSE event. Everything else (the JSON endpoint, the eval)
passes no_progress.
"""

from collections.abc import Awaitable, Callable
from typing import Literal

type Stage = Literal[
    "rewrite",  # understanding a follow-up from the chat history
    "wait",  # the same question is already being answered: waiting for that answer
    "retrieve",  # finding the relevant tables
    "generate",  # writing SQL
    "correct",  # the SQL failed: writing a fixed version
    "execute",  # running the query
]
type Progress = Callable[[Stage], Awaitable[None]]


async def no_progress(stage: Stage) -> None:
    return None
