from .config import settings
from .db import get_conn
from .embeddings import embed_query, embed_texts


def chunk_text(text: str, size: int | None = None, overlap: int | None = None) -> list[str]:
    """Split on paragraph boundaries, packing paragraphs into ~size-char chunks with overlap."""
    size = size or settings.chunk_size
    overlap = overlap if overlap is not None else settings.chunk_overlap

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        # A single huge paragraph gets hard-split
        while len(para) > size:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(para[:size])
            para = para[size - overlap :]

        if len(current) + len(para) + 2 <= size:
            current = f"{current}\n\n{para}" if current else para
        else:
            if current:
                chunks.append(current)
            tail = current[-overlap:] if overlap and current else ""
            current = f"{tail}\n\n{para}".strip() if tail else para

    if current:
        chunks.append(current)
    return chunks


def ingest(scope: str, source: str, text: str, replace: bool = True) -> int:
    """Chunk, embed and store a document. Returns the number of chunks stored."""
    if scope not in ("public", "private"):
        raise ValueError("scope must be 'public' or 'private'")

    chunks = chunk_text(text)
    if not chunks:
        return 0
    vectors = embed_texts(chunks)

    with get_conn() as conn:
        if replace:
            conn.execute(
                "DELETE FROM documents WHERE scope = %s AND source = %s", (scope, source)
            )
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO documents (scope, source, chunk_index, content, embedding)
                VALUES (%s, %s, %s, %s, %s)
                """,
                [
                    (scope, source, i, chunk, vec)
                    for i, (chunk, vec) in enumerate(zip(chunks, vectors))
                ],
            )
    return len(chunks)


def retrieve(scope: str, query: str, k: int | None = None) -> list[dict]:
    """Top-k chunks by cosine similarity, restricted to a single scope.

    The scope filter lives in SQL on purpose: Presentation mode can never see
    private rows, regardless of what the prompt or the user asks for.
    """
    k = k or settings.top_k
    qvec = embed_query(query)

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT source, chunk_index, content, 1 - (embedding <=> %s::vector) AS score
            FROM documents
            WHERE scope = %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (qvec, scope, qvec, k),
        ).fetchall()

    return [
        {"source": r[0], "chunk_index": r[1], "content": r[2], "score": float(r[3])}
        for r in rows
    ]
