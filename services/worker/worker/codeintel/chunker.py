"""Structure-aware chunking.

- Python: `ast` — one chunk per top-level function / class (methods stay with the
  class if the class is small, else split out), plus a module-header chunk.
- JS/TS: brace-depth scan for `function`, `class`, and `const x = (...) =>` decls.
- Everything else: overlapping line windows.

A `tree-sitter` backend can slot in behind `chunk_file()` later; the interface
(list[Chunk]) is stable. Token counts are a cheap chars/4 estimate.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

from worker.codeintel.languages import detect_language

_WINDOW_LINES = 60
_WINDOW_OVERLAP = 12
_CLASS_SPLIT_LINES = 80


@dataclass(slots=True)
class Chunk:
    symbol: str | None
    kind: str  # function | class | method | module | block
    start_line: int
    end_line: int
    content: str

    @property
    def token_estimate(self) -> int:
        return max(1, len(self.content) // 4)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def chunk_file(path: str, source: str) -> list[Chunk]:
    lang = detect_language(path)
    if lang == "python":
        try:
            return _chunk_python(source)
        except SyntaxError:
            return _chunk_windows(source)
    if lang in ("javascript", "typescript"):
        return _chunk_js_like(source)
    return _chunk_windows(source)


def _lines(source: str) -> list[str]:
    return source.splitlines()


def _slice(lines: list[str], start: int, end: int) -> str:
    return "\n".join(lines[start - 1 : end])


def _chunk_python(source: str) -> list[Chunk]:
    tree = ast.parse(source)
    lines = _lines(source)
    chunks: list[Chunk] = []

    first_body_line = min(
        (n.lineno for n in tree.body if isinstance(n, ast.AST) and hasattr(n, "lineno")),
        default=1,
    )
    if first_body_line > 1:
        chunks.append(
            Chunk(
                None,
                "module",
                1,
                min(first_body_line - 1, len(lines)),
                _slice(lines, 1, first_body_line - 1),
            )
        )

    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            end = node.end_lineno or node.lineno
            chunks.append(
                Chunk(node.name, "function", node.lineno, end, _slice(lines, node.lineno, end))
            )
        elif isinstance(node, ast.ClassDef):
            end = node.end_lineno or node.lineno
            span = end - node.lineno + 1
            if span <= _CLASS_SPLIT_LINES:
                chunks.append(
                    Chunk(node.name, "class", node.lineno, end, _slice(lines, node.lineno, end))
                )
            else:
                header_end = min(node.lineno + 3, end)
                chunks.append(
                    Chunk(
                        node.name,
                        "class",
                        node.lineno,
                        header_end,
                        _slice(lines, node.lineno, header_end),
                    )
                )
                for sub in node.body:
                    if isinstance(sub, ast.FunctionDef | ast.AsyncFunctionDef):
                        s_end = sub.end_lineno or sub.lineno
                        chunks.append(
                            Chunk(
                                f"{node.name}.{sub.name}",
                                "method",
                                sub.lineno,
                                s_end,
                                _slice(lines, sub.lineno, s_end),
                            )
                        )
    if not chunks:
        chunks = _chunk_windows(source)
    return [c for c in chunks if c.content.strip()]


_JS_DECL = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?"
    r"(?:(?P<async>async\s+)?function\s*\*?\s*(?P<fn>[A-Za-z0-9_$]+)"
    r"|class\s+(?P<cls>[A-Za-z0-9_$]+)"
    r"|(?:const|let|var)\s+(?P<arrow>[A-Za-z0-9_$]+)\s*=\s*(?:async\s*)?\([^)]*\)\s*(?::[^=]+)?=>)"
)


def _chunk_js_like(source: str) -> list[Chunk]:
    lines = _lines(source)
    chunks: list[Chunk] = []
    i = 0
    n = len(lines)
    while i < n:
        m = _JS_DECL.match(lines[i])
        if not m:
            i += 1
            continue
        symbol = m.group("fn") or m.group("cls") or m.group("arrow")
        kind = "class" if m.group("cls") else "function"
        depth = 0
        seen_brace = False
        j = i
        while j < n:
            depth += lines[j].count("{") - lines[j].count("}")
            if "{" in lines[j]:
                seen_brace = True
            if seen_brace and depth <= 0:
                break
            j += 1
        end = min(j + 1, n)
        chunks.append(Chunk(symbol, kind, i + 1, end, _slice(lines, i + 1, end)))
        i = end
    if not chunks:
        return _chunk_windows(source)
    return [c for c in chunks if c.content.strip()]


def _chunk_windows(source: str) -> list[Chunk]:
    lines = _lines(source)
    if not lines:
        return []
    chunks: list[Chunk] = []
    start = 1
    while start <= len(lines):
        end = min(start + _WINDOW_LINES - 1, len(lines))
        body = _slice(lines, start, end)
        if body.strip():
            chunks.append(Chunk(None, "block", start, end, body))
        if end == len(lines):
            break
        start = end - _WINDOW_OVERLAP + 1
    return chunks
