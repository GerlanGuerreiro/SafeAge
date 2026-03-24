"""
main.py
-------
Ponto de entrada da aplicação FastAPI.

Responsabilidades deste arquivo:
- Inicializar logging ANTES de qualquer outra coisa
- Registrar routers da API
- Gerenciar lifecycle da aplicação (startup/shutdown) via lifespan
- NÃO conter lógica de negócio — isso vai em services/ e api/

Padrão de engenharia usado: Application Factory + Lifespan Events
(o mesmo padrão usado por projetos FastAPI em produção como Pydantic, SQLModel)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

# Logging deve ser o PRIMEIRO import de código próprio
# para garantir que todos os módulos subsequentes já usem o logger configurado
from core.logging_config import configurar_logging, get_logger

# Configura logging imediatamente ao importar main.py
# Isso cobre até erros que acontecem durante o carregamento dos demais módulos
configurar_logging()

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Lifespan: substitui @app.on_event("startup") que está DEPRECATED no FastAPI
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gerencia o ciclo de vida da aplicação.

    Tudo ANTES do yield → executado no startup
    Tudo DEPOIS do yield → executado no shutdown

    Por que lifespan em vez de @app.on_event?
    - Recomendação oficial do FastAPI desde v0.93
    - Permite usar async context managers (ex: pool de banco)
    - Mais fácil de testar
    """
    # ── STARTUP ────────────────────────────────────────────────────────────
    logger.info("Iniciando Sistema de Monitoramento Residencial")

    # TODO Fase 2: inicializar pool de conexão com PostgreSQL aqui
    # await banco_dados.conectar()

    # TODO Fase 2: iniciar consumidor MQTT com reconexão automática aqui
    # await mqtt_client.conectar()

    logger.info("Sistema pronto para receber eventos")

    yield  # ← aplicação rodando

    # ── SHUTDOWN ───────────────────────────────────────────────────────────
    logger.info("Encerrando Sistema de Monitoramento Residencial")

    # TODO Fase 2: fechar conexões graciosamente aqui
    # await banco_dados.fechar()
    # await mqtt_client.desconectar()

    logger.info("Sistema encerrado com sucesso")


# ---------------------------------------------------------------------------
# Criação da aplicação
# ---------------------------------------------------------------------------

def criar_app() -> FastAPI:
    """
    Factory function que cria e configura a aplicação FastAPI.

    Por que uma factory em vez de instância global?
    - Facilita testes (cada teste cria uma instância limpa)
    - Permite criar variações da app (com/sem autenticação, mocks, etc.)
    """
    app = FastAPI(
        title="Sistema de Monitoramento Residencial para Idosos",
        description=(
            "API para gerenciamento de eventos de monitoramento detectados "
            "via visão computacional (Frigate NVR). "
            "Detecta quedas, inatividade e comportamentos anômalos."
        ),
        version="1.0.0",
        lifespan=lifespan,
        # Desabilitar Swagger em produção é boa prática de segurança
        # docs_url=None if os.getenv("AMBIENTE") == "production" else "/docs",
    )

    # ── Middleware de logging de requisições ───────────────────────────────
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        """
        Loga todas as requisições HTTP com método, path e status code.
        Útil para auditoria e debug sem precisar de ferramentas externas.
        """
        logger.debug(
            "Requisição recebida",
            method=request.method,
            path=request.url.path,
            client=request.client.host if request.client else "unknown",
        )

        response = await call_next(request)

        logger.debug(
            "Requisição concluída",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
        )

        return response

    # ── Handler global de exceções ─────────────────────────────────────────
    @app.exception_handler(Exception)
    async def handler_excecao_geral(request: Request, exc: Exception):
        """
        Captura qualquer exceção não tratada, loga com contexto completo
        e retorna uma resposta JSON padronizada ao cliente.

        Sem isso, exceções não tratadas retornam HTML de erro do uvicorn,
        o que é problemático para clientes que esperam JSON.
        """
        logger.exception(
            "Erro não tratado na requisição",
            method=request.method,
            path=request.url.path,
            erro=str(exc),
        )
        return JSONResponse(
            status_code=500,
            content={
                "erro": "Erro interno do servidor",
                "detalhe": "Verifique os logs para mais informações",
            },
        )

    # ── Registro de routers ────────────────────────────────────────────────
    # TODO Fase 3: adicionar routers aqui conforme forem criados
    # from api.routers import eventos, alertas, configuracoes
    # app.include_router(eventos.router, prefix="/api/v1")
    # app.include_router(alertas.router, prefix="/api/v1")

    # ── Health check básico ────────────────────────────────────────────────
    @app.get("/health", tags=["infra"])
    async def health_check():
        """
        Endpoint de health check para o Docker e load balancers.
        Retorna 200 se a API está respondendo.
        TODO Fase 2: incluir status do banco e MQTT no response.
        """
        return {"status": "ok", "servico": "monitoramento-api"}

    return app


# ---------------------------------------------------------------------------
# Instância global (usada pelo uvicorn)
# ---------------------------------------------------------------------------
app = criar_app()


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,   # Apenas em desenvolvimento — no Docker use variável de ambiente
        log_level="info",
    )
