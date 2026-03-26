"""
main.py
-------
Ponto de entrada da aplicação FastAPI.

O consumidor MQTT roda como asyncio background task dentro do mesmo processo,
iniciado no lifespan — sem precisar de um segundo container ou supervisor.
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

from core.logging_config import configurar_logging, get_logger

configurar_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── STARTUP ────────────────────────────────────────────────────────────
    logger.info("Iniciando Sistema de Monitoramento Residencial")

    # Importa aqui para garantir que o logging já está configurado
    from consumidor_mqtt import iniciar_consumidor

    # Cria a task do consumidor MQTT em background
    # create_task() não bloqueia — a API HTTP já está disponível enquanto conecta
    task_mqtt = asyncio.create_task(iniciar_consumidor())
    logger.info("Consumidor MQTT iniciado como background task")

    logger.info("Sistema pronto para receber eventos")

    yield  # ← aplicação rodando

    # ── SHUTDOWN ───────────────────────────────────────────────────────────
    logger.info("Encerrando Sistema de Monitoramento Residencial")

    # Cancela a task do consumidor MQTT de forma limpa
    task_mqtt.cancel()
    try:
        await task_mqtt
    except asyncio.CancelledError:
        pass  # esperado — o consumidor trata CancelledError internamente

    logger.info("Sistema encerrado com sucesso")


def criar_app() -> FastAPI:
    app = FastAPI(
        title="Sistema de Monitoramento Residencial para Idosos",
        description=(
            "API para gerenciamento de eventos de monitoramento detectados "
            "via visão computacional (Frigate NVR). "
            "Detecta quedas, inatividade e comportamentos anômalos."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        logger.debug(
            "Requisição recebida",
            method=request.method,
            path=request.url.path,
        )
        response = await call_next(request)
        logger.debug(
            "Requisição concluída",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
        )
        return response

    @app.exception_handler(Exception)
    async def handler_excecao_geral(request: Request, exc: Exception):
        logger.exception(
            "Erro não tratado na requisição",
            method=request.method,
            path=request.url.path,
            erro=str(exc),
        )
        return JSONResponse(
            status_code=500,
            content={"erro": "Erro interno do servidor"},
        )

    @app.get("/health", tags=["infra"])
    async def health_check():
        """Health check para Docker e load balancers."""
        return {"status": "ok", "servico": "monitoramento-api"}

    return app


app = criar_app()


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
