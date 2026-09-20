from app.crypto import decrypt_password, encrypt_password


def test_encrypt_then_decrypt_roundtrips_to_the_original_value():
    token = encrypt_password("s3cret!")
    assert token != "s3cret!"
    assert decrypt_password(token) == "s3cret!"


def test_encrypting_the_same_value_twice_produces_different_tokens():
    # Fernet includes a random nonce/IV, so ciphertext isn't deterministic —
    # this guards against a future change that accidentally makes it so.
    assert encrypt_password("s3cret!") != encrypt_password("s3cret!")
