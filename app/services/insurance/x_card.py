"""投保步骤的 A2UI v0.9 信封构造器。"""

from typing import Any

from app.services.plans.x_card import A2UI_VERSION

INSURANCE_SURFACE_PREFIX = "insurance_apply"


def _envelope(
    *, surface_id: str, catalog_id: str, components: list[dict[str, Any]], data: dict[str, Any]
) -> dict[str, Any]:
    """生成与现有保险方案卡片相同的三命令信封。"""
    data_commands = [
        {
            "version": A2UI_VERSION,
            "updateDataModel": {"surfaceId": surface_id, "path": f"/{key}", "value": value},
        }
        for key, value in data.items()
    ]
    return {
        "surfaceId": surface_id,
        "commands": [
            {
                "version": A2UI_VERSION,
                "createSurface": {"surfaceId": surface_id, "catalogId": catalog_id},
            },
            {
                "version": A2UI_VERSION,
                "updateComponents": {"surfaceId": surface_id, "components": components},
            },
            *data_commands,
        ],
    }


def _gender_field() -> dict[str, Any]:
    return {
        "id": "field_gender",
        "component": "InsuranceGenderRadio",
        "label": "性别",
        "options": [
            {"label": "男", "value": "MALE"},
            {"label": "女", "value": "FEMALE"},
        ],
        "bindingPath": "form/gender",
        "value": {"path": "/form/gender"},
        "error": {"path": "/errors/gender"},
        "disabled": {"path": "/ui/submitted"},
    }


def _person_fields() -> tuple[list[str], list[dict[str, Any]]]:
    """生成共享身份输入组件；路径值由 XCard data model 在浏览器内解析。"""
    ids: list[str] = []
    components: list[dict[str, Any]] = []
    specs = [
        ("name", "姓名", "text", "请输入真实姓名", "name"),
        ("birth_date", "出生日期", "date", "", "bday"),
        ("occupation", "职业类型", "text", "请输入职业类型", "organization-title"),
        ("mobile", "手机号", "tel", "请输入11位大陆手机号", "tel"),
    ]
    for field, label, input_type, placeholder, autocomplete in specs:
        component_id = f"field_{field}"
        ids.append(component_id)
        components.append(
            {
                "id": component_id,
                "component": "InsuranceInput",
                "field": field,
                "label": label,
                "inputType": input_type,
                "placeholder": placeholder,
                "autocomplete": autocomplete,
                "bindingPath": f"form/{field}",
                "value": {"path": f"/form/{field}"},
                "error": {"path": f"/errors/{field}"},
                "disabled": {"path": "/ui/submitted"},
            }
        )
        if field == "name":
            ids.append("field_gender")
            components.append(_gender_field())
    return ids, components


def _relationship_field() -> dict[str, Any]:
    """投保人第一步中的"投保人是被保人的"关系下拉。"""
    return {
        "id": "field_relationship",
        "component": "InsuranceRelationshipSelect",
        "label": "投保人是被保人的",
        "bindingPath": "form/relationship",
        "value": {"path": "/form/relationship"},
        "error": {"path": "/errors/relationship"},
        "disabled": {"path": "/ui/submitted"},
        "options": [
            {"label": "本人", "value": "SELF"},
            {"label": "配偶", "value": "SPOUSE"},
            {"label": "子女", "value": "CHILD"},
            {"label": "父母", "value": "PARENT"},
        ],
    }


def _consent_field() -> dict[str, Any]:
    return {
        "id": "field_consent",
        "component": "InsuranceConsent",
        "text": "我已阅读并同意个人信息处理授权及投保须知",
        "bindingPath": "form/consent",
        "checked": {"path": "/form/consent"},
        "error": {"path": "/errors/consent"},
        "disabled": {"path": "/ui/submitted"},
    }


def build_applicant_form(*, application_id: str, version: int, catalog_id: str) -> dict[str, Any]:
    """构造第一步投保人信息表单；关系选"本人"时后续被保险人步骤被跳过。"""
    surface_id = f"{INSURANCE_SURFACE_PREFIX}_{application_id}_applicant"
    field_ids, fields = _person_fields()
    form_children = [*field_ids, "field_relationship", "field_consent"]
    components: list[dict[str, Any]] = [
        {
            "id": "root",
            "component": "InsuranceStepLayout",
            "children": ["step", "form", "form_error", "submit"],
        },
        {
            "id": "step",
            "component": "InsuranceStepIndicator",
            "current": 1,
            "total": 3,
            "title": "投保人信息",
        },
        {"id": "form", "component": "InsuranceForm", "children": form_children},
        *fields,
        _relationship_field(),
        _consent_field(),
        {
            "id": "form_error",
            "component": "InsuranceFormError",
            "message": {"path": "/errors/form"},
        },
        {
            "id": "submit",
            "component": "InsuranceSubmitButton",
            "text": "提交并继续",
            "disabled": {"path": "/ui/submitted"},
            "action": {
                "event": {
                    "name": "applicant_submit",
                    "context": {
                        "application_id": application_id,
                        "expected_version": version,
                        "form": {"path": "/form"},
                    },
                }
            },
        },
    ]
    return _envelope(
        surface_id=surface_id,
        catalog_id=catalog_id,
        components=components,
        data={"form": {}, "errors": {}, "ui": {"submitted": False}},
    )


def build_insured_form(*, application_id: str, version: int, catalog_id: str) -> dict[str, Any]:
    """构造第二步被保险人表单；关系已在第一步采集，仅填写人员字段。"""
    surface_id = f"{INSURANCE_SURFACE_PREFIX}_{application_id}_insured"
    field_ids, fields = _person_fields()
    components: list[dict[str, Any]] = [
        {
            "id": "root",
            "component": "InsuranceStepLayout",
            "children": ["step", "form", "form_error", "submit"],
        },
        {
            "id": "step",
            "component": "InsuranceStepIndicator",
            "current": 2,
            "total": 3,
            "title": "被保险人信息",
        },
        {"id": "form", "component": "InsuranceForm", "children": field_ids},
        *fields,
        {
            "id": "form_error",
            "component": "InsuranceFormError",
            "message": {"path": "/errors/form"},
        },
        {
            "id": "submit",
            "component": "InsuranceSubmitButton",
            "text": "提交并进入方案确认",
            "disabled": {"path": "/ui/submitted"},
            "action": {
                "event": {
                    "name": "insured_submit",
                    "context": {
                        "application_id": application_id,
                        "expected_version": version,
                        "form": {"path": "/form"},
                    },
                }
            },
        },
    ]
    return _envelope(
        surface_id=surface_id,
        catalog_id=catalog_id,
        components=components,
        data={"form": {}, "errors": {}, "ui": {"submitted": False}},
    )


def build_plan_confirmation(
    *, application_id: str, version: int, summary: dict[str, Any], catalog_id: str
) -> dict[str, Any]:
    """构造第三步只读方案与人员脱敏摘要。"""
    surface_id = f"{INSURANCE_SURFACE_PREFIX}_{application_id}_confirm"
    components: list[dict[str, Any]] = [
        {
            "id": "root",
            "component": "InsuranceStepLayout",
            "children": ["step", "summary", "form_error", "submit"],
        },
        {
            "id": "step",
            "component": "InsuranceStepIndicator",
            "current": 3,
            "total": 3,
            "title": "方案确认",
        },
        {"id": "summary", "component": "InsurancePlanSummary", **summary},
        {
            "id": "form_error",
            "component": "InsuranceFormError",
            "message": {"path": "/errors/form"},
        },
        {
            "id": "submit",
            "component": "InsuranceSubmitButton",
            "text": "确认方案",
            "disabled": {"path": "/ui/submitted"},
            "action": {
                "event": {
                    "name": "plan_confirm",
                    "context": {
                        "application_id": application_id,
                        "expected_version": version,
                    },
                }
            },
        },
    ]
    return _envelope(
        surface_id=surface_id,
        catalog_id=catalog_id,
        components=components,
        data={"errors": {}, "ui": {"submitted": False}},
    )


def build_completion(*, application_id: str, catalog_id: str) -> dict[str, Any]:
    """构造基础资料确认完成状态。"""
    surface_id = f"{INSURANCE_SURFACE_PREFIX}_{application_id}_completed"
    return _envelope(
        surface_id=surface_id,
        catalog_id=catalog_id,
        components=[
            {"id": "root", "component": "InsuranceCompletion", "applicationId": application_id}
        ],
        data={"ui": {"submitted": True}},
    )
