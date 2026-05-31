"""Testes para scripts/index_knowledge.py — chunking e serialização."""
import json

from scripts.index_knowledge import chunk_text


class TestChunkText:
    def test_basic_chunking(self):
        content = "A" * 2500
        chunks = chunk_text(content, "test.txt", size=1000, overlap=200)
        # 0-1000, 800-1800, 1600-2500, 2400-2500 = 4 chunks
        assert len(chunks) == 4
        assert all(c["source"] == "test.txt" for c in chunks)

    def test_overlap(self):
        content = "A" * 1500
        chunks = chunk_text(content, "test.txt", size=1000, overlap=200)
        assert len(chunks) == 2
        # Segundo chunk começa em 800, então pega 800-1500 = 700 chars
        assert len(chunks[1]["content"]) == 700

    def test_metadata_has_source_and_index(self):
        content = "Conteúdo de teste"
        chunks = chunk_text(content, "doc.pdf", size=1000, overlap=200)
        assert chunks[0]["metadata"]["source"] == "doc.pdf"
        assert chunks[0]["metadata"]["chunk_index"] == 0

    def test_metadata_with_apostrophe_serializes_correctly(self):
        """Metadata com apóstrofo deve serializar corretamente via json.dumps."""
        content = "A paróquia d'água viva"
        chunks = chunk_text(content, "paes_d'agua.pdf", size=1000, overlap=200)
        # json.dumps não quebra com apóstrofo (ao contrário de str().replace("'", '"'))
        metadata_json = json.dumps(chunks[0]["metadata"])
        parsed = json.loads(metadata_json)
        assert parsed["source"] == "paes_d'agua.pdf"

    def test_empty_content_produces_no_chunks(self):
        chunks = chunk_text("", "empty.txt")
        assert chunks == []

    def test_whitespace_only_produces_no_chunks(self):
        chunks = chunk_text("   \n  \t  ", "ws.txt")
        assert chunks == []
