from typing import List, Literal
from pydantic import field_validator, model_validator
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


settings = Settings()
