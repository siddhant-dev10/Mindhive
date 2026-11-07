"""Isolated owner-session, CSRF, and project-ownership coverage."""

import httpx
import pytest

from agenthive.config import settings
from agenthive.database import db
from agenthive.engine.orchestrator import orchestrator
from agenthive.main import app


ORIGIN = "http://127.0.0.1:8000"


@pytest.mark.asyncio
async def test_dashboard_authentication_and_csrf_protect_mutations():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=ORIGIN) as client:
        unauthenticated = await client.get("/api/status")
        assert unauthenticated.status_code == 401

        denied_login = await client.post(
            "/api/auth/session", json={"token": "wrong credential"}, headers={"Origin": ORIGIN}
        )
        assert denied_login.status_code == 401

        login = await client.post(
            "/api/auth/session",
            json={"token": settings.dashboard_api_token},
            headers={"Origin": ORIGIN},
        )
        assert login.status_code == 200
        assert login.json()["authenticated"] is True
        csrf = login.json()["csrf_token"]
        cookie = login.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=strict" in cookie
        assert settings.dashboard_api_token not in login.text

        missing_csrf = await client.post(
            "/api/projects",
            json={"name": "Auth gate test", "description": "Verify authenticated mutation protection"},
            headers={"Origin": ORIGIN},
        )
        assert missing_csrf.status_code == 403

        wrong_origin = await client.post(
            "/api/projects",
            json={"name": "Auth gate test", "description": "Verify authenticated mutation protection"},
            headers={"Origin": "https://attacker.invalid", "X-CSRF-Token": csrf},
        )
        assert wrong_origin.status_code == 403

        created = await client.post(
            "/api/projects",
            json={"name": "Dashboard session project", "description": "Isolated owner session flow"},
            headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
        )
        assert created.status_code == 200, created.text
        project_id = created.json()["project_id"]
        project = orchestrator.get_project(project_id)
        assert project and project.owner_discord_id == settings.discord_owner_id

        with db.get_connection() as conn:
            conn.execute("UPDATE projects SET owner_discord_id = ? WHERE id = ?", ("another-owner", project_id))
            conn.commit()
        hidden = await client.get(f"/api/projects/{project_id}")
        assert hidden.status_code == 404

        logout = await client.delete(
            "/api/auth/session", headers={"Origin": ORIGIN, "X-CSRF-Token": csrf}
        )
        assert logout.status_code == 200
        assert (await client.get("/api/auth/session")).json()["authenticated"] is False

        # Idempotent logout when unauthenticated / expired
        idempotent_logout = await client.delete(
            "/api/auth/session", headers={"Origin": ORIGIN}
        )
        assert idempotent_logout.status_code == 200
        assert idempotent_logout.json()["authenticated"] is False


@pytest.mark.asyncio
async def test_dashboard_session_expiration():
    from agenthive.web_auth import issue_dashboard_session
    import time

    now = int(time.time())
    # Issue a session that expired 60 seconds ago
    _, expired_cookie = issue_dashboard_session(
        str(settings.discord_owner_id),
        settings.dashboard_api_token,
        now=now - 3600,
        ttl=60,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=ORIGIN) as client:
        # Check session endpoint reports unauthenticated
        client.cookies.set("agenthive_session", expired_cookie)
        session_res = await client.get("/api/auth/session")
        assert session_res.status_code == 200
        assert session_res.json()["authenticated"] is False

        # Accessing protected API returns 401
        status_res = await client.get("/api/status")
        assert status_res.status_code == 401

        # Attempting project mutation with expired cookie returns 401
        mutate_res = await client.post(
            "/api/projects",
            json={"name": "Expired test", "description": "Should fail with 401"},
            headers={"Origin": ORIGIN, "X-CSRF-Token": "some-token"},
        )
        assert mutate_res.status_code == 401


@pytest.mark.asyncio
async def test_dashboard_unauthorized_access_to_all_mutation_endpoints():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=ORIGIN) as client:
        # Every mutation endpoint without session must return 401
        endpoints = [
            ("POST", "/api/projects", {"name": "X", "description": "Y"}),
            ("POST", "/api/projects/proj-123/analyse", None),
            ("POST", "/api/projects/proj-123/discuss", None),
            ("POST", "/api/projects/proj-123/assign", None),
            ("POST", "/api/projects/proj-123/approve", None),
            ("POST", "/api/projects/proj-123/reject", {"reason": "test"}),
            ("POST", "/api/projects/proj-123/execute", None),
        ]
        for method, path, json_body in endpoints:
            kwargs = {"headers": {"Origin": ORIGIN}}
            if json_body is not None:
                kwargs["json"] = json_body
            res = await client.request(method, path, **kwargs)
            assert res.status_code == 401, f"{method} {path} returned {res.status_code} instead of 401"


@pytest.mark.asyncio
async def test_dashboard_non_loopback_client_rejection():
    # Simulate a client connecting from an external IP address
    transport = httpx.ASGITransport(app=app, client=("198.51.100.25", 54321))
    async with httpx.AsyncClient(transport=transport, base_url=ORIGIN) as client:
        # Login from non-loopback must be rejected with 403
        login_res = await client.post(
            "/api/auth/session",
            json={"token": settings.dashboard_api_token},
            headers={"Origin": ORIGIN},
        )
        assert login_res.status_code == 403


@pytest.mark.asyncio
async def test_dashboard_login_rate_limiting():
    from agenthive.main import _dashboard_login_attempts
    _dashboard_login_attempts.clear()

    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 54321))
    async with httpx.AsyncClient(transport=transport, base_url=ORIGIN) as client:
        # 5 failed attempts
        for _ in range(5):
            res = await client.post(
                "/api/auth/session",
                json={"token": "incorrect-password"},
                headers={"Origin": ORIGIN},
            )
            assert res.status_code == 401

        # 6th attempt should trigger 429 Too Many Requests
        res = await client.post(
            "/api/auth/session",
            json={"token": settings.dashboard_api_token},
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 429
    _dashboard_login_attempts.clear()


def test_dashboard_does_not_persist_auth_credential_in_frontend():
    from pathlib import Path

    source = Path(__file__).parents[1] / "agenthive" / "ui" / "app.js"
    script = source.read_text()
    assert "localStorage" not in script
    assert "sessionStorage" not in script
