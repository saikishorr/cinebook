# Start from a small official Python image; this is the only build stage.
FROM python:3.14-slim

# Keep Python output visible in container logs and avoid unnecessary cache files.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    API_WORKERS=2

# Use a predictable location for application files.
WORKDIR /app

# Install dependencies first so Docker can reuse this layer when only app code changes.
COPY requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

# Copy only the backend application package into the image.
COPY app/ ./app/

# Create a dedicated, non-root account with its own home directory.
RUN useradd --create-home --home-dir /home/appuser appuser
USER appuser

# Document the port used by the ASGI server.
EXPOSE 8000

# Probe the health endpoint without relying on curl in the slim image.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/health', timeout=4).read()"]

# Run two Uvicorn worker processes and trust forwarded headers from the proxy.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${API_WORKERS:-2} --proxy-headers --forwarded-allow-ips '*'"]
