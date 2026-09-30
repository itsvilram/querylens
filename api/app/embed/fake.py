"""FakeEmbedder for tests: no model, no download, still meaningful.

The "hashing trick": every word adds 1 to one of the 384 positions (chosen by a
hash of the word), then the vector is scaled to length 1. Texts that share
words get similar vectors, so retrieval tests behave sensibly.
"""

import hashlib
import math
import re

from app.embed.base import EMBEDDING_DIMS

_WORD = re.compile(r"[a-z0-9]+")


def _vector(text: str) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMS
    for word in _WORD.findall(text.lower()):
        position = int(hashlib.md5(word.encode(), usedforsecurity=False).hexdigest(), 16)
        vector[position % EMBEDDING_DIMS] += 1.0
    length = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / length for v in vector]


class FakeEmbedder:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [_vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return _vector(text)
