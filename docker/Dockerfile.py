FROM python:3.10-slim

WORKDIR /app

# Install system dependencies required for OpenCV, building native extensions, etc.
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgl1 \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create a non-root user for security
RUN useradd -m appuser

COPY . .

# Adjust permissions for directories the app might write to
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 9381
ENV PYTHONPATH=/app
CMD ["hypercorn", "api.apps:create_app()", "-b", "0.0.0.0:9381"]
