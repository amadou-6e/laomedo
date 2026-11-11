FROM node:22-bookworm-slim@sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c

ARG CODEX_VERSION=0.159.2

RUN apt-get update \
    && apt-get install -y --no-install-recommends bubblewrap ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && npm install --global --omit=dev "@openai/codex@${CODEX_VERSION}" \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin runner

USER runner
ENV HOME=/home/runner
WORKDIR /draft
