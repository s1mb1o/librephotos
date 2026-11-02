FROM python:3.14-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app/src
WORKDIR /app
COPY apps/mcp/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY apps/mcp/src /app/src
USER 10001:10001
ENTRYPOINT ["python", "-m", "librephotos_mcp"]
CMD ["--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8000"]
