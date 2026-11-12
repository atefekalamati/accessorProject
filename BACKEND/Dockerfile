# syntax=docker/dockerfile:1
FROM python:3.12-slim AS runtime

# pip reads PIP_INDEX_URL from the environment of RUN steps; override via compose build args.
ARG PIP_INDEX_URL=https://pypi.org/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10

RUN groupadd --system app && useradd --system --gid app --create-home app

WORKDIR /srv/app

# Dependencies first, from the hashed lock (SEC-06): a tampered or unpinned package fails the
# build, and this layer stays cached until the lock changes.
# BuildKit cache mount keeps downloaded wheels across builds, so a retry resumes instead of
# starting over. The cache lives outside the image layer.
COPY requirements.lock ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --require-hashes --no-deps -r requirements.lock

COPY pyproject.toml README.md ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini

# The project itself only; every dependency already came from the lock.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-deps .

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
