"""
core/config.py
--------------
Configuração centralizada da aplicação via pydantic-settings.

Por que pydantic-settings em vez de os.getenv()?

1. FALHA RÁPIDO: variáveis obrigatórias ausentes quebram no STARTUP,
   não silenciosamente em produção às 3h da manhã.

2. TIPAGEM: porta MQTT vira int automaticamente, sem int() manual.

3. DOCUMENTAÇÃO VIVA: este arquivo é o contrato completo do sistema.
   Qualquer dev novo sabe exatamente quais variáveis configurar.

4. VALIDAÇÃO: regex, ranges, choices — tudo suportado nativamente.

5. ÚNICO PONTO DE VERDADE: sem valores padrão espalhados em 5 arquivos.

Uso nos outros módulos:
    from core.config import settings
    host = settings.broker_mqtt_host
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configurações do sistema lidas do .env automaticamente.

    Campos sem default são OBRIGATÓRIOS — o sistema recusa subir se faltarem.
    Campos com default são opcionais.
    """

    model_config = SettingsConfigDict(
        env_file=".env",          # lê o .env na raiz do projeto
        env_file_encoding="utf-8",
        case_sensitive=False,     # NOME_BANCO e nome_banco são equivalentes
        extra="ignore",           # ignora variáveis extras no .env (ex: CAMERA_*)
    )

    # ── Banco de dados (obrigatórios) ──────────────────────────────────────
    usuario_banco: str
    senha_banco:   str
    nome_banco:    str
    postgres_host: str = "banco_dados"  # default: nome do serviço no Docker

    # ── MQTT ──────────────────────────────────────────────────────────────
    endereco_broker_mqtt: str = "broker_mqtt"
    porta_broker_mqtt:    int = 1883        # pydantic converte string → int automaticamente
    topico_mqtt_frigate:  str = "frigate/events"

    # ── Telegram (opcionais — sistema funciona sem eles) ──────────────────
    telegram_token:   str = ""
    telegram_chat_id: str = ""

    # ── Ambiente ──────────────────────────────────────────────────────────
    ambiente:   str = "development"
    nivel_log:  str = ""           # se vazio, logging_config decide baseado no ambiente
    tz:         str = "America/Manaus"

    # ── Propriedades computadas ───────────────────────────────────────────

    @property
    def telegram_configurado(self) -> bool:
        """Retorna True se ambas as variáveis do Telegram estão preenchidas."""
        return bool(self.telegram_token and self.telegram_chat_id)

    @property
    def em_producao(self) -> bool:
        """Retorna True se o ambiente é produção."""
        return self.ambiente.lower() == "production"

    @property
    def conexao_postgres(self) -> dict:
        """Retorna dict de conexão pronto para o psycopg2."""
        return {
            "host":            self.postgres_host,
            "database":        self.nome_banco,
            "user":            self.usuario_banco,
            "password":        self.senha_banco,
            "connect_timeout": 5,
        }


@lru_cache
def get_settings() -> Settings:
    """
    Retorna a instância singleton das configurações.

    lru_cache garante que o .env é lido apenas uma vez,
    mesmo que get_settings() seja chamado de vários módulos.

    Uso:
        from core.config import settings
        print(settings.nome_banco)
    """
    return Settings()


# Instância global — importe este objeto nos outros módulos
settings = get_settings()
