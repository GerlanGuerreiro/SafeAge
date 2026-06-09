import cv2
import subprocess
import time
import os

# Configurações do Stream (Ajuste se o seu vídeo for muito diferente)
WIDTH = 1280
HEIGHT = 720
FPS = 15

# Como o container vai rodar em uma rede compartilhada, transmitimos para 'localhost'
# O MediaMTX (que vai rodar junto neste container) vai disponibilizar para o Frigate
rtsp_url = "rtsp://127.0.0.1:8554/live"
video_path = "/app/videos/video_teste.mp4"

# Comando FFmpeg otimizado (Ultra-fast e Zero Latency)
command = [
    'ffmpeg',
    '-y',
    '-f', 'rawvideo',
    '-vcodec', 'rawvideo',
    '-pix_fmt', 'bgr24',
    '-s', f'{WIDTH}x{HEIGHT}',
    '-r', str(FPS),
    '-i', '-',  # Entrada via Pipe (Python -> FFmpeg)
    '-c:v', 'libx264',
    '-pix_fmt', 'yuv420p',
    '-preset', 'ultrafast',
    '-tune', 'zerolatency',
    '-f', 'rtsp',
    rtsp_url
]

print("Aguardando inicialização do servidor de mídia...")
time.sleep(3)  # Dá tempo para o servidor RTSP interno subir

print(f"Iniciando transmissão RTSP em: {rtsp_url}")
process = subprocess.Popen(command, stdin=subprocess.PIPE)

try:
    while True:
        if not os.path.exists(video_path):
            print(f"Erro: Coloque o vídeo em {video_path}")
            time.sleep(5)
            continue

        cap = cv2.VideoCapture(video_path)

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break  # Vídeo terminou, o loop principal vai reiniciar o arquivo

            # Garante que o frame está no tamanho correto
            frame = cv2.resize(frame, (WIDTH, HEIGHT))

            # Envia o frame bruto para o FFmpeg
            process.stdin.write(frame.tobytes())

            # Sincroniza com o FPS desejado
            time.sleep(1.0 / FPS)

        cap.release()
        print("Vídeo reiniciado (Loop)...")

except KeyboardInterrupt:
    print("Finalizando câmera virtual...")
finally:
    if process.stdin:
        process.stdin.close()
    process.terminate()
