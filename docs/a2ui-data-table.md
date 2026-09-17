# data_query 意图的数据表格卡片（A2UI v0.9）

用户询问业务数据统计问题（「这个月有多少笔投保单」「投保量排前三的方案」）时，
后端会识别为 `data_query` 意图，由服务端生成 SQL、经白名单校验后只读执行，
并把查询结果以 A2UI v0.9 表格卡片的形式放在助手回复正文里。本文是前后端之间
关于 `DataTable` 组件的契约说明；信封格式、围栏解析方式与
`a2ui-plan-cards.md` 完全一致，这里只说明差异。

## 一、消息形态

与方案卡片一致：一句自然语言总结 + 空行 + ```a2ui 围栏。围栏同样是 SSE 流的
最后一段正文增量，前端沿用「累积 `delta.content` 到结束再解析」的现有做法。

- `surfaceId`：**每轮唯一**，形如 `data_table_9c2e41ab`。
- `catalogId`：与方案卡片相同（`settings.plan_show_catalog_id`，默认 A2UI 官方
  基本目录）。前端把 `DataTable` 组件注册进同一 catalog 即可。
- 固定三条命令、顺序固定：`createSurface` → `updateComponents` → `updateDataModel`，
  每条命令都带 `"version": "v0.9"`。

单标量结果（1 行 1 列，如「共 12 款」）**不下发卡片**，只回正文。

## 二、DataTable 组件

`updateComponents` 的 `components` 数组只有一个根组件，扁平邻接表没有子组件：

```json
{
  "id": "root",
  "component": "DataTable",
  "columns": ["group_name", "total"],
  "rows": [["鸿利悠享2.0两全保险（分红型）", "23"], ["鑫福人生年金保险", "11"]],
  "truncated": false
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | 固定 `root` |
| `component` | string | 固定 `DataTable` |
| `columns` | string[] | 列名（SQL 结果的原始列名或别名），最多 8 列 |
| `rows` | string[][] | 行数据，**所有单元格已转字符串**（含数字），每行与 `columns` 对齐，最多 20 行 |
| `truncated` | boolean | `true` 表示实际结果超过 20 行，表格只展示前 20 行 |

## 三、updateDataModel

```json
{
  "surfaceId": "data_table_9c2e41ab",
  "path": "/ui",
  "value": { "total": 27, "truncated": true }
}
```

`total` 是查询的实际总行数（截断前的受限行数上限内），`truncated` 与组件上
的同名字段一致；前端可用来渲染「共 27 条，仅展示前 20 条」。

## 四、渲染建议

- 数字右对齐、文本左对齐可以按 `columns` 的语义（后端无法保证列类型元信息）。
- 超过 8 列被裁掉时，正文总结仍包含关键数字，可提示用户细化查询列。
- 前端未注册 `DataTable` 组件时，X-Card 会把未知组件渲染成占位文本；此时正文
  里的自然语言总结仍然完整，不阻塞功能使用。
