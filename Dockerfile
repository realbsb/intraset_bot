FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY handlers ./handlers
COPY services ./services

RUN pip install --no-cache-dir -e .

COPY . .

CMD ["python", "bot.py"]