from typing import Literal

from pydantic import BaseModel, Field

PageType = Literal["entity", "concept", "synthesis", "comparison", "reference"]


class WikiPage(BaseModel):
    """LLM 编译出的单个 Wiki 页面。"""

    type: PageType
    title: str = Field(..., description="页面标题，也是文件名（TitleCase 或中文）")
    aliases: list[str] = Field(default_factory=list)
    summary: str = Field(..., description="不超过 5 句话的摘要")
    body: str = Field(..., description="Markdown 正文，不含摘要、相关链接、来源")
    related: list[str] = Field(
        default_factory=list,
        description="相关页面的 [[页面名]]，可以指向尚未创建的页面",
    )
    sources: list[str] = Field(
        default_factory=list,
        description="原始素材路径或 URL",
    )
    confidence: Literal["high", "medium", "low"] = "medium"
    conflicts: list[str] = Field(
        default_factory=list,
        description="与其他来源冲突的信息说明，没有则为空",
    )


class WikiPageBatch(BaseModel):
    """一次编译的产物，包含多个页面。"""

    pages: list[WikiPage] = Field(default_factory=list)
    notes: str = Field(default="", description="编译过程中的备注，写入 log.md")
