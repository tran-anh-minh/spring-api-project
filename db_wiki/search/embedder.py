"""Lazy-loaded embedding engine for vector search (CONFIG-01, CONFIG-04).

Sentence-transformers and torch are NOT imported at module level.
They are loaded on first call to ensure_ready(), which is triggered
by the first search query (D-09).
"""
import logging
import sqlite3
import struct
from typing import Any

from db_wiki.core.config import EmbeddingConfig
from db_wiki.core.store import init_vec_table

logger = logging.getLogger(__name__)


def serialize_embedding(values: list[float]) -> bytes:
    """Pack float list to bytes for sqlite-vec. Lists not accepted directly."""
    return struct.pack(f"{len(values)}f", *values)


class Embedder:
    """Lazy-loaded embedding engine. Does not import torch until needed."""

    def __init__(self, config: EmbeddingConfig):
        self.config = config
        self._model: Any = None
        self._ready = False

    @property
    def dimensions(self) -> int:
        if self.config.provider == "openai":
            return self.config.openai_dimensions
        return self.config.dimensions

    @property
    def vec_table_name(self) -> str:
        return f"vec_embeddings_{self.dimensions}"

    def ensure_ready(self) -> None:
        """Lazy-load the embedding model. First call downloads model if needed."""
        if self._ready:
            return
        if self.config.provider == "local":
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.config.model_name)
            self._ready = True
            logger.info("Loaded local embedding model: %s", self.config.model_name)
        elif self.config.provider == "openai":
            import openai

            self._model = openai.OpenAI()
            self._ready = True
            logger.info("Initialized OpenAI embedding client")
        else:
            raise ValueError(f"Unknown embedding provider: {self.config.provider}")

    def encode(self, texts: list[str]) -> list[list[float]]:
        """Encode texts to embedding vectors."""
        self.ensure_ready()
        if self.config.provider == "local":
            embeddings = self._model.encode(texts, convert_to_numpy=True)
            return [emb.tolist() for emb in embeddings]
        elif self.config.provider == "openai":
            response = self._model.embeddings.create(
                model=self.config.openai_model,
                input=texts,
            )
            return [item.embedding for item in response.data]
        return []

    def embed_entities(
        self,
        conn: sqlite3.Connection,
        entities: list[dict],  # [{"entity_type": "table", "entity_id": 1, "text": "..."}]
    ) -> int:
        """Embed and store entities in sqlite-vec. Returns count inserted."""
        if not entities:
            return 0
        init_vec_table(conn, self.dimensions)
        texts = [e["text"] for e in entities]
        vectors = self.encode(texts)
        count = 0
        for entity, vec in zip(entities, vectors):
            conn.execute(
                f"INSERT INTO {self.vec_table_name}(entity_type, entity_id, embedding) "
                f"VALUES (?, ?, ?)",
                (entity["entity_type"], entity["entity_id"], serialize_embedding(vec)),
            )
            count += 1
        conn.commit()
        return count

    def search_similar(
        self,
        conn: sqlite3.Connection,
        query_text: str,
        limit: int = 10,
    ) -> list[tuple[str, int, float]]:
        """Find similar entities by vector distance. Returns (entity_type, entity_id, distance)."""
        self.ensure_ready()
        init_vec_table(conn, self.dimensions)
        query_vec = self.encode([query_text])[0]
        rows = conn.execute(
            f"SELECT entity_type, entity_id, distance "
            f"FROM {self.vec_table_name} "
            f"WHERE embedding MATCH ? "
            f"ORDER BY distance LIMIT ?",
            (serialize_embedding(query_vec), limit),
        ).fetchall()
        return [(row[0], row[1], row[2]) for row in rows]
