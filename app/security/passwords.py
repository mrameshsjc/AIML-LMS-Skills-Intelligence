"""
Password hashing (Phase 17).

NEVER STORE PASSWORDS
    Only a HASH is stored: a one-way fingerprint. At login the typed password is
    hashed the same way and the two hashes are compared.

PBKDF2-SHA256 (Python's built-in hashlib)
    - a random SALT per password, so two users with the same password get
      different hashes, and precomputed "rainbow tables" are useless;
    - 600,000 ITERATIONS, so every guess costs real time (the OWASP
      recommendation for PBKDF2-SHA256);
    - hmac.compare_digest compares in constant time.
    Stored as:  pbkdf2_sha256$600000$<salt hex>$<hash hex>

    bcrypt or Argon2 are equally good choices; PBKDF2 needs no extra package.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 600_000


def hash_password(password: str, iterations: int = ITERATIONS) -> str:
    if len(password) < 8:
        raise ValueError("A password must have at least 8 characters.")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"{ALGORITHM}${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt, expected = stored.split("$")
    except ValueError:
        return False
    if algorithm != ALGORITHM:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
    return hmac.compare_digest(digest.hex(), expected)
