# Multi-stage (research.md R-docker): uv y la caché del build no llegan a runtime.
FROM python:3.12.15-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.12.15-slim
# Mismo WORKDIR que el builder: el .venv guarda rutas absolutas.
WORKDIR /app
# Borra el paquete, no solo el script: así `python -m pip` tampoco anda.
RUN pip uninstall -y pip && useradd --system --no-create-home app
COPY --from=builder /app/.venv /app/.venv
COPY app/ ./app/
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER app
# slim no trae curl.
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${PORT:-8000}/health')"
# Forma shell: la forma exec no expande $PORT.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
