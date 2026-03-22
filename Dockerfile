FROM python:3.13-slim

# Create a non-root user and group
RUN addgroup --system appgroup && adduser --system --group appuser

WORKDIR /app

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY main.py .

# Create the data directory and give ownership ONLY to the non-root user
RUN mkdir -p /app/data && chown -R appuser:appgroup /app

# Drop root privileges!
USER appuser

# Run the server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]