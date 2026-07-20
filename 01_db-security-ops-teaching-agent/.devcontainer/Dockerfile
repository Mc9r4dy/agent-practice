FROM node:24-bookworm-slim AS node_runtime

FROM python:3.13-slim-bookworm

COPY --from=node_runtime /usr/local/ /usr/local/

RUN apt-get update \
    && apt-get install -y --no-install-recommends default-mysql-client git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && git config --system --add safe.directory /workspace \
    && useradd --create-home --shell /bin/bash vscode \
    && pip install --no-cache-dir pytest==9.1.1 PyYAML==6.0.3 PyMySQL==1.2.0

WORKDIR /workspace
USER vscode
CMD ["sleep", "infinity"]
