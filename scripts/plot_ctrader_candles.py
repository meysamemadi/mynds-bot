from __future__ import annotations

import traceback
import webbrowser
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ctrader_open_api import Client, EndPoints, Protobuf, TcpProtocol
from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import ProtoHeartbeatEvent
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
from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOATrendbarPeriod
from twisted.internet import reactor
from twisted.python.failure import Failure

from nds_bot.config import load_settings
from nds_bot.domain.market.candle import Candle
from nds_bot.domain.market.timeframe import Timeframe
from nds_bot.domain.market.z import (
    DEFAULT_Z_REFERENCE_LOOKBACK_BARS,
    ZAnchor,
    find_bull_z_anchor,
)
from nds_bot.infrastructure.market_data.ctrader.trendbar_mapper import (
    CTraderTrendbar,
    map_trendbar_to_candle,
)
from nds_bot.infrastructure.visualization.plotly_candles import (
    write_switchable_candlestick_chart,
)

AUTH_TIMEOUT_SECONDS = 20
MARKET_DATA_TIMEOUT_SECONDS = 60
HISTORICAL_CHUNK_SIZE = 1000
HISTORICAL_REQUEST_DELAY_SECONDS = 0.25
Z_REFERENCE_LOOKBACK_BARS = DEFAULT_Z_REFERENCE_LOOKBACK_BARS

TIMEFRAMES = (
    Timeframe.M1,
    Timeframe.M3,
    Timeframe.M15,
    Timeframe.H1,
)

LOOKBACK_DAYS = {
    Timeframe.M1: 7,
    Timeframe.M3: 14,
    Timeframe.M15: 30,
    Timeframe.H1: 60,
}


@dataclass(frozen=True, slots=True)
class ChartInstrument:
    symbol: str
    symbol_id: int


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

    if settings.ctrader_gold_symbol_id is None:
        raise RuntimeError(
            "CTRADER_GOLD_SYMBOL_ID is not configured. "
            "Run scripts/discover_ctrader_chart_symbols.py first."
        )

    if settings.ctrader_dow_symbol_id is None:
        raise RuntimeError(
            "CTRADER_DOW_SYMBOL_ID is not configured. "
            "Run scripts/discover_ctrader_chart_symbols.py first."
        )

    instruments = (
        ChartInstrument(
            symbol="GOLD",
            symbol_id=settings.ctrader_gold_symbol_id,
        ),
        ChartInstrument(
            symbol="DOW",
            symbol_id=settings.ctrader_dow_symbol_id,
        ),
    )

    target_candle_count = settings.ctrader_history_candle_count
    account_id = settings.ctrader_account_id
    host = select_host(settings.ctrader_environment)

    client = Client(
        host,
        EndPoints.PROTOBUF_PORT,
        TcpProtocol,
    )

    pending_series = deque(
        (instrument, timeframe)
        for instrument in instruments
        for timeframe in TIMEFRAMES
    )

    series: dict[tuple[str, Timeframe], list[Candle]] = {}
    symbol_digits: dict[int, int] = {}
    active_request: tuple[ChartInstrument, Timeframe] | None = None
    active_to_timestamp_ms: int | None = None
    shutdown_started = False

    def stop_reactor() -> None:
        if reactor.running:
            reactor.stop()

    def shutdown() -> None:
        nonlocal shutdown_started

        if shutdown_started:
            return

        shutdown_started = True
        print("Closing cTrader connection...")
        client.stopService()
        reactor.callLater(0.5, stop_reactor)

    def schedule_shutdown() -> None:
        reactor.callLater(0, shutdown)

    def on_request_error(failure: Failure) -> None:
        if shutdown_started:
            return

        print("Request failed")
        print("Error type:", type(failure.value).__name__)
        print("Error message:", failure.getErrorMessage())
        schedule_shutdown()

    def send_application_auth(connected_client: Client) -> None:
        request = ProtoOAApplicationAuthReq()
        request.clientId = settings.ctrader_client_id
        request.clientSecret = settings.ctrader_client_secret

        deferred = connected_client.send(
            request,
            clientMsgId="application-auth",
            responseTimeoutInSeconds=AUTH_TIMEOUT_SECONDS,
        )
        deferred.addErrback(on_request_error)

        print("Application authentication request sent")

    def send_account_auth(connected_client: Client) -> None:
        request = ProtoOAAccountAuthReq()
        request.ctidTraderAccountId = account_id
        request.accessToken = settings.ctrader_access_token

        deferred = connected_client.send(
            request,
            clientMsgId="account-auth",
            responseTimeoutInSeconds=AUTH_TIMEOUT_SECONDS,
        )
        deferred.addErrback(on_request_error)

        print("Account authentication request sent")

    def send_symbol_metadata_request(connected_client: Client) -> None:
        request = ProtoOASymbolByIdReq()
        request.ctidTraderAccountId = account_id
        request.symbolId.extend(instrument.symbol_id for instrument in instruments)

        deferred = connected_client.send(
            request,
            clientMsgId="symbol-metadata",
            responseTimeoutInSeconds=MARKET_DATA_TIMEOUT_SECONDS,
        )
        deferred.addErrback(on_request_error)

        print("Symbol metadata request sent for GOLD and DOW")

    def finish_active_series(
        connected_client: Client,
        *,
        history_exhausted: bool = False,
    ) -> None:
        nonlocal active_request
        nonlocal active_to_timestamp_ms

        if active_request is None:
            raise RuntimeError("No active historical series to finish")

        instrument, timeframe = active_request
        key = (instrument.symbol, timeframe)
        candles = series[key]

        if not candles:
            raise RuntimeError(
                f"No trendbars returned for {instrument.symbol} {timeframe.value}"
            )

        suffix = " (history exhausted)" if history_exhausted else ""
        print(
            f"Series ready: {instrument.symbol} {timeframe.value} "
            f"({len(candles)} candles){suffix}"
        )

        active_request = None
        active_to_timestamp_ms = None

        reactor.callLater(
            HISTORICAL_REQUEST_DELAY_SECONDS,
            send_next_trendbars_request,
            connected_client,
        )

    def send_next_trendbars_request(connected_client: Client) -> None:
        nonlocal active_request
        nonlocal active_to_timestamp_ms

        if active_request is None:
            if not pending_series:
                schedule_shutdown()
                return

            active_request = pending_series.popleft()
            active_to_timestamp_ms = int(datetime.now(UTC).timestamp() * 1000)

            instrument, timeframe = active_request
            series[(instrument.symbol, timeframe)] = []

            print()
            print(
                f"Loading {instrument.symbol} {timeframe.value}: "
                f"target={target_candle_count} candles"
            )

        if active_to_timestamp_ms is None:
            raise RuntimeError("Historical cursor is not initialized")

        instrument, timeframe = active_request
        key = (instrument.symbol, timeframe)
        current_candles = series[key]
        remaining = target_candle_count - len(current_candles)

        if remaining <= 0:
            finish_active_series(connected_client)
            return

        request_count = min(HISTORICAL_CHUNK_SIZE, remaining)
        to_time = datetime.fromtimestamp(
            active_to_timestamp_ms / 1000,
            tz=UTC,
        )
        from_time = to_time - timedelta(days=LOOKBACK_DAYS[timeframe])

        request = ProtoOAGetTrendbarsReq()
        request.ctidTraderAccountId = account_id
        request.symbolId = instrument.symbol_id
        request.period = ProtoOATrendbarPeriod.Value(timeframe.value)
        request.fromTimestamp = int(from_time.timestamp() * 1000)
        request.toTimestamp = active_to_timestamp_ms
        request.count = request_count

        deferred = connected_client.send(
            request,
            clientMsgId=(
                f"trendbars-{instrument.symbol}-{timeframe.value}-"
                f"{len(current_candles)}"
            ),
            responseTimeoutInSeconds=MARKET_DATA_TIMEOUT_SECONDS,
        )
        deferred.addErrback(on_request_error)

        print(
            f"Historical chunk sent: {instrument.symbol} {timeframe.value} "
            f"need={request_count} already={len(current_candles)}"
        )

    def handle_symbol_metadata(
        connected_client: Client,
        response: ProtoOASymbolByIdRes,
    ) -> None:
        for symbol in response.symbol:
            symbol_digits[int(symbol.symbolId)] = int(symbol.digits)

        missing_ids = [
            instrument.symbol_id
            for instrument in instruments
            if instrument.symbol_id not in symbol_digits
        ]

        if missing_ids:
            raise RuntimeError(f"No metadata returned for symbol IDs: {missing_ids}")

        for instrument in instruments:
            print(
                f"Metadata ready: {instrument.symbol} "
                f"id={instrument.symbol_id} digits={symbol_digits[instrument.symbol_id]}"
            )

        reactor.callLater(0, send_next_trendbars_request, connected_client)

    def handle_trendbars(
        connected_client: Client,
        response: ProtoOAGetTrendbarsRes,
    ) -> None:
        nonlocal active_to_timestamp_ms

        if active_request is None:
            raise RuntimeError("Received trendbars without an active request")

        instrument, timeframe = active_request
        key = (instrument.symbol, timeframe)
        digits = symbol_digits[instrument.symbol_id]

        trendbars = sorted(
            response.trendbar,
            key=lambda bar: bar.utcTimestampInMinutes,
        )

        if not trendbars:
            finish_active_series(
                connected_client,
                history_exhausted=True,
            )
            return

        chunk_candles = [
            map_trendbar_to_candle(
                trendbar=CTraderTrendbar(
                    low=int(bar.low),
                    delta_open=int(bar.deltaOpen),
                    delta_high=int(bar.deltaHigh),
                    delta_close=int(bar.deltaClose),
                    volume=int(bar.volume),
                    utc_timestamp_in_minutes=int(bar.utcTimestampInMinutes),
                ),
                symbol=instrument.symbol,
                timeframe=timeframe,
                digits=digits,
            )
            for bar in trendbars
        ]

        candles_by_time = {
            candle.opened_at: candle
            for candle in series[key]
        }
        candles_by_time.update(
            {candle.opened_at: candle for candle in chunk_candles}
        )

        series[key] = sorted(
            candles_by_time.values(),
            key=lambda candle: candle.opened_at,
        )[-target_candle_count:]

        earliest_timestamp_minutes = min(
            int(bar.utcTimestampInMinutes)
            for bar in trendbars
        )
        active_to_timestamp_ms = earliest_timestamp_minutes * 60_000 - 1

        print(
            f"Historical chunk received: {instrument.symbol} {timeframe.value} "
            f"chunk={len(chunk_candles)} total={len(series[key])}"
        )

        if len(series[key]) >= target_candle_count:
            finish_active_series(connected_client)
            return

        if active_to_timestamp_ms <= 0:
            finish_active_series(
                connected_client,
                history_exhausted=True,
            )
            return

        reactor.callLater(
            HISTORICAL_REQUEST_DELAY_SECONDS,
            send_next_trendbars_request,
            connected_client,
        )

    def on_message_received(connected_client: Client, message: Any) -> None:
        if shutdown_started:
            return

        try:
            response = Protobuf.extract(message)

            if isinstance(response, ProtoHeartbeatEvent):
                return

            if isinstance(response, ProtoOAApplicationAuthRes):
                print("Application authentication successful")
                reactor.callLater(0, send_account_auth, connected_client)
                return

            if isinstance(response, ProtoOAAccountAuthRes):
                print("Account authentication successful")
                reactor.callLater(0, send_symbol_metadata_request, connected_client)
                return

            if isinstance(response, ProtoOASymbolByIdRes):
                handle_symbol_metadata(connected_client, response)
                return

            if isinstance(response, ProtoOAGetTrendbarsRes):
                handle_trendbars(connected_client, response)
                return

            if isinstance(response, ProtoOAErrorRes):
                print("cTrader returned an error")
                print("Error code:", response.errorCode)
                print("Description:", response.description or "(no description)")
                schedule_shutdown()
                return

            print("Unhandled message:", type(response).__name__)

        except Exception:
            print("The message handler crashed")
            traceback.print_exc()
            schedule_shutdown()

    def on_connected(connected_client: Client) -> None:
        try:
            print(f"Connected to {host}")
            send_application_auth(connected_client)
        except Exception:
            print("The connected callback crashed")
            traceback.print_exc()
            schedule_shutdown()

    def on_disconnected(disconnected_client: Client, reason: Any) -> None:
        del disconnected_client

        if shutdown_started:
            print("Disconnected from cTrader")
            stop_reactor()
            return

        print("Unexpected disconnection from cTrader")
        print("Reason:", reason)
        stop_reactor()

    client.setConnectedCallback(on_connected)
    client.setDisconnectedCallback(on_disconnected)
    client.setMessageReceivedCallback(on_message_received)

    client.startService()
    reactor.run()

    expected_series_count = len(instruments) * len(TIMEFRAMES)

    if len(series) != expected_series_count:
        raise RuntimeError(
            f"Expected {expected_series_count} chart series, received {len(series)}"
        )

    z_anchors: dict[tuple[str, Timeframe], ZAnchor] = {}
    calculation_time = datetime.now(UTC)

    print()
    print(
        "Calculating Bull Z anchors with NodeCounterv2 contract: "
        f"reference_lookback={Z_REFERENCE_LOOKBACK_BARS}"
    )

    for key, candles in series.items():
        symbol, timeframe = key
        closed_candles = [
            candle
            for candle in candles
            if candle.closed_at <= calculation_time
        ]

        z_anchor = find_bull_z_anchor(
            closed_candles,
            reference_lookback=Z_REFERENCE_LOOKBACK_BARS,
        )

        if z_anchor is None:
            print(f"Z not found: {symbol} {timeframe.value}")
            continue

        z_anchors[key] = z_anchor
        mode = "ATH" if z_anchor.all_time_high_mode else "BOUNDED"
        boundary = (
            "none"
            if z_anchor.left_boundary_index is None
            else str(z_anchor.left_boundary_index)
        )
        print(
            f"Z ready: {symbol} {timeframe.value} "
            f"time={z_anchor.time.isoformat()} price={z_anchor.price} "
            f"reference_high={z_anchor.reference_high} "
            f"boundary={boundary} mode={mode}"
        )

    chart_path = write_switchable_candlestick_chart(
        series,
        output_path=Path("artifacts/ctrader_candles.html"),
        initial_symbol="GOLD",
        initial_timeframe=Timeframe.M1,
        z_anchors=z_anchors,
    )

    resolved_path = chart_path.resolve()
    print(f"Chart written to: {resolved_path}")
    webbrowser.open(resolved_path.as_uri())


if __name__ == "__main__":
    main()
