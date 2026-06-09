FROM python:3.11-slim

# Instala o FFmpeg e bibliotecas modernas do sistema necessárias para o OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libglib2.0-0 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copia e instala as dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o script
COPY camera.py .

# Comando para rodar o script
CMD ["python", "-u", "camera.py"]
