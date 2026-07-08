import pytest

from app.shortener import ALPHABET, generate_code


def test_generate_code_has_requested_length():
    assert len(generate_code(7)) == 7
    assert len(generate_code(1)) == 1


def test_generate_code_uses_base62_alphabet():
    code = generate_code(50)
    assert all(ch in ALPHABET for ch in code)


def test_generate_code_is_reasonably_unique():
    codes = {generate_code(8) for _ in range(1000)}
    # Collisions in 1000 draws over 62^8 space should be effectively impossible.
    assert len(codes) == 1000


def test_generate_code_rejects_invalid_length():
    with pytest.raises(ValueError):
        generate_code(0)
