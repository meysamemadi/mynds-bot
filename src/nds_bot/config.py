from dataclasses import dataclass
from os import getenv

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True, slots=True)
class Settings:
    ctrader_environment: str
    ctrader_client_id: str
    ctrader_client_secret: str
    ctrader_access_token: str | None
    ctrader_refresh_token: str | None
    ctrader_account_id: int | None


def load_settings() -> Settings:
    client_id = getenv("CTRADER_CLIENT_ID")
    client_secret = getenv("CTRADER_CLIENT_SECRET")

    if not client_id:
        raise RuntimeError("CTRADER_CLIENT_ID is not configured")

    if not client_secret:
        raise RuntimeError("CTRADER_CLIENT_SECRET is not configured")

    account_id_value = getenv("CTRADER_ACCOUNT_ID")

    return Settings(
        ctrader_environment=getenv(
            "CTRADER_ENVIRONMENT",
            "demo",
        ),
        ctrader_client_id=client_id,
        ctrader_client_secret=client_secret,
        ctrader_access_token=getenv("CTRADER_ACCESS_TOKEN"),
        ctrader_refresh_token=getenv("CTRADER_REFRESH_TOKEN"),
        ctrader_account_id=(int(account_id_value) if account_id_value else None),
    )
