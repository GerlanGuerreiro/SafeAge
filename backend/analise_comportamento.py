"""
analise_comportamento.py
------------------------
Motor de análise comportamental do SafeAge.

LÓGICA DE IMOBILIDADE CORRIGIDA:
O Frigate emite eventos 'update' continuamente enquanto uma pessoa está
no frame — mesmo que ela esteja completamente parada. Isso significa que
o timer de "último evento" fica sendo resetado, e nunca detectamos imobilidade
com a abordagem anterior.

Solução: rastrear o INÍCIO de cada evento por evento_id.
- Se o mesmo evento_id continua em 'update' por muito tempo → imobilidade
- Se nenhum evento aparece por muito tempo → ausência prolongada

Dois estados distintos:
1. Pessoa presente mas imóvel: evento_id ativo há > TEMPO_IMOBILIDADE
2. Pessoa ausente: nenhum evento há > TEMPO_AUSENCIA
"""

import asyncio
from datetime import datetime, timedelta

from banco_dados import salvar_evento, salvar_alerta
from core.logging_config import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Estado em memória
# ---------------------------------------------------------------------------

# Quando vimos qualquer evento desta câmera (para detectar ausência)
_ultimo_evento_camera: dict[str, datetime] = {}

# Quando cada evento_id foi visto pela primeira vez (para detectar imobilidade)
_inicio_evento: dict[str, datetime] = {}

# Qual evento_id está ativo por câmera
_evento_ativo_camera: dict[str, str] = {}

# Caminho do snapshot gerado pelo Frigate por evento_id
# Frigate salva em /media/frigate/clips/{evento_id}.jpg
FRIGATE_CLIPS_DIR = "/media/frigate/clips"

# Limites
TEMPO_IMOBILIDADE       = timedelta(minutes=2)   # mesmo evento ativo por 2min = imobilidade
TEMPO_AUSENCIA          = timedelta(minutes=10)   # nenhum evento por 10min = ausência
INTERVALO_VERIFICACAO_S = 30   # verifica a cada 30s para reduzir delay
JANELA_ANTI_SPAM_ALERTA = timedelta(minutes=30)

_ultimo_alerta: dict[str, datetime] = {}


# ---------------------------------------------------------------------------
# Processamento de eventos MQTT
# ---------------------------------------------------------------------------

def processar_evento(dados: dict) -> None:
    """
    Processa evento do Frigate: persiste e atualiza estado de presença.
    """
    after       = dados.get("after", {})
    tipo_evento = dados.get("type", "desconhecido")
    camera      = after.get("camera", "desconhecida")
    label       = after.get("label", "desconhecido")
    confianca   = after.get("score", 0.0)
    evento_id   = after.get("id", "")
    start_time  = after.get("start_time")
    end_time    = after.get("end_time")

    # Persiste apenas eventos finalizados
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
                camera=camera,
                duracao_segundos=duracao,
            )

        # Evento encerrou — limpa rastreamento e reseta anti-spam de imobilidade
        # Motivo: se a pessoa saiu e voltou, o próximo evento deve disparar alerta
        # normalmente, não ficar bloqueado pelo anti-spam do evento anterior
        _inicio_evento.pop(evento_id, None)
        if _evento_ativo_camera.get(camera) == evento_id:
            _evento_ativo_camera.pop(camera, None)
        # Limpa anti-spam de imobilidade para esta câmera
        chave_imobilidade = f"imobilidade:{camera}"
        _ultimo_alerta.pop(chave_imobilidade, None)
        logger.debug("Anti-spam de imobilidade resetado", camera=camera)

    elif tipo_evento in ("new", "update"):
        # Registra início do evento se for novo
        if evento_id not in _inicio_evento:
            _inicio_evento[evento_id] = datetime.now()
            logger.debug(
                "Novo evento rastreado",
                camera=camera,
                evento_id=evento_id,
            )

        # Atualiza evento ativo da câmera
        _evento_ativo_camera[camera] = evento_id

    # Sempre atualiza timestamp de última atividade
    _ultimo_evento_camera[camera] = datetime.now()
    logger.debug("Presença registrada", camera=camera)


# ---------------------------------------------------------------------------
# Loop independente de verificação
# ---------------------------------------------------------------------------

async def loop_verificacao() -> None:
    """
    Verifica imobilidade e ausência a cada INTERVALO_VERIFICACAO_S segundos.
    Roda como background task independente do fluxo MQTT.
    """
    logger.info(
        "Loop de verificação comportamental iniciado",
        intervalo_segundos=INTERVALO_VERIFICACAO_S,
        limiar_imobilidade=str(TEMPO_IMOBILIDADE),
        limiar_ausencia=str(TEMPO_AUSENCIA),
    )

    while True:
        await asyncio.sleep(INTERVALO_VERIFICACAO_S)

        if not _ultimo_evento_camera:
            logger.debug("Loop: nenhuma câmera registrada ainda")
            continue

        agora = datetime.now()

        for camera in list(_ultimo_evento_camera.keys()):
            ultimo = _ultimo_evento_camera[camera]
            tempo_sem_evento = agora - ultimo

            logger.debug(
                "Verificando câmera",
                camera=camera,
                sem_evento_ha=str(tempo_sem_evento).split(".")[0],
                evento_ativo=_evento_ativo_camera.get(camera, "nenhum"),
            )

            # ── Ausência prolongada ───────────────────────────────────────
            # Nenhum evento chegou por TEMPO_AUSENCIA
            if tempo_sem_evento > TEMPO_AUSENCIA:
                await _processar_alerta_async({
                    "tipo_alerta": "ausencia_prolongada",
                    "camera":      camera,
                    "tempo":       str(tempo_sem_evento).split(".")[0],
                })
                continue

            # ── Imobilidade ───────────────────────────────────────────────
            # Mesmo evento_id ativo há muito tempo → pessoa parada
            evento_id_ativo = _evento_ativo_camera.get(camera)
            if evento_id_ativo and evento_id_ativo in _inicio_evento:
                duracao_evento = agora - _inicio_evento[evento_id_ativo]
                logger.debug(
                    "Evento ativo há",
                    camera=camera,
                    evento_id=evento_id_ativo,
                    duracao=str(duracao_evento).split(".")[0],
                )
                if duracao_evento > TEMPO_IMOBILIDADE:
                    await _processar_alerta_async({
                        "tipo_alerta":         "imobilidade",
                        "camera":              camera,
                        "tempo_sem_movimento": str(duracao_evento).split(".")[0],
                    })


# ---------------------------------------------------------------------------
# Processamento de alertas
# ---------------------------------------------------------------------------

async def _processar_alerta_async(alerta: dict) -> None:
    tipo   = alerta.get("tipo_alerta", "desconhecido")
    camera = alerta.get("camera", "desconhecida")
    chave  = f"{tipo}:{camera}"
    agora  = datetime.now()

    ultimo = _ultimo_alerta.get(chave)
    if ultimo and (agora - ultimo) < JANELA_ANTI_SPAM_ALERTA:
        logger.debug(
            "Alerta suprimido (anti-spam)",
            tipo_alerta=tipo,
            camera=camera,
            proximo_em=str(JANELA_ANTI_SPAM_ALERTA - (agora - ultimo)).split(".")[0],
        )
        return

    descricao = _formatar_descricao(alerta)

    id_alerta = await asyncio.to_thread(
        salvar_alerta,
        tipo_alerta=tipo,
        camera=camera,
        descricao=descricao,
    )

    if id_alerta:
        _ultimo_alerta[chave] = agora
        logger.warning(
            "Alerta gerado e salvo",
            id_alerta=id_alerta,
            tipo_alerta=tipo,
            camera=camera,
            descricao=descricao,
        )
        try:
            from notificador import enviar_alerta
            import os

            # Busca snapshot do evento ativo
            # Frigate salva como: {camera}-{evento_id}.jpg
            # Estratégia: tenta pelo evento_id exato; se não achar, pega o .jpg
            # mais recente da câmera no diretório de clips.
            snapshot = None
            evento_id_ativo = _evento_ativo_camera.get(camera)
            if evento_id_ativo:
                caminho_exato = f"{FRIGATE_CLIPS_DIR}/{camera}-{evento_id_ativo}.jpg"
                if os.path.exists(caminho_exato):
                    snapshot = caminho_exato
                    logger.debug("Snapshot encontrado pelo evento_id", caminho=snapshot)
                else:
                    # Fallback: pega o .jpg mais recente desta câmera
                    try:
                        import glob
                        padrao = f"{FRIGATE_CLIPS_DIR}/{camera}-*.jpg"
                        candidatos = glob.glob(padrao)
                        if candidatos:
                            snapshot = max(candidatos, key=os.path.getmtime)
                            logger.debug("Snapshot mais recente usado", caminho=snapshot)
                        else:
                            logger.debug("Nenhum snapshot encontrado", padrao=padrao)
                    except Exception as e_glob:
                        logger.warning("Erro ao buscar snapshot", erro=str(e_glob))

            await enviar_alerta(
                tipo_alerta=tipo,
                camera=camera,
                descricao=descricao,
                caminho_snapshot=snapshot,
            )

            # Apaga snapshot após envio para não acumular arquivos
            if snapshot and os.path.exists(snapshot):
                try:
                    os.remove(snapshot)
                    logger.debug("Snapshot removido após envio", caminho=snapshot)
                except Exception as e_rm:
                    logger.warning("Falha ao remover snapshot", erro=str(e_rm))

        except Exception as e:
            logger.error("Erro ao enviar notificação Telegram", erro=str(e))


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
