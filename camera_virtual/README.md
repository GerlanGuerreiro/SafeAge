# Especificação Técnica: Câmera Virtual RTSP Isolada

Este módulo implementa uma câmera de vídeo virtual baseada em software que emula o comportamento exato de uma câmera de segurança física IP. O sistema converte um arquivo de vídeo local (`.mp4`) em um fluxo de transmissão contínuo utilizando o protocolo **RTSP (Real-Time Streaming Protocol)**, tornando-o totalmente compatível com o Frigate NVR sem a necessidade de modificar o sistema de monitoramento principal.

## 1. Motivação e Objetivos

* **Isolamento de Ambiente:** Manter o ambiente de desenvolvimento e simulação de vídeo completamente separado do ecossistema principal do sistema de monitoramento residencial.
* **Transparência para o NVR:** Fazer com que o Frigate processe o sinal gerado por software exatamente da mesma forma que processa uma câmera física, garantindo que os pipelines de detecção de movimento, gravação e IA nativa funcionem sem adaptações no código-fonte.
* **Flexibilidade de Testes:** Permitir alternar rapidamente entre a câmera virtual e a câmera física modificando apenas variáveis de ambiente (`.env`).
* **Eficiência de Recursos:** Utilizar processamento em baixo nível via FFmpeg e pipes de memória para reduzir drasticamente o uso de CPU no ecossistema Docker.

---

## 2. Estrutura de Diretórios

Abaixo está a arquitetura de arquivos implementada para o módulo isolado da câmera virtual:

```text
camera_virtual/
├── videos/
│   └── video_teste.mp4      # Arquivo de vídeo de origem rodando em loop
├── Dockerfile                # Configuração da imagem base (Python + FFmpeg)
├── requirements.txt          # Dependências do ecossistema Python
├── camera.py                 # Script de captura, processamento e injeção de frames
└── docker-compose.yml        # Orquestração do servidor RTSP e do script gerador

## 3. Arquitetura e Fluxo de Dados

A solução adota uma arquitetura de microsserviços dividida em duas camadas dentro do mesmo escopo de rede isolada:

    Gerador de Fluxo (camera.py): * Utiliza a biblioteca OpenCV para decodificar o arquivo video_teste.mp4 frame a frame.

        Redimensiona e sincroniza a taxa de quadros (FPS) em tempo real para evitar sobrecarga.

        Transmite a matriz de bytes brutos dos frames (bgr24) via stdout (Pipe do sistema operacional) diretamente para uma instância do FFmpeg integrada.

    Encodamento e Empacotamento (FFmpeg):

        O processo FFmpeg recebe o fluxo bruto, codifica os frames no codec de vídeo H.264 (perfil de compatibilidade ideal para o Frigate) e aplica os parâmetros -preset ultrafast e -tune zerolatency para mitigar delays.

        Publica o fluxo resultante no servidor RTSP local.

    Servidor de Mídia (MediaMTX):

        Atua como o servidor de streaming (Gateway RTSP), expondo o endpoint /live na porta 8554 para toda a rede Docker compartilhada do projeto.

## 4. Especificações de Implementação dos Arquivos
requirements.txt

Define as dependências leves necessárias, optando pela versão headless do OpenCV para remover dependências de interface gráfica (X11/GUI), ideal para ambientes de containers.
Plaintext

opencv-python-headless==4.9.0.80
numpy==1.26.4

Dockerfile

Baseado em Python 11 slim. Atualizado especificamente para compatibilidade com o ecossistema Debian 13 (Trixie), substituindo bibliotecas gráficas obsoletas pelo pacote moderno libgl1.
Dockerfile

FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libglib2.0-0 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY camera.py .

CMD ["python", "-u", "camera.py"]

docker-compose.yml

Orquestra o servidor de mídia e o gerador em Python. Utiliza o modo de rede de serviço nativo (network_mode: "service:servidor_rtsp") para garantir comunicação instantânea via localhost entre o script e o servidor, enquanto expõe a porta de rede externamente sob o nome rede_compartilhada_nvr.
YAML

networks:
  rede_cameras:
    name: rede_compartilhada_nvr
    driver: bridge

services:
  servidor_rtsp:
    image: bluenviron/mediamtx:latest
    container_name: camera_virtual_server
    ports:
      - "8554:8554"
    networks:
      - rede_cameras

  gerador_fluxo:
    build: .
    container_name: camera_virtual_app
    restart: unless-stopped
    volumes:
      - ./videos:/app/videos:ro
    network_mode: "service:servidor_rtsp"
    depends_on:
      - servidor_rtsp

## 5. Parâmetros de Vídeo Configurados

Para garantir o perfeito equilíbrio entre qualidade de imagem e desempenho de processamento na IA do Frigate, o stream foi padronizado com as seguintes especificações técnicas:

    Resolução Nativa: 1280x720 (HD 720p)

    Taxa de Quadros (FPS): 15 FPS (Consistente com a amostragem ideal para detecção de objetos do Frigate)

    Formato de Pixel Interno: bgr24 convertido para yuv420p (Padrão de compressão H.264)

    Codec de Vídeo: H.264 (MPEG-4 AVC)

## 6. Integração com o Ecossistema Principal

Para que o NVR consuma este serviço, a comunicação é realizada através do DNS interno do Docker. O arquivo .env do sistema principal parametriza a conexão da seguinte forma:
Ini, TOML

CAMERA_HOST=camera_virtual_server
CAMERA_PORT=8554
CAMERA_ENDPOINT=live

A URL final resolvida dinamicamente pelo Frigate passa a ser:

rtsp://camera_virtual_server:8554/live
