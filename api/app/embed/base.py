"""What the rest of the app knows about embeddings: text in, a vector of numbers out.

Similar meaning -> vectors pointing in a similar direction, so "money by
category" lands close to the payment and category table descriptions.
"""

from typing import Protocol

EMBEDDING_DIMS = 384  # BAAI/bge-small-en-v1.5; must match vector(384) in app.schema_docs


class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Vectors for the things we search in (table and column descriptions)."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """The vector for what we search with (the user's question)."""
        ...
