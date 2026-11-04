from pydantic import BaseSettings


class Settings(BaseSettings):
    AUTH_TOKEN: str
    CASE_SEARCH_URL: str
    CL_BASE_URL: str
    CL_FORM_ACTION_URL: str
    CL_JUDGE_WISE_REGULAR_URL: str
    CL_JUDGE_WISE_URL: str = "https://new.phhc.gov.in/cause/cause-list"
    CL_DAILY_URL: str = "https://new.phhc.gov.in/cause/daily-cause-list"
    EMAIL_RECIPIENTS: str
    PHHC_API_BASE_URL: str
    SENDER_EMAIL: str
    SENDER_PASSWORD: str
    SENDER_NAME: str
    SMTP_SERVER: str = "smtp.gmail.com"
    SMTP_PORT: int = 587

    class Config:
        env_file = ".env"


settings = Settings()

# Shared by every outbound request to the court sites (cause-list page, PDFs, APIs).
# Mirrors what desktop Chrome sends when opening a cause-list PDF link, so the
# court's server treats us like a normal browser. Accept-Encoding is left to
# `requests` (it can't decode brotli/zstd without extra packages).
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "application/pdf,application/json,*/*;q=0.8"
    ),
    "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
    "Upgrade-Insecure-Requests": "1",
}

# What Chrome sends when the new.phhc.gov.in frontend calls its JSON API
# (livedb9010.phhc.gov.in): a same-site XHR, not a page navigation.
API_REQUEST_HEADERS = {
    "User-Agent": REQUEST_HEADERS["User-Agent"],
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": REQUEST_HEADERS["Accept-Language"],
    "Origin": "https://new.phhc.gov.in",
    "Referer": "https://new.phhc.gov.in/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
    "sec-ch-ua": '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
}
