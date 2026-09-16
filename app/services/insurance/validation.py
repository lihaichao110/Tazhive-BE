"""大陆身份证和投保表单的确定性校验。"""

import re
from datetime import date, datetime
from typing import Any

PHONE_PATTERN = re.compile(r"^1[3-9]\d{9}$")
ID_PATTERN = re.compile(r"^\d{17}[\dXx]$")
ID_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
ID_CHECK_CODES = "10X98765432"
RELATIONSHIPS = frozenset({"SELF", "SPOUSE", "CHILD", "PARENT"})


def validate_cn_id_card(value: str) -> bool:
    """校验18位大陆身份证格式、生日和校验位。"""
    normalized = value.upper()
    if not ID_PATTERN.fullmatch(normalized):
        return False
    try:
        datetime.strptime(normalized[6:14], "%Y%m%d")
    except ValueError:
        return False
    checksum = sum(
        int(char) * weight for char, weight in zip(normalized[:17], ID_WEIGHTS, strict=True)
    )
    return normalized[-1] == ID_CHECK_CODES[checksum % 11]


def validate_person_form(value: Any) -> tuple[dict[str, str] | None, dict[str, str]]:
    """归一化人员表单并返回不包含原始输入的字段错误。"""
    if not isinstance(value, dict):
        return None, {"form": "请完整填写人员信息"}

    def normalized(key: str) -> str:
        item = value.get(key)
        return item.strip() if isinstance(item, str) else ""

    fields = {
        key: normalized(key) for key in ("name", "birth_date", "occupation", "mobile", "id_number")
    }
    errors: dict[str, str] = {}
    if not 2 <= len(fields["name"]) <= 50:
        errors["name"] = "姓名长度应为2至50个字符"
    if not 1 <= len(fields["occupation"]) <= 100:
        errors["occupation"] = "请输入职业，最多100个字符"
    if not PHONE_PATTERN.fullmatch(fields["mobile"]):
        errors["mobile"] = "请输入正确的11位大陆手机号"
    try:
        birth_date = date.fromisoformat(fields["birth_date"])
        if birth_date > date.today():
            errors["birth_date"] = "出生日期不能晚于今天"
    except ValueError:
        errors["birth_date"] = "请输入有效的出生日期"
    id_number = fields["id_number"].upper()
    fields["id_number"] = id_number
    if not validate_cn_id_card(id_number):
        errors["id_number"] = "请输入有效的18位大陆身份证号"
    elif "birth_date" not in errors and id_number[6:14] != fields["birth_date"].replace("-", ""):
        errors["id_number"] = "身份证号码与出生日期不一致"
    return (fields if not errors else None), errors
