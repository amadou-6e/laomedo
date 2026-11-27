FROM python:3.12.12-slim-bookworm@sha256:2986c55feb36e6cae00fa1fefb454283e4b33f35e75ff8bdd123b134130be301
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp LANGFLOW_DO_NOT_TRACK=true
LABEL org.opencontainers.image.source="https://github.com/amadou-6e/laomedo" \
    laomedo.lfx.revision="fec71dca901949c09ed4d63315804337cd2eb13d"
COPY requirements.txt /opt/requirements.txt
RUN python -m pip install --no-cache-dir --require-hashes -r /opt/requirements.txt \
    && python -m pip install --no-cache-dir hatchling==1.27.0
COPY src/lfx /opt/lfx
COPY src/sdk /opt/sdk
RUN python -m pip install --no-cache-dir --no-deps --no-build-isolation /opt/sdk /opt/lfx \
    && python -m pip check
USER 65532:65532
WORKDIR /tmp
ENTRYPOINT ["python"]
