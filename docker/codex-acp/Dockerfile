FROM node:22-bookworm-slim@sha256:de170b39439eb0e5a3444ad7d60b015614a381e10fecae2e30ec9e735122f38d AS adapter
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
ADD https://codeload.github.com/agentclientprotocol/codex-acp/tar.gz/68d7d2d5ddfc0ed5746f9f6130892dda685e65dd /tmp/adapter.tar.gz
RUN echo "51ba8d1d302f8a854c0501887ffbe12fb267f6e8fdae9ad2b58e2c8fc9513b1e  /tmp/adapter.tar.gz" | sha256sum -c - \
    && mkdir /source && tar -xzf /tmp/adapter.tar.gz -C /source --strip-components=1
WORKDIR /source
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY native-events.patch /tmp/native-events.patch
COPY LaomedoExtension.ts src/LaomedoExtension.ts
COPY LaomedoExtension.test.ts src/LaomedoExtension.test.ts
RUN git apply /tmp/native-events.patch && npm run typecheck \
    && npx vitest run src/LaomedoExtension.test.ts --no-file-parallelism && npm run build \
    && sha256sum /tmp/native-events.patch src/LaomedoExtension.ts dist/index.js > /tmp/adapter-checksums.txt

FROM node:22-bookworm-slim@sha256:de170b39439eb0e5a3444ad7d60b015614a381e10fecae2e30ec9e735122f38d
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git python3 ripgrep \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 runner && useradd --uid 10001 --gid 10001 --create-home runner \
    && mkdir /draft /opt/acp && chown runner:runner /draft
COPY package.json package-lock.json /opt/codex/
RUN npm ci --prefix /opt/codex --omit=dev --ignore-scripts --no-audit --no-fund \
    && ln -s /opt/codex/node_modules/.bin/codex /usr/local/bin/codex \
    && test "$(codex --version)" = "codex-cli 0.159.2"
COPY --from=adapter /source/dist/index.js /opt/acp/index.mjs
COPY --from=adapter /source/LICENSE /opt/acp/LICENSE
COPY --from=adapter /tmp/adapter-checksums.txt /opt/acp/adapter-checksums.txt
LABEL org.opencontainers.image.source="https://github.com/agentclientprotocol/codex-acp" \
    org.opencontainers.image.revision="68d7d2d5ddfc0ed5746f9f6130892dda685e65dd" \
    org.opencontainers.image.licenses="Apache-2.0"
USER runner
ENV HOME=/home/runner CODEX_PATH=/usr/local/bin/codex LAOMEDO_CODEX_NATIVE_EVENTS=1
WORKDIR /draft
CMD ["node", "/opt/acp/index.mjs"]
