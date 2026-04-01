"""
consumidor_mqtt.py
------------------
Consumidor MQTT integrado ao loop asyncio do FastAPI.
Configuração lida de settings em vez de os.getenv().
"""

import asyncio
import json

import paho.mqtt.client as mqtt

from core.config import settings
from core.logging_config import get_logger, LogContexto

logger = get_logger(__name__)

# Lê configurações do settings centralizado — tipadas e validadas no startup
BROKER_HOST    = settings.endereco_broker_mqtt
BROKER_PORT    = settings.porta_broker_mqtt      # já é int, sem int() manual
TOPICO_EVENTOS = settings.topico_mqtt_frigate
CLIENT_ID      = "monitoramento-backend"

_fila_mensagens: asyncio.Queue = asyncio.Queue()


# ---------------------------------------------------------------------------
# Callbacks síncronos do paho
# ---------------------------------------------------------------------------

def _ao_conectar(client, userdata, flags, rc):
    if rc == 0:
        logger.info(
            "Conectado ao broker MQTT",
            broker=BROKER_HOST,
            porta=BROKER_PORT,
            **{LogContexto.TOPICO_MQTT: TOPICO_EVENTOS},
        )
        client.subscribe(TOPICO_EVENTOS)
        logger.debug("Subscrito no tópico", topico=TOPICO_EVENTOS)
    else:
        logger.error("Falha na conexão MQTT", codigo_retorno=rc)


def _ao_desconectar(client, userdata, rc):
    if rc == 0:
        logger.info("Desconectado do broker MQTT (encerramento limpo)")
    else:
        logger.warning("Desconexão inesperada do broker MQTT", codigo_retorno=rc)


def _ao_receber_mensagem(client, userdata, message):
    try:
        payload = json.loads(message.payload.decode("utf-8"))
        _fila_mensagens.put_nowait(payload)
    except Exception as e:
        logger.warning("Payload MQTT inválido", erro=str(e))


# ---------------------------------------------------------------------------
# Processador async
# ---------------------------------------------------------------------------

async def _processar_fila():
    logger.info("Processador de fila MQTT iniciado")
    while True:
        dados = await _fila_mensagens.get()

        tipo_evento = dados.get("type", "desconhecido")
        after       = dados.get("after", {})
        camera_id   = after.get("camera", "desconhecida")
        label       = after.get("label", "desconhecido")
        confianca   = after.get("score", 0.0)
        evento_id   = after.get("id", "sem-id")

        logger.info(
            "Evento MQTT processado",
            **{
                LogContexto.CAMERA_ID:   camera_id,
                LogContexto.TIPO_EVENTO: tipo_evento,
                LogContexto.CONFIANCA:   round(confianca, 3),
                LogContexto.EVENTO_ID:   evento_id,
                "label":                 label,
            },
        )

        if label != "person":
            logger.debug("Evento ignorado (não é person)", label=label)
            _fila_mensagens.task_done()
            continue

        try:
            from analise_comportamento import processar_evento
            await asyncio.to_thread(processar_evento, dados)
        except Exception as e:
            logger.exception(
                "Erro ao processar evento",
                erro=str(e),
                **{LogContexto.EVENTO_ID: evento_id},
            )

        _fila_mensagens.task_done()


# ---------------------------------------------------------------------------
# Ponto de entrada público
# ---------------------------------------------------------------------------

async def iniciar_consumidor() -> None:
    """
    Inicia o cliente MQTT com reconexão automática (backoff exponencial).
    Chamado pelo lifespan do main.py como asyncio background task.
    """
    asyncio.create_task(_processar_fila())

    client = mqtt.Client(client_id=CLIENT_ID, clean_session=True)
    client.on_connect    = _ao_conectar
    client.on_disconnect = _ao_desconectar
    client.on_message    = _ao_receber_mensagem

    espera = 2

    while True:
        try:
            logger.info(
                "Tentando conectar ao broker MQTT",
                broker=BROKER_HOST,
                porta=BROKER_PORT,
            )
            await asyncio.to_thread(client.connect, BROKER_HOST, BROKER_PORT, 60)
            client.loop_start()
            logger.info("Consumidor MQTT ativo e aguardando eventos")
            espera = 2

            while True:
                await asyncio.sleep(5)
                if not client.is_connected():
                    logger.warning("Cliente MQTT desconectou — reconectando...")
                    client.loop_stop()
                    break

        except (ConnectionRefusedError, OSError) as e:
            logger.warning(
                "Broker MQTT indisponível",
                erro=str(e),
                aguardando_segundos=espera,
            )
            await asyncio.sleep(espera)
            espera = min(espera * 2, 30)

        except asyncio.CancelledError:
            logger.info("Consumidor MQTT encerrado pelo shutdown")
            client.loop_stop()
            client.disconnect()
            return

        except Exception as e:
            logger.exception("Erro inesperado no consumidor MQTT", erro=str(e))
            await asyncio.sleep(espera)
            espera = min(espera * 2, 30)
