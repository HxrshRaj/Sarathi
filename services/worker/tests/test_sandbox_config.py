"""Sandbox hardening flags — asserted without needing a Docker daemon."""

import inspect

from worker.sandbox.runner import SandboxConfig, SandboxRunner, _looks_secret, _tar_workspace


def test_config_for_language_picks_images():
    assert "python" in SandboxConfig.for_language("python").image
    assert "node" in SandboxConfig.for_language("typescript").image


def test_secret_env_keys_filtered():
    assert _looks_secret("ANTHROPIC_API_KEY")
    assert _looks_secret("db_password")
    assert not _looks_secret("PATH")
    assert not _looks_secret("LANG")


def test_runner_run_uses_hardening_flags():
    src = inspect.getsource(SandboxRunner.run)
    for needle in (
        'network_mode="none"',
        'cap_drop=["ALL"]',
        'security_opt=["no-new-privileges"]',
        "pids_limit=",
        "mem_limit=",
        "memswap_limit=",
        'user="65532:65532"',
        "tmpfs={",
        "remove(force=True)",
    ):
        assert needle in src, needle


def test_no_shell_tool_exists():
    import worker.tools.exec_tools as ex
    import worker.tools.fs_tools as fs

    names = []
    for mod in (fs, ex):
        names += [n for n in dir(mod) if "shell" in n.lower() or n.lower() == "exec"]
    assert names == []


def test_tar_skips_vcs_and_deps(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref: x")
    (tmp_path / "keep.py").write_text("1\n")
    blob = _tar_workspace(tmp_path)
    assert b"keep.py" in blob
    assert b".git/HEAD" not in blob
