"""Tests for db_wiki.search — embedder, FTS5, and hybrid search."""
import sqlite3
import struct
import sys
from unittest.mock import MagicMock, patch

import pytest

from db_wiki.core.config import EmbeddingConfig
from db_wiki.core.store import init_schema


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def search_db():
    """In-memory SQLite with schema + sqlite-vec loaded."""
    import sqlite_vec

    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    init_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def config_local():
    return EmbeddingConfig(provider="local", model_name="all-MiniLM-L6-v2", dimensions=384)


@pytest.fixture
def config_openai():
    return EmbeddingConfig(provider="openai", openai_dimensions=1536)


# ---------------------------------------------------------------------------
# Task 1: Embedder tests
# ---------------------------------------------------------------------------


class TestSerializeEmbedding:
    def test_pack_floats_to_bytes(self):
        from db_wiki.search.embedder import serialize_embedding

        result = serialize_embedding([0.1, 0.2, 0.3])
        assert isinstance(result, bytes)
        assert len(result) == 3 * 4  # 3 floats * 4 bytes each

    def test_roundtrip(self):
        from db_wiki.search.embedder import serialize_embedding

        values = [1.0, 2.0, 3.0, 4.0]
        packed = serialize_embedding(values)
        unpacked = list(struct.unpack(f"{len(values)}f", packed))
        assert unpacked == pytest.approx(values)


class TestEmbedderInit:
    def test_no_torch_import_at_init(self, config_local):
        """Embedder.__init__ must NOT import sentence_transformers or torch."""
        # Remove from sys.modules if cached
        for mod in list(sys.modules):
            if mod.startswith("sentence_transformers") or mod == "torch":
                del sys.modules[mod]

        from db_wiki.search.embedder import Embedder

        embedder = Embedder(config_local)
        assert embedder._model is None
        assert not embedder._ready
        assert "sentence_transformers" not in sys.modules
        assert "torch" not in sys.modules

    def test_dimensions_local(self, config_local):
        from db_wiki.search.embedder import Embedder

        embedder = Embedder(config_local)
        assert embedder.dimensions == 384

    def test_dimensions_openai(self, config_openai):
        from db_wiki.search.embedder import Embedder

        embedder = Embedder(config_openai)
        assert embedder.dimensions == 1536

    def test_vec_table_name(self, config_local):
        from db_wiki.search.embedder import Embedder

        embedder = Embedder(config_local)
        assert embedder.vec_table_name == "vec_embeddings_384"


class TestEmbedderEnsureReady:
    def test_lazy_loads_sentence_transformers(self, config_local):
        from db_wiki.search.embedder import Embedder

        embedder = Embedder(config_local)

        mock_model = MagicMock()
        with patch(
            "db_wiki.search.embedder.SentenceTransformer",
            create=True,
        ) as mock_cls:
            # Patch the lazy import inside ensure_ready
            import db_wiki.search.embedder as emb_module

            with patch.dict("sys.modules", {"sentence_transformers": MagicMock()}):
                mock_st = sys.modules["sentence_transformers"]
                mock_st.SentenceTransformer = mock_cls
                mock_cls.return_value = mock_model
                embedder.ensure_ready()

        assert embedder._ready
        assert embedder._model is mock_model

    def test_unknown_provider_raises(self):
        from db_wiki.search.embedder import Embedder

        config = EmbeddingConfig(provider="unknown")
        embedder = Embedder(config)
        with pytest.raises(ValueError, match="Unknown embedding provider"):
            embedder.ensure_ready()


class TestEmbedderEncode:
    def test_encode_returns_float_lists(self, config_local):
        """Mocked encode returns vectors with correct dimensions."""
        from db_wiki.search.embedder import Embedder

        embedder = Embedder(config_local)
        mock_model = MagicMock()

        # Create a mock numpy-like array that supports .tolist()
        class FakeArray:
            def __init__(self, data):
                self._data = data

            def tolist(self):
                return self._data

        fake_result = [FakeArray([0.1] * 384), FakeArray([0.2] * 384)]
        mock_model.encode.return_value = fake_result
        embedder._model = mock_model
        embedder._ready = True

        result = embedder.encode(["text1", "text2"])
        assert len(result) == 2
        assert len(result[0]) == 384
        assert all(isinstance(v, float) for v in result[0])


def _fake_vectors(n: int, dim: int, fill: float = 0.1) -> list:
    """Create fake numpy-like array results for mocked model.encode()."""

    class FakeArray:
        def __init__(self, data):
            self._data = data

        def tolist(self):
            return self._data

    return [FakeArray([fill + i * 0.01] * dim) for i in range(n)]


class TestEmbedderEmbedEntities:
    def test_embed_entities_inserts_vectors(self, search_db, config_local):
        """embed_entities should insert vectors into vec table."""
        from db_wiki.search.embedder import Embedder

        embedder = Embedder(config_local)
        mock_model = MagicMock()
        mock_model.encode.return_value = _fake_vectors(2, 384)
        embedder._model = mock_model
        embedder._ready = True

        entities = [
            {"entity_type": "table", "entity_id": 1, "text": "Orders table"},
            {"entity_type": "table", "entity_id": 2, "text": "Customers table"},
        ]
        count = embedder.embed_entities(search_db, entities)
        assert count == 2

        # Verify rows exist
        row_count = search_db.execute("SELECT COUNT(*) FROM vec_embeddings_384").fetchone()[0]
        assert row_count == 2

    def test_embed_entities_empty_list(self, search_db, config_local):
        from db_wiki.search.embedder import Embedder

        embedder = Embedder(config_local)
        count = embedder.embed_entities(search_db, [])
        assert count == 0

    def test_embed_entities_creates_vec_table(self, search_db, config_local):
        """init_vec_table should be called to create the table if needed."""
        from db_wiki.search.embedder import Embedder

        embedder = Embedder(config_local)
        mock_model = MagicMock()
        mock_model.encode.return_value = _fake_vectors(1, 384)
        embedder._model = mock_model
        embedder._ready = True

        entities = [{"entity_type": "table", "entity_id": 1, "text": "test"}]
        embedder.embed_entities(search_db, entities)

        # Table should exist now
        exists = search_db.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='vec_embeddings_384'"
        ).fetchone()[0]
        assert exists == 1


class TestEmbedderSearchSimilar:
    def test_search_similar_returns_tuples(self, search_db, config_local):
        """search_similar returns (entity_type, entity_id, distance) tuples."""
        from db_wiki.search.embedder import Embedder

        embedder = Embedder(config_local)
        mock_model = MagicMock()
        # Use deterministic vectors for insert and query
        mock_model.encode.side_effect = [
            _fake_vectors(2, 384, fill=0.1),  # embed_entities call
            _fake_vectors(1, 384, fill=0.1),  # search_similar query call
        ]
        embedder._model = mock_model
        embedder._ready = True

        entities = [
            {"entity_type": "table", "entity_id": 1, "text": "close to query"},
            {"entity_type": "table", "entity_id": 2, "text": "far from query"},
        ]
        embedder.embed_entities(search_db, entities)
        results = embedder.search_similar(search_db, "close to query", limit=10)

        assert len(results) >= 1
        # Each result is (entity_type, entity_id, distance)
        assert results[0][0] == "table"
        assert isinstance(results[0][1], int)
        assert isinstance(results[0][2], float)


class TestEmbedderOpenAIDimensions:
    def test_openai_uses_1536_dimensions(self, config_openai):
        from db_wiki.search.embedder import Embedder

        embedder = Embedder(config_openai)
        assert embedder.dimensions == 1536
        assert embedder.vec_table_name == "vec_embeddings_1536"
