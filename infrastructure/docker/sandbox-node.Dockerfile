# Sandbox image for executing JS/TS repository / generated code.
# Run with the same hardening flags as sandbox-python (see docs/SANDBOX.md).
FROM node:22-slim

RUN npm install -g --no-fund --no-audit \
    jest@29.7.0 vitest@2.1.8 eslint@9.17.0 prettier@3.4.2 typescript@5.7.2

RUN useradd --uid 65532 --no-create-home --shell /usr/sbin/nologin sandbox
WORKDIR /workspace
USER 65532:65532
CMD ["node", "--version"]
