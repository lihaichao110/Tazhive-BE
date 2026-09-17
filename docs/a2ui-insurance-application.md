# 投保流程 A2UI v0.9 契约

投保交互使用 `POST /api/v1/threads/{thread_id}/insurance/actions`，不进入意图分类器或
大模型。接口响应中的 `assistant_message.content` 仍采用“说明文字 + `a2ui` 围栏”，
因此实时追加和历史消息使用同一套解析逻辑。

## 事件与步骤

| 事件 | 前置步骤/版本 | 成功后的步骤/版本 |
| --- | --- | --- |
| `plan_apply` | 无 | `APPLICANT_INFO` / 1 |
| `applicant_submit` | `APPLICANT_INFO` / 1 | 关系为 `SELF` 时 `PLAN_CONFIRMATION` / 3；其余关系 `INSURED_INFO` / 2 |
| `insured_submit` | `INSURED_INFO` / 2 | `PLAN_CONFIRMATION` / 3 |
| `plan_confirm` | `PLAN_CONFIRMATION` / 3 | `CONFIRMED` / 4 |

每次请求必须使用新的 UUID `event_id`。网络重试复用同一 UUID 时，后端返回第一次生成的
消息；使用旧 `expected_version` 操作历史表单时返回 `409 stale_step`。

投保人在第一步通过“投保人是被保人的”下拉选择与被保险人的关系；选 `SELF` 时后端复制
投保人的加密资料作为被保险人并跳过第二步，直接进入方案确认。

## 表单约定

投保人填写姓名、性别（单选，`MALE`/`FEMALE`）、出生日期、职业类型、手机号，选择
“投保人是被保人的”关系（仅支持 `SELF`、`SPOUSE`、`CHILD`、`PARENT`），并确认版本
`v1` 的个人信息授权。表单不采集身份证号，实名信息在后续环节补录。被保险人表单与投保人
共用同一组人员字段，但不包含关系下拉和授权勾选；关系以第一步提交并持久化的值为准，
`insured_submit` 时由后端从投保人记录读取。

表单值只存在于 XCard data model 和动作请求的 `context.form`。标准请求应在发送事件前解析
`{"path": "/form"}`，将性别、姓名等字段直接放在 `context.form` 下。为兼容旧版前端，
服务端也长期接受单层包装结构 `context.form.value`；新代码不得继续生成该包装结构。服务端
返回的消息和 A2UI 只包含空表单或脱敏摘要，禁止携带原始姓名和手机号。

标准结构：

```json
{
  "context": {
    "form": {
      "name": "张三",
      "gender": "MALE",
      "birth_date": "1949-12-31",
      "occupation": "教师",
      "mobile": "13800138000",
      "relationship": "SELF",
      "consent": true
    }
  }
}
```

兼容结构：

```json
{
  "context": {
    "form": {
      "value": {
        "gender": "MALE",
        "name": "张三",
        "birth_date": "1949-12-31"
      }
    }
  }
}
```

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
