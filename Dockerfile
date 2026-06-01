FROM python:3.14-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install -e . --no-cache-dir

CMD ["discord-quest-bot"]
