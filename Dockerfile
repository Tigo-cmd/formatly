# Formatly: the website and the API in one container.
#   docker compose up --build      then open http://localhost:8000

# Base images can come from a mirror, e.g. --build-arg REGISTRY=public.ecr.aws/docker/library/
ARG REGISTRY=
FROM ${REGISTRY}node:22-slim AS web
WORKDIR /app
COPY app/package.json app/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY app/ ./
RUN npm run build

FROM ${REGISTRY}python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    FORMATLY_DATABASE_URL=sqlite:////data/formatly.db \
    FORMATLY_STORAGE_DIR=/data/files \
    FORMATLY_WEB_DIR=/srv/web
WORKDIR /srv
COPY engine/ engine/
COPY server/ server/
RUN pip install --no-cache-dir ./engine ./server
COPY --from=web /app/dist /srv/web
RUN useradd --create-home formatly && mkdir -p /data && chown formatly /data
USER formatly
VOLUME /data
EXPOSE 8000
CMD ["uvicorn", "formatly_server.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
