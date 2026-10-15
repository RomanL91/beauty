# Образ инструментов спайка: MCP-заглушка, bootstrap профилей и прогон сценариев.
# Docker CLI нужен, чтобы выполнять `hermes profile …` внутри контейнера Hermes (docker exec).
FROM docker:27-cli AS docker-cli

FROM python:3.13-slim

COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    SPIKE_DATA_DIR=/spike

WORKDIR /app
RUN pip install "mcp>=2.0" "httpx>=0.28" "uvicorn[standard]>=0.32" "pyyaml>=6"
COPY spikes ./spikes

ENTRYPOINT ["python", "-m", "spikes.hermes"]
CMD ["--help"]
