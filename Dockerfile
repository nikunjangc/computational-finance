# Live agentic market-event tracker
FROM python:3.11-slim

# Keep Python lean and unbuffered so `docker logs` streams alerts in real time.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements-tracker.txt ./
RUN pip install --no-cache-dir -r requirements-tracker.txt

# Copy the application.
COPY stock_tracker ./stock_tracker
COPY run_tracker.py ./

# Run as a non-root user.
RUN useradd --create-home --uid 10001 tracker
USER tracker

# Default: live agentic mode (override with `--demo` for a smoke test).
ENTRYPOINT ["python", "run_tracker.py"]
CMD ["--live"]
