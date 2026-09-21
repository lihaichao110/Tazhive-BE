"""手动触发一次 Wiki 编译，用于本地验证。

用法：
    uv run python scripts/wiki_ingest.py your-file.md
"""

import sys
from pathlib import Path

from sqlmodel import Session

from app.services.database import engine
from app.services.llm.registry import default_registry
from app.services.wiki.service import WikiService


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/wiki_ingest.py <raw-relative-source-file>")
        sys.exit(1)

    source = Path(sys.argv[1])
    service = WikiService()
    llm_client = default_registry.get_model()

    with Session(engine) as db:
        result = service.compile_file(source, llm_client, db=db)
    print(f"Source: {result['source']}")
    print(f"Pages: {result['page_count']}")
    for title in result["pages"]:
        print(f"  - {title}")
    print(f"Indexed documents: {len(result['indexed_document_ids'])}")
    if result["notes"]:
        print(f"Notes: {result['notes']}")


if __name__ == "__main__":
    main()
