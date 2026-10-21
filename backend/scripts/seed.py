"""Load every .md/.txt file under data/public and data/private into the vector store.

Usage (from the backend/ directory):
    python -m scripts.seed
"""

from pathlib import Path

from app import rag
from app.db import close_pool, init_pool

DATA = Path(__file__).resolve().parent.parent / "data"


def main() -> None:
    init_pool()
    try:
        for scope in ("public", "private"):
            folder = DATA / scope
            if not folder.exists():
                continue
            for path in sorted(folder.glob("*")):
                if path.suffix.lower() not in {".md", ".txt"}:
                    continue
                n = rag.ingest(scope, path.name, path.read_text(encoding="utf-8"))
                print(f"[{scope}] {path.name}: {n} chunks")
    finally:
        close_pool()


if __name__ == "__main__":
    main()
