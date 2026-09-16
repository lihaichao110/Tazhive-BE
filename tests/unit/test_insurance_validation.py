"""投保表单校验与 PII 加密测试。"""

from cryptography.fernet import Fernet

from app.services.insurance.security import PIICipher, mask_id_number, mask_mobile, mask_name
from app.services.insurance.validation import validate_cn_id_card, validate_person_form

VALID_ID = "11010519491231002X"


def test_cn_id_card_validates_checksum_and_birth_date():
    assert validate_cn_id_card(VALID_ID)
    assert not validate_cn_id_card("110105194912310021")
    assert not validate_cn_id_card("11010519491331002X")


def test_person_form_requires_matching_birth_date_and_mainland_mobile():
    person, errors = validate_person_form(
        {
            "name": "张三",
            "birth_date": "1949-12-30",
            "occupation": "教师",
            "mobile": "12800138000",
            "id_number": VALID_ID,
        }
    )
    assert person is None
    assert set(errors) == {"mobile", "id_number"}


def test_pii_cipher_round_trip_and_masking():
    cipher = PIICipher(Fernet.generate_key().decode())
    payload = {
        "name": "张三",
        "birth_date": "1949-12-31",
        "occupation": "教师",
        "mobile": "13800138000",
        "id_number": VALID_ID,
    }
    encrypted = cipher.encrypt(payload)
    assert all(value not in encrypted for value in payload.values())
    assert cipher.decrypt(encrypted) == payload
    assert mask_name("张三") == "张*"
    assert mask_mobile("13800138000") == "138****8000"
    assert mask_id_number(VALID_ID) == "110***********002X"
