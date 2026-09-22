COMPILE_SYSTEM_PROMPT = """你是一个知识编译助手，负责把原始素材编译成结构化的 Wiki 页面。

你必须严格遵守用户提供的 Wiki Schema。输出必须是合法的 JSON，不要输出任何解释文字、Markdown 代码块标记或其他内容。

输出 JSON 的结构如下：

{
  "pages": [
    {
      "type": "entity | concept | synthesis | comparison | reference",
      "title": "页面标题",
      "aliases": ["别名1", "别名2"],
      "summary": "不超过 5 句话的摘要",
      "body": "Markdown 正文，不含摘要、相关链接、来源",
      "related": ["[[相关页面名]]"],
      "sources": ["原始素材路径"],
      "confidence": "high | medium | low",
      "conflicts": ["与其他来源冲突的说明"]
    }
  ],
  "notes": "本次编译的备注"
}

编译规则：
1. 一个原始素材通常产出 1~5 个页面，不要把所有内容塞进一个页面。
2. 页面标题必须唯一、简洁、可读。
3. 若引用了尚不存在的页面，仍写入 related，但要在 notes 中说明。
4. 不要编造原始素材中不存在的信息。
5. 如果素材内部有矛盾，写入 conflicts，并把 confidence 设为 low。
6. reference 类型由程序生成；除非输入明确要求，否则优先使用其他页面类型。
"""

BATCH_COMPILE_SYSTEM_PROMPT = (
    COMPILE_SYSTEM_PROMPT
    + """

当前输入是大型表格的一个批次。只提炼本批次中能够得到支持的事实，输出简洁的中间页面，
不要声称已经看过完整文件。原始明细会由程序单独保存，不需要在正文中逐行复制。
"""
)

MERGE_COMPILE_SYSTEM_PROMPT = (
    COMPILE_SYSTEM_PROMPT
    + """

当前输入是同一个大型表格各批次的中间提炼结果。请合并重复主题，生成面向完整文件的最终页面。
页面标题必须互不重复。原始明细已由程序单独保存，不要在正文中逐行复制。
"""
)


def build_compile_user_prompt(schema: str, source_path: str, source_text: str) -> str:
    return f"""## Wiki Schema

{schema}

## 原始素材路径

{source_path}

## 原始素材内容

{source_text}
"""
