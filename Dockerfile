# syntax=docker/dockerfile:1

# The CTRL4 application image intentionally contains source code and Python
# dependencies only. Runtime secrets, MySQL data, the approved model weight,
# generated RAG index, sessions, and logs are supplied as external assets.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# libgomp is required by the CPU runtime used by PyTorch and scikit-learn.
RUN apt-get update \
    && apt-get install --no-install-recommends -y libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
# The current VPS runs CPU inference. Use PyTorch's CPU wheel rather than
# allowing PyPI to resolve the NVIDIA CUDA dependency set on Linux.
RUN python -m pip install --upgrade pip \
    && python -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.5.1 \
    && python -m pip install -r requirements.txt

COPY backend ./backend
COPY ai_engine ./ai_engine
COPY frontend ./frontend

# The process has no need for root privileges. Mounted persistent directories
# must be writable by this runtime user in the deployment environment.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin ctrl4 \
    && mkdir -p /runtime/sessions /runtime/logs /runtime/rag_index \
    && chown -R ctrl4:ctrl4 /app /runtime

USER ctrl4

EXPOSE 5001

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5001/health', timeout=3).read()"

# One worker is intentional: CTRL4 uses CacheLib filesystem sessions and the
# supported topology is one application process on one host.
CMD ["gunicorn", "--workers", "1", "--bind", "0.0.0.0:5001", "--timeout", "180", "--access-logfile", "-", "--error-logfile", "-", "backend.app:app"]
