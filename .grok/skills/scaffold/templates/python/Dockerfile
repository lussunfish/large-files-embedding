FROM ghcr.io/astral-sh/uv:python{{RUNTIME_VERSION}}-bookworm-slim
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
COPY pyproject.toml README.md ./
COPY src ./src
{{DOCKER_UV_SYNC}}
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD {{DOCKER_CMD}}
