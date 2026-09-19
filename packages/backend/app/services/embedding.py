import hashlib
import math
import numpy as np
from typing import List, Optional

from app.core.logging import logger

MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384


class EmbeddingService:
    """
    Local privacy-first embedding service powered by FastEmbed ONNX Runtime.
    Operates strictly on CPU without GPU/PyTorch overhead and zero external network calls.
    Includes a deterministic normalized fallback vectorizer for airgapped or offline boot.
    """

    def __init__(self, model_name: str = MODEL_NAME, dimension: int = EMBEDDING_DIM):
        self.model_name = model_name
        self.dimension = dimension
        self._model = None
        self._is_fallback = False

    def _get_model(self):
        if self._model is None and not self._is_fallback:
            try:
                from fastembed import TextEmbedding
                logger.info(f"Loading local embedding model: {self.model_name}")
                self._model = TextEmbedding(model_name=self.model_name)
                logger.info(f"Embedding model '{self.model_name}' initialized successfully.")
            except Exception as e:
                logger.warning(
                    f"Could not initialize FastEmbed model ({e}). Switching to resilient local deterministic fallback embedder."
                )
                self._is_fallback = True
        return self._model

    def embed_query(self, query: str) -> List[float]:
        """Embeds a single search query into a normalized dense float vector."""
        vectors = self.embed_documents([query])
        return vectors[0] if vectors else [0.0] * self.dimension

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embeds a batch of text chunks into normalized dense float vectors."""
        if not texts:
            return []

        cleaned_texts = [t.strip() if t and t.strip() else " " for t in texts]
        model = self._get_model()

        if model is not None and not self._is_fallback:
            try:
                # FastEmbed returns a generator of numpy arrays
                generator = model.embed(cleaned_texts)
                vectors = []
                for vec in generator:
                    v = vec.tolist() if hasattr(vec, "tolist") else list(vec)
                    vectors.append(v)
                return vectors
            except Exception as e:
                logger.warning(f"FastEmbed inference error: {e}. Using deterministic fallback.")
                return [self._fallback_embed(t) for t in cleaned_texts]

        return [self._fallback_embed(t) for t in cleaned_texts]

    def _fallback_embed(self, text: str) -> List[float]:
        """
        Deterministic pseudo-embedding for testing and offline airgapped environments.
        Computes an n-gram hashed feature projection normalized to unit L2 norm.
        """
        vec = np.zeros(self.dimension, dtype=np.float32)
        text_lower = text.lower().strip()
        if not text_lower:
            return vec.tolist()

        words = text_lower.split()
        for i, word in enumerate(words):
            # Map word to buckets
            h1 = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16) % self.dimension
            h2 = int(hashlib.sha256(word.encode("utf-8")).hexdigest(), 16) % self.dimension
            sign = 1.0 if (h1 % 2 == 0) else -1.0
            weight = 1.0 / math.sqrt(i + 1)
            vec[h1] += sign * weight
            vec[h2] += (sign * -0.5) * weight

        # Character n-grams for subword matching
        for n in range(3, min(6, len(text_lower) + 1)):
            for j in range(len(text_lower) - n + 1):
                gram = text_lower[j : j + n]
                gh = int(hashlib.blake2b(gram.encode("utf-8"), digest_size=8).hexdigest(), 16) % self.dimension
                vec[gh] += 0.25

        norm = np.linalg.norm(vec)
        if norm > 1e-6:
            vec = vec / norm
        return vec.tolist()

    @property
    def is_fallback(self) -> bool:
        return self._is_fallback


embedding_service = EmbeddingService()
