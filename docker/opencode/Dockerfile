FROM node:22-bookworm-slim@sha256:de170b39439eb0e5a3444ad7d60b015614a381e10fecae2e30ec9e735122f38d
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git python3 ripgrep \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 runner && useradd --uid 10001 --gid 10001 --create-home runner \
    && mkdir /draft && chown runner:runner /draft
COPY package.json package-lock.json /opt/opencode/
RUN npm ci --prefix /opt/opencode --omit=dev --no-audit --no-fund \
    && ln -s /opt/opencode/node_modules/.bin/opencode /usr/local/bin/opencode \
    && test "$(opencode --version)" = "1.18.33"
USER runner
ENV HOME=/home/runner
WORKDIR /draft
ENTRYPOINT ["opencode"]
CMD ["acp"]
