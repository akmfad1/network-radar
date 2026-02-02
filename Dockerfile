# Network Radar Docker Image
# ایمیج داکر سرویس مانیتورینگ شبکه

FROM python:3.11-alpine

# Install system dependencies
RUN apk add --no-cache \
    iputils \
    bind-tools \
    curl \
    libcap

# Create app directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    --index-url https://mirror-pypi.runflare.com/simple/ \
    --trusted-host mirror-pypi.runflare.com

# Copy application files
COPY app.py .
COPY config.yaml .
COPY templates/ templates/

# Create non-root user and grant ping capability
RUN adduser -D -s /bin/sh radar && \
    chown -R radar:radar /app && \
    setcap cap_net_raw+ep /bin/ping

USER radar

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/api/summary || exit 1

# Run application with gunicorn
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
