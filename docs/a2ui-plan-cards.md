# insurance 意图的方案卡片（A2UI v0.9）

用户表达投保意向（「我想买保险」「你们有哪些保险产品在售」）时，后端会识别为
`insurance` 意图，查询 `plan_shows` 表里的在售方案，并把卡片以 A2UI v0.9 命令的
形式放在助手回复正文里。本文是前后端之间的契约说明。

## 一、消息形态

助手回复 = 一句自然语言说明 + 空行 + ```a2ui 围栏：

````
以下是我们当前在售的 25 款保障方案，涵盖寿险、健康、年金、万能四类，您可以逐张查看。

```a2ui
{"surfaceId":"insurance_plans_7f3a91c2","commands":[ ... ]}
```
````

围栏前面有说明文字，因此**请用正则提取围栏**，不要用 `startsWith` 判断：

```ts
const A2UI_FENCE = /```a2ui\s*([\s\S]*?)```/
const match = A2UI_FENCE.exec(message.content)
if (match) {
  const envelope: { surfaceId: string; commands: XAgentCommand_v0_9[] } = JSON.parse(match[1])
}
```

SSE 流式过程中，围栏是**最后一段正文增量**：它之后才是 `finish_reason: "stop"`
的帧和 `data: [DONE]`。也就是说前端沿用「累积 `delta.content` 到结束再解析」的
现有做法即可，不需要新增帧类型。

## 二、信封形状

与你现有 mock（`createInsuranceCardEnvelope`）完全一致，固定三条命令、顺序固定：

| 命令 | 作用 |
| --- | --- |
| `createSurface` | 创建 surface，携带 `surfaceId` 与 `catalogId` |
| `updateComponents` | 下发扁平邻接表的全部组件 |
| `updateDataModel` | 初始化 `/ui`，目前只有 `{"total": 方案数}`，可选使用 |

- `surfaceId`：**每轮唯一**，形如 `insurance_plans_7f3a91c2`。同一会话里两轮
  保险问答是两个不同 surface，前端按消息渲染各自的 `XCard.Box` 不会互相覆盖。
- 每条命令都带 `"version": "v0.9"`（A2UI 规范硬性要求）。

单张方案卡的真实输出（示例数据，实际是 25 条）：

```json
{
  "surfaceId": "insurance_plans_7f3a91c2",
  "commands": [
    {
      "version": "v0.9",
      "createSurface": {
        "surfaceId": "insurance_plans_7f3a91c2",
        "catalogId": "https://a2ui.org/specification/v0_9/basic_catalog.json"
      }
    },
    {
      "version": "v0.9",
      "updateComponents": {
        "surfaceId": "insurance_plans_7f3a91c2",
        "components": [
          { "id": "root", "component": "PlanList", "children": ["plan_G0264"] },
          {
            "id": "plan_G0264",
            "component": "PlanCard",
            "groupCode": "G0264",
            "groupName": "鸿利悠享2.0两全保险（分红型）",
            "title": "寿险",
            "hasSale": "2",
            "children": ["plan_G0264_img", "plan_G0264_points", "plan_G0264_act"]
          },
          {
            "id": "plan_G0264_img",
            "component": "PlanImage",
            "url": "https://wcins.cathaylife.cn/storage/insapl/imageFile/AYT_1762219972270.png",
            "altText": "鸿利悠享2.0两全保险（分红型）"
          },
          {
            "id": "plan_G0264_points",
            "component": "PlanPoints",
            "items": ["幸福晚年加厚度", "健康保障有力度", "品质晚年享温度", "灵活权益多维度"]
          },
          {
            "id": "plan_G0264_act",
            "component": "PlanActions",
            "children": ["plan_G0264_pre", "plan_G0264_apply"]
          },
          {
            "id": "plan_G0264_pre",
            "component": "PlanActionButton",
            "text": "预核保",
            "backgroundColor": "#699bf6",
            "color": "#ffffff",
            "borderRadius": "6px",
            "action": {
              "event": {
                "name": "plan_pre_underwrite",
                "context": {
                  "group_code": "G0264",
                  "group_name": "鸿利悠享2.0两全保险（分红型）",
                  "title": "寿险",
                  "insur_list": ["AYR", "AYS", "AYT"]
                }
              }
            }
          },
          {
            "id": "plan_G0264_apply",
            "component": "PlanActionButton",
            "text": "正式投保",
            "backgroundColor": "#028550",
            "color": "#ffffff",
            "borderRadius": "6px",
            "action": {
              "event": {
                "name": "plan_apply",
                "context": {
                  "group_code": "G0264",
                  "group_name": "鸿利悠享2.0两全保险（分红型）",
                  "title": "寿险",
                  "insur_list": ["AYR", "AYS", "AYT"]
                }
              }
            }
          }
        ]
      }
    },
    {
      "version": "v0.9",
      "updateDataModel": {
        "surfaceId": "insurance_plans_7f3a91c2",
        "path": "/ui",
        "value": { "total": 1 }
      }
    }
  ]
}
```

## 三、组件契约

组件名是业务专用的，需要在 `registerCatalog` 注册的目录里全部实现（目录文件见
`docs/catalogs/plan_show_catalog.json`，可直接拿去用）。

| 组件 | props | 说明 |
| --- | --- | --- |
| `PlanList` | `children: string[]` | 根容器，垂直单列（当前不做分类 Tab） |
| `PlanCard` | `groupCode`, `groupName`, `title`, `hasSale`, `children: string[]` | 单张方案卡；展示数据都在 props 上，子组件只管排版 |
| `PlanImage` | `url`, `altText` | 方案配图；源数据缺图时该组件不下发 |
| `PlanPoints` | `items: string[]` | 卖点；源数据的 CRLF 多行文案已按行拆好；无卖点时不下发 |
| `PlanActions` | `children: string[]` | 按钮容器 |
| `PlanActionButton` | `text`, `backgroundColor`, `color`, `borderRadius`, `action` | 两个按钮共用同一组件 |

边界情况（已按「不留空块」处理，前端不必兜底）：

- `PlanCard.children` 只包含**实际存在**的子组件 id：缺图就没有 `PlanImage`，
  无卖点就没有 `PlanPoints`，最小情况是 `["plan_xxx_act"]`。
- 组件 id 由 `groupCode` 拼成并做了字符清洗（`G-0264/x` → `plan_G_0264_x`）。
- `hasSale` 原样透传源数据的 `"1"`/`"2"`（语义尚未确认），是否置灰或打标签由
  前端决定；后端目前**不做过滤**，25 条方案全部下发。

## 四、按钮与 action 契约

| 文案 | backgroundColor | color | borderRadius | `action.event.name` |
| --- | --- | --- | --- | --- |
| 预核保 | `#699bf6` | `#ffffff` | `6px` | `plan_pre_underwrite` |
| 正式投保 | `#028550` | `#ffffff` | `6px` | `plan_apply` |

`action.event.context` 里是**字面量**而不是 `{ path }` 绑定，所以点击时 X-Card
原样透传，`onAction` 里直接取到值：

```ts
const handleAction = (payload: ActionPayload) => {
  if (payload.name === 'plan_pre_underwrite' || payload.name === 'plan_apply') {
    const { group_code, group_name, title, insur_list } = payload.context
    // 跳转预核保/投保页，或把这些字段回传给 Agent 继续对话
  }
}
```

`insur_list` 是险种代码数组（如 `["AYR","AYS","AYT"]`），投保与预核保需要它。
`plan_shows` 表里**没有详情页 URL**，所以两个按钮不携带链接，去向由前端决定。

## 五、历史消息重放

落库的 assistant 消息 content 里**包含同一段围栏**，所以：

- `GET /api/v1/threads/{thread_id}/messages` 拿到的历史消息，用同一套正则解析
  就能复现卡片；
- 只有实时流和历史消息两条路径，卡片内容同形，不需要维护两套渲染逻辑。

注意围栏**不会进入模型的对话记忆**：`chat.py` 把卡片追加到 SSE 正文和数据库，
但不写进 LangGraph checkpoint 消息。25 张卡的命令 JSON 实测约 35KB（约 1 万
token），若进入上下文，
之后每轮请求都要重复消耗这些 token。

## 六、catalogId 与目录注册（易错点）

`createSurface.catalogId` 由后端配置 `PLAN_SHOW_CATALOG_ID` 决定，默认是 A2UI
官方基本目录：

```
https://a2ui.org/specification/v0_9/basic_catalog.json
```

但上表的组件是业务专用组件，**不在官方基本目录里**。A2UI 渲染器对「目录里查不到
的组件」是优雅降级（渲染占位文本，不崩溃），因此这个组合能跑但会丢组件校验。

前端要做的：把 `docs/catalogs/plan_show_catalog.json` 里的 6 个组件注册进目录，
并且保证**注册时用的 id 与后端下发的 catalogId 完全一致**。

- 若前端就是在官方基本目录 id 下注册（把业务组件合并进同一份目录），无需改动；
- 若前端注册的是本地目录（如 `local://plan_show_catalog.json`），在后端 `.env`
  里加一行即可对齐，不用改代码：

```
PLAN_SHOW_CATALOG_ID=local://plan_show_catalog.json
```

## 七、已知边界

- 源数据里「组合」分类（`titleId=4`）没有任何方案行，当前布局是单列卡片流，
  不涉及分类 Tab，所以不受影响；若以后要做 Tab，tab 列表需前端自行兜底。
- 25 张卡用字面量 props 生成（实测约 35KB）。若后续要压缩体积，可以改成 A2UI 的
  `List` 模板模式（`children: {path, componentId}` + `updateDataModel` 一次写入
  数组），命令体量能降到 ~1KB，代价是前端要实现模板渲染与相对路径绑定。
- 本轮查询失败或没有方案时，后端不下发围栏，只回一段说明文字（不会出现空卡片）。
- 围栏用 ``` 包裹，如果哪天方案名或卖点文案里出现三连反引号，前端正则会在那里
  提前截断。当前库里的 25 条数据都不含反引号，属于潜在风险而非现存问题；真出现
  时需要在生成侧转义，或把围栏标记换成不会与正文冲突的分隔符。

## 八、本地怎么验

```bash
# 纯函数与查询层的行为（含按钮颜色、组件引用完整性、排序）
uv run pytest tests/unit/test_plan_show_x_card.py -v

# 子图 + SSE 端到端：围栏帧在 stop 帧之前、落库内容与流式输出同形
uv run pytest tests/unit/test_insurance_agent.py -v
```
