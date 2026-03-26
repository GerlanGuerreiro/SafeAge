"""
Motor de análise de comportamento do idoso.

Responsável por:

- detectar imobilidade
- detectar ausência prolongada
- gerar alertas
"""

from datetime import datetime, timedelta
from core.logging_config import get_logger
logger = get_logger(__name__)

# guarda último evento detectado
ultimo_evento_camera = {}

# limites de comportamento
TEMPO_IMOBILIDADE = timedelta(minutes=15)
TEMPO_AUSENCIA = timedelta(hours=2)


def registrar_evento(camera):
    """
    Atualiza último momento que a pessoa foi vista.
    """

    ultimo_evento_camera[camera] = datetime.now()


def verificar_imobilidade(camera):
    """
    Verifica se a pessoa está imóvel por muito tempo.
    """

    if camera not in ultimo_evento_camera:
        return None

    agora = datetime.now()
    ultimo = ultimo_evento_camera[camera]

    if agora - ultimo > TEMPO_IMOBILIDADE:
        return {
            "tipo_alerta": "imobilidade",
            "camera": camera,
            "tempo_sem_movimento": str(agora - ultimo)
        }

    return None


def verificar_ausencia(camera):
    """
    Verifica se não houve presença por muito tempo.
    """

    if camera not in ultimo_evento_camera:
        return None

    agora = datetime.now()
    ultimo = ultimo_evento_camera[camera]

    if agora - ultimo > TEMPO_AUSENCIA:
        return {
            "tipo_alerta": "ausencia_prolongada",
            "camera": camera,
            "tempo": str(agora - ultimo)
        }

    return None

def processar_evento(dados: dict) -> None:
    """
    Ponto de entrada único chamado pelo consumidor MQTT.
    Orquestra registro e verificações de comportamento.
    """
    after     = dados.get("after", {})
    camera    = after.get("camera", "desconhecida")

    # Registra presença
    registrar_evento(camera)

    # Verifica comportamentos anômalos
    alerta_imobilidade = verificar_imobilidade(camera)
    alerta_ausencia    = verificar_ausencia(camera)

    if alerta_imobilidade:
        logger.warning("Alerta de imobilidade detectado", **alerta_imobilidade)

    if alerta_ausencia:
        logger.warning("Alerta de ausência prolongada detectada", **alerta_ausencia)
