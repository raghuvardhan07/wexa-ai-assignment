from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # CognoDB
    cognodb_uri: str
    cognodb_username: str = "cognodb"
    cognodb_password: str
    cognodb_database: str = "neo4j"

    # Server (PORT is injected by most hosting platforms; API_PORT is for local override)
    api_host: str = "0.0.0.0"
    api_port: int = Field(
        default=8000,
        validation_alias=AliasChoices("api_port", "PORT"),
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
