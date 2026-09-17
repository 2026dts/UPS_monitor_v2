FROM python:3.12-slim

# curl for health check, libpq-dev for psycopg2
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all Python source files
COPY *.py .

# Non-root user for security
RUN adduser --disabled-password --no-create-home appuser
USER appuser

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:5000/api/status || exit 1

ENTRYPOINT ["python3", "main.py"]
