# Memory Rhythm backend — FastAPI on Python 3.12, managed with uv.
# Boots with zero secrets (AI_PROVIDER=mock, STORE=memory): no DB, no API key.
FROM python:3.12-slim

# uv: fast Python package/deps manager.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install dependencies first (better layer caching). README is referenced by
# pyproject's [project].readme, so provide a stub if the real one is absent.
COPY pyproject.toml ./
RUN touch README.md && uv sync --no-install-project

# Copy the application source.
COPY app ./app

# Default demo config — overridable at run time:
#   docker run -e AI_PROVIDER=openai -e OPENAI_API_KEY=sk-... ...
ENV AI_PROVIDER=mock \
    STORE=memory \
    PORT=8000

EXPOSE 8000

# Run uvicorn through uv so the synced virtualenv is used.
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
