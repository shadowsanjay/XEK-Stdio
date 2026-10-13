FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-noto-core libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml ./
COPY services/api services/api
RUN pip install --no-cache-dir '.[transcription]'
COPY migrations migrations
COPY alembic.ini ./
COPY workflows workflows
COPY examples examples
RUN useradd -m -u 10001 xek && mkdir /data && chown xek:xek /data
USER xek
EXPOSE 8000
CMD ["uvicorn", "xek.main:app", "--host", "0.0.0.0", "--port", "8000"]
