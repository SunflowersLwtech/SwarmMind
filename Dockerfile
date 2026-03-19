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

# Start: uvicorn serves both the FastAPI backend and static frontend
# Render uses PORT env var (default 10000)
CMD uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-10000}
