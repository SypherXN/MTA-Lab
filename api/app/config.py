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
    dashboard_password: str = ""
    session_secret: str = "change-me-session-secret"
    session_ttl_hours: int = 168
    daily_budget_usd: float = 5.0
    monthly_budget_usd: float = 50.0
    compact_payload_max_bytes: int = 4096
    sequential_lanes: bool = False
    lane_lock_ttl_minutes: int = 45
    plans_repo_dir: str = ""

    @property
    def read_auth_enabled(self) -> bool:
        return bool(self.read_api_key.strip())

    @property
    def dashboard_auth_enabled(self) -> bool:
        return bool(self.dashboard_password.strip())

    @property
    def alert_enabled(self) -> bool:
        return bool(self.alert_webhook_url.strip())

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def resolved_plans_dir(self):
        from pathlib import Path

        if self.plans_repo_dir.strip():
            path = Path(self.plans_repo_dir)
            if not path.is_absolute():
                path = Path(__file__).resolve().parent.parent / path
            return path.resolve()
        return (Path(__file__).resolve().parent.parent.parent / "plans").resolve()


settings = Settings()
