FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY src ./src

RUN pip install --no-cache-dir -e .

CMD ["uvicorn", "novel_translation_backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
