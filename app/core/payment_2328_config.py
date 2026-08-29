from pydantic_settings import BaseSettings, SettingsConfigDict


class Payment2328Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="PAYMENT_2328_",
    )

    project_uuid: str = ""
    api_key: str = ""
    base_url: str = "https://api.2328.io/api"


payment_2328_settings = Payment2328Settings()
