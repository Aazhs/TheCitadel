FROM python:3.12-slim AS base

WORKDIR /app

# Copy project files needed for installation
COPY pyproject.toml docs/README.md ./
COPY src/ src/

# Install dependencies and the project itself
RUN pip install --no-cache-dir .

# Copy remaining files
COPY alembic.ini .
COPY migrations/ migrations/

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

CMD ["python", "-m", "src.main"]
