import json
from typing import Any, Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DB_HOST: str
    DB_PORT: int
    DB_USER: str
    DB_PASS: str
    DB_NAME: str

    BOT_TOKEN_1: str
    BOT_TOKEN_2: str
    BOT_TOKEN_3: str

    GOOGLE_SHEET_ID: str

    OPENAI_GPT_KEY: str
    OPENAI_EMBEDDING_KEY: str
    OPENAI_WHISPER_KEY: str

    WELCOME_TEXT: Optional[str] = None
    PARSE_MODE: Optional[str] = None
    MANAGER_CHAT_ID: Optional[int] = None
    CURRENT_WELCOME_FILE: str = "currentWelcome.json"
    TO_DELETE_FILE: str = "toDelete.json"
    WELCOME_LIFETIME: int = 300
    MANAGER_USERNAME: str = "@Bright099"

    SERVICE_ACCOUNT_JSON: Any = None  # Загружается из credentials.json, если не задано явно

    model_config = SettingsConfigDict(env_file=".env")

    @property
    def DATABASE_URL_asyncpg(self) -> str:
        return (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASS}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @field_validator("SERVICE_ACCOUNT_JSON", mode="before")
    @classmethod
    def load_service_account_json(cls, v):
        if isinstance(v, dict):
            return v
        if isinstance(v, str) and v.strip():
            try:
                return json.loads(v)
            except json.JSONDecodeError as e:
                raise ValueError(f"SERVICE_ACCOUNT_JSON is not valid JSON: {e}")
        try:
            with open("credentials.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            raise ValueError("credentials.json not found and SERVICE_ACCOUNT_JSON not provided.")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in credentials.json: {e}")


def load_additional_from_json(settings_obj: Settings, json_path: str = "config.json"):
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}

    for key in [
        "WELCOME_TEXT", "PARSE_MODE", "MANAGER_CHAT_ID",
        "CURRENT_WELCOME_FILE", "TO_DELETE_FILE", "WELCOME_LIFETIME",
        "MANAGER_USERNAME", "SERVICE_ACCOUNT_JSON"
    ]:
        if key in data:
            setattr(settings_obj, key, data[key])

    # Повторная валидация экземпляра — по сути "пересоздание"
    settings_obj.__init__(**settings_obj.model_dump())


def load_config() -> Settings:
    s = Settings()
    load_additional_from_json(s)
    return s


config = load_config()
