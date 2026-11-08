"""Unit tests for GitHub integration and Codebase Understanding Engine."""

import pytest
import tempfile
from pathlib import Path
import unittest.mock as mock

from agenthive.services.github_service import (
    GitHubService,
    CodebaseAnalyzer,
    parse_repo_target,
    is_sensitive_path,
    validate_relative_path,
    codebase_analyzer,
)


def test_parse_repo_target():
    # HTTPS full URL
    owner, repo, is_local = parse_repo_target("https://github.com/openai/whisper")
    assert owner == "openai"
    assert repo == "whisper"
    assert is_local is False

    # URL with trailing .git and slash
    owner, repo, is_local = parse_repo_target("https://github.com/facebook/react.git/")
    assert owner == "facebook"
    assert repo == "react"
    assert is_local is False

    # Owner/Repo slug
    owner, repo, is_local = parse_repo_target("psf/requests")
    assert owner == "psf"
    assert repo == "requests"
    assert is_local is False

    # Local Path
    with tempfile.TemporaryDirectory() as td:
        owner, repo, is_local = parse_repo_target(td)
        assert owner == "local"
        assert is_local is True

    # Empty string
    owner, repo, is_local = parse_repo_target("")
    assert owner is None
    assert repo is None
    assert is_local is False
    assert owner is None
    assert repo is None


def test_sensitive_file_exclusion():
    # Must be excluded
    assert is_sensitive_path(".env")
    assert is_sensitive_path(".env.production")
    assert is_sensitive_path("config/.env")
    assert is_sensitive_path("id_rsa")
    assert is_sensitive_path("id_ed25519")
    assert is_sensitive_path("server.key")
    assert is_sensitive_path("certificate.pem")
    assert is_sensitive_path("secret_token.json")
    assert is_sensitive_path("credentials.yml")
    assert is_sensitive_path("node_modules/package/index.js")
    assert is_sensitive_path("venv/lib/python3.11/site-packages/pkg.py")
    assert is_sensitive_path(".git/HEAD")

    # Allowed code files
    assert not is_sensitive_path("README.md")
    assert not is_sensitive_path("main.py")
    assert not is_sensitive_path("src/server.ts")
    assert not is_sensitive_path("package.json")
    assert not is_sensitive_path("requirements.txt")
    assert not is_sensitive_path("Dockerfile")
    assert not is_sensitive_path("tests/test_api.py")


def test_path_traversal_prevention():
    # Path traversal attempts must raise PermissionError
    with pytest.raises(PermissionError, match="Path traversal rejected"):
        validate_relative_path("../../../etc/passwd")

    with pytest.raises(PermissionError, match="Absolute path rejected"):
        validate_relative_path("/etc/shadow")

    # Valid paths must pass
    assert validate_relative_path("src/app.py") == "src/app.py"
    assert validate_relative_path("tests/test_main.py") == "tests/test_main.py"

    # Valid paths must pass
    assert validate_relative_path("src/app.py") == "src/app.py"
    assert validate_relative_path("tests/test_main.py") == "tests/test_main.py"


@pytest.mark.asyncio
async def test_local_codebase_analysis_and_understanding():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "README.md").write_text("# Test Microservice\nA high-throughput async API.", encoding="utf-8")
        (root / "requirements.txt").write_text("fastapi==0.110.0\nuvicorn>=0.28.0\npytest>=8.0.0\n", encoding="utf-8")
        (root / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")
        
        tests_dir = root / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_main.py").write_text("def test_dummy(): pass\n", encoding="utf-8")

        # Create sensitive files that must be ignored
        (root / ".env").write_text("SECRET_KEY=super-secret-123\n", encoding="utf-8")
        (root / "id_rsa").write_text("-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n", encoding="utf-8")

        inv = await codebase_analyzer.analyze_local_repository(root)

        assert inv.is_local
        assert inv.primary_language == "Python"
        assert "FastAPI" in inv.frameworks
        assert "Uvicorn ASGI" in inv.frameworks
        assert "Pytest Suite" in inv.frameworks
        assert "main.py" in inv.entry_points
        assert "# Test Microservice" in inv.readme_content

        # Sensitive files must NOT be in tree or citations
        assert ".env" not in inv.file_tree
        assert "id_rsa" not in inv.file_tree
        assert all("super-secret" not in text for text in inv.manifests.values())
        assert all("super-secret" not in text for text in inv.file_citations.values())

        # Recommendations generated
        assert len(inv.improvement_recommendations) >= 3
        assert any("P0" in r["priority"] for r in inv.improvement_recommendations)


@pytest.mark.asyncio
async def test_github_service_rate_limit_handling():
    service = GitHubService(token="fake-token")

    with mock.patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 403
        mock_resp.headers = {"X-RateLimit-Remaining": "0"}
        mock_resp.text = "API rate limit exceeded"
        mock_get.return_value = mock_resp

        with pytest.raises(PermissionError, match="rate limit exceeded"):
            await service.get_repository_metadata("octocat", "Hello-World")
