# Any container host (Railway, Koyeb, Fly.io, Cloud Run, Hugging Face Spaces...).
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agent ./agent
COPY web ./web
COPY data ./data
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn web.app:app --host 0.0.0.0 --port ${PORT}"]
