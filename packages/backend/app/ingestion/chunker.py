import hashlib
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from app.ingestion.parsers import ParsedDocument, TextBlock


class Chunk(BaseModel):
    chunk_index: int
    content: str
    token_count: int
    chunk_hash: str
    location_meta: Dict[str, Any] = Field(default_factory=dict)
    anchor_label: str = ""


class Chunker:
    """
    Overlapping sliding window chunker preserving structural document anchors.
    Default: target ~400-500 words / 1500 chars with 200 char overlap.
    """

    def __init__(self, target_chars: int = 1500, overlap_chars: int = 200):
        self.target_chars = target_chars
        self.overlap_chars = overlap_chars

    def chunk_document(self, parsed_doc: ParsedDocument) -> List[Chunk]:
        chunks: List[Chunk] = []
        blocks = parsed_doc.blocks

        if not blocks:
            # Fallback if document has no structured blocks
            if parsed_doc.raw_text.strip():
                return self._chunk_plain_text(parsed_doc.raw_text)
            return []

        current_text_parts: List[str] = []
        current_len = 0
        current_pages: set = set()
        min_line: Optional[int] = None
        max_line: Optional[int] = None
        sections: set = set()
        extra_meta: Dict[str, Any] = {}

        chunk_index = 0

        for block in blocks:
            b_text = block.text.strip()
            if not b_text:
                continue

            # Update locators
            if block.page_number:
                current_pages.add(block.page_number)
            if block.line_start is not None:
                min_line = block.line_start if min_line is None else min(min_line, block.line_start)
            if block.line_end is not None:
                max_line = block.line_end if max_line is None else max(max_line, block.line_end)
            if block.section_title:
                sections.add(block.section_title)
            if block.extra_meta:
                extra_meta.update(block.extra_meta)

            current_text_parts.append(b_text)
            current_len += len(b_text)

            if current_len >= self.target_chars:
                chunk_text = "\n\n".join(current_text_parts).strip()
                chunks.append(self._create_chunk(
                    chunk_index=chunk_index,
                    text=chunk_text,
                    pages=current_pages,
                    min_line=min_line,
                    max_line=max_line,
                    sections=sections,
                    extra_meta=extra_meta,
                    filename=parsed_doc.metadata.get("filename", "")
                ))
                chunk_index += 1

                # Retain overlap from last part
                if len(current_text_parts) > 1 and len(current_text_parts[-1]) < self.overlap_chars:
                    current_text_parts = [current_text_parts[-1]]
                    current_len = len(current_text_parts[0])
                else:
                    current_text_parts = []
                    current_len = 0

                current_pages = set()
                min_line = None
                max_line = None
                sections = set()
                extra_meta = {}

        # Flush final remaining text
        if current_text_parts:
            chunk_text = "\n\n".join(current_text_parts).strip()
            if chunk_text:
                chunks.append(self._create_chunk(
                    chunk_index=chunk_index,
                    text=chunk_text,
                    pages=current_pages,
                    min_line=min_line,
                    max_line=max_line,
                    sections=sections,
                    extra_meta=extra_meta,
                    filename=parsed_doc.metadata.get("filename", "")
                ))

        return chunks

    def _chunk_plain_text(self, text: str) -> List[Chunk]:
        chunks = []
        step = max(1, self.target_chars - self.overlap_chars)
        idx = 0
        for i in range(0, len(text), step):
            sub = text[i:i + self.target_chars].strip()
            if sub:
                chunks.append(self._create_chunk(
                    chunk_index=idx,
                    text=sub,
                    pages=set(),
                    min_line=None,
                    max_line=None,
                    sections=set(),
                    extra_meta={},
                    filename=""
                ))
                idx += 1
        return chunks

    def _create_chunk(
        self,
        chunk_index: int,
        text: str,
        pages: set,
        min_line: Optional[int],
        max_line: Optional[int],
        sections: set,
        extra_meta: dict,
        filename: str
    ) -> Chunk:
        # Approximate tokens
        words = text.split()
        token_count = max(1, int(len(text) / 4))

        # Build human-readable anchor
        anchor_parts = []
        if pages:
            sorted_pages = sorted(list(pages))
            if len(sorted_pages) == 1:
                anchor_parts.append(f"Page {sorted_pages[0]}")
            else:
                anchor_parts.append(f"Pages {sorted_pages[0]}-{sorted_pages[-1]}")
        elif min_line is not None and max_line is not None:
            if filename:
                anchor_parts.append(f"{filename}:{min_line}-{max_line}")
            else:
                anchor_parts.append(f"Lines {min_line}-{max_line}")
        elif sections:
            anchor_parts.append(f"Section: {list(sections)[0]}")

        anchor_label = " • ".join(anchor_parts) if anchor_parts else f"Chunk #{chunk_index + 1}"

        loc_meta = {
            "pages": sorted(list(pages)) if pages else [],
            "line_start": min_line,
            "line_end": max_line,
            "sections": list(sections),
            "anchor_label": anchor_label,
            **extra_meta
        }

        chunk_hash = hashlib.sha256(f"{chunk_index}:{text}".encode("utf-8")).hexdigest()

        return Chunk(
            chunk_index=chunk_index,
            content=text,
            token_count=token_count,
            chunk_hash=chunk_hash,
            location_meta=loc_meta,
            anchor_label=anchor_label
        )
