"""Short-code generation.

Uses a cryptographically strong random generator over a base62 alphabet.
Kept dependency-free and pure so it is trivial to unit test.
"""

import secrets   # cryptographically strong randomness (not the predictable `random`)
import string

# base62 = a-z + A-Z + 0-9 (62 characters).
ALPHABET = string.ascii_letters + string.digits


def generate_code(length: int) -> str:
    """Return a random base62 code of the requested length."""
    # Guard against a bad config value.
    if length < 1:
        raise ValueError("short_code_length must be >= 1")
    # Pick `length` random characters and join them into one string.
    return "".join(secrets.choice(ALPHABET) for _ in range(length))
