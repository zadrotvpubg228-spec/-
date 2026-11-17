FROM python:3.10-slim
WORKDIR /app

RUN pip install --no-cache-dir aiogram==3.32.0 aiosqlite==0.22.1 aiohttp==3.14.5

COPY . .
CMD ["python", "bot.py"]
