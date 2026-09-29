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

COPY pyproject.toml README.md ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini

# BuildKit cache mount keeps downloaded wheels across builds, so a retry resumes instead of
# starting over. The cache lives outside the image layer.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && pip install .

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
