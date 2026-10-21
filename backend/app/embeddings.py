from functools import lru_cache

from fastembed import TextEmbedding

from .config import settings


@lru_cache(maxsize=1)
def _model() -> TextEmbedding:
    # Downloads a small ONNX model (~130MB) on first use, then caches it.
    return TextEmbedding(model_name=settings.embedding_model)


def embed_texts(texts: list[str]) -> list[list[float]]:
    # fastembed returns unit-length vectors for this model, so cosine search works as-is.
    return [v.tolist() for v in _model().embed(texts)]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
