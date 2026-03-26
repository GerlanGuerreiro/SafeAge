"""
consumidor_mqtt.py
------------------
Consumidor MQTT integrado ao loop asyncio do FastAPI.

Por que async em vez de loop_forever()?
- loop_forever() é BLOQUEANTE — trava a thread e impede o uvicorn de funcionar
- asyncio permite rodar o consumidor MQTT em paralelo com a API HTTP
- Um único processo, sem necessidade de supervisor ou segundo container

Fluxo de execução:
  lifespan (main.py)
    └── asyncio.create_task(iniciar_consumidor())
          └── loop: conecta → subscreve → processa mensagens → reconecta se cair
"""

import asyncio
import json
import os

import paho.mqtt.client as mqtt

from core.logging_config import get_logger, LogContexto

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
BROKER_HOST    = os.getenv("ENDERECO_BROKER_MQTT", "broker_mqtt")
BROKER_PORT    = int(os.getenv("PORTA_BROKER_MQTT", "1883"))
TOPICO_EVENTOS = os.getenv("TOPICO_MQTT_FRIGATE", "frigate/events")
CLIENT_ID      = "monitoramento-backend"

# Fila asyncio: ponte entre o callback síncrono do paho e o loop async
_fila_mensagens: asyncio.Queue = asyncio.Queue()


# ---------------------------------------------------------------------------
# Callbacks síncronos do paho (rodam na thread interna do paho)
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
    """
    Callback síncrono do paho — NÃO pode fazer await aqui.
    Coloca a mensagem na fila para ser processada pelo loop async.
    """
    try:
        payload = json.loads(message.payload.decode("utf-8"))
        _fila_mensagens.put_nowait(payload)
    except Exception as e:
        logger.warning("Payload MQTT inválido", erro=str(e))


# ---------------------------------------------------------------------------
# Processador async — consome a fila e chama a análise comportamental
# ---------------------------------------------------------------------------

async def _processar_fila():
    """
    Loop assíncrono que consome mensagens da fila e as processa.
    Roda indefinidamente até o shutdown da aplicação.
    """
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

        # ── Despacha para análise comportamental ──────────────────────────
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
# Ponto de entrada público — chamado pelo lifespan do main.py
# ---------------------------------------------------------------------------

async def iniciar_consumidor() -> None:
    """
    Inicia o cliente MQTT e o processador de fila como tasks assíncronas.

    Reconexão com backoff exponencial:
    2s → 4s → 8s → 16s → 30s (máximo)
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

            # loop_start() inicia thread interna do paho — NÃO bloqueia o asyncio
            client.loop_start()
            logger.info("Consumidor MQTT ativo e aguardando eventos")
            espera = 2  # reseta backoff após conexão bem-sucedida

            # Monitora a conexão a cada 5s
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
