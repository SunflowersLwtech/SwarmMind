# SwarmMind — multi-stage build for Render deployment
# Stage 1: Build frontend
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python runtime
FROM python:3.13-slim
WORKDIR /app

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend
COPY backend/ ./backend/

# Copy frontend build artifacts
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# Copy config files
COPY .env.example ./

EXPOSE 10000

# Start script: write SA credentials from env var, then launch uvicorn
# Render passes GOOGLE_APPLICATION_CREDENTIALS_JSON as env var;
# Vertex AI SDK needs it as a file at GOOGLE_APPLICATION_CREDENTIALS path.
# Use python to write the file to avoid shell escaping issues with \n in private keys.
CMD ["sh", "-c", "python -c \"import os; j=os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON',''); open('/tmp/gcp-sa-key.json','w').write(j) if j else None\" && export GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcp-sa-key.json && uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
