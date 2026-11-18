from typing import List, Literal
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

    # App
    PROJECT_NAME: str = "Infra Platform API"
    API_VERSION: str = "1.0.0"
    DEBUG: bool = False
    APP_ENV: Literal["development", "test", "production"] = "development"
    APP_ORIGIN: str = "http://localhost:3000"

    # Security
    SECRET_KEY: str = "CHANGE_ME"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ALGORITHM: str = "HS256"
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"
    # Rate-limiting de login (fuerza bruta)
    LOGIN_MAX_FAILS: int = 5
    LOGIN_FAIL_WINDOW_SEC: int = 300

    # Windows Agent.
    # Por defecto el modulo se activa y desactiva desde el panel (Configuracion > Agentes)
    # y el backend genera y custodia su propia llave de firma de comandos.
    # AGENT_MODULE_SELF_SERVICE=false impide que se active desde el panel.
    # AGENT_MODULE_ENABLED=true lo fuerza encendido con la llave de las variables de
    # entorno (modo gestionado por el servidor); el panel ya no puede apagarlo.
    AGENT_MODULE_SELF_SERVICE: bool = True
    AGENT_MODULE_ENABLED: bool = False
    AGENT_COMMAND_SIGNING_PRIVATE_KEY: str = ""
    AGENT_COMMAND_SIGNING_KEY_ID: str = ""
    # URL publica que usan los agentes. Vacia: se usa APP_ORIGIN, que reenvia /agent/v1.
    AGENT_CONTROL_PLANE_URL: str = ""
    AGENT_PACKAGE_VERSION: str = "0.5.0"
    AGENT_MODULE_REFRESH_SEC: int = Field(15, ge=5, le=300)
    AGENT_ENROLLMENT_TTL_SEC: int = Field(600, ge=60, le=3600)
    AGENT_COMMAND_TTL_SEC: int = Field(120, ge=30, le=600)
    AGENT_MAX_CLOCK_SKEW_SEC: int = Field(120, ge=30, le=300)
    AGENT_MAX_BODY_BYTES: int = Field(262144, ge=1024, le=1048576)
    AGENT_MIN_VERSION: str = "0.3.0"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://infra_user:infra_pass@db:5432/infra_platform"

    # CORS
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost"]

    # SQL Server (backup target)
    SQLSERVER_SERVER: str = "localhost"
    SQLSERVER_PORT: int = 1433
    SQLSERVER_USER: str = "sa"
    SQLSERVER_PASSWORD: str = ""
    SQLSERVER_DRIVER: str = "ODBC Driver 17 for SQL Server"
    SQLSERVER_BACKUP_PATH: str = "C:\\Backups\\InfraPlatform"
    # Tuning de rendimiento de backups
    SQLSERVER_BACKUP_STRIPES: int = 1        # nº de archivos .bak escritos en paralelo
    SQLSERVER_BACKUP_BUFFERCOUNT: int = 8    # nº de buffers de I/O
    SQLSERVER_BACKUP_VERIFY: bool = True     # RESTORE VERIFYONLY tras respaldar

    # Operational storage boundaries
    CLEANUP_TRASH_PATH: str = ''
    FM_ALLOWED_ROOTS: str = ''

    # Seguridad (C-6): rechazar secretos por defecto/débiles. La validación se ejecuta
    # al instanciar Settings (arranque), abortando si SECRET_KEY no fue rotada.
    @field_validator("SECRET_KEY")
    @classmethod
    def _reject_weak_secret(cls, v: str) -> str:
        normalized = v.strip()
        known_placeholders = {"change_me", "changeme", "dev-secret-key-change-in-prod"}
        is_placeholder = normalized.lower() in known_placeholders or "change_me" in normalized.lower()
        if len(normalized) < 32 or is_placeholder:
            raise ValueError(
                "SECRET_KEY inseguro/por defecto. Genera uno con: "
                'python -c "import secrets; print(secrets.token_hex(32))" '
                "y defínelo como variable de entorno SECRET_KEY."
            )
        return v

    @field_validator("COOKIE_SAMESITE")
    @classmethod
    def _validate_samesite(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"lax", "strict", "none"}:
            raise ValueError("COOKIE_SAMESITE debe ser lax, strict o none")
        return normalized

    @model_validator(mode="after")
    def _validate_production_transport(self):
        if self.APP_ENV == "production":
            if not self.APP_ORIGIN.startswith("https://") or not self.COOKIE_SECURE:
                raise ValueError("Produccion requiere APP_ORIGIN HTTPS y COOKIE_SECURE=true")
        return self

    @property
    def agent_signing_key_from_environment(self) -> bool:
        return bool(self.AGENT_COMMAND_SIGNING_PRIVATE_KEY or self.AGENT_COMMAND_SIGNING_KEY_ID)

    @property
    def agent_control_plane_url(self) -> str:
        return (self.AGENT_CONTROL_PLANE_URL or self.APP_ORIGIN).rstrip("/")

    @model_validator(mode="after")
    def _validate_agent_control_plane(self):
        from urllib.parse import urlsplit

        parts = urlsplit(self.agent_control_plane_url)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("AGENT_CONTROL_PLANE_URL debe ser una URL http(s) valida")
        if parts.path not in {"", "/"} or parts.query or parts.fragment:
            raise ValueError("AGENT_CONTROL_PLANE_URL no debe llevar ruta ni parametros")
        if self.APP_ENV == "production" and parts.scheme != "https":
            raise ValueError("En produccion AGENT_CONTROL_PLANE_URL debe ser HTTPS")
        return self

    @model_validator(mode="after")
    def _validate_agent_signing(self):
        # La llave de entorno se valida siempre que se configure, aunque el modulo se
        # active desde el panel: una llave mal pegada debe fallar al arrancar, no al
        # firmar el primer comando.
        if not self.AGENT_MODULE_ENABLED and not self.agent_signing_key_from_environment:
            return self
        key_id = self.AGENT_COMMAND_SIGNING_KEY_ID
        valid_key_id = (
            1 <= len(key_id) <= 64
            and all(character.isalnum() or character in "._-" for character in key_id)
        )
        if not valid_key_id:
            raise ValueError("AGENT_COMMAND_SIGNING_KEY_ID invalido")
        try:
            from app.agent_protocol import load_private_key

            load_private_key(self.AGENT_COMMAND_SIGNING_PRIVATE_KEY)
        except Exception as exc:
            raise ValueError("Clave privada de comandos del agente invalida") from exc
        return self


settings = Settings()
