from typing import Optional

from pydantic_settings import BaseSettings


class EnvironmentConfig(BaseSettings):
    CRYPTO_DOT_COM_EXCHANGE_API_KEY: str
    CRYPTO_DOT_COM_EXCHANGE_SECRET_KEY: str
    app_env: str
    dynamodb_region: str
    dynamodb_endpoint_url: Optional[str] = None
    google_client_id: str
    google_client_secret: str
    jwt_secret_key: str
    postgres_host: str
    postgres_user: str
    postgres_password: str
    postgres_database: str

    class Config:
        env_file = ".env"
