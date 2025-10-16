from pydantic import BaseModel
import os

class Settings(BaseModel):
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./modacct.db")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    openex_app_id: str | None = os.getenv("OPENEXCHANGERATES_APP_ID")
    alphavantage_key: str | None = os.getenv("ALPHAVANTAGE_API_KEY")
    newsapi_key: str | None = os.getenv("NEWSAPI_KEY")
    gdelt_user_agent: str | None = os.getenv("GDELT_USER_AGENT")

settings = Settings()
