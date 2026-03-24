"""
logging_config.py
-----------------
Configuração centralizada de logging para o sistema de monitoramento.

Por que loguru?
- API simples: uma linha para configurar tudo
- Rotação automática de arquivos de log
- Formatação colorida no terminal
- Saída JSON estruturada para produção (compatível com Grafana/Loki/ELK)
- Suporte nativo a context variables (útil para rastrear eventos por câmera/sessão)

Como usar em outros módulos:
    from core.logging_config import get_logger
    logger = get_logger(__name__)
    logger.info("Evento recebido", camera="sala", tipo="queda")
"""

import sys
import os
from loguru import logger


def configurar_logging() -> None:
    """
    Configura o sistema de logging para toda a aplicação.

    Comportamento por ambiente:
    - DESENVOLVIMENTO: logs coloridos no terminal com nível DEBUG
    - PRODUÇÃO: logs JSON estruturados em arquivo + terminal, nível INFO

    Chame esta função UMA VEZ na inicialização do app (main.py ou lifespan).
    """

    # Remove os handlers padrão da loguru para ter controle total
    logger.remove()

    # Determina o ambiente a partir da variável de ambiente
    # Valor padrão: "development" para não quebrar em ambientes sem .env configurado
    ambiente = os.getenv("AMBIENTE", "development").lower()
    nivel_log = os.getenv("NIVEL_LOG", "DEBUG" if ambiente == "development" else "INFO")

    if ambiente == "production":
        _configurar_producao(nivel_log)
    else:
        _configurar_desenvolvimento(nivel_log)

    logger.info(
        "Sistema de logging inicializado",
        ambiente=ambiente,
        nivel=nivel_log,
    )


def _configurar_desenvolvimento(nivel: str) -> None:
    """
    Configuração para desenvolvimento:
    - Saída colorida no terminal
    - Inclui nome do arquivo e linha para facilitar debug
    - Nível DEBUG para ver tudo
    """
    formato_dev = (
        "<green>{time:HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
        # Extra context (campos adicionais passados como kwargs no log)
        "{extra}"
    )

    logger.add(
        sys.stderr,
        format=formato_dev,
        level=nivel,
        colorize=True,
        # Exibe exceções completas com traceback bonito
        backtrace=True,
        diagnose=True,
    )


def _configurar_producao(nivel: str) -> None:
    """
    Configuração para produção:
    - Saída JSON no stderr (capturada pelo Docker/k8s)
    - Arquivo rotacionado para auditoria e análise posterior
    - Sem diagnose (evita vazar dados sensíveis em stacktraces)
    """
    # Handler 1: JSON no stderr → capturado pelo Docker logs / sistemas de observabilidade
    logger.add(
        sys.stderr,
        format="{time} {level} {name} {message} {extra}",
        level=nivel,
        serialize=True,  # Gera JSON puro — compatível com Loki, ELK, Datadog
        colorize=False,
        backtrace=False,
        diagnose=False,
    )

    # Handler 2: Arquivo rotacionado localmente (backup de auditoria)
    # Rotação: novo arquivo a cada 10MB ou à meia-noite
    # Retenção: arquivos dos últimos 7 dias
    logger.add(
        "logs/monitoramento_{time:YYYY-MM-DD}.log",
        format="{time} | {level} | {name} | {message} | {extra}",
        level=nivel,
        rotation="10 MB",
        retention="7 days",
        compression="zip",
        serialize=False,
        encoding="utf-8",
    )


def get_logger(nome_modulo: str):
    """
    Retorna um logger com o nome do módulo como contexto.

    Uso:
        logger = get_logger(__name__)
        logger.info("Mensagem", camera_id="sala", evento="queda")

    O nome do módulo aparece nos logs facilitando identificar a origem
    de cada mensagem sem precisar ler o stacktrace completo.
    """
    return logger.bind(modulo=nome_modulo)


# ---------------------------------------------------------------------------
# Constantes de contexto — use nos logs para padronizar os campos
# Isso garante que todos os módulos usem os mesmos nomes de campo,
# facilitando buscas e dashboards de observabilidade.
# ---------------------------------------------------------------------------

class LogContexto:
    """Chaves padronizadas para campos de contexto nos logs."""
    CAMERA_ID    = "camera_id"
    TIPO_EVENTO  = "tipo_evento"
    CONFIANCA    = "confianca"
    DURACAO_S    = "duracao_segundos"
    ALERTA_ENVID = "alerta_enviado"
    TOPICO_MQTT  = "topico_mqtt"
    EVENTO_ID    = "evento_id"
