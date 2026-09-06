"""Language detection + framework / package-manager / test-framework heuristics."""

from __future__ import annotations

import json
from pathlib import Path

_EXT_LANG = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".sh": "shell",
    ".sql": "sql",
    ".scala": "scala",
    ".swift": "swift",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".json": "json",
    ".md": "markdown",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
}

_MANIFESTS = {
    "package.json": "npm",
    "pnpm-lock.yaml": "pnpm",
    "yarn.lock": "yarn",
    "requirements.txt": "pip",
    "pyproject.toml": "pip/poetry/uv",
    "poetry.lock": "poetry",
    "Pipfile": "pipenv",
    "go.mod": "go modules",
    "Cargo.toml": "cargo",
    "pom.xml": "maven",
    "build.gradle": "gradle",
    "Gemfile": "bundler",
    "composer.json": "composer",
}

_FRAMEWORK_SIGNS = {
    "fastapi": ["fastapi"],
    "flask": ["flask"],
    "django": ["django"],
    "express": ["express"],
    "next": ["next"],
    "react": ["react"],
    "vue": ["vue"],
    "spring-boot": ["spring-boot", "spring-boot-starter"],
    "rails": ["rails"],
    "gin": ["github.com/gin-gonic/gin"],
}

_TEST_SIGNS = {
    "pytest": ["pytest"],
    "unittest": ["unittest"],
    "jest": ["jest"],
    "vitest": ["vitest"],
    "mocha": ["mocha"],
    "go test": ["testing"],
    "cargo test": [],
}


def detect_language(path: str) -> str | None:
    return _EXT_LANG.get(Path(path).suffix.lower())


def _read(p: Path) -> str:
    try:
        return p.read_text("utf-8", errors="ignore")
    except OSError:
        return ""


def analyze_repo(root: Path) -> dict:
    """Deterministic first-pass repo analysis; the LLM summary builds on this."""
    languages: dict[str, int] = {}
    package_managers: set[str] = set()
    frameworks: set[str] = set()
    test_frameworks: set[str] = set()
    important_dirs: set[str] = set()
    entry_points: list[str] = []

    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if any(
            seg in {".git", "node_modules", ".venv", "dist", "build", "__pycache__"}
            for seg in p.parts
        ):
            continue
        lang = detect_language(rel)
        if lang:
            languages[lang] = languages.get(lang, 0) + 1
        if p.name in _MANIFESTS:
            package_managers.add(_MANIFESTS[p.name])
        if p.name in {"main.py", "app.py", "manage.py", "server.js", "index.js", "main.go"}:
            entry_points.append(rel)
        top = p.relative_to(root).parts[0] if len(p.relative_to(root).parts) > 1 else ""
        if top in {"src", "app", "lib", "api", "server", "cmd", "internal", "pkg", "tests", "test"}:
            important_dirs.add(top)

    blob = ""
    for name in ("package.json", "pyproject.toml", "requirements.txt", "go.mod", "Cargo.toml"):
        fp = root / name
        if fp.exists():
            blob += "\n" + _read(fp).lower()
    for fw, signs in _FRAMEWORK_SIGNS.items():
        if any(s in blob for s in signs):
            frameworks.add(fw)
    for tf, signs in _TEST_SIGNS.items():
        if signs and any(s in blob for s in signs):
            test_frameworks.add(tf)

    pkg = root / "package.json"
    if pkg.exists():
        try:
            scripts = json.loads(_read(pkg)).get("scripts", {})
            if "test" in scripts:
                test_frameworks.add("npm test")
        except json.JSONDecodeError:
            pass

    return {
        "languages": sorted(languages, key=languages.get, reverse=True),  # type: ignore[arg-type]
        "language_file_counts": languages,
        "package_managers": sorted(package_managers),
        "frameworks": sorted(frameworks),
        "test_frameworks": sorted(test_frameworks),
        "entry_points": entry_points[:10],
        "important_directories": sorted(important_dirs),
    }
