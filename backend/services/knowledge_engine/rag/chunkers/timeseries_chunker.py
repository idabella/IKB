from typing import Any, Dict, List

from backend.services.knowledge_engine.rag.chunkers.base_chunker import BaseChunker, Chunk


class TimeseriesChunker(BaseChunker):
    """
    Chunker for time-series style text (sensor logs, CSV exports, trend reports).
    Splits on timestamp-like line boundaries when present, otherwise falls back to
    fixed-size windows.
    """

    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 80) -> None:
        super().__init__()
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk(self, text: str, metadata: Dict[str, Any]) -> List[Chunk]:
        lines = [line for line in text.splitlines() if line.strip()]
        if not lines:
            return []

        chunks: List[Chunk] = []
        buffer: List[str] = []
        buffer_len = 0

        for line in lines:
            line_len = len(line)
            if buffer and buffer_len + line_len > self.chunk_size:
                chunk_text = "\n".join(buffer)
                chunks.append(
                    Chunk(
                        text=chunk_text,
                        metadata={**metadata, "chunk_type": "timeseries"},
                    )
                )
                overlap_lines = max(1, self.chunk_overlap // max(1, line_len))
                buffer = buffer[-overlap_lines:]
                buffer_len = sum(len(item) for item in buffer)

            buffer.append(line)
            buffer_len += line_len

        if buffer:
            chunks.append(
                Chunk(
                    text="\n".join(buffer),
                    metadata={**metadata, "chunk_type": "timeseries"},
                )
            )

        return chunks
