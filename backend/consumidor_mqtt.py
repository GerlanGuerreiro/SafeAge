"""
consumidor_mqtt.py
------------------
Consome eventos do broker MQTT publicados pelo Frigate NVR.

Responsabilidades:
- Conectar ao broker Mosquitto
- Subscrever nos tópicos relevantes do Frigate
- Parsear o payload JSON
- Despachar para a camada de análise comportamental

O que mudou em relação à versão anterior:
- print() → logger estruturado com contexto
- Variáveis de ambiente via pydantic-settings (Fase 1, item 3)
- Reconexão automática com backoff exponencial (Fase 2)
  → Por enquanto: placeholder indicando onde implementar

IMPORTANTE sobre MQTT + Frigate:
Os tópicos seguem o padrão:
  frigate/events           → todos os eventos de detecção
  frigate/<camera>/person  → eventos de pessoa numa câmera específica
  frigate/+/person         → wildcard para todas as câmeras
"""

import json
import os
import time

import paho.mqtt.client as mqtt

from core.logging_config import get_logger, LogContexto

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Configuração via variáveis de ambiente
# ---------------------------------------------------------------------------
# TODO Fase 1 item 3: mover para core/config.py com pydantic-settings
# Por ora, mantemos os os.getenv com valores padrão explícitos

BROKER_HOST    = os.getenv("ENDERECO_BROKER_MQTT", "localhost")
BROKER_PORT    = int(os.getenv("PORTA_BROKER_MQTT", "1883"))
TOPICO_EVENTOS = os.getenv("TOPICO_MQTT_FRIGATE", "frigate/events")
CLIENT_ID      = "monitoramento-backend"


# ---------------------------------------------------------------------------
# Callbacks MQTT
# ---------------------------------------------------------------------------

def ao_conectar(client: mqtt.Client, userdata, flags, rc: int) -> None:
    """
    Callback disparado quando a conexão com o broker é estabelecida ou falha.

    rc (return code) indica o resultado:
    0 = sucesso, 1-5 = diferentes tipos de falha
    """
    codigos_retorno = {
        0: "Conexão bem-sucedida",
        1: "Protocolo incorreto",
        2: "Identificador inválido",
        3: "Servidor indisponível",
        4: "Credenciais inválidas",
        5: "Não autorizado",
    }

    mensagem = codigos_retorno.get(rc, f"Código desconhecido: {rc}")

    if rc == 0:
        logger.info(
            "Conectado ao broker MQTT",
            **{
                LogContexto.TOPICO_MQTT: TOPICO_EVENTOS,
                "broker": BROKER_HOST,
                "porta": BROKER_PORT,
            }
        )
        # Subscreve no tópico após conexão bem-sucedida
        client.subscribe(TOPICO_EVENTOS)
        logger.debug("Subscrito no tópico", topico=TOPICO_EVENTOS)
    else:
        # ERRO: não loga como exception (sem traceback), mas como error com contexto
        logger.error(
            "Falha ao conectar no broker MQTT",
            broker=BROKER_HOST,
            porta=BROKER_PORT,
            codigo_retorno=rc,
            detalhe=mensagem,
        )


def ao_desconectar(client: mqtt.Client, userdata, rc: int) -> None:
    """
    Callback disparado quando a conexão é encerrada.

    rc == 0 → desconexão intencional (shutdown limpo)
    rc != 0 → desconexão inesperada (rede caiu, broker reiniciou, etc.)
    """
    if rc == 0:
        logger.info("Desconectado do broker MQTT (encerramento limpo)")
    else:
        # Desconexão inesperada — log como warning pois o sistema tentará reconectar
        logger.warning(
            "Desconexão inesperada do broker MQTT",
            codigo_retorno=rc,
            nota="Reconexão automática será tentada (Fase 2)",
        )


def ao_receber_mensagem(
    client: mqtt.Client, userdata, message: mqtt.MQTTMessage
) -> None:
    """
    Callback principal — disparado para cada mensagem recebida.

    Fluxo:
    1. Decodifica o payload JSON
    2. Extrai campos relevantes do evento Frigate
    3. Loga com contexto estruturado
    4. Despacha para análise comportamental

    Formato do payload Frigate (simplificado):
    {
        "type": "new" | "update" | "end",
        "before": { "id": "...", "camera": "...", "label": "person", ... },
        "after":  { "id": "...", "camera": "...", "label": "person",
                    "box": [x, y, width, height], "score": 0.87 }
    }
    """
    topico  = message.topic
    payload = message.payload

    # ── 1. Parse do JSON ───────────────────────────────────────────────────
    try:
        dados = json.loads(payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.warning(
            "Payload MQTT inválido — não é JSON válido",
            **{
                LogContexto.TOPICO_MQTT: topico,
                "payload_bruto": payload[:200],  # Limita para não poluir o log
                "erro": str(e),
            }
        )
        return

    # ── 2. Extração de campos do evento Frigate ────────────────────────────
    tipo_evento  = dados.get("type", "desconhecido")
    after        = dados.get("after", {})
    camera_id    = after.get("camera", "desconhecida")
    label        = after.get("label", "desconhecido")
    confianca    = after.get("score", 0.0)
    evento_id    = after.get("id", "sem-id")

    # ── 3. Log estruturado com todos os campos relevantes ──────────────────
    # Note: usamos as constantes de LogContexto para padronizar os campos
    logger.info(
        "Evento MQTT recebido",
        **{
            LogContexto.CAMERA_ID:   camera_id,
            LogContexto.TIPO_EVENTO: tipo_evento,
            LogContexto.CONFIANCA:   round(confianca, 3),
            LogContexto.EVENTO_ID:   evento_id,
            LogContexto.TOPICO_MQTT: topico,
            "label": label,
        }
    )

    # ── 4. Filtragem: processa apenas eventos de pessoa ────────────────────
    if label != "person":
        logger.debug(
            "Evento ignorado (label não é 'person')",
            label=label,
            **{LogContexto.CAMERA_ID: camera_id}
        )
        return

    # ── 5. Despacho para análise comportamental ────────────────────────────
    # TODO: importar e chamar analise_comportamento.processar_evento(dados)
    # Por ora, apenas loga o despacho
    logger.debug(
        "Despachando evento para análise comportamental",
        **{
            LogContexto.EVENTO_ID:   evento_id,
            LogContexto.CAMERA_ID:   camera_id,
            LogContexto.TIPO_EVENTO: tipo_evento,
        }
    )


# ---------------------------------------------------------------------------
# Cliente MQTT
# ---------------------------------------------------------------------------

def criar_cliente_mqtt() -> mqtt.Client:
    """
    Cria e configura o cliente MQTT com os callbacks registrados.

    Retorna o cliente pronto para conectar (mas sem chamar connect() ainda).
    Isso permite testar a configuração dos callbacks separadamente da conexão.
    """
    client = mqtt.Client(client_id=CLIENT_ID, clean_session=True)

    # Registra os callbacks
    client.on_connect    = ao_conectar
    client.on_disconnect = ao_desconectar
    client.on_message    = ao_receber_mensagem

    # TODO Fase 1 item 3: credenciais MQTT via pydantic-settings
    usuario_mqtt = os.getenv("USUARIO_MQTT")
    senha_mqtt   = os.getenv("SENHA_MQTT")
    if usuario_mqtt and senha_mqtt:
        client.username_pw_set(usuario_mqtt, senha_mqtt)
        logger.debug("Autenticação MQTT configurada", usuario=usuario_mqtt)

    return client


def iniciar_consumidor() -> None:
    """
    Inicia o loop de consumo MQTT com tentativa de conexão.

    TODO Fase 2: substituir este loop simples por reconexão com
    backoff exponencial usando tenacity:

        from tenacity import retry, wait_exponential, stop_after_attempt
        @retry(wait=wait_exponential(min=1, max=60), stop=stop_after_attempt(10))
        def conectar_com_retry(): ...
    """
    client = criar_cliente_mqtt()

    logger.info(
        "Tentando conectar ao broker MQTT",
        broker=BROKER_HOST,
        porta=BROKER_PORT,
    )

    tentativas = 0
    max_tentativas = 5

    while tentativas < max_tentativas:
        try:
            client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
            client.loop_forever()
            break  # Se loop_forever() retorna, é encerramento limpo
        except ConnectionRefusedError:
            tentativas += 1
            espera = min(2 ** tentativas, 30)  # Backoff simples: 2, 4, 8, 16, 30s
            logger.warning(
                "Conexão MQTT recusada, tentando novamente",
                tentativa=tentativas,
                max_tentativas=max_tentativas,
                aguardando_segundos=espera,
            )
            time.sleep(espera)
        except Exception as e:
            logger.exception(
                "Erro inesperado no consumidor MQTT",
                erro=str(e),
            )
            break

    if tentativas >= max_tentativas:
        logger.error(
            "Máximo de tentativas MQTT atingido — consumidor não iniciado",
            max_tentativas=max_tentativas,
        )


if __name__ == "__main__":
    iniciar_consumidor()
