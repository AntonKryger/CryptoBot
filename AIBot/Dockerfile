FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ src/
COPY main_ai.py .
RUN mkdir -p logs data
CMD ["python", "-u", "main_ai.py", "--config", "config.yaml"]
