# Use Python 3.10 slim image for smaller size
FROM python:3.10.14-slim
RUN apt-get update && apt-get install -y tesseract-ocr tesseract-ocr-jpn
# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/

# Change to src directory for proper imports
WORKDIR /app/src

# Expose port (Render will override this with $PORT)
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start the application
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]