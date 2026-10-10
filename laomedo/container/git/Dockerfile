FROM laomedo-codex-boundary:0.159.2@sha256:7b79ce12be47d6c8262dd4043895112d204416bda5cd891d124775df55587239

# This derivative adds Git without rebuilding Codex or changing the historic
# default image. The base digest is the local IMAGE_ID in local_runner.py.
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

USER runner
ENV HOME=/home/runner
WORKDIR /draft
