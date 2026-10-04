FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY tests ./tests
COPY conftest.py pytest.ini ./
COPY inspect_cli.py .
EXPOSE 9800
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9800"]
