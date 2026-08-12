# syntax=docker/dockerfile:1

FROM node:22-alpine AS frontend-build
WORKDIR /build/frontend
RUN corepack enable && corepack prepare pnpm@11.16.0 --activate
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN pnpm build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    QUANTLAB_MODE=WEB \
    QUANTLAB_HOST=0.0.0.0 \
    QUANTLAB_PORT=8000 \
    QUANTLAB_DATA_DIR=/data \
    QUANTLAB_FRONTEND_DIR=/app/frontend
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/
RUN python -m pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 quantlab \
    && mkdir -p /data \
    && chown quantlab:quantlab /data
COPY --from=frontend-build /build/frontend/dist/ /app/frontend/
USER quantlab
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('QUANTLAB_PORT','8000')+'/api/health/ready', timeout=3)"
CMD ["python", "-m", "quant_lab.server"]
