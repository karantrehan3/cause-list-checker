from pydantic import BaseSettings


class Settings(BaseSettings):
    AUTH_TOKEN: str
    SENDER_EMAIL: str
    SENDER_PASSWORD: str
    SENDER_NAME: str
    SMTP_SERVER: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    CL_BASE_URL: str
    MAIN_BASE_URL: str
    FORM_ACTION_URL: str
    CASE_SEARCH_URL: str
    CASE_DETAILS_URL: str
    EMAIL_RECIPIENTS: str

    class Config:
        env_file = ".env"


settings = Settings()
