"""
main.py
-------
Ponto de entrada da aplicação FastAPI.

Startup order:
1. Logging configurado
2. Tabelas do banco criadas
3. Teste de conexão Telegram (envia mensagem de "sistema online")
4. Consumidor MQTT iniciado como background task
5. API HTTP disponível
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

    # 1. Cria tabelas do banco
    try:
        from modelos import criar_tabelas
        await asyncio.to_thread(criar_tabelas)
    except Exception as e:
        logger.error("Falha ao criar tabelas no banco", erro=str(e))

    # 2. Testa conexão Telegram e envia mensagem de startup
    try:
        from notificador import testar_conexao
        await testar_conexao()
    except Exception as e:
        # Não impede o startup — Telegram é opcional
        logger.warning("Telegram indisponível no startup", erro=str(e))

    # 3. Inicia consumidor MQTT
    from consumidor_mqtt import iniciar_consumidor
    task_mqtt = asyncio.create_task(iniciar_consumidor())
    logger.info("Consumidor MQTT iniciado como background task")

    logger.info("Sistema pronto para receber eventos")

    yield  # ← aplicação rodando

    # ── SHUTDOWN ───────────────────────────────────────────────────────────
    logger.info("Encerrando Sistema de Monitoramento Residencial")
    task_mqtt.cancel()
    try:
        await task_mqtt
    except asyncio.CancelledError:
        pass
    logger.info("Sistema encerrado com sucesso")


def criar_app() -> FastAPI:
    app = FastAPI(
        title="Sistema de Monitoramento Residencial para Idosos",
        description=(
            "API para gerenciamento de eventos detectados via visão computacional. "
            "Detecta quedas, imobilidade e ausência prolongada."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        logger.debug("Requisição recebida", method=request.method, path=request.url.path)
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
        logger.exception("Erro não tratado", method=request.method, path=request.url.path)
        return JSONResponse(status_code=500, content={"erro": "Erro interno do servidor"})

    @app.get("/health", tags=["infra"])
    async def health_check():
        return {"status": "ok", "servico": "monitoramento-api"}

    return app


app = criar_app()

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
