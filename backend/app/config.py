from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    research_agent_url: str = "http://localhost:8001"
    developer_agent_url: str = "http://localhost:8002"
    callback_base_url: str = "http://localhost:8000"
    dashboard_origin: str = "http://localhost:5173"
    agent_timeout_s: float = 120
    gemini_timeout_s: float = 30


settings = Settings()
