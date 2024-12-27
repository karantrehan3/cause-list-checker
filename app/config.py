from pydantic import BaseSettings


class Settings(BaseSettings):
    AUTH_TOKEN: str
    SENDER_EMAIL: str
    SENDER_PASSWORD: str
    SENDER_NAME: str
    SMTP_SERVER: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    BASE_URL: str
    FORM_ACTION_URL: str
    EMAIL_RECIPIENTS: str

    class Config:
        env_file = ".env"


settings = Settings()
