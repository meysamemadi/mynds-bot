from __future__ import annotations

import traceback
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from ctrader_open_api import Client, EndPoints, Protobuf, TcpProtocol
from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import (
    ProtoHeartbeatEvent,
)
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOAAccountAuthReq,
    ProtoOAAccountAuthRes,
    ProtoOAApplicationAuthReq,
    ProtoOAApplicationAuthRes,
    ProtoOAErrorRes,
    ProtoOAGetTrendbarsReq,
    ProtoOAGetTrendbarsRes,
    ProtoOASymbolByIdReq,
    ProtoOASymbolByIdRes,
)
from ctrader_open_api.messages.OpenApiModelMessages_pb2 import (
    ProtoOATrendbarPeriod,
)
from twisted.internet import reactor
from twisted.python.failure import Failure

from nds_bot.config import load_settings

AUTH_TIMEOUT_SECONDS = 20
MARKET_DATA_TIMEOUT_SECONDS = 60

TARGET_SYMBOL = "EURUSD"

# این ID را در مرحله Symbol Discovery
# برای حساب Demo فعلی به دست آوردیم.
#
# در معماری نهایی هاردکد نخواهد شد.
TARGET_SYMBOL_ID = 1

TARGET_PERIOD = "M1"
TREND_BAR_COUNT = 20
LOOKBACK_DAYS = 3

CTRADER_PRICE_DIVISOR = Decimal("100000")


def select_host(environment: str) -> str:
    if environment == "demo":
        return EndPoints.PROTOBUF_DEMO_HOST

    if environment == "live":
        return EndPoints.PROTOBUF_LIVE_HOST

    raise ValueError("CTRADER_ENVIRONMENT must be either 'demo' or 'live'")


def main() -> None:
    settings = load_settings()

    if not settings.ctrader_access_token:
        raise RuntimeError("CTRADER_ACCESS_TOKEN is not configured in .env")

    if settings.ctrader_account_id is None:
        raise RuntimeError("CTRADER_ACCOUNT_ID is not configured in .env")

    account_id = settings.ctrader_account_id
    host = select_host(settings.ctrader_environment)

    client = Client(
        host,
        EndPoints.PROTOBUF_PORT,
        TcpProtocol,
    )

    shutdown_started = False

    symbol_digits: int | None = None
    pip_position: int | None = None

    def stop_reactor() -> None:
        if reactor.running:
            reactor.stop()

    def shutdown() -> None:
        nonlocal shutdown_started

        if shutdown_started:
            return

        shutdown_started = True

        print()
        print("Closing cTrader connection...")

        client.stopService()

        # Fallback در صورتی که callback قطع اتصال
        # به هر دلیلی اجرا نشود.
        reactor.callLater(
            0.5,
            stop_reactor,
        )

    def schedule_shutdown() -> None:
        reactor.callLater(
            0,
            shutdown,
        )

    def on_request_error(
        failure: Failure,
    ) -> None:
        if shutdown_started:
            return

        print()
        print("Request failed")
        print(
            "Error type:",
            type(failure.value).__name__,
        )
        print(
            "Error message:",
            failure.getErrorMessage(),
        )

        schedule_shutdown()

    def relative_price_to_decimal(
        raw_price: int,
    ) -> Decimal:
        if symbol_digits is None:
            raise RuntimeError("Symbol digits are not available")

        price = Decimal(raw_price) / CTRADER_PRICE_DIVISOR

        precision = Decimal(1).scaleb(-symbol_digits)

        return price.quantize(precision)

    def send_application_auth(
        connected_client: Client,
    ) -> None:
        request = ProtoOAApplicationAuthReq()

        request.clientId = settings.ctrader_client_id

        request.clientSecret = settings.ctrader_client_secret

        deferred = connected_client.send(
            request,
            clientMsgId="application-auth",
            responseTimeoutInSeconds=(AUTH_TIMEOUT_SECONDS),
        )

        deferred.addErrback(on_request_error)

        print("Application authentication request sent")

    def send_account_auth(
        connected_client: Client,
    ) -> None:
        request = ProtoOAAccountAuthReq()

        request.ctidTraderAccountId = account_id

        request.accessToken = settings.ctrader_access_token

        deferred = connected_client.send(
            request,
            clientMsgId="account-auth",
            responseTimeoutInSeconds=(AUTH_TIMEOUT_SECONDS),
        )

        deferred.addErrback(on_request_error)

        print("Account authentication request sent")

    def send_symbol_by_id_request(
        connected_client: Client,
    ) -> None:
        request = ProtoOASymbolByIdReq()

        request.ctidTraderAccountId = account_id

        request.symbolId.append(TARGET_SYMBOL_ID)

        deferred = connected_client.send(
            request,
            clientMsgId="symbol-by-id",
            responseTimeoutInSeconds=(MARKET_DATA_TIMEOUT_SECONDS),
        )

        deferred.addErrback(on_request_error)

        print("Symbol metadata request sent")
        print(
            "Symbol:",
            TARGET_SYMBOL,
        )
        print(
            "Symbol ID:",
            TARGET_SYMBOL_ID,
        )

    def send_trendbars_request(
        connected_client: Client,
    ) -> None:
        now = datetime.now(UTC)

        start = now - timedelta(days=LOOKBACK_DAYS)

        request = ProtoOAGetTrendbarsReq()

        request.ctidTraderAccountId = account_id

        request.symbolId = TARGET_SYMBOL_ID

        request.period = ProtoOATrendbarPeriod.Value(TARGET_PERIOD)

        request.fromTimestamp = int(start.timestamp() * 1000)

        request.toTimestamp = int(now.timestamp() * 1000)

        request.count = TREND_BAR_COUNT

        print()
        print("Requesting historical trendbars")

        print(
            "Symbol:",
            TARGET_SYMBOL,
        )

        print(
            "Symbol ID:",
            TARGET_SYMBOL_ID,
        )

        print(
            "Period:",
            TARGET_PERIOD,
        )

        print(
            "Count:",
            TREND_BAR_COUNT,
        )

        print(
            "From:",
            start.isoformat(),
        )

        print(
            "To:",
            now.isoformat(),
        )

        deferred = connected_client.send(
            request,
            clientMsgId="trendbars",
            responseTimeoutInSeconds=(MARKET_DATA_TIMEOUT_SECONDS),
        )

        deferred.addErrback(on_request_error)

        print("Trendbars request sent")

    def handle_symbol_metadata(
        connected_client: Client,
        response: ProtoOASymbolByIdRes,
    ) -> None:
        nonlocal symbol_digits
        nonlocal pip_position

        symbols = list(response.symbol)

        if not symbols:
            print("No symbol metadata returned")

            schedule_shutdown()
            return

        symbol = symbols[0]

        symbol_digits = int(symbol.digits)

        pip_position = int(symbol.pipPosition)

        print()
        print("Symbol metadata received")

        print(
            "Symbol ID:",
            symbol.symbolId,
        )

        print(
            "Digits:",
            symbol_digits,
        )

        print(
            "Pip position:",
            pip_position,
        )

        reactor.callLater(
            0,
            send_trendbars_request,
            connected_client,
        )

    def handle_trendbars(
        response: ProtoOAGetTrendbarsRes,
    ) -> None:
        trendbars = sorted(
            response.trendbar,
            key=lambda bar: bar.utcTimestampInMinutes,
        )

        print()
        print(
            "Trendbars received:",
            len(trendbars),
        )

        if not trendbars:
            print("No trendbars returned")

            schedule_shutdown()
            return

        print()
        print(f"{TARGET_SYMBOL} {TARGET_PERIOD} candles")

        print()

        for bar in trendbars:
            low_raw = int(bar.low)

            open_raw = low_raw + int(bar.deltaOpen)

            high_raw = low_raw + int(bar.deltaHigh)

            close_raw = low_raw + int(bar.deltaClose)

            opened_at = datetime.fromtimestamp(
                int(bar.utcTimestampInMinutes) * 60,
                tz=UTC,
            )

            open_price = relative_price_to_decimal(open_raw)

            high_price = relative_price_to_decimal(high_raw)

            low_price = relative_price_to_decimal(low_raw)

            close_price = relative_price_to_decimal(close_raw)

            volume = int(bar.volume)

            print(
                opened_at.isoformat(),
                "| O:",
                open_price,
                "| H:",
                high_price,
                "| L:",
                low_price,
                "| C:",
                close_price,
                "| Volume:",
                volume,
            )

        print()

        print(
            "Has more:",
            bool(
                getattr(
                    response,
                    "hasMore",
                    False,
                )
            ),
        )

        schedule_shutdown()

    def on_message_received(
        connected_client: Client,
        message: Any,
    ) -> None:
        if shutdown_started:
            return

        try:
            response = Protobuf.extract(message)

            # SDK خودش Heartbeat را پاسخ می‌دهد.
            # ما فقط از نمایش آن صرف‌نظر می‌کنیم.
            if isinstance(
                response,
                ProtoHeartbeatEvent,
            ):
                return

            print()
            print(
                "Received message:",
                type(response).__name__,
            )

            if isinstance(
                response,
                ProtoOAApplicationAuthRes,
            ):
                print("Application authentication successful")

                reactor.callLater(
                    0,
                    send_account_auth,
                    connected_client,
                )

                return

            if isinstance(
                response,
                ProtoOAAccountAuthRes,
            ):
                print("Account authentication successful")

                reactor.callLater(
                    0,
                    send_symbol_by_id_request,
                    connected_client,
                )

                return

            if isinstance(
                response,
                ProtoOASymbolByIdRes,
            ):
                handle_symbol_metadata(
                    connected_client,
                    response,
                )

                return

            if isinstance(
                response,
                ProtoOAGetTrendbarsRes,
            ):
                handle_trendbars(response)

                return

            if isinstance(
                response,
                ProtoOAErrorRes,
            ):
                print("cTrader returned an error")

                print(
                    "Error code:",
                    response.errorCode,
                )

                print(
                    "Description:",
                    response.description or "(no description)",
                )

                schedule_shutdown()
                return

            print(
                "Unhandled message:",
                type(response).__name__,
            )

        except Exception:
            print()
            print("The message handler crashed")

            traceback.print_exc()

            schedule_shutdown()

    def on_connected(
        connected_client: Client,
    ) -> None:
        try:
            print(f"Connected to {host}")

            send_application_auth(connected_client)

        except Exception:
            print("The connected callback crashed")

            traceback.print_exc()

            schedule_shutdown()

    def on_disconnected(
        disconnected_client: Client,
        reason: Any,
    ) -> None:
        del disconnected_client

        if shutdown_started:
            print("Disconnected from cTrader")

            stop_reactor()
            return

        print()
        print("Unexpected disconnection from cTrader")

        print(
            "Reason:",
            reason,
        )

        stop_reactor()

    client.setConnectedCallback(on_connected)

    client.setDisconnectedCallback(on_disconnected)

    client.setMessageReceivedCallback(on_message_received)

    client.startService()

    reactor.run()


if __name__ == "__main__":
    main()
