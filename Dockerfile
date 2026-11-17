FROM python:3.10-slim
WORKDIR /app

RUN pip install --no-cache-dir aiogram aiosqlite aiohttp

COPY . .
CMD ["python", "bot.py"]
