FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app.py .
COPY config.py .
COPY evc_api.py .
COPY templates/ templates/

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import requests; r=requests.get('http://localhost:5000/health', timeout=5); r.raise_for_status()"

# Run with production server
CMD ["python", "app.py"]
