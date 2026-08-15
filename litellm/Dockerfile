FROM ghcr.io/berriai/litellm-database:v1.97.0-rc.1

LABEL org.opencontainers.image.source=https://github.com/Ninthless/llm-gateway-lite

COPY config.yaml /app/config.yaml

EXPOSE 4000

CMD ["--config", "/app/config.yaml", "--port", "4000", "--num_workers", "1"]
