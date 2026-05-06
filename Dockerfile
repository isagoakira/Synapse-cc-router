FROM python:3.11-slim AS builder

WORKDIR /build
COPY . .
RUN pip install --no-cache-dir build && \
    python -m build --wheel

# ── Runtime stage ───────────────────────────────────────────────
FROM python:3.11-slim

RUN groupadd -r ccrouter && useradd -r -g ccrouter -d /app -s /sbin/nologin ccrouter

WORKDIR /app

# Install only the wheel
COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

# Default port
EXPOSE 8765

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8765/health')" || exit 1

# Run as non-root user
USER ccrouter

ENTRYPOINT ["python", "-m", "cc_router"]
CMD ["--host", "0.0.0.0", "--port", "8765"]
