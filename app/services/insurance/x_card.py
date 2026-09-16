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


def _person_fields(*, include_consent: bool) -> tuple[list[str], list[dict[str, Any]]]:
    """生成共享身份输入组件；路径值由 XCard data model 在浏览器内解析。"""
    specs = [
        ("name", "姓名", "text", "请输入真实姓名", "name"),
        ("birth_date", "出生日期", "date", "", "bday"),
        ("occupation", "职业", "text", "请输入职业", "organization-title"),
        ("mobile", "手机号", "tel", "请输入11位大陆手机号", "tel"),
        ("id_number", "身份证号", "text", "请输入18位大陆身份证号", "off"),
    ]
    ids: list[str] = []
    components: list[dict[str, Any]] = []
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
                "disabled": {"path": "/ui/person_fields_disabled"},
            }
        )
    if include_consent:
        ids.append("field_consent")
        components.append(
            {
                "id": "field_consent",
                "component": "InsuranceConsent",
                "text": "我已阅读并同意个人信息处理授权及投保须知",
                "bindingPath": "form/consent",
                "checked": {"path": "/form/consent"},
                "error": {"path": "/errors/consent"},
                "disabled": {"path": "/ui/submitted"},
            }
        )
    return ids, components


def build_applicant_form(*, application_id: str, version: int, catalog_id: str) -> dict[str, Any]:
    """构造第一步投保人信息表单。"""
    surface_id = f"{INSURANCE_SURFACE_PREFIX}_{application_id}_applicant"
    field_ids, fields = _person_fields(include_consent=True)
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
        data={
            "form": {},
            "errors": {},
            "ui": {"submitted": False, "person_fields_disabled": False},
        },
    )


def build_insured_form(
    *, application_id: str, version: int, applicant_masked: dict[str, str], catalog_id: str
) -> dict[str, Any]:
    """构造第二步被保险人表单；选本人时服务端复制投保人资料。"""
    surface_id = f"{INSURANCE_SURFACE_PREFIX}_{application_id}_insured"
    field_ids, fields = _person_fields(include_consent=False)
    components: list[dict[str, Any]] = [
        {
            "id": "root",
            "component": "InsuranceStepLayout",
            "children": ["step", "relationship", "same_hint", "form", "form_error", "submit"],
        },
        {
            "id": "step",
            "component": "InsuranceStepIndicator",
            "current": 2,
            "total": 3,
            "title": "被保险人信息",
        },
        {
            "id": "relationship",
            "component": "InsuranceRelationshipSelect",
            "label": "与投保人关系",
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
        },
        {
            "id": "same_hint",
            "component": "InsuranceSameApplicantHint",
            "name": applicant_masked["name"],
            "mobile": applicant_masked["mobile"],
            "visible": {"path": "/ui/person_fields_disabled"},
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
        data={
            "form": {},
            "errors": {},
            "ui": {"submitted": False, "person_fields_disabled": False},
        },
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
