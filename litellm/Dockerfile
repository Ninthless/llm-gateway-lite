ARG LITELLM_VERSION=v1.98.0-rc.1

FROM ghcr.io/berriai/litellm-database:${LITELLM_VERSION}

LABEL org.opencontainers.image.source=https://github.com/Ninthless/llm-gateway-lite

COPY config.yaml /app/config.yaml
COPY call_id_hook.py /app/call_id_hook.py

EXPOSE 4000

CMD ["--config", "/app/config.yaml", "--port", "4000", "--num_workers", "1"]
