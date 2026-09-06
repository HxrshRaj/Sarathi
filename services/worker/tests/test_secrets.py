from worker.codeintel.secrets import REDACTION, contains_secret, redact, scan


def test_redacts_aws_key():
    text = 'aws_key = "AKIAIOSFODNN7EXAMPLE"'
    out = redact(text)
    assert "AKIAIOSFODNN7EXAMPLE" not in out
    assert REDACTION in out


def test_redacts_generic_assignment():
    text = "password: 'hunter2hunter2'\napi_key = \"abcdef1234567890abcd\""
    out = redact(text)
    assert "hunter2hunter2" not in out
    assert "abcdef1234567890abcd" not in out


def test_redacts_private_key_header():
    text = "-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----"
    assert "BEGIN RSA PRIVATE KEY" not in redact(text)


def test_redacts_connection_string_password():
    text = "postgresql://user:sup3rs3cr3tpw@db:5432/app"
    out = redact(text)
    assert "sup3rs3cr3tpw" not in out


def test_scan_reports_line_numbers():
    text = "clean line\nGITHUB_TOKEN = \"ghp_0123456789abcdefghijklmnopqrstuvwx12\"\n"
    hits = scan(text)
    assert hits and hits[0].line == 2


def test_no_false_positive_on_plain_prose():
    text = "This function calculates the password strength score for the user."
    assert not contains_secret(text)
    assert redact(text) == text


def test_high_entropy_quoted_token_redacted():
    # 40-char mixed-case+digit opaque token in a quoted assignment
    text = 'token = "b3k9Qz7Xr2Lp8Nf4Wm1Td0Yv6Hs5Jc1Ab2Cd3Ef"'
    assert REDACTION in redact(text)
