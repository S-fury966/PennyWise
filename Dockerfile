# ============================================================================
# Backend Dockerfile — AI Finance Controller (Reconciliation Agent)
# ============================================================================
# Placed at the project root (not in backend/) because backend/main.py
# imports from src/ which lives at the project root level. The build
# context MUST include both backend/ and src/ directories.
#
# Base image: Python 3.12-slim. Chosen because the codebase uses Python
# 3.10+ syntax (dict | None union types in backend/main.py, str | None
# in type hints throughout src/). Python 3.12-slim provides a good
# balance of modern features and small image size.
# ============================================================================

FROM python:3.12-slim AS backend

# Prevent Python from writing .pyc files and enable unbuffered stdout/stderr
# so logs appear immediately in docker logs.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# --- Dependency layer (cached unless requirements.txt changes) ---
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Application code ---
# Copy backend/ and src/ — the two directories needed at runtime.
COPY backend/ backend/
COPY src/ src/

# --- Data directories ---
# data/raw/ and data/ground_truth/ contain committed sample data.
# data/custom/ and output/ are runtime-generated — create them empty
# so the app can write into them without errors.
COPY data/raw/ data/raw/
COPY data/ground_truth/ data/ground_truth/
RUN mkdir -p data/custom output

# --- Run the server ---
# EXPOSE documents the port the container listens on.
EXPOSE 8000

# Bind to 0.0.0.0, NOT 127.0.0.1.
# 127.0.0.1 inside a container only accepts connections from within that
# same container (i.e. from other processes in the same network namespace).
# Docker networking needs the server to accept connections from the host
# machine and from other containers on the bridge network, so we bind to
# all interfaces (0.0.0.0).
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
