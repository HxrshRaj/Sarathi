from worker.codeintel.chunker import chunk_file, estimate_tokens


def test_python_functions_and_classes():
    src = (
        "import os\n\n\n"
        "def alpha():\n    return 1\n\n\n"
        "class Beta:\n    def m(self):\n        return 2\n\n\n"
        "def gamma(x):\n    return x + 1\n"
    )
    chunks = chunk_file("mod.py", src)
    symbols = {c.symbol for c in chunks}
    assert "alpha" in symbols
    assert "gamma" in symbols
    assert any(c.kind == "class" and c.symbol == "Beta" for c in chunks)


def test_python_syntax_error_falls_back_to_windows():
    chunks = chunk_file("broken.py", "def (( this is not python\n" * 5)
    assert chunks
    assert all(c.kind == "block" for c in chunks)


def test_js_function_and_arrow():
    src = (
        "export function handler(req, res) {\n  return res.end();\n}\n\n"
        "const add = (a, b) => {\n  return a + b;\n};\n"
    )
    chunks = chunk_file("h.js", src)
    symbols = {c.symbol for c in chunks}
    assert "handler" in symbols
    assert "add" in symbols


def test_unknown_language_uses_line_windows():
    chunks = chunk_file("notes.txt", "line\n" * 200)
    assert len(chunks) >= 2
    assert chunks[0].kind == "block"


def test_token_estimate_positive():
    assert estimate_tokens("") == 1
    assert estimate_tokens("abcd" * 100) > 50


def test_line_ranges_are_within_source():
    src = "\n".join(f"row {i}" for i in range(50))
    for c in chunk_file("x.txt", src):
        assert 1 <= c.start_line <= c.end_line <= 50
