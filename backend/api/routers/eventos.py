"""
api/routers/eventos.py
----------------------
Endpoints REST para consulta de eventos e alertas.

Rotas:
    GET /api/v1/eventos          — lista eventos paginados
    GET /api/v1/eventos/{id}     — evento específico
    GET /api/v1/alertas          — lista alertas paginados
    GET /api/v1/dashboard/resumo — dados agregados para o dashboard
"""

import asyncio
from typing import Optional

from fastapi import APIRouter, Query, HTTPException

import banco_dados as db
from core.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["monitoramento"])


# ---------------------------------------------------------------------------
# Eventos
# ---------------------------------------------------------------------------

@router.get("/eventos", summary="Lista eventos de detecção")
async def listar_eventos(
    limite: int = Query(default=20, ge=1, le=100, description="Itens por página"),
    offset: int = Query(default=0, ge=0, description="Paginação"),
    camera: Optional[str] = Query(default=None, description="Filtrar por câmera"),
):
    """
    Retorna eventos de detecção registrados pelo Frigate.
    Suporta paginação e filtro por câmera.
    """
    eventos = await db.listar_eventos_async(
        limite=limite, offset=offset, camera=camera
    )

    # Serializa datetimes para string ISO
    for e in eventos:
        for campo in ("inicio_evento", "fim_evento", "criado_em"):
            if e.get(campo):
                e[campo] = e[campo].isoformat()

    logger.debug("Eventos listados", total=len(eventos), camera=camera)
    return {
        "total":   len(eventos),
        "limite":  limite,
        "offset":  offset,
        "eventos": eventos,
    }


@router.get("/alertas", summary="Lista alertas comportamentais")
async def listar_alertas(
    limite: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    camera: Optional[str] = Query(default=None),
):
    """
    Retorna alertas gerados pela análise comportamental
    (imobilidade, ausência prolongada).
    """
    alertas = await db.listar_alertas_async(
        limite=limite, offset=offset, camera=camera
    )

    for a in alertas:
        if a.get("criado_em"):
            a["criado_em"] = a["criado_em"].isoformat()

    logger.debug("Alertas listados", total=len(alertas))
    return {
        "total":   len(alertas),
        "limite":  limite,
        "offset":  offset,
        "alertas": alertas,
    }


@router.get("/dashboard/resumo", summary="Dados agregados para o dashboard")
async def resumo_dashboard():
    """
    Retorna métricas consolidadas:
    - totais de eventos e alertas
    - eventos nas últimas 24h
    - média de confiança do modelo
    - câmeras ativas
    - últimos 5 alertas
    - eventos por hora (últimas 24h) para o gráfico
    """
    resumo = await db.obter_resumo_async()

    if not resumo:
        raise HTTPException(status_code=503, detail="Banco de dados indisponível")

    # Serializa datetimes
    for alerta in resumo.get("alertas_recentes", []):
        if alerta.get("criado_em"):
            alerta["criado_em"] = alerta["criado_em"].isoformat()

    for hora in resumo.get("eventos_por_hora", []):
        if hora.get("hora"):
            hora["hora"] = hora["hora"].isoformat()

    return resumo
