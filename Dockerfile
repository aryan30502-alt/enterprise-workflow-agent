# Use Python 3.11 slim image as requested
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements first for layer caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project
COPY . .

# Create the output directory
RUN mkdir -p output

# Default command
CMD ["python", "main.py"]
