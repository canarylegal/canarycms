FROM python:3.12-slim@sha256:6c4dd321d176d61ea848dc8c73a4f7dbae8f70e0ee48bb411ea2f045b599fa8e

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# git: optional live commit readout when CANARY_COMPOSE_PROJECT_DIR is mounted (Admin → Deploy notify-only).
# Docker CLI was removed — in-app Compose updates are not supported (no docker.sock).
COPY debian.sources /etc/apt/sources.list.d/debian.sources
RUN apt-get update \
  && apt-get install -y --no-install-recommends git=1:2.47.3-0+deb13u1 ca-certificates=20250419+deb13u1 \
  && rm -rf /var/lib/apt/lists/*

COPY build-requirements.lock requirements.lock /app/
RUN python -m pip install --no-cache-dir --require-hashes -r build-requirements.lock \
  && python -m pip install --no-cache-dir --require-hashes --no-build-isolation -r requirements.lock \
  && python -m pip check

ARG GIT_COMMIT=unknown
ENV CANARY_BUILD_COMMIT=${GIT_COMMIT}

# Includes docker-entrypoint.sh (required — do not gitignore)
COPY . /app

# Bundled precedent templates (manifest.json + bundle/*) — populate with scripts/export_precedent_seed.py
COPY precedents_seed /app/precedents_seed

RUN chmod +x /app/app/docker-entrypoint.sh

ENTRYPOINT ["/app/app/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
