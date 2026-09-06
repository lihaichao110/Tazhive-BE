from pathlib import Path
from langchain_community.document_loaders import TextLoader, PyPDFLoader, Docx2txtLoader
from app.core.logging import logger

def load_document(file_path: str) -> list[str]:
    """加载文档并返回纯文本列表（按页或整个）"""
    path = Path(file_path)
    ext = path.suffix.lower()
    if ext in [".txt", ".md"]:
        loader = TextLoader(str(path), encoding="utf-8")
        docs = loader.load()
        return [doc.page_content for doc in docs]
    elif ext == ".pdf":
        loader = PyPDFLoader(str(path))
        docs = loader.load()
        return [doc.page_content for doc in docs]
    elif ext == ".docx":
        loader = Docx2txtLoader(str(path))
        docs = loader.load()
        return [doc.page_content for doc in docs]
    else:
        raise ValueError(f"不支持的文件类型: {ext}")