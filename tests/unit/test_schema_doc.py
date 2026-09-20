"""schema_doc 单元测试：结果列名兜底映射与白名单表字段覆盖。"""

from app.services.dataquery.guard import ALLOWED_TABLES
from app.services.dataquery.schema_doc import COLUMN_LABELS, translate_columns


def test_known_columns_are_translated_and_unknown_pass_through():
    columns = ["group_name", "weird_metric", "STATUS"]
    assert translate_columns(columns) == ["方案名称", "weird_metric", "投保状态"]


def test_every_allowed_table_field_has_a_label():
    """映射需覆盖 4 张白名单表的全部业务字段，漏了兜底就会漏中文表头。"""
    expected = {
        "products": {
            "name",
            "classification",
            "terms_url",
            "description_url",
            "additional_premium_rule_url",
        },
        "plan_shows": {
            "group_code",
            "group_name",
            "title_id",
            "title",
            "order_num",
            "title_ord_num",
            "has_sale",
            "insur_list",
            "is_more_insur",
            "contents",
        },
        "insurance_applications": {
            "user_id",
            "thread_id",
            "group_code",
            "group_name",
            "plan_title",
            "current_step",
            "status",
            "confirmed_at",
            "version",
            "insur_list_json",
        },
        "insurance_events": {
            "event_id",
            "application_id",
            "event_name",
            "resulting_step",
            "resulting_version",
            "user_id",
            "thread_id",
        },
    }
    for table, fields in expected.items():
        assert table in ALLOWED_TABLES
        assert fields <= COLUMN_LABELS.keys(), f"{table} 存在未映射的字段"
