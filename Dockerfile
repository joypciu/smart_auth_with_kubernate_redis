# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /build

RUN apt-get update \
    && apt-get install --no-install-recommends -y build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy only dependency manifests so this expensive layer is cached
# independently of any application code changes.
COPY pyproject.toml README.md ./

# Wheel only the declared dependencies — NOT the app package itself.
# This way no stub is needed and nothing in site-packages will shadow
# the real app code mounted or copied at /code.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip \
    && python3 -c "\
import subprocess, sys, tomllib; \
data = tomllib.load(open('pyproject.toml','rb')); \
deps = data['project']['dependencies']; \
subprocess.run([sys.executable,'-m','pip','wheel','--wheel-dir','/wheels']+deps, check=True)"

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /code

RUN addgroup --system --gid 10001 app \
    && adduser --system --uid 10001 --ingroup app --home /home/app app

COPY --from=builder /wheels /wheels
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip \
    && pip install /wheels/*.whl \
    && rm -rf /wheels

COPY --chown=app:app app ./app
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app alembic.ini ./alembic.ini
COPY --chown=app:app pyproject.toml ./pyproject.toml
COPY --chown=app:app README.md ./README.md

USER app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
