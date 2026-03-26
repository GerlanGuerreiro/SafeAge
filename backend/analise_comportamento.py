"""
analise_comportamento.py
------------------------
Motor de análise comportamental do sistema de monitoramento.

Responsabilidades:
- Processar cada evento recebido do Frigate via MQTT
- Detectar comportamentos anômalos (imobilidade, ausência, queda)
- Persistir eventos e alertas no PostgreSQL
- (Fase 2) Disparar notificações via Telegram

Fluxo por evento:
  processar_evento(dados)
    ├── salva evento 'end' no banco (evita spam de updates)
    ├── registra presença para análise temporal
    ├── verifica imobilidade → salva alerta se detectado
    └── verifica ausência   → salva alerta se detectado
"""

from datetime import datetime, timedelta

from banco_dados import salvar_evento, salvar_alerta
from core.logging_config import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Estado em memória
# Armazena último momento que cada câmera detectou movimento
# TODO Fase 2: migrar para Redis para persistir entre restarts do container
# ---------------------------------------------------------------------------
_ultimo_evento_camera: dict[str, datetime] = {}

# ---------------------------------------------------------------------------
# Limites de comportamento (configuráveis via variáveis de ambiente futuramente)
# ---------------------------------------------------------------------------
TEMPO_IMOBILIDADE = timedelta(minutes=15)
TEMPO_AUSENCIA    = timedelta(hours=2)

# Anti-spam: não salva múltiplos alertas do mesmo tipo/câmera
# dentro desta janela de tempo
JANELA_ANTI_SPAM_ALERTA = timedelta(minutes=30)
_ultimo_alerta: dict[str, datetime] = {}  # chave: "tipo:camera"


# ---------------------------------------------------------------------------
# Ponto de entrada público — chamado pelo consumidor_mqtt.py
# ---------------------------------------------------------------------------

def processar_evento(dados: dict) -> None:
    """
    Processa um evento recebido do Frigate e executa a pipeline completa:
    persistência → análise → alerta.

    Só persiste eventos do tipo 'end' para evitar duplicatas:
    o Frigate envia 'new' + vários 'update' + 'end' para cada detecção.
    Salvar apenas o 'end' garante um registro limpo e completo por ocorrência.
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
    # Motivo: 'new' e 'update' chegam a cada frame — salvar todos infla o banco
    # O evento 'end' contém o score final e os timestamps completos
    if tipo_evento == "end":
        inicio = datetime.fromtimestamp(start_time) if start_time else None
        fim    = datetime.fromtimestamp(end_time)   if end_time   else None
        duracao = int(end_time - start_time) if (start_time and end_time) else None

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

    # ── 2. Atualiza estado de presença ────────────────────────────────────
    # Atualiza para qualquer tipo de evento (new/update/end) para ter
    # o timestamp mais recente de atividade nesta câmera
    registrar_evento(camera)

    # ── 3. Verifica comportamentos anômalos ───────────────────────────────
    alerta_imobilidade = verificar_imobilidade(camera)
    if alerta_imobilidade:
        _processar_alerta(alerta_imobilidade)

    alerta_ausencia = verificar_ausencia(camera)
    if alerta_ausencia:
        _processar_alerta(alerta_ausencia)


def _processar_alerta(alerta: dict) -> None:
    """
    Salva alerta no banco com controle anti-spam.

    Não salva o mesmo tipo de alerta para a mesma câmera
    dentro da janela JANELA_ANTI_SPAM_ALERTA.
    Isso evita dezenas de alertas de 'imobilidade' em sequência.
    """
    tipo   = alerta.get("tipo_alerta", "desconhecido")
    camera = alerta.get("camera", "desconhecida")
    chave  = f"{tipo}:{camera}"
    agora  = datetime.now()

    # Verifica janela anti-spam
    ultimo = _ultimo_alerta.get(chave)
    if ultimo and (agora - ultimo) < JANELA_ANTI_SPAM_ALERTA:
        logger.debug(
            "Alerta suprimido (anti-spam)",
            tipo_alerta=tipo,
            camera=camera,
            proximo_em=str(JANELA_ANTI_SPAM_ALERTA - (agora - ultimo)),
        )
        return

    # Monta descrição legível para o alerta
    descricao = _formatar_descricao(alerta)

    id_alerta = salvar_alerta(
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
        # TODO Fase 2: chamar notificador.enviar_telegram(alerta)


def _formatar_descricao(alerta: dict) -> str:
    """Formata uma descrição legível para o alerta."""
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
# Funções de análise comportamental (mantidas do código original)
# ---------------------------------------------------------------------------

def registrar_evento(camera: str) -> None:
    """Atualiza o timestamp da última detecção para esta câmera."""
    _ultimo_evento_camera[camera] = datetime.now()


def verificar_imobilidade(camera: str) -> dict | None:
    """
    Retorna alerta se a pessoa não se moveu por TEMPO_IMOBILIDADE.
    Retorna None se estiver dentro do limite normal.
    """
    if camera not in _ultimo_evento_camera:
        return None

    agora  = datetime.now()
    ultimo = _ultimo_evento_camera[camera]

    if agora - ultimo > TEMPO_IMOBILIDADE:
        return {
            "tipo_alerta":        "imobilidade",
            "camera":             camera,
            "tempo_sem_movimento": str(agora - ultimo),
        }
    return None


def verificar_ausencia(camera: str) -> dict | None:
    """
    Retorna alerta se não houve nenhuma presença por TEMPO_AUSENCIA.
    Retorna None se dentro do limite normal.
    """
    if camera not in _ultimo_evento_camera:
        return None

    agora  = datetime.now()
    ultimo = _ultimo_evento_camera[camera]

    if agora - ultimo > TEMPO_AUSENCIA:
        return {
            "tipo_alerta": "ausencia_prolongada",
            "camera":      camera,
            "tempo":       str(agora - ultimo),
        }
    return None
