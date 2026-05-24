"""
main.py
-------
SafeAge — Inteligência que protege.
Ponto de entrada da aplicação FastAPI.

Startup order:
1. Logging configurado
2. Tabelas do banco criadas
3. Telegram: mensagem de startup
4. Consumidor MQTT iniciado (background task)
5. Loop de verificação comportamental iniciado (background task)
6. API HTTP disponível
"""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from core.logging_config import configurar_logging, get_logger

configurar_logging()
logger = get_logger(__name__)

STATIC_DIR = Path(__file__).parent / "api" / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Iniciando SafeAge — Inteligência que protege")

    # 1. Banco de dados
    try:
        from modelos import criar_tabelas
        await asyncio.to_thread(criar_tabelas)
    except Exception as e:
        logger.error("Falha ao criar tabelas no banco", erro=str(e))

    # 2. Telegram startup
    try:
        from notificador import testar_conexao
        await testar_conexao()
    except Exception as e:
        logger.warning("Telegram indisponível no startup", erro=str(e))

    # 3. Consumidor MQTT
    from consumidor_mqtt import iniciar_consumidor
    task_mqtt = asyncio.create_task(iniciar_consumidor())
    logger.info("Consumidor MQTT iniciado como background task")

    # 4. Loop de verificação comportamental
    from analise_comportamento import loop_verificacao
    task_verificacao = asyncio.create_task(loop_verificacao())
    logger.info("Loop de verificação comportamental iniciado como background task")

    logger.info("SafeAge pronto para monitorar")

    yield

    # Shutdown limpo
    logger.info("Encerrando SafeAge")
    task_mqtt.cancel()
    task_verificacao.cancel()
    try:
        await asyncio.gather(task_mqtt, task_verificacao, return_exceptions=True)
    except Exception:
        pass
    logger.info("SafeAge encerrado com sucesso")


def criar_app() -> FastAPI:
    app = FastAPI(
        title="SafeAge",
        description=(
            "**Inteligência que protege.**\n\n"
            "Sistema de monitoramento residencial para idosos via visão computacional. "
            "Detecta quedas, imobilidade prolongada e ausência, gerando alertas em tempo real."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    from api.routers.eventos import router as router_eventos
    app.include_router(router_eventos)

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        if not request.url.path.startswith("/static"):
            logger.debug("Requisição", method=request.method, path=request.url.path)
        return await call_next(request)

    @app.exception_handler(Exception)
    async def handler_excecao_geral(request: Request, exc: Exception):
        logger.exception("Erro não tratado", path=request.url.path)
        return JSONResponse(status_code=500, content={"erro": "Erro interno do servidor"})

    @app.get("/health", tags=["infra"])
    async def health_check():
        return {"status": "ok", "servico": "safeage-api"}

    @app.get("/", include_in_schema=False)
    async def dashboard():
        return FileResponse(str(STATIC_DIR / "dashboard.html"))

    return app


app = criar_app()

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
