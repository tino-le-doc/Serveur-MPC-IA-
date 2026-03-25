FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY mcp_ultra.py .
CMD ["python", "mcp_ultra.py"]
