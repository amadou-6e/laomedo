FROM node:22-bookworm-slim@sha256:de170b39439eb0e5a3444ad7d60b015614a381e10fecae2e30ec9e735122f38d
ARG CLAUDE_VERSION=2.1.310
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates git ripgrep python3 && rm -rf /var/lib/apt/lists/* \
    && npm install --global @anthropic-ai/claude-code@${CLAUDE_VERSION} \
    && test "$(claude --version)" = "${CLAUDE_VERSION} (Claude Code)" \
    && mkdir -p /profile /draft && chown node:node /profile /draft
COPY command_mcp.py /opt/laomedo/command_mcp.py
USER node
ENV HOME=/profile CLAUDE_CONFIG_DIR=/profile/config \
    CLAUDE_CODE_DISABLE_AUTO_MEMORY=1 DISABLE_AUTOUPDATER=1
WORKDIR /draft
ENTRYPOINT ["claude"]
