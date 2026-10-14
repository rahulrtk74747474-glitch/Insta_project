FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libsndfile1 git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt requirements-demucs.txt ./
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir -r requirements-demucs.txt
COPY hindi_pipeline ./hindi_pipeline
COPY run.py config.yaml ./
RUN useradd -m -u 10001 reel && mkdir -p /app/output /app/state && chown -R reel:reel /app
USER reel
ENTRYPOINT ["python","run.py"]
