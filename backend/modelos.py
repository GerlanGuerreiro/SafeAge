"""
modelos.py
----------
Criação e migração das tabelas do banco de dados.

Chamado UMA VEZ no startup da aplicação (via lifespan no main.py).
Usa CREATE TABLE IF NOT EXISTS — seguro para rodar múltiplas vezes.

Tabelas gerenciadas:
- eventos_monitoramento : todos os eventos detectados pelo Frigate
- alertas               : alertas gerados pela análise comportamental
"""

from banco_dados import obter_conexao
from core.logging_config import get_logger

logger = get_logger(__name__)


def criar_tabelas() -> None:
    """
    Cria todas as tabelas necessárias se não existirem.
    Ponto de entrada único — chame apenas esta função no startup.
    """
    criar_tabela_eventos()
    criar_tabela_alertas()
    logger.info("Tabelas do banco verificadas/criadas com sucesso")


def criar_tabela_eventos() -> None:
    """
    Tabela principal: registra cada evento detectado pelo Frigate.

    Campos adicionados vs versão anterior:
    - confianca          : score do modelo de IA (0.0 a 1.0)
    - evento_id_frigate  : ID único do Frigate para correlacionar
                           múltiplos updates do mesmo evento
    """
    sql = """
    CREATE TABLE IF NOT EXISTS eventos_monitoramento (
        id                  SERIAL PRIMARY KEY,
        tipo_evento         VARCHAR(50)   NOT NULL,
        objeto_detectado    VARCHAR(100),
        camera              VARCHAR(100),
        inicio_evento       TIMESTAMP,
        fim_evento          TIMESTAMP,
        duracao_segundos    INTEGER,
        confianca           FLOAT,
        evento_id_frigate   VARCHAR(100),
        criado_em           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Índices para acelerar as queries mais comuns
    -- (histórico por câmera, filtro por tipo, ordenação por data)
    CREATE INDEX IF NOT EXISTS idx_eventos_camera
        ON eventos_monitoramento (camera);
    CREATE INDEX IF NOT EXISTS idx_eventos_tipo
        ON eventos_monitoramento (tipo_evento);
    CREATE INDEX IF NOT EXISTS idx_eventos_criado_em
        ON eventos_monitoramento (criado_em DESC);
    """
    try:
        with obter_conexao() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(sql)
        logger.debug("Tabela eventos_monitoramento verificada")
    except Exception as e:
        logger.exception("Erro ao criar tabela eventos_monitoramento", erro=str(e))
        raise


def criar_tabela_alertas() -> None:
    """
    Tabela de alertas: registra comportamentos anômalos detectados.
    Alimentada pela análise comportamental, não diretamente pelo Frigate.
    """
    sql = """
    CREATE TABLE IF NOT EXISTS alertas (
        id          SERIAL PRIMARY KEY,
        tipo_alerta VARCHAR(100) NOT NULL,
        camera      VARCHAR(100),
        descricao   TEXT,
        criado_em   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_alertas_camera
        ON alertas (camera);
    CREATE INDEX IF NOT EXISTS idx_alertas_criado_em
        ON alertas (criado_em DESC);
    """
    try:
        with obter_conexao() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(sql)
        logger.debug("Tabela alertas verificada")
    except Exception as e:
        logger.exception("Erro ao criar tabela alertas", erro=str(e))
        raise
