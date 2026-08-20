FROM node:22-alpine AS miniapp
WORKDIR /src/frontend/mini-app
COPY frontend/mini-app/package.json ./
RUN npm install --no-audit --no-fund
COPY frontend/mini-app ./
RUN npm run build

FROM python:3.12-slim AS runtime
ARG MINI_APP_RELEASE_SHA=unknown
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
RUN pip install --no-cache-dir . && rm -rf ./app/web/mini_app
COPY --from=miniapp /src/frontend/mini-app/out ./app/web/mini_app
RUN printf '{"sha":"%s"}\n' "${MINI_APP_RELEASE_SHA}" > ./app/web/mini_app/release.json
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
