"""
banco_dados.py
--------------
Camada de acesso ao PostgreSQL.
Usa settings centralizado em vez de os.getenv().
"""

import asyncio
from datetime import datetime
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor

from core.config import settings
from core.logging_config import get_logger

logger = get_logger(__name__)


@contextmanager
def obter_conexao():
    """
    Context manager que abre e fecha a conexão automaticamente.
    Parâmetros de conexão vêm de settings.conexao_postgres.
    """
    conexao = None
    try:
        conexao = psycopg2.connect(**settings.conexao_postgres)
        logger.debug("Conexão com PostgreSQL estabelecida")
        yield conexao
        conexao.commit()
    except psycopg2.OperationalError as e:
        logger.error(
            "Falha ao conectar ao PostgreSQL",
            erro=str(e),
            host=settings.postgres_host,
            banco=settings.nome_banco,
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
# Escrita
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
    sql = """
        INSERT INTO eventos_monitoramento (
            tipo_evento, objeto_detectado, camera,
            inicio_evento, fim_evento, duracao_segundos,
            confianca, evento_id_frigate
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id;
    """
    try:
        with obter_conexao() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(sql, (
                    tipo_evento, objeto_detectado, camera,
                    inicio_evento, fim_evento, duracao_segundos,
                    confianca, evento_id_frigate,
                ))
                id_gerado = cursor.fetchone()[0]
        logger.info("Evento salvo no banco", id=id_gerado, camera=camera)
        return id_gerado
    except Exception as e:
        logger.exception("Erro ao salvar evento", erro=str(e))
        return None


def salvar_alerta(tipo_alerta: str, camera: str, descricao: str) -> int | None:
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
        logger.warning("Alerta salvo no banco", id=id_gerado, tipo_alerta=tipo_alerta)
        return id_gerado
    except Exception as e:
        logger.exception("Erro ao salvar alerta", erro=str(e))
        return None


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------

def listar_eventos(
    limite: int = 50,
    offset: int = 0,
    camera: str | None = None,
) -> list[dict]:
    filtro = "WHERE camera = %s" if camera else ""
    params = [camera, limite, offset] if camera else [limite, offset]
    sql = f"""
        SELECT id, tipo_evento, objeto_detectado, camera,
               inicio_evento, fim_evento, duracao_segundos,
               confianca, evento_id_frigate, criado_em
        FROM eventos_monitoramento
        {filtro}
        ORDER BY criado_em DESC
        LIMIT %s OFFSET %s;
    """
    try:
        with obter_conexao() as conexao:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, params)
                return [dict(r) for r in cursor.fetchall()]
    except Exception as e:
        logger.exception("Erro ao listar eventos", erro=str(e))
        return []


def listar_alertas(
    limite: int = 50,
    offset: int = 0,
    camera: str | None = None,
) -> list[dict]:
    filtro = "WHERE camera = %s" if camera else ""
    params = [camera, limite, offset] if camera else [limite, offset]
    sql = f"""
        SELECT id, tipo_alerta, camera, descricao, criado_em
        FROM alertas
        {filtro}
        ORDER BY criado_em DESC
        LIMIT %s OFFSET %s;
    """
    try:
        with obter_conexao() as conexao:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql, params)
                return [dict(r) for r in cursor.fetchall()]
    except Exception as e:
        logger.exception("Erro ao listar alertas", erro=str(e))
        return []


def obter_resumo() -> dict:
    sql_totais = """
        SELECT
            (SELECT COUNT(*) FROM eventos_monitoramento)                            AS total_eventos,
            (SELECT COUNT(*) FROM alertas)                                          AS total_alertas,
            (SELECT COUNT(*) FROM eventos_monitoramento
             WHERE criado_em >= NOW() - INTERVAL '24 hours')                        AS eventos_24h,
            (SELECT ROUND(AVG(confianca)::numeric, 3)
             FROM eventos_monitoramento WHERE confianca IS NOT NULL)                AS media_confianca,
            (SELECT COUNT(DISTINCT camera) FROM eventos_monitoramento)              AS cameras_ativas;
    """
    sql_alertas_recentes = """
        SELECT tipo_alerta, camera, descricao, criado_em
        FROM alertas ORDER BY criado_em DESC LIMIT 5;
    """
    sql_eventos_por_hora = """
        SELECT DATE_TRUNC('hour', criado_em) AS hora, COUNT(*) AS quantidade
        FROM eventos_monitoramento
        WHERE criado_em >= NOW() - INTERVAL '24 hours'
        GROUP BY hora ORDER BY hora;
    """
    try:
        with obter_conexao() as conexao:
            with conexao.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(sql_totais)
                totais = dict(cursor.fetchone())
                cursor.execute(sql_alertas_recentes)
                alertas_recentes = [dict(r) for r in cursor.fetchall()]
                cursor.execute(sql_eventos_por_hora)
                eventos_por_hora = [dict(r) for r in cursor.fetchall()]
        return {**totais, "alertas_recentes": alertas_recentes, "eventos_por_hora": eventos_por_hora}
    except Exception as e:
        logger.exception("Erro ao obter resumo", erro=str(e))
        return {}


# ---------------------------------------------------------------------------
# Wrappers assíncronos
# ---------------------------------------------------------------------------

async def salvar_evento_async(*args, **kwargs) -> int | None:
    return await asyncio.to_thread(salvar_evento, *args, **kwargs)

async def salvar_alerta_async(*args, **kwargs) -> int | None:
    return await asyncio.to_thread(salvar_alerta, *args, **kwargs)

async def listar_eventos_async(**kwargs) -> list[dict]:
    return await asyncio.to_thread(listar_eventos, **kwargs)

async def listar_alertas_async(**kwargs) -> list[dict]:
    return await asyncio.to_thread(listar_alertas, **kwargs)

async def obter_resumo_async() -> dict:
    return await asyncio.to_thread(obter_resumo)
