from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    kotak_consumer_key: str = ""
    kotak_mobile_number: str = ""
    kotak_ucc: str = ""
    kotak_mpin: str = ""
    max_daily_loss: float = 5000.0
    risk_percent: float = 2.0
    default_quantity: int = 50
    min_risk_reward: float = 2.0
    max_open_trades: int = 1
    paper_trading: bool = True
    log_level: str = "INFO"
    log_dir: str = "logs"
    groq_api_key: str = ""
    
    supabase_db_url: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
