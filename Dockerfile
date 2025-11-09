# Use a slim Python base image
FROM python:3.10-slim

# Set the working directory inside the container
WORKDIR /usr/src/app

# Set environment variables for Python
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install curl, which is needed for the HEALTHCHECK
RUN apt-get update && apt-get install -y curl \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code
COPY . .

# Expose the port the app runs on
EXPOSE 8081

# Add health check (required by your assignment)
# This checks if the /healthz endpoint is responsive.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8081/healthz || exit 1

# Run the application with Gunicorn (production server)
CMD ["gunicorn", "--bind", "0.0.0.0:8081", "--workers", "4", "app:app"]