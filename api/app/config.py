from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="MTA_", extra="ignore")

    database_path: str = "./data/mta_lab.db"
    write_api_key: str = "dev-key-change-me"
    read_api_key: str = ""
    cors_origins: str = "http://localhost:8080"
    initial_simulated_cash: float = 10000.0
    backup_dir: str = "./data/backups"
    backup_keep: int = 14
    rate_limit_per_minute: int = 120
    rate_limit_enabled: bool = True
    alert_webhook_url: str = ""
    alert_cooldown_minutes: int = 60
    watcher_pct_threshold: float = 1.5
    plan_history_keep: int = 20

    @property
    def read_auth_enabled(self) -> bool:
        return bool(self.read_api_key.strip())

    @property
    def alert_enabled(self) -> bool:
        return bool(self.alert_webhook_url.strip())

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
