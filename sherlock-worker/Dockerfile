FROM python:3.13-slim

# Create a non-root user and group
RUN addgroup --system appgroup && adduser --system --group appuser

WORKDIR /app

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the worker code
COPY . /app/

# Give ownership of the directory to the non-root user
RUN chown -R appuser:appgroup /app

# Drop root privileges!
USER appuser

# Run the server using the dynamic $PORT provided by Cloud Run
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]