FROM python:3.12-slim

ARG GIT_COMMIT=unknown
ENV CANARY_BUILD_COMMIT=${GIT_COMMIT}

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# docker-compose CLI + git (optional CANARY_COMPOSE_GIT_PULL) for CANARY_COMPOSE_UPDATE_ENABLED GUI updates via mounted docker.sock.
# Binaries below are linux-amd64; use buildx with a different Dockerfile stage for arm64 hosts if needed.
ARG DOCKER_STATIC_VERSION=27.3.1
ARG COMPOSE_PLUGIN_VERSION=2.29.7
RUN apt-get update \
  && apt-get install -y --no-install-recommends git ca-certificates curl \
  && curl -fsSL "https://download.docker.com/linux/static/stable/x86_64/docker-${DOCKER_STATIC_VERSION}.tgz" \
    | tar -xz --strip-components=1 -C /usr/local/bin docker/docker \
  && curl -fsSL "https://github.com/docker/compose/releases/download/v${COMPOSE_PLUGIN_VERSION}/docker-compose-linux-x86_64" \
    -o /usr/local/bin/docker-compose \
  && chmod +x /usr/local/bin/docker-compose \
  && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Includes docker-entrypoint.sh (required — do not gitignore)
COPY . /app

# Bundled precedent templates (manifest.json + bundle/*) — populate with scripts/export_precedent_seed.py
COPY precedents_seed /app/precedents_seed

RUN chmod +x /app/app/docker-entrypoint.sh

ENTRYPOINT ["/app/app/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
