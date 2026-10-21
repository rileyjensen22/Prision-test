FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN mkdir isd && pip install --no-cache-dir -e ".[dev]"
COPY . .
CMD ["uvicorn", "isd.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
