FROM python:3.11-slim

# Install system dependencies for OpenCV and GL/media libraries
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libgomp1 \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project code
COPY . .

# Environment variable default
ENV PYTHONUNBUFFERED=1

# Command to run bot
CMD ["python", "bot.py"]
