"""
analise_comportamento.py
------------------------
Motor de análise comportamental — agora com notificações Telegram.

Fluxo por evento 'end':
  processar_evento(dados)
    ├── salva evento no PostgreSQL
    ├── registra presença
    ├── verifica imobilidade → salva alerta + envia Telegram
    └── verifica ausência   → salva alerta + envia Telegram
"""

import asyncio
from datetime import datetime, timedelta

from banco_dados import salvar_evento, salvar_alerta
from core.logging_config import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Estado em memória
# ---------------------------------------------------------------------------
_ultimo_evento_camera: dict[str, datetime] = {}

TEMPO_IMOBILIDADE = timedelta(minutes=15)
TEMPO_AUSENCIA    = timedelta(hours=2)

JANELA_ANTI_SPAM_ALERTA = timedelta(minutes=30)
_ultimo_alerta: dict[str, datetime] = {}


# ---------------------------------------------------------------------------
# Ponto de entrada público
# ---------------------------------------------------------------------------

def processar_evento(dados: dict) -> None:
    """
    Processa evento do Frigate: persiste, analisa e notifica.
    Chamado via asyncio.to_thread() pelo consumidor_mqtt.
    """
    after        = dados.get("after", {})
    tipo_evento  = dados.get("type", "desconhecido")
    camera       = after.get("camera", "desconhecida")
    label        = after.get("label", "desconhecido")
    confianca    = after.get("score", 0.0)
    evento_id    = after.get("id", "")
    start_time   = after.get("start_time")
    end_time     = after.get("end_time")

    # ── 1. Persiste apenas eventos finalizados ────────────────────────────
    if tipo_evento == "end":
        inicio  = datetime.fromtimestamp(start_time) if start_time else None
        fim     = datetime.fromtimestamp(end_time)   if end_time   else None
        duracao = int(end_time - start_time)          if (start_time and end_time) else None

        id_salvo = salvar_evento(
            tipo_evento       = tipo_evento,
            objeto_detectado  = label,
            camera            = camera,
            inicio_evento     = inicio,
            fim_evento        = fim,
            duracao_segundos  = duracao,
            confianca         = round(confianca, 3),
            evento_id_frigate = evento_id,
        )

        if id_salvo:
            logger.info(
                "Evento persistido no banco",
                id_banco=id_salvo,
                evento_id_frigate=evento_id,
                camera=camera,
                duracao_segundos=duracao,
            )

    # ── 2. Atualiza presença ──────────────────────────────────────────────
    registrar_evento(camera)

    # ── 3. Verifica comportamentos e notifica ─────────────────────────────
    alerta_imobilidade = verificar_imobilidade(camera)
    if alerta_imobilidade:
        _processar_alerta(alerta_imobilidade)

    alerta_ausencia = verificar_ausencia(camera)
    if alerta_ausencia:
        _processar_alerta(alerta_ausencia)


def _processar_alerta(alerta: dict) -> None:
    """
    Salva alerta no banco e dispara notificação Telegram.
    Controle anti-spam por tipo+câmera.
    """
    tipo   = alerta.get("tipo_alerta", "desconhecido")
    camera = alerta.get("camera", "desconhecida")
    chave  = f"{tipo}:{camera}"
    agora  = datetime.now()

    # Anti-spam
    ultimo = _ultimo_alerta.get(chave)
    if ultimo and (agora - ultimo) < JANELA_ANTI_SPAM_ALERTA:
        logger.debug(
            "Alerta suprimido (anti-spam)",
            tipo_alerta=tipo,
            camera=camera,
        )
        return

    descricao = _formatar_descricao(alerta)

    # Salva no banco
    id_alerta = salvar_alerta(
        tipo_alerta=tipo,
        camera=camera,
        descricao=descricao,
    )

    if id_alerta:
        _ultimo_alerta[chave] = agora
        logger.warning(
            "Alerta gerado",
            id_alerta=id_alerta,
            tipo_alerta=tipo,
            camera=camera,
        )

        # Dispara Telegram em background — não bloqueia o processamento
        # Usa asyncio.run_coroutine_threadsafe pois estamos numa thread síncrona
        # (chamada via asyncio.to_thread pelo consumidor_mqtt)
        try:
            loop = asyncio.get_event_loop()
            from notificador import enviar_alerta
            loop.call_soon_threadsafe(
                lambda: asyncio.ensure_future(
                    enviar_alerta(
                        tipo_alerta=tipo,
                        camera=camera,
                        descricao=descricao,
                    )
                )
            )
        except Exception as e:
            logger.error("Erro ao agendar notificação Telegram", erro=str(e))


def _formatar_descricao(alerta: dict) -> str:
    tipo   = alerta.get("tipo_alerta", "")
    camera = alerta.get("camera", "")

    if tipo == "imobilidade":
        tempo = alerta.get("tempo_sem_movimento", "desconhecido")
        return f"Pessoa sem movimento por {tempo} na câmera {camera}"

    if tipo == "ausencia_prolongada":
        tempo = alerta.get("tempo", "desconhecido")
        return f"Nenhuma presença detectada por {tempo} na câmera {camera}"

    return f"Alerta do tipo '{tipo}' na câmera {camera}"


# ---------------------------------------------------------------------------
# Funções de análise
# ---------------------------------------------------------------------------

def registrar_evento(camera: str) -> None:
    _ultimo_evento_camera[camera] = datetime.now()


def verificar_imobilidade(camera: str) -> dict | None:
    if camera not in _ultimo_evento_camera:
        return None
    agora  = datetime.now()
    ultimo = _ultimo_evento_camera[camera]
    if agora - ultimo > TEMPO_IMOBILIDADE:
        return {
            "tipo_alerta":         "imobilidade",
            "camera":              camera,
            "tempo_sem_movimento": str(agora - ultimo).split(".")[0],
        }
    return None


def verificar_ausencia(camera: str) -> dict | None:
    if camera not in _ultimo_evento_camera:
        return None
    agora  = datetime.now()
    ultimo = _ultimo_evento_camera[camera]
    if agora - ultimo > TEMPO_AUSENCIA:
        return {
            "tipo_alerta": "ausencia_prolongada",
            "camera":      camera,
            "tempo":       str(agora - ultimo).split(".")[0],
        }
    return None
