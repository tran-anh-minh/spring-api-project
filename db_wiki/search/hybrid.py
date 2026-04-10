"""Hybrid search combining vector similarity and FTS5 keyword search (D-08).

Score fusion normalizes both score types to [0, 1] and combines with
configurable weights (default 0.5/0.5).
"""
import logging
import sqlite3

from db_wiki.core.config import EmbeddingConfig
from db_wiki.search.embedder import Embedder
from db_wiki.search.fts import search_fts

logger = logging.getLogger(__name__)


def fuse_scores(
    fts_results: list[tuple[str, str, int, float]],   # (entity_type, name, entity_id, rank)
    vec_results: list[tuple[str, int, float]],         # (entity_type, entity_id, distance)
    fts_weight: float = 0.5,
    vec_weight: float = 0.5,
) -> list[tuple[str, int, float]]:
    """Fuse FTS5 rank and vector distance into combined score.

    FTS5 rank: negative (less negative = better). Normalize: abs(rank) / max_abs_rank.
    Vec distance: non-negative (lower = closer). Normalize: 1 - (distance / max_distance).
    Combined: fts_weight * fts_norm + vec_weight * vec_norm. Higher = better.
    """
    # Normalize FTS scores
    fts_scores: dict[tuple[str, int], float] = {}
    fts_names: dict[tuple[str, int], str] = {}
    if fts_results:
        max_abs = max(abs(r[3]) for r in fts_results) or 1.0
        for r in fts_results:
            key = (r[0], r[2])  # (entity_type, entity_id)
            fts_scores[key] = abs(r[3]) / max_abs
            fts_names[key] = r[1]

    # Normalize vec scores
    vec_scores: dict[tuple[str, int], float] = {}
    if vec_results:
        max_dist = max(r[2] for r in vec_results) or 1.0
        for r in vec_results:
            key = (r[0], r[1])  # (entity_type, entity_id)
            vec_scores[key] = 1.0 - (r[2] / max_dist)

    # Merge
    all_keys = set(fts_scores) | set(vec_scores)
    combined: list[tuple[str, int, float]] = []
    for key in all_keys:
        score = fts_weight * fts_scores.get(key, 0.0) + vec_weight * vec_scores.get(key, 0.0)
        combined.append((key[0], key[1], score))

    return sorted(combined, key=lambda x: -x[2])


def hybrid_search(
    conn: sqlite3.Connection,
    query: str,
    config: EmbeddingConfig,
    fts_weight: float = 0.5,
    vec_weight: float = 0.5,
    limit: int = 10,
) -> list[tuple[str, int, float]]:
    """Hybrid search: FTS5 + vector similarity with score fusion (D-08).

    On first call, triggers on-demand embedding of all unembedded entities (D-09).
    Returns (entity_type, entity_id, combined_score) sorted by relevance.
    """
    # FTS5 search (always available, no lazy loading)
    fts_results = search_fts(conn, query, limit=limit * 2)

    # Vector search (lazy-loads embedding model on first call)
    vec_results: list[tuple[str, int, float]] = []
    if vec_weight > 0:
        try:
            embedder = Embedder(config)
            # Check if any embeddings exist; if not, embed all entities (D-09 on-demand)
            vec_table = embedder.vec_table_name
            from db_wiki.core.store import init_vec_table

            init_vec_table(conn, embedder.dimensions)
            count = conn.execute(
                f"SELECT COUNT(*) FROM {vec_table}"
            ).fetchone()[0]
            if count == 0:
                _embed_all_entities(conn, embedder)
            vec_results = embedder.search_similar(conn, query, limit=limit * 2)
        except ImportError:
            logger.warning("sentence-transformers not installed; using FTS5-only search")
        except Exception as e:
            logger.warning("Vector search failed: %s; using FTS5-only search", e)

    return fuse_scores(fts_results, vec_results, fts_weight, vec_weight)[:limit]


def _embed_all_entities(conn: sqlite3.Connection, embedder: Embedder) -> int:
    """Embed all current entities that don't have embeddings yet (D-09 on-demand)."""
    entities = []
    for row in conn.execute(
        "SELECT id, table_name, description FROM current_db_tables"
    ).fetchall():
        text = f"{row[1]}: {row[2] or ''}"
        entities.append({"entity_type": "table", "entity_id": row[0], "text": text})
    for row in conn.execute(
        "SELECT id, procedure_name, description FROM current_db_procedures"
    ).fetchall():
        text = f"{row[1]}: {row[2] or ''}"
        entities.append({"entity_type": "procedure", "entity_id": row[0], "text": text})
    for row in conn.execute(
        "SELECT id, column_name, data_type, description FROM current_db_columns"
    ).fetchall():
        text = f"{row[1]} ({row[2] or ''}): {row[3] or ''}"
        entities.append({"entity_type": "column", "entity_id": row[0], "text": text})
    if entities:
        return embedder.embed_entities(conn, entities)
    return 0
