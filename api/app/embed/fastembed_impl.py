"""Local embeddings with fastembed (ONNX, CPU): free, no API key, no quota.

The model (~67 MB) is downloaded once into data/models/ (git-ignored) and
loaded on first use. Embedding one question takes ~50 ms on a slow laptop CPU.
"""

import os

from fastembed import TextEmbedding

# huggingface_hub warns about symlinks on Windows without Developer Mode; harmless.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


class FastEmbedder:
    def __init__(self, model_name: str, cache_dir: str) -> None:
        self._model_name = model_name
        self._cache_dir = cache_dir
        self._model: TextEmbedding | None = None

    def _loaded(self) -> TextEmbedding:
        if self._model is None:
            self._model = TextEmbedding(self._model_name, cache_dir=self._cache_dir)
        return self._model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(x) for x in vector] for vector in self._loaded().embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        # BGE models add a short instruction to queries (not documents) for better search.
        vector = next(iter(self._loaded().query_embed(text)))
        return [float(x) for x in vector]
