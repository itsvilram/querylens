"""The answer-cache key: when do two questions deserve the same answer?

Same key = same normalized standalone question AND the same everything that
shapes the answer: the database schema, the prompt, the model and the
pipeline settings. The cache runs after the rewrite, so "Only for store 2"
in one chat and a full question typed in another can share an answer, while
the same words about a changed schema never do.
"""

import hashlib
import json

from app.config import Settings
from app.db.schema import schema_version
from app.llm.prompts import PROMPT_VERSION

# Bump when the cached answer's JSON shape changes, so old entries are ignored.
CACHE_FORMAT = "v3"  # v2: sql is pretty-printed; v3: no one-bar charts


def normalize_question(question: str) -> str:
    """Lower case, single spaces, no final punctuation: "How many films?" = "how many films"."""
    return " ".join(question.lower().split()).rstrip("?.! ")


def pipeline_fingerprint(*, schema_text: str, model: str, settings: Settings) -> str:
    """Everything besides the question that changes the answer, as one short hash."""
    parts: dict[str, object] = {
        "schema": schema_version(schema_text),
        "prompt": PROMPT_VERSION,
        "model": model,
        "schema_mode": settings.schema_mode,
        "row_cap": settings.row_cap,
        "correction_retries": settings.correction_retries,
    }
    if settings.schema_mode == "retrieved":
        parts["retrieval"] = [settings.retrieval_k, settings.embedding_model]
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:16]


def answer_cache_key(question: str, fingerprint: str) -> str:
    # Hashed: a fixed-length key, whatever the question looks like.
    digest = hashlib.sha256(f"{fingerprint}\n{normalize_question(question)}".encode())
    return f"answer:{CACHE_FORMAT}:{digest.hexdigest()[:32]}"
