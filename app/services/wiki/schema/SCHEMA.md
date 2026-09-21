# LLM Wiki Schema

## 1. 页面类型

每个 Wiki 页面必须属于以下类型之一：

- `entity`：人物、组织、产品、系统、项目等具体实体
- `concept`：概念、方法、术语、技术原理
- `synthesis`：跨多个来源的综合摘要
- `comparison`：两个或多个对象的对比分析

## 2. 文件命名

- 使用 TitleCase，空格用 `-` 连接，例如：`LLM-Wiki.md`
- 中文标题可以保留中文，例如：`知识编译.md`
- 文件名必须与页面标题一致

## 3. Frontmatter

每个 Markdown 页面必须以 YAML frontmatter 开头：

```yaml
---
type: entity | concept | synthesis | comparison
title: 页面标题
aliases: []
sources: []
confidence: high | medium | low
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
---
```

## 4. 页面结构
正文必须包含以下部分：

1. `## 摘要`：不超过 5 句话
2. `## 正文`：结构化说明
3. `## 相关链接`：使用 `[[页面名]]`
4. `## 来源`：列出原始素材路径或 URL

## 5. 链接规则
- 内部链接统一使用 `[[页面名]]`
- 不允许创建空链接页面
- 如果引用了不存在的页面，必须在 `log.md `

## 6. 冲突处理
- 新信息与旧信息矛盾时，不允许直接覆盖
- 在页面中增加：
  ```markdown
  > [!warning] 冲突
  > 旧信息：...
  > 新信息：...
  > 来源：...
  ```
- 同时更新 `confidence` 为 `low`

## 7. 索引与日志
- `vault/index.md`：所有页面的索引
- `vault/log.md`：追加式操作日志，记录每次编译、更新、冲突

```text
这个文件是后面 LLM 编译知识时的“宪法”。第一步只要把它建好，不需要调用 LLM。
```