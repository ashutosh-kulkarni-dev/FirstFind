"""Critical auth paths: register, login, bad password, rate limit, me."""
import uuid


def _email() -> str:
    return f"user_{uuid.uuid4().hex[:8]}@example.com"


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_security_headers_present(client):
    r = client.get("/api/health")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert "max-age" in r.headers.get("Strict-Transport-Security", "")


def test_register_then_login(client):
    email = _email()
    r = client.post("/api/auth/register",
                    json={"name": "Alice", "email": email, "password": "secret12"})
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    assert token

    r = client.post("/api/auth/login", json={"email": email, "password": "secret12"})
    assert r.status_code == 200
    assert r.json()["email"] == email


def test_login_rejects_wrong_password(client):
    email = _email()
    client.post("/api/auth/register",
                json={"name": "Bob", "email": email, "password": "secret12"})
    r = client.post("/api/auth/login", json={"email": email, "password": "wrong-pw"})
    assert r.status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401


def test_password_hash_uses_600k_iters():
    """Guard against accidental downgrade of the work factor."""
    from app.auth import hash_password, PBKDF2_ITERS
    assert PBKDF2_ITERS >= 600_000
    assert hash_password("x").startswith(f"{PBKDF2_ITERS}:")


def test_legacy_hash_still_verifies_and_is_flagged_for_rehash():
    """A row hashed at the old iteration count must still log in."""
    import hashlib
    from app.auth import verify_password, needs_rehash
    salt = b"\x00" * 16
    dk = hashlib.pbkdf2_hmac("sha256", b"legacy-pw", salt, 120_000)
    legacy = salt.hex() + ":" + dk.hex()
    assert verify_password("legacy-pw", legacy) is True
    assert needs_rehash(legacy) is True


def test_auth_rate_limit_trips_on_11th_attempt(client):
    """Per-(ip,email) auth throttle: 10/min, 11th should be 429."""
    email = _email()
    for _ in range(10):
        client.post("/api/auth/login",
                    json={"email": email, "password": "nope"})
    r = client.post("/api/auth/login",
                    json={"email": email, "password": "nope"})
    assert r.status_code == 429
