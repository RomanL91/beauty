# Один образ на все роли: api | bot | relay | scheduler (выбирается аргументом команды).
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install .

COPY alembic.ini ./
COPY migrations ./migrations

RUN useradd --system --uid 10001 beauty && mkdir -p /app/var/files && chown -R beauty /app/var
USER beauty

ENTRYPOINT ["beauty"]
CMD ["api"]
