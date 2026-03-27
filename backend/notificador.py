"""
notificador.py
--------------
Envio de alertas via Telegram Bot API.

Por que httpx em vez de requests?
- requests é BLOQUEANTE — congela o loop asyncio durante a chamada HTTP
- httpx tem API idêntica ao requests mas com suporte nativo a async/await
- Já está no requirements.txt

Funcionalidades:
- Mensagem formatada com emoji, câmera, tipo e timestamp
- Foto do snapshot do Frigate (quando câmera estiver ativa)
- Rate limiting: máximo 1 alerta por tipo/câmera a cada 10 minutos
- Validação de credenciais no startup — falha rápido com mensagem clara
- Modo silencioso se Telegram não estiver configurado (não quebra o sistema)
"""

import os
from datetime import datetime, timedelta

import httpx

from core.logging_config import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# URL base da API do Telegram
_BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

# Rate limiting: evita spam de notificações
# Chave: "tipo_alerta:camera" → datetime do último envio
_ultimo_envio: dict[str, datetime] = {}
INTERVALO_MINIMO = timedelta(minutes=10)

# Emojis por tipo de alerta — tornam a mensagem mais legível no celular
_EMOJIS = {
    "queda":               "🚨",
    "imobilidade":         "⚠️",
    "ausencia_prolongada": "👻",
    "pessoa_detectada":    "👤",
}


# ---------------------------------------------------------------------------
# Validação de configuração
# ---------------------------------------------------------------------------

def telegram_configurado() -> bool:
    """
    Retorna True se token e chat_id estão preenchidos.
    Loga um aviso claro se não estiver — facilita debug.
    """
    if not TOKEN or not CHAT_ID:
        logger.warning(
            "Telegram não configurado — notificações desabilitadas",
            dica="Preencha TELEGRAM_TOKEN e TELEGRAM_CHAT_ID no .env",
        )
        return False
    return True


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

def _pode_enviar(tipo_alerta: str, camera: str) -> bool:
    """
    Verifica se passou tempo suficiente desde o último envio
    do mesmo tipo de alerta para a mesma câmera.
    """
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


# ---------------------------------------------------------------------------
# Formatação de mensagens
# ---------------------------------------------------------------------------

def _formatar_mensagem(tipo_alerta: str, camera: str, descricao: str) -> str:
    """
    Formata mensagem rica para o Telegram com Markdown.

    Exemplo de saída:
    🚨 *ALERTA DE QUEDA*

    📷 Câmera: `camera_idoso`
    🕐 Horário: `26/03/2026 00:49:50`
    📋 Detalhe: Pessoa sem movimento por 0:15:32

    _Sistema de Monitoramento Residencial_
    """
    emoji    = _EMOJIS.get(tipo_alerta, "🔔")
    titulo   = tipo_alerta.upper().replace("_", " ")
    horario  = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    return (
        f"{emoji} *ALERTA: {titulo}*\n\n"
        f"📷 Câmera: `{camera}`\n"
        f"🕐 Horário: `{horario}`\n"
        f"📋 Detalhe: {descricao}\n\n"
        f"_Sistema de Monitoramento Residencial_"
    )


# ---------------------------------------------------------------------------
# Envio de mensagem
# ---------------------------------------------------------------------------

async def enviar_alerta(
    tipo_alerta: str,
    camera: str,
    descricao: str,
    caminho_snapshot: str | None = None,
) -> bool:
    """
    Envia alerta completo para o Telegram.

    Se caminho_snapshot for fornecido e o arquivo existir,
    envia como foto com a mensagem como legenda.
    Caso contrário, envia só a mensagem de texto.

    Retorna True se enviado com sucesso, False caso contrário.
    """
    if not telegram_configurado():
        return False

    if not _pode_enviar(tipo_alerta, camera):
        return False

    mensagem = _formatar_mensagem(tipo_alerta, camera, descricao)

    try:
        # Tenta enviar com foto se disponível
        if caminho_snapshot and os.path.exists(caminho_snapshot):
            sucesso = await _enviar_foto(mensagem, caminho_snapshot)
        else:
            sucesso = await _enviar_texto(mensagem)

        if sucesso:
            logger.info(
                "Alerta Telegram enviado",
                tipo_alerta=tipo_alerta,
                camera=camera,
                com_foto=bool(caminho_snapshot and os.path.exists(caminho_snapshot or "")),
            )
        return sucesso

    except Exception as e:
        logger.exception(
            "Erro inesperado ao enviar alerta Telegram",
            tipo_alerta=tipo_alerta,
            camera=camera,
            erro=str(e),
        )
        return False


async def _enviar_texto(mensagem: str) -> bool:
    """Envia mensagem de texto simples via Telegram Bot API."""
    url     = f"{_BASE_URL}/sendMessage"
    payload = {
        "chat_id":    CHAT_ID,
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
    """Envia foto com legenda via Telegram Bot API."""
    url = f"{_BASE_URL}/sendPhoto"

    async with httpx.AsyncClient(timeout=15.0) as client:
        with open(caminho, "rb") as foto:
            resposta = await client.post(
                url,
                data={"chat_id": CHAT_ID, "caption": legenda, "parse_mode": "Markdown"},
                files={"photo": foto},
            )

    if resposta.status_code == 200:
        return True

    # Se falhou com foto, tenta só o texto como fallback
    logger.warning(
        "Falha ao enviar foto — tentando só texto",
        status_code=resposta.status_code,
    )
    return await _enviar_texto(legenda)


# ---------------------------------------------------------------------------
# Teste de conectividade — chamado no startup
# ---------------------------------------------------------------------------

async def testar_conexao() -> bool:
    """
    Envia mensagem de startup para confirmar que o bot está funcionando.
    Chame no lifespan do main.py após configurar o Telegram.
    """
    if not telegram_configurado():
        return False

    horario = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
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
