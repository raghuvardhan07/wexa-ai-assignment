FROM python:3.13-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml uv.lock README.md ./
COPY cascade/ ./cascade/
COPY seed.py ./

RUN uv sync --frozen --no-dev

EXPOSE 8000

CMD ["uv", "run", "cascade-api"]
