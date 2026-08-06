FROM python:3.12-slim AS base

WORKDIR /app

# Install dependencies first for better layer caching
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy source code and migrations
COPY src/ src/
COPY alembic.ini .
COPY migrations/ migrations/

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

CMD ["python", "-m", "src.main"]
