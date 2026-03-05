FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc && \
    rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY . .

# Create data directories
RUN mkdir -p data/state data/logs data/knowledge

# Default port
EXPOSE 8080

# Environment
ENV PYTHONUNBUFFERED=1
ENV AICOS_DASHBOARD_HOST=0.0.0.0
ENV AICOS_DASHBOARD_PORT=8080

# Entrypoint
CMD ["python", "main.py"]
