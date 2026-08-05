from dataclasses import dataclass
from enum import StrEnum


class CTraderEnvironment(StrEnum):
    DEMO = "demo"
    LIVE = "live"


@dataclass(frozen=True, slots=True)
class CTraderConnectionConfig:
    environment: CTraderEnvironment
    client_id: str
    client_secret: str
