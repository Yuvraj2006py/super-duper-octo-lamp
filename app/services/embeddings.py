import hashlib
import math
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterable

import numpy as np

from app.core.config import get_settings


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed_texts(self, texts: Iterable[str]) -> list[list[float]]:
        raise NotImplementedError


class MockEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dim: int | None = None) -> None:
        settings = get_settings()
        self.dim = dim or settings.embedding_dim

    def embed_texts(self, texts: Iterable[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        tokens = [tok for tok in text.lower().split() if tok]
        if not tokens:
            return vec

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dim
            sign = -1.0 if digest[4] % 2 else 1.0
            magnitude = 1.0 + (digest[5] / 255.0)
            vec[idx] += sign * magnitude

        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0:
            return vec
        return [v / norm for v in vec]


class BGEEmbeddingProvider(EmbeddingProvider):
    def __init__(self, *, model_name: str, dim: int, cache_dir: Path | None = None) -> None:
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise RuntimeError(
                "BGE embedding provider requires 'fastembed'. Install dependencies and rebuild containers."
            ) from exc

        self.model_name = model_name
        self.dim = dim
        cache = cache_dir or Path("/workspace/.cache/fastembed")
        cache.mkdir(parents=True, exist_ok=True)
        self._model = TextEmbedding(model_name=model_name, cache_dir=str(cache))

    def embed_texts(self, texts: Iterable[str]) -> list[list[float]]:
        text_list = list(texts)
        if not text_list:
            return []
        vectors = list(self._model.embed(text_list))
        return [self._normalize_and_resize(np.asarray(vec, dtype=float).tolist()) for vec in vectors]

    def _normalize_and_resize(self, vector: list[float]) -> list[float]:
        if len(vector) > self.dim:
            resized = vector[: self.dim]
        elif len(vector) < self.dim:
            resized = [*vector, *([0.0] * (self.dim - len(vector)))]
        else:
            resized = vector

        norm = math.sqrt(sum(v * v for v in resized))
        if norm == 0:
            return resized
        return [v / norm for v in resized]


def build_embedding_provider():
    settings = get_settings()
    provider = (settings.embedding_provider or "mock").strip().lower()

    if provider == "mock":
        return MockEmbeddingProvider(dim=settings.embedding_dim)

    if provider == "bge":
        model_name = settings.embedding_model_name
        if not model_name or model_name == "mock-embed-v1":
            model_name = "BAAI/bge-small-en-v1.5"
        return BGEEmbeddingProvider(
            model_name=model_name,
            dim=settings.embedding_dim,
            cache_dir=settings.embedding_cache_dir,
        )

    raise ValueError("Unsupported EMBEDDING_PROVIDER. Supported values: mock, bge.")


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    if vec_a is None or vec_b is None:
        return 0.0
    if len(vec_a) == 0 or len(vec_b) == 0:
        return 0.0
    if len(vec_a) != len(vec_b):
        return 0.0
    return float(sum(a * b for a, b in zip(vec_a, vec_b)))
