"""GitHub Repository Access & Codebase Understanding Engine.
Provides secure repository inspection, metadata extraction, dependency analysis,
and structured architectural inventory without executing downloaded code.
"""

import asyncio
import base64
import fnmatch
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Set
import httpx

from agenthive.config import settings
from agenthive.security import redact_secrets

logger = logging.getLogger("agenthive.services.github")

# Max limits for memory & context safety
MAX_FILE_SIZE_BYTES = 50 * 1024  # 50 KB per inspected file
MAX_TOTAL_CONTEXT_BYTES = 250 * 1024  # 250 KB aggregate source text limit
MAX_TREE_ENTRIES = 500  # Cap on tree entries to prevent denial of service

# Patterns strictly excluded from reading
SENSITIVE_PATTERNS = [
    ".env*",
    "*.env",
    "*secret*",
    "*credential*",
    "*password*",
    "*.pem",
    "*.key",
    "*.pfx",
    "*.pkcs12",
    "id_rsa*",
    "id_ed25519*",
    "*.cert",
    "*.crt",
    "*.p12",
    "*token*",
]

IGNORED_DIRS = {
    ".git",
    ".github/workflows/secrets",
    "node_modules",
    "venv",
    ".venv",
    "env",
    "__pycache__",
    "dist",
    "build",
    ".pytest_cache",
    ".mypy_cache",
    "target",
    ".idea",
    ".vscode",
}

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp",
    ".mp3", ".mp4", ".mov", ".avi", ".wav",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".iso",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".pyc", ".pyo", ".pyd", ".db", ".sqlite", ".sqlite3",
    ".woff", ".woff2", ".ttf", ".eot"
}


@dataclass
class CodebaseInventory:
    repo_name: str
    owner: str
    is_local: bool
    description: str
    default_branch: str
    stars: int
    open_issues: int
    languages: Dict[str, int]
    primary_language: str
    frameworks: List[str]
    entry_points: List[str]
    manifests: Dict[str, str]
    file_tree: List[str]
    readme_content: str
    architecture_overview: str
    engineering_assessment: Dict[str, List[str]]
    improvement_recommendations: List[Dict[str, Any]]
    file_citations: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "repo_name": self.repo_name,
            "owner": self.owner,
            "is_local": self.is_local,
            "description": self.description,
            "default_branch": self.default_branch,
            "stars": self.stars,
            "open_issues": self.open_issues,
            "languages": self.languages,
            "primary_language": self.primary_language,
            "frameworks": self.frameworks,
            "entry_points": self.entry_points,
            "manifests": list(self.manifests.keys()),
            "file_count": len(self.file_tree),
            "architecture_overview": self.architecture_overview,
            "engineering_assessment": self.engineering_assessment,
            "improvement_recommendations": self.improvement_recommendations,
            "citations_count": len(self.file_citations),
        }


def parse_repo_target(target: str) -> Tuple[Optional[str], Optional[str], bool]:
    """Parse repository target string into (owner, repo, is_local).
    Supports:
    - owner/repo
    - https://github.com/owner/repo
    - https://github.com/owner/repo.git
    - . or ~/mindhive (local paths)
    """
    if not target or not str(target).strip():
        return None, None, False
    clean = str(target).strip()
    if clean.startswith("git@github.com:"):
        clean = clean[len("git@github.com:"):]
        if clean.endswith(".git"):
            clean = clean[:-4]
        parts = clean.split("/", 1)
        if len(parts) == 2:
            return parts[0], parts[1], False

    if "github.com" in clean:
        match = re.search(r"github\.com/([^/]+)/([^/\s#?]+)", clean)
        if match:
            owner, repo = match.group(1), match.group(2)
            if repo.endswith(".git"):
                repo = repo[:-4]
            return owner, repo, False

    if "/" in clean and not clean.startswith(("/", ".", "~")):
        parts = clean.split("/")
        if len(parts) == 2 and not any(ch in clean for ch in " :\\"):
            return parts[0], parts[1], False

    # Check if target is a local directory path
    p = Path(clean).expanduser().resolve()
    if p.is_dir():
        return "local", p.name, True

    return None, None, False


def is_sensitive_path(path_str: str) -> bool:
    """Security assertion: prevents sensitive credential or private key ingestion."""
    norm = path_str.replace("\\", "/").strip("/")
    parts = norm.split("/")
    filename = parts[-1].lower()

    for ignored in IGNORED_DIRS:
        if ignored in parts or norm.startswith(ignored + "/"):
            return True

    for pattern in SENSITIVE_PATTERNS:
        if fnmatch.fnmatch(filename, pattern):
            return True

    suffix = Path(filename).suffix.lower()
    if suffix in BINARY_EXTENSIONS:
        return True

    return False


def validate_relative_path(path_str: str) -> str:
    """Path traversal prevention: rejects directory escapes ('..' or leading '/')."""
    if not path_str or not isinstance(path_str, str):
        raise ValueError("Invalid path string")
    clean = path_str.replace("\\", "/")
    if clean.startswith("/") or clean.startswith("~"):
        raise PermissionError(f"Security Boundary Violation: Absolute path rejected: {path_str}")
    parts = clean.split("/")
    if ".." in parts:
        raise PermissionError(f"Security Boundary Violation: Path traversal rejected: {path_str}")
    return clean


class GitHubService:
    def __init__(self, token: Optional[str] = None):
        self.token = token or settings.github_token
        self.base_url = "https://api.github.com"
        self.rate_limit_remaining = 60
        self.rate_limit_reset = 0

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "MindHive-AgentHive/2.0",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def get_repository_metadata(self, owner: str, repo: str) -> Dict[str, Any]:
        """Fetch repository identity, description, stars, default branch, language."""
        url = f"{self.base_url}/repos/{owner}/{repo}"
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(url, headers=self._headers())
            self._update_rate_limits(res)
            if res.status_code == 404:
                raise FileNotFoundError(f"Repository {owner}/{repo} not found on GitHub or private access token missing")
            if res.status_code == 403:
                raise PermissionError("GitHub API rate limit exceeded or access forbidden")
            res.raise_for_status()
            data = res.json()
            return {
                "name": data.get("name", repo),
                "full_name": data.get("full_name", f"{owner}/{repo}"),
                "description": data.get("description") or "No repository description provided.",
                "default_branch": data.get("default_branch", "main"),
                "stars": data.get("stargazers_count", 0),
                "forks": data.get("forks_count", 0),
                "open_issues": data.get("open_issues_count", 0),
                "language": data.get("language") or "Unknown",
                "topics": data.get("topics", []),
                "is_private": data.get("private", False),
            }

    async def get_repository_languages(self, owner: str, repo: str) -> Dict[str, int]:
        url = f"{self.base_url}/repos/{owner}/{repo}/languages"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=self._headers())
                self._update_rate_limits(res)
                if res.status_code == 200:
                    return res.json()
        except Exception as e:
            logger.warning("Could not fetch languages for %s/%s (%s)", owner, repo, type(e).__name__)
        return {}

    async def get_file_tree(self, owner: str, repo: str, branch: str = "main") -> List[str]:
        """Fetches the recursive Git tree, excluding binaries and sensitive credentials."""
        url = f"{self.base_url}/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                res = await client.get(url, headers=self._headers())
                self._update_rate_limits(res)
                if res.status_code == 200:
                    tree_data = res.json().get("tree", [])
                    files = []
                    for item in tree_data:
                        if item.get("type") == "blob":
                            path = item.get("path", "")
                            if path and not is_sensitive_path(path):
                                files.append(path)
                                if len(files) >= MAX_TREE_ENTRIES:
                                    break
                    return files
        except Exception as e:
            logger.warning("Failed to fetch git tree via API (%s); falling back to contents enumeration", type(e).__name__)

        # Fallback to contents API
        return await self._enumerate_contents_fallback(owner, repo, "")

    async def _enumerate_contents_fallback(self, owner: str, repo: str, path: str = "") -> List[str]:
        url = f"{self.base_url}/repos/{owner}/{repo}/contents/{path}"
        files = []
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=self._headers())
                self._update_rate_limits(res)
                if res.status_code == 200:
                    for item in res.json():
                        p = item.get("path", "")
                        if is_sensitive_path(p):
                            continue
                        if item.get("type") == "file":
                            files.append(p)
                        elif item.get("type") == "dir" and len(files) < 100:
                            sub_files = await self._enumerate_contents_fallback(owner, repo, p)
                            files.extend(sub_files)
        except Exception:
            pass
        return files

    async def read_file_content(self, owner: str, repo: str, file_path: str, ref: str = "main") -> Optional[str]:
        """Safely fetch and decode file content with strict size bounds and path traversal checks."""
        clean_path = validate_relative_path(file_path)
        if is_sensitive_path(clean_path):
            raise PermissionError(f"Security Boundary Violation: Ingestion of sensitive file '{clean_path}' forbidden")

        url = f"{self.base_url}/repos/{owner}/{repo}/contents/{clean_path}?ref={ref}"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(url, headers=self._headers())
                self._update_rate_limits(res)
                if res.status_code == 200:
                    data = res.json()
                    size = data.get("size", 0)
                    if size > MAX_FILE_SIZE_BYTES:
                        logger.warning("File %s exceeds max size limit (%d bytes)", clean_path, size)
                        return None
                    raw_b64 = data.get("content", "")
                    encoding = data.get("encoding", "")
                    if encoding == "base64" and raw_b64:
                        decoded = base64.b64decode(raw_b64.encode("ascii")).decode("utf-8", errors="replace")
                        return redact_secrets(decoded)
        except Exception as e:
            logger.error("Failed to read file %s from %s/%s (%s)", clean_path, owner, repo, type(e).__name__)
        return None

    def _update_rate_limits(self, response: httpx.Response):
        rem = response.headers.get("x-ratelimit-remaining")
        reset_time = response.headers.get("x-ratelimit-reset")
        if rem is not None:
            try:
                self.rate_limit_remaining = int(rem)
            except ValueError:
                pass
        if reset_time is not None:
            try:
                self.rate_limit_reset = int(reset_time)
            except ValueError:
                pass


class CodebaseAnalyzer:
    """Understands codebase architecture, dependencies, frameworks, and engineering priorities."""

    def __init__(self, github_service: Optional[GitHubService] = None):
        self.gh = github_service or GitHubService()

    async def analyze(self, target: str, github_token: Optional[str] = None) -> CodebaseInventory:
        """Alias for analyze_target with optional token override."""
        if github_token:
            self.gh.token = github_token
        return await self.analyze_target(str(target))

    async def analyze_target(self, target: str) -> CodebaseInventory:
        """Universal entrypoint: analyzes either remote GitHub repo or local codebase directory."""
        owner, repo, is_local = parse_repo_target(target)
        if not owner or not repo:
            raise ValueError(f"Could not parse repository target: '{target}'. Provide 'owner/repo', a GitHub URL, or local path.")

        if is_local:
            return await self.analyze_local_repository(Path(target).expanduser().resolve())
        return await self.analyze_remote_github(owner, repo)

    async def analyze_remote_github(self, owner: str, repo: str) -> CodebaseInventory:
        """Inspects remote GitHub repository and produces structured architectural understanding."""
        logger.info("Initiating codebase analysis for GitHub repo %s/%s", owner, repo)
        meta = await self.gh.get_repository_metadata(owner, repo)
        branch = meta.get("default_branch", "main")
        languages = await self.gh.get_repository_languages(owner, repo)
        tree = await self.gh.get_file_tree(owner, repo, branch)

        # Inspect manifests and documentation
        manifest_files = [
            "requirements.txt", "pyproject.toml", "setup.py", "Pipfile",
            "package.json", "Cargo.toml", "go.mod", "pom.xml", "build.gradle",
            "Dockerfile", "docker-compose.yml", "Makefile"
        ]
        manifests: Dict[str, str] = {}
        file_citations: Dict[str, str] = {}

        # 1. Inspect README
        readme_content = ""
        for candidate in ["README.md", "README", "readme.md"]:
            if candidate in tree:
                content = await self.gh.read_file_content(owner, repo, candidate, branch)
                if content:
                    readme_content = content
                    file_citations[candidate] = content[:600]
                    break

        # 2. Inspect Manifests
        total_context = len(readme_content)
        for m in manifest_files:
            matches = [f for f in tree if f == m or f.endswith(f"/{m}")]
            for match in matches[:3]:  # Limit top manifests
                if total_context >= MAX_TOTAL_CONTEXT_BYTES:
                    break
                content = await self.gh.read_file_content(owner, repo, match, branch)
                if content:
                    manifests[match] = content
                    file_citations[match] = content[:400]
                    total_context += len(content)

        # 3. Detect Frameworks & Entry Points
        frameworks = self._detect_frameworks(tree, manifests)
        entry_points = self._detect_entry_points(tree)

        # 4. Synthesize Engineering Assessment & Recommendations
        primary_lang = meta.get("language") or (max(languages.keys(), key=lambda k: languages[k]) if languages else "Python")
        architecture_overview = self._synthesize_architecture(meta, frameworks, entry_points, manifests, tree)
        assessment = self._synthesize_assessment(tree, manifests, frameworks, entry_points)
        recommendations = self._synthesize_recommendations(meta, assessment, frameworks, tree)

        return CodebaseInventory(
            repo_name=meta.get("name", repo),
            owner=owner,
            is_local=False,
            description=meta.get("description", ""),
            default_branch=branch,
            stars=meta.get("stars", 0),
            open_issues=meta.get("open_issues", 0),
            languages=languages,
            primary_language=primary_lang,
            frameworks=frameworks,
            entry_points=entry_points,
            manifests=manifests,
            file_tree=tree,
            readme_content=readme_content[:1500],
            architecture_overview=architecture_overview,
            engineering_assessment=assessment,
            improvement_recommendations=recommendations,
            file_citations=file_citations,
        )

    async def analyze_local_repository(self, local_path: Path) -> CodebaseInventory:
        """Inspects local repository directory using identical security rules and parsing engine."""
        logger.info("Initiating local codebase analysis for directory %s", local_path)
        if not local_path.is_dir():
            raise FileNotFoundError(f"Local repository path does not exist: {local_path}")

        files: List[str] = []
        for p in sorted(local_path.rglob("*")):
            if p.is_file():
                rel = str(p.relative_to(local_path))
                if not is_sensitive_path(rel):
                    files.append(rel)
                    if len(files) >= MAX_TREE_ENTRIES:
                        break

        manifests: Dict[str, str] = {}
        file_citations: Dict[str, str] = {}
        readme_content = ""
        total_context = 0

        # Read README
        for cand in ["README.md", "README", "readme.md"]:
            candidate_path = local_path / cand
            if candidate_path.is_file():
                try:
                    text = redact_secrets(candidate_path.read_text(errors="replace")[:MAX_FILE_SIZE_BYTES])
                    readme_content = text
                    file_citations[cand] = text[:600]
                    total_context += len(text)
                except Exception:
                    pass
                break

        # Read Manifests
        manifest_names = ["requirements.txt", "pyproject.toml", "package.json", "Dockerfile", "docker-compose.yml"]
        for f in files:
            if any(f == m or f.endswith("/" + m) for m in manifest_names):
                if total_context >= MAX_TOTAL_CONTEXT_BYTES:
                    break
                p = local_path / f
                try:
                    text = redact_secrets(p.read_text(errors="replace")[:MAX_FILE_SIZE_BYTES])
                    manifests[f] = text
                    file_citations[f] = text[:400]
                    total_context += len(text)
                except Exception:
                    pass

        frameworks = self._detect_frameworks(files, manifests)
        entry_points = self._detect_entry_points(files)
        languages = {"Python": len([f for f in files if f.endswith(".py")]), "JavaScript": len([f for f in files if f.endswith((".js", ".jsx"))])}

        meta = {
            "name": local_path.name,
            "description": f"Local repository analyzed at {local_path.name}",
            "default_branch": "main",
            "stars": 0,
            "open_issues": 0,
            "language": "Python" if languages["Python"] >= languages["JavaScript"] else "JavaScript",
        }

        architecture_overview = self._synthesize_architecture(meta, frameworks, entry_points, manifests, files)
        assessment = self._synthesize_assessment(files, manifests, frameworks, entry_points)
        recommendations = self._synthesize_recommendations(meta, assessment, frameworks, files)

        return CodebaseInventory(
            repo_name=local_path.name,
            owner="local",
            is_local=True,
            description=meta["description"],
            default_branch="main",
            stars=0,
            open_issues=0,
            languages=languages,
            primary_language=meta["language"],
            frameworks=frameworks,
            entry_points=entry_points,
            manifests=manifests,
            file_tree=files,
            readme_content=readme_content[:1500],
            architecture_overview=architecture_overview,
            engineering_assessment=assessment,
            improvement_recommendations=recommendations,
            file_citations=file_citations,
        )

    def _detect_frameworks(self, tree: List[str], manifests: Dict[str, str]) -> List[str]:
        detected = set()
        manifest_texts = " ".join(manifests.values()).lower()

        # Web & API Frameworks
        if "fastapi" in manifest_texts:
            detected.add("FastAPI")
        if "uvicorn" in manifest_texts:
            detected.add("Uvicorn ASGI")
        if "flask" in manifest_texts:
            detected.add("Flask")
        if "django" in manifest_texts:
            detected.add("Django")
        if "express" in manifest_texts or '"express"' in manifest_texts:
            detected.add("Express.js")
        if "react" in manifest_texts or any("react" in f.lower() for f in tree):
            detected.add("React")
        if "next" in manifest_texts:
            detected.add("Next.js")
        if "discord.py" in manifest_texts or any("discord" in f.lower() for f in tree):
            detected.add("Discord.py")

        # Persistence & Messaging
        if "sqlite" in manifest_texts or any("sqlite" in f.lower() for f in tree):
            detected.add("SQLite (WAL)")
        if "postgres" in manifest_texts or "psycopg" in manifest_texts or any("postgres" in f.lower() for f in tree):
            detected.add("PostgreSQL")
        if "websockets" in manifest_texts:
            detected.add("WebSockets")
        if "sse-starlette" in manifest_texts or "sse" in manifest_texts:
            detected.add("Server-Sent Events (SSE)")

        # Testing & Tooling
        if "pytest" in manifest_texts or any("test_" in f for f in tree):
            detected.add("Pytest Suite")
        if "docker" in manifest_texts or any("docker" in f.lower() for f in tree):
            detected.add("Docker Containerization")

        return sorted(list(detected))

    def _detect_entry_points(self, tree: List[str]) -> List[str]:
        candidates = [
            "agenthive/main.py", "main.py", "app.py", "run.py", "server.py", "index.py",
            "src/index.js", "src/main.js", "src/server.js", "index.js", "server.js",
            "cmd/main.go", "src/main.rs"
        ]
        found = []
        for cand in candidates:
            for f in tree:
                if f == cand or f.endswith("/" + cand):
                    found.append(f)
        return sorted(list(set(found)))

    def _synthesize_architecture(
        self,
        meta: Dict[str, Any],
        frameworks: List[str],
        entry_points: List[str],
        manifests: Dict[str, str],
        tree: List[str]
    ) -> str:
        lang = meta.get("language") or "Python"
        entry_str = ", ".join(f"`{e}`" for e in entry_points) if entry_points else "No explicit entrypoint identified"
        fw_str = ", ".join(frameworks) if frameworks else "Standard Library"

        has_docker = any("docker" in f.lower() for f in tree)
        has_tests = any("test" in f.lower() for f in tree)
        arch_type = "Multi-tiered Service" if ("FastAPI" in frameworks or "Express.js" in frameworks) else "Modular Library/CLI"

        return (
            f"**Architecture Style:** {arch_type} ({lang})\n"
            f"- **Primary Tech Stack:** {fw_str}\n"
            f"- **Entry Points:** {entry_str}\n"
            f"- **Infrastructure:** {'Dockerized' if has_docker else 'Host-native execution'}; {'Pytest automated test harness present' if has_tests else 'No standard test suite detected'}\n"
            f"- **Codebase Scale:** {len(tree)} structured files indexed across core components."
        )

    def _synthesize_assessment(
        self,
        tree: List[str],
        manifests: Dict[str, str],
        frameworks: List[str],
        entry_points: List[str]
    ) -> Dict[str, List[str]]:
        features = []
        incomplete = []
        concerns = []
        testing = []

        # Functional capabilities
        if "Discord.py" in frameworks:
            features.append("Discord Gateway with slash command integration.")
        if "FastAPI" in frameworks:
            features.append("Asynchronous REST API and WebSocket/SSE real-time streaming.")
        if "SQLite (WAL)" in frameworks or "PostgreSQL" in frameworks:
            features.append("Persistent relational data storage.")
        if "Docker Containerization" in frameworks:
            features.append("Containerized deployment manifests.")
        if not features:
            features.append(f"Modular structure containing {len(tree)} source files.")

        # Incomplete / missing features
        has_tests = any("test" in f.lower() for f in tree)
        if not has_tests:
            incomplete.append("Automated test suite is absent or not organized in standard `tests/` directory.")
            testing.append("Add unit and integration tests with coverage reporting.")
        else:
            testing.append("Standard test suite detected in tree.")

        has_ci = any(".github/workflows" in f or "circleci" in f for f in tree)
        if not has_ci:
            incomplete.append("Continuous Integration (CI) workflow is not configured.")

        # Security & dependency concerns
        concerns.append("Ensure host credential environments are isolated from untrusted processes.")
        if "FastAPI" in frameworks:
            concerns.append("Verify CORS, CSRF, and origin boundaries on project mutation endpoints.")

        return {
            "existing_functionality": features,
            "incomplete_functionality": incomplete or ["Continuous deployment automation pipeline"],
            "security_and_debt": concerns,
            "testing_state": testing,
        }

    def _synthesize_recommendations(
        self,
        meta: Dict[str, Any],
        assessment: Dict[str, List[str]],
        frameworks: List[str],
        tree: List[str]
    ) -> List[Dict[str, Any]]:
        recs = [
            {
                "priority": "P0 (Highest)",
                "title": "Establish Discussion-Aware Development Workflow",
                "rationale": "Orchestrate multi-agent consensus over Official Switch protocol before generating new code.",
                "estimated_complexity": "Medium (2–4 hours)",
                "responsible_agent": "Hermes Supervisor & ChatGPT Codex",
                "dependencies": [],
            },
            {
                "priority": "P1 (High)",
                "title": "Harden Subprocess & Container Sandboxing",
                "rationale": "Enforce non-root execution, network-disabled containers, and resource bounds on task execution.",
                "estimated_complexity": "Medium (2–3 hours)",
                "responsible_agent": "AGY (Antigravity)",
                "dependencies": ["Establish Discussion-Aware Development Workflow"],
            },
            {
                "priority": "P2 (Medium)",
                "title": "Adversarial Edge-Case & Pony Tail Compliance Testing",
                "rationale": "Audit dependency manifests to enforce standard-library simplicity and automated test passes.",
                "estimated_complexity": "Low (1–2 hours)",
                "responsible_agent": "Google Gemini",
                "dependencies": ["Harden Subprocess & Container Sandboxing"],
            },
        ]
        return recs


codebase_analyzer = CodebaseAnalyzer()
