import pytest
from app.ingestion.parsers import ParsedDocument, TextBlock
from app.ingestion.chunker import Chunker, Chunk


def test_chunker_sliding_window():
    chunker = Chunker(target_chars=200, overlap_chars=50)

    blocks = [
        TextBlock(text="Paragraph 1 with interesting content about search systems.", line_start=1, line_end=2),
        TextBlock(text="Paragraph 2 explaining BM25 inverted lexical indexing algorithms.", line_start=3, line_end=4),
        TextBlock(text="Paragraph 3 discussing reciprocal rank fusion across multiple retrieval stages.", line_start=5, line_end=6),
        TextBlock(text="Paragraph 4 detailing dense vector semantic nearest neighbor search.", line_start=7, line_end=8),
    ]

    doc = ParsedDocument(
        title="Search Engine Theory",
        raw_text="Full text...",
        blocks=blocks,
        mime_type="text/markdown",
        metadata={"filename": "search_theory.md"}
    )

    chunks = chunker.chunk_document(doc)
    assert len(chunks) >= 2
    for i, chunk in enumerate(chunks):
        assert chunk.chunk_index == i
        assert len(chunk.content) > 0
        assert chunk.chunk_hash is not None
        assert "search_theory.md:" in chunk.anchor_label or "Lines" in chunk.anchor_label


def test_chunker_page_anchors():
    chunker = Chunker(target_chars=100, overlap_chars=20)

    blocks = [
        TextBlock(text="PDF Page 1 text talking about privacy.", page_number=1),
        TextBlock(text="PDF Page 2 text describing local AI model execution.", page_number=2),
    ]

    doc = ParsedDocument(
        title="Privacy Whitepaper",
        raw_text="...",
        blocks=blocks,
        mime_type="application/pdf",
        metadata={"filename": "whitepaper.pdf"}
    )

    chunks = chunker.chunk_document(doc)
    assert len(chunks) >= 1
    assert any("Page" in c.anchor_label for c in chunks)
