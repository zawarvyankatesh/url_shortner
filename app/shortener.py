"""Short-code generation.

Uses a cryptographically strong random generator over a base62 alphabet.
Kept dependency-free and pure so it is trivial to unit test.
"""

import secrets
import string

ALPHABET = string.ascii_letters + string.digits


def generate_code(length: int) -> str:
    """Return a random base62 code of the requested length."""
    if length < 1:
        raise ValueError("short_code_length must be >= 1")
    return "".join(secrets.choice(ALPHABET) for _ in range(length))
