import json
import re
from datetime import date
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from app.schemas.wiki import WikiPage, WikiPageBatch
from app.services.wiki.ingestion.parsers import parse_source
from app.services.wiki.ingestion.parsers.models import SourceBatch
from app.services.wiki.ingestion.prompts import (
    BATCH_COMPILE_SYSTEM_PROMPT,
    COMPILE_SYSTEM_PROMPT,
    MERGE_COMPILE_SYSTEM_PROMPT,
    build_compile_user_prompt,
)


class WikiCompiler:
    """
    Wiki 编译器：把一份原始素材交给LLM，自动生成一个/多个Wiki页面并落地为md文件。
    流程：读取源文件 -> 构造Prompt -> LLM调用 -> 解析LLM返回JSON -> 写md知识库页面 -> 更新索引与日志
    """

    def __init__(
        self,
        llm_client,
        vault_dir: Path,
        schema_path: Path,
        *,
        batch_chars: int = 24_000,
        max_batches: int = 20,
    ) -> None:
        # LLM客户端实例，用来调用大模型对话接口
        self.llm_client = llm_client
        # 知识库输出目录，存放编译后的 .md wiki页面
        self.vault_dir = Path(vault_dir)
        # Wiki结构Schema文件路径，给LLM参考输出格式与约束
        self.schema_path = Path(schema_path)
        if batch_chars <= 0:
            raise ValueError("Wiki 表格批次字符数必须大于 0")
        if max_batches <= 0:
            raise ValueError("Wiki 表格最大批次数必须大于 0")
        self.batch_chars = batch_chars
        self.max_batches = max_batches

    def compile_file(self, source_path: Path) -> WikiPageBatch:
        """
        主入口：编译单个原始素材文件，输出一批Wiki页面并写入vault知识库
        :param source_path: 原始素材文件路径（raw目录下文档）
        :return: WikiPageBatch，本次编译产出的所有页面 + 编译备注
        """
        source_path = Path(source_path)
        parsed_source = parse_source(source_path, batch_chars=self.batch_chars)
        if len(parsed_source.batches) > self.max_batches:
            raise ValueError(
                f"表格被拆分为 {len(parsed_source.batches)} 个批次，"
                f"超过上限 {self.max_batches}；请拆分文件或调整 WIKI_COMPILE_MAX_BATCHES"
            )
        # 读取wiki schema，作为LLM输出规范
        schema = self.schema_path.read_text(encoding="utf-8")
        if parsed_source.kind == "table" and len(parsed_source.batches) > 1:
            batch = self._compile_large_table(parsed_source.batches, source_path, schema)
        else:
            source_batch = parsed_source.batches[0]
            batch = self._invoke_compile(
                schema=schema,
                source_path=str(source_path),
                source_text=source_batch.text,
                system_prompt=COMPILE_SYSTEM_PROMPT,
            )

        if parsed_source.kind == "table":
            batch.pages.extend(self._build_reference_pages(parsed_source.batches, source_path))
        self._validate_unique_pages(batch)
        # 将batch内所有页面写入vault目录md文件，更新索引和编译日志
        self._write_pages(batch, source_path)
        return batch

    def _invoke_compile(
        self,
        *,
        schema: str,
        source_path: str,
        source_text: str,
        system_prompt: str,
    ) -> WikiPageBatch:
        """调用一次模型并校验结构化输出。"""
        user_prompt = build_compile_user_prompt(
            schema=schema,
            source_path=source_path,
            source_text=source_text,
        )
        response = self.llm_client.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]
        )
        raw_output = self._response_text(response.content)
        return self._parse_output(raw_output)

    def _compile_large_table(
        self,
        source_batches: tuple[SourceBatch, ...],
        source_path: Path,
        schema: str,
    ) -> WikiPageBatch:
        """先逐批提炼大表，再将中间结果汇总成最终页面。"""
        intermediate: list[dict] = []
        for source_batch in source_batches:
            label = (
                f"{source_path}#工作表={source_batch.section_name}"
                f"&批次={source_batch.part_number}"
            )
            batch = self._invoke_compile(
                schema=schema,
                source_path=label,
                source_text=source_batch.text,
                system_prompt=BATCH_COMPILE_SYSTEM_PROMPT,
            )
            intermediate.append(batch.model_dump(mode="json"))

        merge_text = (
            "以下 JSON 数组是同一个表格文件各批次的中间提炼结果。"
            "请去重并合并为最终 Wiki 页面：\n\n"
            + json.dumps(intermediate, ensure_ascii=False)
        )
        return self._invoke_compile(
            schema=schema,
            source_path=str(source_path),
            source_text=merge_text,
            system_prompt=MERGE_COMPILE_SYSTEM_PROMPT,
        )

    @staticmethod
    def _build_reference_pages(
        source_batches: tuple[SourceBatch, ...], source_path: Path
    ) -> list[WikiPage]:
        """用程序直接生成表格明细页，避免 LLM 改写或遗漏原始行。"""
        pages: list[WikiPage] = []
        for source_batch in source_batches:
            title = (
                f"{source_path.stem}-{source_batch.section_name}-"
                f"明细-{source_batch.part_number:03d}"
            )
            row_range = f"第 {source_batch.row_start}–{source_batch.row_end} 行"
            pages.append(
                WikiPage(
                    type="reference",
                    title=title,
                    aliases=[],
                    summary=f"{source_path.name} 的 {source_batch.section_name} 工作表{row_range}。",
                    body=source_batch.detail_markdown or source_batch.text,
                    related=[],
                    sources=[str(source_path)],
                    confidence="high",
                    conflicts=[],
                )
            )
        return pages

    def _validate_unique_pages(self, batch: WikiPageBatch) -> None:
        """写盘前阻止重复标题或清理后文件名冲突造成静默覆盖。"""
        titles: set[str] = set()
        filenames: set[str] = set()
        for page in batch.pages:
            normalized_title = page.title.strip().casefold()
            if normalized_title in titles:
                raise ValueError(f"LLM 输出了重复的 Wiki 页面标题: {page.title}")
            titles.add(normalized_title)

            filename = self.page_path(page).name.casefold()
            if filename in filenames:
                raise ValueError(f"Wiki 页面文件名发生冲突: {page.title}")
            filenames.add(filename)

    @staticmethod
    def _response_text(content: object) -> str:
        """兼容模型返回纯字符串或 content block 列表。"""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict) and isinstance(block.get("text"), str):
                    parts.append(block["text"])
            if parts:
                return "\n".join(parts)
        raise ValueError("LLM 输出不包含可解析的文本内容")

    def _parse_output(self, raw_output: str) -> WikiPageBatch:
        """
        解析LLM返回的原始字符串，容错剥离markdown代码块标记，加载JSON并校验Pydantic模型
        :param raw_output: LLM返回原始文本
        :return: 校验完成的WikiPageBatch实例
        """
        text = raw_output.strip()
        # 容错：去掉LLM常见的 ```json ... ``` 代码块包裹符号
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            # JSON解析失败，抛出异常并携带原始LLM输出方便排错
            raise ValueError(f"LLM 输出不是合法 JSON: {exc}\n原始输出:\n{raw_output}") from exc
        # 使用Pydantic校验JSON结构，转成WikiPageBatch对象，字段类型自动校验
        return WikiPageBatch.model_validate(data)

    def _write_pages(self, batch: WikiPageBatch, source_path: Path) -> None:
        """
        批量写入本次编译生成的所有wiki页面，完成后更新索引、追加编译日志
        :param batch: 本次编译产出的页面批次对象
        :param source_path: 原始素材文件路径
        """
        # 确保知识库目录存在
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        # 循环写入每一个wiki页面md文件
        for page in batch.pages:
            self._write_single_page(page, source_path)
        # 重建全局wiki索引index.md
        self._update_index()
        # 追加本次编译记录到log.md
        self._append_log(batch, source_path)

    def _write_single_page(self, page: WikiPage, source_path: Path) -> None:
        """
        将单个WikiPage对象渲染成完整Markdown并写入vault目录
        :param page: 单条wiki页面结构体
        :param source_path: 原始素材路径
        """
        # 输出md文件路径，文件名使用页面标题
        target = self.page_path(page)
        # 构建YAML frontmatter头部元信息
        frontmatter = self._build_frontmatter(page, source_path)
        # 组装md文档各个模块
        body_parts = [
            frontmatter,
            f"## 摘要\n\n{page.summary}",
            f"## 正文\n\n{page.body}",
        ]
        # 存在相关页面链接，则追加【相关链接】板块
        if page.related:
            related_lines = "\n".join(f"- {link}" for link in page.related)
            body_parts.append(f"## 相关链接\n\n{related_lines}")
        # 存在冲突信息，则追加【冲突】板块
        if page.conflicts:
            conflict_lines = "\n".join(f"- {c}" for c in page.conflicts)
            body_parts.append(f"## 冲突\n\n{conflict_lines}")
        # 来源列表，无自定义来源则默认使用原始素材路径
        sources = page.sources or [str(source_path)]
        source_lines = "\n".join(f"- {s}" for s in sources)
        body_parts.append(f"## 来源\n\n{source_lines}")
        # 拼接所有模块并写入md文件
        target.write_text("\n\n".join(body_parts) + "\n", encoding="utf-8")

    def page_path(self, page: WikiPage) -> Path:
        """返回页面的安全落盘路径，阻止标题造成目录穿越。"""
        filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", page.title).strip(" .")
        filename = re.sub(r"-+", "-", filename)[:120].rstrip(" .")
        if not filename or filename in {".", ".."}:
            raise ValueError(f"Wiki 页面标题无法转换为安全文件名: {page.title!r}")
        return self.vault_dir / f"{filename}.md"

    def _build_frontmatter(self, page: WikiPage, source_path: Path) -> str:
        """
        构建md文件顶部YAML frontmatter元数据块
        :param page: wiki页面对象
        :param source_path: 原始素材路径
        :return: frontmatter字符串（---包裹的yaml）
        """
        today = date.today().isoformat()
        # 别名数组转为json字符串写入yaml
        aliases = json.dumps(page.aliases, ensure_ascii=False)
        sources = page.sources or [str(source_path)]
        sources_json = json.dumps(sources, ensure_ascii=False)
        return (
            "---\n"
            f"type: {page.type}\n"
            f"title: {page.title}\n"
            f"aliases: {aliases}\n"
            f"sources: {sources_json}\n"
            f"confidence: {page.confidence}\n"
            f"created_at: {today}\n"
            f"updated_at: {today}\n"
            "---"
        )

    def _update_index(self) -> None:
        """
        重建Wiki索引文件 index.md
        扫描vault下所有md，排除自身index.md，生成[[页面名]]双向链接列表
        """
        index_path = self.vault_dir / "index.md"
        # 获取所有md文件名（不带后缀stem），排除index.md本身，排序
        pages = sorted(
            p.stem for p in self.vault_dir.glob("*.md") if p.name not in {"index.md", "log.md"}
        )
        lines = ["# Wiki 索引", ""]
        lines.extend(f"- [[{name}]]" for name in pages)
        index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _append_log(self, batch: WikiPageBatch, source_path: Path) -> None:
        """
        追加本次编译记录到 log.md，记录日期、源文件、生成页面数量、页面名称类型、备注
        :param batch: 本次编译批次对象
        :param source_path: 原始素材文件路径
        """
        log_path = self.vault_dir / "log.md"
        today = date.today().isoformat()
        entry_lines = [
            f"## {today} · {source_path.name}",
            "",
            f"- 生成页面数：{len(batch.pages)}",
        ]
        entry_lines.extend(f"- 页面：{p.title} ({p.type})" for p in batch.pages)
        if batch.notes:
            entry_lines.append(f"- 备注：{batch.notes}")
        entry_lines.append("")
        # 追加写入模式 a，持续累加日志
        with log_path.open("a", encoding="utf-8") as f:
            f.write("\n".join(entry_lines) + "\n")
