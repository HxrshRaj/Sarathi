# Sarathi API + worker in one container, for a free Hugging Face Space.
# The Space repo only needs this file, start.sh and README.md — the app code is
# pulled from GitHub at build time.
#
# No Docker daemon on a Space, so the code sandbox is disabled (SANDBOX_DISABLED):
# agent runs still plan / retrieve / edit / review / open PRs, but test execution
# reports "blocked".

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends git curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

# Pin to a ref for reproducible rebuilds; override with --build-arg SARATHI_REF=<sha>
ARG SARATHI_REPO=https://github.com/HxrshRaj/Sarathi.git
ARG SARATHI_REF=main
RUN git clone "${SARATHI_REPO}" . && git checkout "${SARATHI_REF}"

RUN pip install --upgrade pip \
 && pip install -e "apps/api[worker]" \
 && pip install -e "services/worker"

ENV CODEPILOT_BENCHMARKS_DIR=/srv/packages/evaluation/benchmarks \
    SANDBOX_DISABLED=true \
    RUN_WORKSPACE_ROOT=/tmp/sarathi-workspaces \
    PORT=7860

# HF Spaces run as a non-root user (uid 1000).
RUN useradd -m -u 1000 user && mkdir -p /tmp/sarathi-workspaces && chown -R user /srv /tmp/sarathi-workspaces
USER user

COPY --chown=user start.sh /srv/start.sh
RUN chmod +x /srv/start.sh

EXPOSE 7860
CMD ["bash", "/srv/start.sh"]
