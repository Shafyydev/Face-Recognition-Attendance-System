# =============================================================================
# Face Recognition Attendance System - Dockerfile
# =============================================================================
# Multi-stage build for the Flask + OpenCV + face_recognition application.
#
# NOTE: Webcam access requires host device passthrough (--device /dev/video0)
# on Linux. On Windows, use the native EXE build for camera features.
#
# Build:   docker build -t attendance-system .
# Run:     docker run -p 5000:5000 -v ./data:/app/data attendance-system
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Builder - Install system deps and Python packages
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

# Install system dependencies for dlib, OpenCV, and face_recognition
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    libopenblas-dev \
    liblapack-dev \
    libx11-dev \
    libgtk-3-dev \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy requirements first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------------------------------------------------------------------------
# Stage 2: Runtime - Slim final image
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Install only runtime system libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    libopenblas0 \
    liblapack3 \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder stage
COPY --from=builder /install /usr/local

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# Copy application code
COPY app.py launcher.py notification_service.py tts_service.py __init__.py ./
COPY database/ database/
COPY face_utils/ face_utils/
COPY templates/ templates/
COPY static/ static/
COPY middleware/ middleware/
COPY gateway/ gateway/
COPY .env.example .env.example

# Create data directories
RUN mkdir -p data/known_faces data/embeddings && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Environment variables
ENV FLASK_APP=app.py \
    FLASK_ENV=production \
    PYTHONUNBUFFERED=1 \
    ATTENDANCE_DB_PATH=/app/data/attendance.db

# Expose Flask port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1

# Start the application
CMD ["python", "app.py"]
