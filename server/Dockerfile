# DEP-003 多阶段构建 + 非 root 运行
FROM python:3.11-slim AS base

WORKDIR /srv/app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini

# 非 root：容器逃逸时的第一道减损
RUN useradd --system --uid 10001 appuser \
 && mkdir -p /srv/data && chown -R appuser:appuser /srv/data /srv/app
USER appuser

ENV PLATFORM_DATABASE_URL=sqlite:////srv/data/platform.db \
    PYTHONUNBUFFERED=1
VOLUME ["/srv/data"]
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
