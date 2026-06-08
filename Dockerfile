FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04 AS base

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    python3.10 python3-pip python3.10-venv \
    git git-lfs ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN git lfs install

RUN groupadd -r ttsuser && useradd -r -g ttsuser -d /app -s /sbin/nologin ttsuser

WORKDIR /app

COPY pyproject.toml .
COPY requirements.txt .

RUN pip3 install --no-cache-dir -r requirements.txt

COPY . .

RUN pip3 install --no-cache-dir -e .

EXPOSE 7869

ENV TTS_AUTO_LOAD_MODEL=1
ENV TTS_AUTO_LOAD_ENGINE=voxcpm2

RUN chown -R ttsuser:ttsuser /app
USER ttsuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:7869/api/system/health')" || exit 1

CMD ["python3", "-m", "integrated_app.cli", "--host", "0.0.0.0", "--port", "7869"]
