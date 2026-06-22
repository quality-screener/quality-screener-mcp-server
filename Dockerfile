FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app
COPY . .
RUN uv sync --frozen --no-dev

ENV QSCREENER_MCP_TRANSPORT=streamable-http \
    QSCREENER_MCP_PORT=8080

EXPOSE 8080

CMD ["uv", "run", "--no-sync", "qscreener-mcp"]
