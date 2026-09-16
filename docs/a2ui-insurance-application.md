# 投保流程 A2UI v0.9 契约

投保交互使用 `POST /api/v1/threads/{thread_id}/insurance/actions`，不进入意图分类器或
大模型。接口响应中的 `assistant_message.content` 仍采用“说明文字 + `a2ui` 围栏”，
因此实时追加和历史消息使用同一套解析逻辑。

## 事件与步骤

| 事件 | 前置步骤/版本 | 成功后的步骤/版本 |
| --- | --- | --- |
| `plan_apply` | 无 | `APPLICANT_INFO` / 1 |
| `applicant_submit` | `APPLICANT_INFO` / 1 | `INSURED_INFO` / 2 |
| `insured_submit` | `INSURED_INFO` / 2 | `PLAN_CONFIRMATION` / 3 |
| `plan_confirm` | `PLAN_CONFIRMATION` / 3 | `CONFIRMED` / 4 |

每次请求必须使用新的 UUID `event_id`。网络重试复用同一 UUID 时，后端返回第一次生成的
消息；使用旧 `expected_version` 操作历史表单时返回 `409 stale_step`。

## 表单约定

投保人填写姓名、出生日期、职业、手机号、身份证号并确认版本 `v1` 的个人信息授权。
被保险人与投保人的关系仅支持 `SELF`、`SPOUSE`、`CHILD`、`PARENT`；`SELF` 由后端
复制投保人资料，其余关系填写同一组身份字段。

表单值只存在于 XCard data model 和动作请求的 `context.form`。服务端返回的消息和 A2UI
只包含空表单或脱敏摘要，禁止携带原始姓名、手机号和身份证号。

字段错误返回：

```json
{
  "detail": {
    "code": "validation_failed",
    "message": "请检查投保人信息",
    "field_errors": { "mobile": "请输入正确的11位大陆手机号" }
  }
}
```

前端把 `field_errors` 作为 `updateDataModel` 命令写入原 surface 的 `/errors`，以保留已
填写的数据并原地展示错误。
