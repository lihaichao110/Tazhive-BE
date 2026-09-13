from app.core.security import (
    create_access_token,
    decode_access_token,
    get_password_hash,
    verify_password,
)


def test_password_hash_and_verify():
    password = "secret123"
    hashed = get_password_hash(password)
    assert verify_password(password, hashed)
    assert not verify_password("wrong", hashed)


def test_jwt_token_roundtrip():
    token = create_access_token("user123")
    user_id = decode_access_token(token)
    assert user_id == "user123"
