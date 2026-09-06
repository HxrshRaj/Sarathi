# Sandbox image for executing Python repository / generated code.
# Minimal toolchain. No secrets. Run with: --network none --cap-drop ALL
# --security-opt no-new-privileges --read-only --user 65532:65532 (see docs/SANDBOX.md).
FROM python:3.11-slim

RUN pip install --no-cache-dir \
    pytest==8.3.4 pytest-cov==6.0.0 \
    ruff==0.8.4 pyflakes==3.2.0 \
    bandit==1.8.0 pip-audit==2.7.3

# Unprivileged, no shell login, no home writes needed (workspace is a tmpfs).
RUN useradd --uid 65532 --no-create-home --shell /usr/sbin/nologin sandbox
WORKDIR /workspace
USER 65532:65532
CMD ["python", "--version"]
