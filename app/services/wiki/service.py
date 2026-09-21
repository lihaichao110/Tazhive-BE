from pathlib import Path

from sqlmodel import Session

from app.core.config import settings
from app.services.wiki.indexing.service import index_wiki_pages
from app.services.wiki.ingestion.pipeline import WikiCompiler


class WikiService:
    """LLM Wiki 对外入口：状态查询、资料编译与向量索引。"""

    def __init__(self) -> None:
        # 从全局配置读取各个目录、文件路径，转为Path对象方便文件操作
        self.data_dir = Path(settings.wiki_data_dir)  # wiki根数据目录
        self.raw_dir = Path(settings.wiki_raw_dir)  # 原始资料存放目录（待处理文件）
        self.vault_dir = Path(settings.wiki_vault_dir)  # 知识库目录，存放处理完成的md文档
        self.schema_path = Path(
            settings.wiki_schema_path
        )  # wiki结构Schema文件路径（给LLM用的模型描述）

        # 初始化时自动确保需要的文件夹存在
        self.ensure_dirs()

    def ensure_dirs(self) -> None:
        """
        保证必要目录存在，不存在则创建；已存在不会抛出异常
        parents=True：递归创建多层父目录
        exist_ok=True：目录已存在时不报错
        """
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.vault_dir.mkdir(parents=True, exist_ok=True)

    def get_status(self) -> dict:
        """
        获取Wiki知识库整体运行状态信息
        返回字典，包含路径、目录是否存在、文件数量等监控信息
        """
        # 递归遍历raw目录下所有文件；目录不存在则返回空列表
        raw_files = list(self.raw_dir.rglob("*")) if self.raw_dir.exists() else []
        # 递归查找vault目录下所有 .md 知识库页面
        vault_pages = list(self.vault_dir.rglob("*.md")) if self.vault_dir.exists() else []

        return {
            "data_dir": str(self.data_dir),
            "raw_dir": str(self.raw_dir),
            "vault_dir": str(self.vault_dir),
            "schema_path": str(self.schema_path),
            "raw_dir_exists": self.raw_dir.exists(),  # 原始目录是否存在
            "vault_dir_exists": self.vault_dir.exists(),  # 知识库目录是否存在
            "schema_exists": self.schema_path.exists(),  # schema定义文件是否存在
            "raw_file_count": len(
                [p for p in raw_files if p.is_file()]
            ),  # raw下文件总数（排除文件夹）
            "vault_page_count": len(vault_pages),  # vault下md文档数量
        }

    def get_schema(self) -> str:
        """
        读取Wiki的Schema文本内容
        如果schema文件不存在，抛出文件不存在异常
        返回：schema文件完整文本(utf-8编码)
        """
        if not self.schema_path.exists():
            raise FileNotFoundError(f"Wiki schema 找不到: {self.schema_path}")
        # 以utf8读取schema文件内容返回
        return self.schema_path.read_text(encoding="utf-8")

    def resolve_source(self, source_path: str | Path) -> Path:
        """只允许读取 raw 目录内的源文件。"""
        raw_root = self.raw_dir.resolve()
        candidate = Path(source_path)
        if not candidate.is_absolute():
            candidate = raw_root / candidate
        candidate = candidate.resolve()
        if not candidate.is_relative_to(raw_root):
            raise ValueError("Wiki 源文件必须位于 raw 目录内")
        if not candidate.is_file():
            raise FileNotFoundError(f"未找到资源: {candidate}")
        return candidate

    def compile_file(
        self,
        source_path: str | Path,
        llm_client,
        db: Session | None = None,
    ) -> dict:
        """把一份原始素材编译进 vault，并可选地写入向量库。"""
        source_path = self.resolve_source(source_path)

        compiler = WikiCompiler(
            llm_client=llm_client,
            vault_dir=self.vault_dir,
            schema_path=self.schema_path,
        )
        batch = compiler.compile_file(source_path)
        page_paths = [compiler.page_path(page) for page in batch.pages]
        indexed_document_ids = (
            index_wiki_pages(page_paths, vault_dir=self.vault_dir, db=db) if db is not None else []
        )

        return {
            "source": str(source_path),
            "page_count": len(batch.pages),
            "pages": [p.title for p in batch.pages],
            "page_paths": [str(path) for path in page_paths],
            "indexed_document_ids": indexed_document_ids,
            "notes": batch.notes,
        }
