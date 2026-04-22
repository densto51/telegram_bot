FROM python:3.12-slim

WORKDIR /app

# Системные зависимости (ffmpeg нужен для конвертации аудио под Whisper)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Создаём директорию для данных
RUN mkdir -p /app/data
ENV DATABASE_PATH=/app/data/finance.db

CMD ["python", "main.py"]
