FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ src/
COPY main_kraken.py .
RUN mkdir -p logs data shared
CMD ["python", "-u", "main_kraken.py", "--config", "config.yaml"]
