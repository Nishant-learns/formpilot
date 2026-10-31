# Production Dockerfile for FormPilot (FastAPI + Playwright Chromium + React Frontend)
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

# Set environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8000 \
    HOST=0.0.0.0 \
    FORMPILOT_ENV=production \
    FORMPILOT_DEMO_MODE=1 \
    FORMPILOT_DATA_DIR=/app/data \
    FORMPILOT_UPLOADS_DIR=/app/uploads

# Install Node.js for building frontend
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Install and build frontend
COPY frontend/package*.json ./frontend/
RUN cd frontend && npm install
COPY frontend/ ./frontend/
RUN cd frontend && npm run build

# Copy backend and data
COPY backend/ ./backend/
COPY data/ ./data/

# Ensure runtime directories exist
RUN mkdir -p /app/data /app/uploads /app/data/runs

EXPOSE 8000

# Start unified server
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
