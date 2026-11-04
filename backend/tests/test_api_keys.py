from app.auth.api_keys import generate_api_key, hash_api_key, parse_prefix, verify_api_key

PEPPER = "pepper"


def test_generated_key_format_and_prefix() -> None:
    key = generate_api_key(PEPPER)
    assert key.plaintext.startswith(key.prefix + "_")
    assert parse_prefix(key.plaintext) == key.prefix
    assert len(key.prefix) == len("rw_") + 8


def test_hash_is_not_plaintext_and_verifies() -> None:
    key = generate_api_key(PEPPER)
    assert key.plaintext not in key.key_hash
    assert len(key.key_hash) == 64
    assert verify_api_key(key.plaintext, key.key_hash, PEPPER)


def test_wrong_key_or_pepper_fails() -> None:
    key = generate_api_key(PEPPER)
    assert not verify_api_key(key.plaintext + "x", key.key_hash, PEPPER)
    assert not verify_api_key(key.plaintext, key.key_hash, "other-pepper")
    assert hash_api_key(key.plaintext, PEPPER) != hash_api_key(key.plaintext, "other-pepper")


def test_keys_are_unique() -> None:
    keys = {generate_api_key(PEPPER).plaintext for _ in range(200)}
    assert len(keys) == 200


def test_malformed_keys_have_no_prefix() -> None:
    for bad in ["", "rw_short", "sk-something", "rw_ABCDEFGH_" + "x" * 40, "rw_abcdefgh_short"]:
        assert parse_prefix(bad) is None
