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
    ctrader_gold_symbol_id: int | None
    ctrader_dow_symbol_id: int | None


def _optional_int(name: str) -> int | None:
    value = getenv(name)
    return int(value) if value else None


def load_settings() -> Settings:
    client_id = getenv("CTRADER_CLIENT_ID")
    client_secret = getenv("CTRADER_CLIENT_SECRET")

    if not client_id:
        raise RuntimeError("CTRADER_CLIENT_ID is not configured")

    if not client_secret:
        raise RuntimeError("CTRADER_CLIENT_SECRET is not configured")

    return Settings(
        ctrader_environment=getenv(
            "CTRADER_ENVIRONMENT",
            "demo",
        ),
        ctrader_client_id=client_id,
        ctrader_client_secret=client_secret,
        ctrader_access_token=getenv("CTRADER_ACCESS_TOKEN"),
        ctrader_refresh_token=getenv("CTRADER_REFRESH_TOKEN"),
        ctrader_account_id=_optional_int("CTRADER_ACCOUNT_ID"),
        ctrader_gold_symbol_id=_optional_int("CTRADER_GOLD_SYMBOL_ID"),
        ctrader_dow_symbol_id=_optional_int("CTRADER_DOW_SYMBOL_ID"),
    )
