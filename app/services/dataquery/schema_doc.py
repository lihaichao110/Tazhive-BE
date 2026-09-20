"""text2sql 生成提示词使用的数据库 schema 文档与业务术语字典。

只描述允许自然语言查询的 4 张业务表；users（密码）、insurance_parties（加密
PII）、document_chunks（向量）、threads / messages（会话内容）等敏感或无关表
不出现在文档里，模型无从引用。字段信息以 app/models/ 下的表定义为唯一事实
来源，表结构或枚举值变更时需同步更新本文件。
"""

SQL_SCHEMA_DOC = """
# 数据库说明（PostgreSQL）

可查询的表只有以下 4 张。所有表都有公共字段：
- id：UUID 字符串主键
- created_at / updated_at：timestamp（UTC），创建 / 更新时间

时间类筛选一律基于 created_at（UTC 时区）。表之间没有数据库级外键约束，
关联条件如下，JOIN 时必须显式写出：
- insurance_applications.group_code = plan_shows.group_code（投保单投的是哪个方案）
- insurance_events.application_id = insurance_applications.id（事件属于哪笔投保单）
- insurance_applications.user_id / insurance_events.user_id 是用户 id（用户表不可查询）

## 表清单

### products —— 在售保险产品目录
| 字段 | 类型 | 说明 |
|---|---|---|
| name | varchar(255) | 产品名称 |
| classification | varchar(10) | 产品分类分级，取值 P1 / P2 / P3 |
| terms_url | varchar(512) | 条款 PDF 链接 |
| description_url | varchar(512) | 说明文档链接，可空 |
| additional_premium_rule_url | varchar(512) | 追加保险费规则链接，可空 |

### plan_shows —— 保险方案展示（每行 = 一个分类下的一个方案分组）
| 字段 | 类型 | 说明 |
|---|---|---|
| group_code | varchar(64) | 方案分组编码，业务唯一（如 G0264） |
| group_name | varchar(255) | 方案名称，如「鸿利悠享2.0两全保险（分红型）」 |
| title_id | int | 所属分类 id |
| title | varchar(50) | 所属分类名称 |
| order_num | int | 分类内展示顺序 |
| title_ord_num | int | 分类 tab 展示顺序 |
| has_sale | varchar(10) | 是否在售标识，字符串 '1'/'2'（注意是字符串不是数字；语义未完全确认，统计时不要用它过滤） |
| insur_list | json | 关联险种代码数组，如 ["AYR","AYS","AYT"]；判断是否包含某险种可用 insur_list @> '["AYR"]'::jsonb（需先 ::jsonb 转换） |
| is_more_insur | int | 是否多险种投保，0/1 |
| contents | text | 多行卖点文案（CRLF 分隔），可空 |

### insurance_applications —— 投保单（每行一笔投保流程）
| 字段 | 类型 | 说明 |
|---|---|---|
| user_id | varchar(64) | 发起用户 id |
| thread_id | varchar(64) | 所属会话 id |
| group_code | varchar(64) | 投保的方案编码，关联 plan_shows.group_code |
| group_name | varchar(255) | 方案名称快照 |
| plan_title | varchar(50) | 方案分类名称快照 |
| current_step | varchar(50) | 当前步骤，取值 APPLICANT_INFO / INSURED_INFO / PLAN_CONFIRMATION / CONFIRMED |
| status | varchar(50) | 状态：IN_PROGRESS 进行中 / CONFIRMED 已确认投保 |
| confirmed_at | timestamp | 确认投保时间，未确认为 NULL |
| version | int | 乐观锁版本号 |
| insur_list_json | text | 投保险种 JSON 字符串 |

### insurance_events —— 投保流程事件流水（幂等）
| 字段 | 类型 | 说明 |
|---|---|---|
| event_id | varchar(36) | 幂等事件 id，唯一 |
| application_id | varchar(64) | 所属投保单 id，关联 insurance_applications.id |
| event_name | varchar(50) | 事件名：plan_apply 发起投保 / applicant_submit 提交投保人信息 / insured_submit 提交被保人信息 / plan_confirm 确认投保 |
| resulting_step | varchar(50) | 事件发生后的步骤 |
| resulting_version | int | 事件发生后的版本号 |
| user_id | varchar(64) | 用户 id |
| thread_id | varchar(64) | 会话 id |

## 业务术语对照

| 用户说法 | 查询口径 |
|---|---|
| 投保量 / 投保单量 | COUNT(*) FROM insurance_applications |
| 确认投保量 / 成交量 | insurance_applications WHERE status = 'CONFIRMED' |
| 方案 / 保险方案 | plan_shows（方案名是 group_name） |
| 产品 | products |
| 分级 / 产品分级 | products.classification（P1/P2/P3） |
| 分类 / 方案分类 | plan_shows.title |
| 险种 | plan_shows.insur_list 里的险种代码 |
| 在售方案 | plan_shows 全量（has_sale 语义未确认，不要用它过滤） |
""".strip()

COLUMN_LABELS: dict[str, str] = {
    # 公共字段
    "id": "ID",
    "created_at": "创建时间",
    "updated_at": "更新时间",
    # products
    "name": "产品名称",
    "classification": "产品分类",
    "terms_url": "条款链接",
    "description_url": "说明文档链接",
    "additional_premium_rule_url": "追加保费规则链接",
    # plan_shows
    "group_code": "方案编码",
    "group_name": "方案名称",
    "title_id": "分类ID",
    "title": "分类名称",
    "order_num": "分类内展示顺序",
    "title_ord_num": "分类Tab展示顺序",
    "has_sale": "是否在售",
    "insur_list": "关联险种代码",
    "is_more_insur": "是否多险种投保",
    "contents": "卖点文案",
    # insurance_applications
    "user_id": "用户ID",
    "thread_id": "会话ID",
    "plan_title": "方案分类名称",
    "current_step": "当前步骤",
    "status": "投保状态",
    "confirmed_at": "确认投保时间",
    "version": "版本号",
    "insur_list_json": "投保险种",
    # insurance_events
    "event_id": "事件ID",
    "application_id": "投保单ID",
    "event_name": "事件名",
    "resulting_step": "事件后步骤",
    "resulting_version": "事件后版本号",
}
"""结果列名 → 中文表头的兜底映射，与上方 SQL_SCHEMA_DOC 同源维护。

正常路径下 SQL 生成规则已要求模型为每个输出列起中文 AS 别名，本映射只在
模型漏起别名时兜底；表结构变更时需与 SQL_SCHEMA_DOC 同步更新，跨表同名字段
（group_code / user_id / thread_id 等）在各表中含义一致，扁平键不会冲突。
"""


def translate_columns(columns: list[str]) -> list[str]:
    """把结果列名中的已知英文列名替换为中文表头，未命中原样返回。"""
    return [
        COLUMN_LABELS.get(column) or COLUMN_LABELS.get(column.lower()) or column
        for column in columns
    ]
