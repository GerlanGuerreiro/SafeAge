"""
banco_dados.py
--------------
Camada de acesso ao PostgreSQL.

Decisão de arquitetura: mantemos psycopg2 síncrono (já existente no projeto)
e usamos asyncio.to_thread() para não bloquear o loop do FastAPI.
Migrar para asyncpg seria mais performático, mas quebraria o código existente
sem ganho real neste estágio do projeto.

Responsabilidades:
- Gerenciar conexão com o banco
- Salvar eventos de detecção
- Salvar alertas gerados
- Buscar histórico (usado pelos endpoints da API - Fase 3)
"""

import os
import asyncio
from datetime import datetime
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor

from core.logging_config import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Configuração de conexão
# ---------------------------------------------------------------------------

def _parametros_conexao() -> dict:
    """Retorna os parâmetros de conexão a partir das variáveis de ambiente."""
    return {
        "host":     os.getenv("POSTGRES_HOST", "banco_dados"),
        "database": os.getenv("NOME_BANCO"),
        "user":     os.getenv("USUARIO_BANCO"),
        "password": os.getenv("SENHA_BANCO"),
        "connect_timeout": 5,
    }


@contextmanager
def obter_conexao():
    """
    Context manager que abre e fecha a conexão automaticamente.

    Uso correto:
        with obter_conexao() as conexao:
            cursor = conexao.cursor()
            ...

    Por que context manager em vez de retornar a conexão diretamente?
    - Garante que a conexão SEMPRE seja fechada, mesmo se houver exceção
    - Elimina o padrão manual de cursor.close() / conexao.close()
    - Faz rollback automático em caso de erro
    """
    conexao = None
    try:
        conexao = psycopg2.connect(**_parametros_conexao())
        logger.debug("Conexão com PostgreSQL estabelecida")
        yield conexao
        conexao.commit()
    except psycopg2.OperationalError as e:
        logger.error(
            "Falha ao conectar ao PostgreSQL",
            erro=str(e),
            host=os.getenv("POSTGRES_HOST", "banco_dados"),
            banco=os.getenv("NOME_BANCO"),
        )
        raise
    except Exception as e:
        if conexao:
            conexao.rollback()
            logger.warning("Rollback executado após erro", erro=str(e))
        raise
    finally:
        if conexao:
            conexao.close()
            logger.debug("Conexão com PostgreSQL fechada")


# ---------------------------------------------------------------------------
# Persistência de eventos
# ---------------------------------------------------------------------------

def salvar_evento(
    tipo_evento: str,
    objeto_detectado: str,
    camera: str,
    inicio_evento: datetime,
    fim_evento: datetime | None = None,
    duracao_segundos: int | None = None,
    confianca: float | None = None,
    evento_id_frigate: str | None = None,
) -> int | None:
    """
    Salva um evento de detecção no banco de dados.

    Retorna o ID gerado pelo banco, ou None em caso de falha.

    Parâmetros:
        tipo_evento         : 'new', 'update', 'end', 'queda', 'imobilidade'
        objeto_detectado    : 'person', 'car', etc.
        camera              : nome da câmera no Frigate
        inicio_evento       : timestamp de início (unix → datetime)
        fim_evento          : timestamp de fim (None se evento ainda ativo)
        duracao_segundos    : duração calculada em segundos
        confianca           : score de confiança do Frigate (0.0 a 1.0)
        evento_id_frigate   : ID único gerado pelo Frigate para rastreamento
    """
    sql = """
        INSERT INTO eventos_monitoramento (
            tipo_evento,
            objeto_detectado,
            camera,
            inicio_evento,
            fim_evento,
            duracao_segundos,
            confianca,
            evento_id_frigate
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id;
    """
    try:
        with obter_conexao() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(sql, (
                    tipo_evento,
                    objeto_detectado,
                    camera,
                    inicio_evento,
                    fim_evento,
                    duracao_segundos,
                    confianca,
                    evento_id_frigate,
                ))
                id_gerado = cursor.fetchone()[0]

        logger.info(
            "Evento salvo no banco",
            id=id_gerado,
            tipo_evento=tipo_evento,
            camera=camera,
            confianca=confianca,
            evento_id_frigate=evento_id_frigate,
        )
        return id_gerado

    except Exception as e:
        logger.exception(
            "Erro ao salvar evento no banco",
            tipo_evento=tipo_evento,
            camera=camera,
            erro=str(e),
        )
        return None


def salvar_alerta(
    tipo_alerta: str,
    camera: str,
    descricao: str,
) -> int | None:
    """
    Salva um alerta gerado pela análise comportamental.

    Retorna o ID gerado, ou None em caso de falha.

    Parâmetros:
        tipo_alerta : 'queda', 'imobilidade', 'ausencia_prolongada'
        camera      : câmera onde o comportamento foi detectado
        descricao   : texto descritivo do alerta para exibição
    """
    sql = """
        INSERT INTO alertas (tipo_alerta, camera, descricao)
        VALUES (%s, %s, %s)
        RETURNING id;
    """
    try:
        with obter_conexao() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(sql, (tipo_alerta, camera, descricao))
                id_gerado = cursor.fetchone()[0]

        logger.warning(
            "Alerta salvo no banco",
            id=id_gerado,
            tipo_alerta=tipo_alerta,
            camera=camera,
        )
        return id_gerado

    except Exception as e:
        logger.exception(
            "Erro ao salvar alerta no banco",
            tipo_alerta=tipo_alerta,
            camera=camera,
            erro=str(e),
        )
        return None


# ---------------------------------------------------------------------------
# Wrappers assíncronos
# Permitem chamar funções síncronas do psycopg2 sem bloquear o loop asyncio
# ---------------------------------------------------------------------------

async def salvar_evento_async(*args, **kwargs) -> int | None:
    """Versão async de salvar_evento — use esta nos handlers do FastAPI."""
    return await asyncio.to_thread(salvar_evento, *args, **kwargs)


async def salvar_alerta_async(*args, **kwargs) -> int | None:
    """Versão async de salvar_alerta — use esta nos handlers do FastAPI."""
    return await asyncio.to_thread(salvar_alerta, *args, **kwargs)
