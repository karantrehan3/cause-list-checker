from pydantic import BaseSettings


class Settings(BaseSettings):
    AUTH_TOKEN: str
    CASE_SEARCH_URL: str
    CASE_DETAILS_URL: str
    CL_BASE_URL: str
    CL_FORM_ACTION_URL: str
    CL_JUDGE_WISE_REGULAR_URL: str
    EMAIL_RECIPIENTS: str
    MAIN_BASE_URL: str
    SENDER_EMAIL: str
    SENDER_PASSWORD: str
    SENDER_NAME: str
    SMTP_SERVER: str = "smtp.gmail.com"
    SMTP_PORT: int = 587

    class Config:
        env_file = ".env"


settings = Settings()
