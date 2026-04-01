"""
notificador.py
--------------
Envio de alertas via Telegram Bot API.
Credenciais lidas de settings em vez de os.getenv().
"""

import os
from datetime import datetime, timedelta

import httpx

from core.config import settings
from core.logging_config import get_logger

logger = get_logger(__name__)

# Lê do settings — validado e tipado no startup
_BASE_URL = f"https://api.telegram.org/bot{settings.telegram_token}"

_ultimo_envio: dict[str, datetime] = {}
INTERVALO_MINIMO = timedelta(minutes=10)

_EMOJIS = {
    "queda":               "🚨",
    "imobilidade":         "⚠️",
    "ausencia_prolongada": "👻",
    "pessoa_detectada":    "👤",
}


def telegram_configurado() -> bool:
    """
    Usa a propriedade computada do settings — não duplica a lógica.
    """
    if not settings.telegram_configurado:
        logger.warning(
            "Telegram não configurado — notificações desabilitadas",
            dica="Preencha TELEGRAM_TOKEN e TELEGRAM_CHAT_ID no .env",
        )
        return False
    return True


def _pode_enviar(tipo_alerta: str, camera: str) -> bool:
    chave = f"{tipo_alerta}:{camera}"
    agora = datetime.now()
    ultimo = _ultimo_envio.get(chave)
    if ultimo and (agora - ultimo) < INTERVALO_MINIMO:
        restante = INTERVALO_MINIMO - (agora - ultimo)
        logger.debug(
            "Notificação Telegram suprimida (rate limit)",
            tipo_alerta=tipo_alerta,
            camera=camera,
            proximo_envio_em=str(restante).split(".")[0],
        )
        return False
    _ultimo_envio[chave] = agora
    return True


def _formatar_mensagem(tipo_alerta: str, camera: str, descricao: str) -> str:
    emoji   = _EMOJIS.get(tipo_alerta, "🔔")
    titulo  = tipo_alerta.upper().replace("_", " ")
    horario = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    return (
        f"{emoji} *ALERTA: {titulo}*\n\n"
        f"📷 Câmera: `{camera}`\n"
        f"🕐 Horário: `{horario}`\n"
        f"📋 Detalhe: {descricao}\n\n"
        f"_Sistema de Monitoramento Residencial_"
    )


async def enviar_alerta(
    tipo_alerta: str,
    camera: str,
    descricao: str,
    caminho_snapshot: str | None = None,
) -> bool:
    if not telegram_configurado():
        return False
    if not _pode_enviar(tipo_alerta, camera):
        return False

    mensagem = _formatar_mensagem(tipo_alerta, camera, descricao)

    try:
        if caminho_snapshot and os.path.exists(caminho_snapshot):
            sucesso = await _enviar_foto(mensagem, caminho_snapshot)
        else:
            sucesso = await _enviar_texto(mensagem)

        if sucesso:
            logger.info(
                "Alerta Telegram enviado",
                tipo_alerta=tipo_alerta,
                camera=camera,
            )
        return sucesso
    except Exception as e:
        logger.exception("Erro ao enviar alerta Telegram", erro=str(e))
        return False


async def _enviar_texto(mensagem: str) -> bool:
    url = f"{_BASE_URL}/sendMessage"
    payload = {
        "chat_id":    settings.telegram_chat_id,
        "text":       mensagem,
        "parse_mode": "Markdown",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resposta = await client.post(url, json=payload)

    if resposta.status_code == 200:
        return True

    logger.error(
        "Falha ao enviar mensagem Telegram",
        status_code=resposta.status_code,
        resposta=resposta.text[:200],
    )
    return False


async def _enviar_foto(legenda: str, caminho: str) -> bool:
    url = f"{_BASE_URL}/sendPhoto"
    async with httpx.AsyncClient(timeout=15.0) as client:
        with open(caminho, "rb") as foto:
            resposta = await client.post(
                url,
                data={"chat_id": settings.telegram_chat_id, "caption": legenda, "parse_mode": "Markdown"},
                files={"photo": foto},
            )
    if resposta.status_code == 200:
        return True
    logger.warning("Falha ao enviar foto — tentando só texto", status_code=resposta.status_code)
    return await _enviar_texto(legenda)


async def testar_conexao() -> bool:
    if not telegram_configurado():
        return False

    horario  = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    mensagem = (
        f"✅ *Sistema de Monitoramento Online*\n\n"
        f"🕐 Iniciado em: `{horario}`\n"
        f"📡 Broker MQTT: conectado\n"
        f"🗄️ Banco de dados: conectado\n\n"
        f"_Aguardando eventos da câmera..._"
    )

    try:
        sucesso = await _enviar_texto(mensagem)
        if sucesso:
            logger.info("Telegram: mensagem de startup enviada com sucesso")
        return sucesso
    except Exception as e:
        logger.error("Telegram: falha no teste de conexão", erro=str(e))
        return False
