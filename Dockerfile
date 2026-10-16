# Один образ на все роли: api | bot | relay | scheduler | worker | mcp (выбирается аргументом команды).
FROM docker:27-cli AS docker-cli

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

ENTRYPOINT ["beauty"]

# Операции с Hermes (`beauty agent bootstrap|provision`): docker CLI для `docker exec` в
# контейнер Hermes и root — файлам профилей нужно вернуть владельца Hermes (UID 10000).
FROM base AS ops
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
CMD ["--help"]

FROM base AS app
RUN useradd --system --uid 10001 beauty && mkdir -p /app/var/files && chown -R beauty /app/var
USER beauty
CMD ["api"]
