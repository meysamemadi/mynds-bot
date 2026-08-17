from __future__ import annotations

import traceback
from typing import Any

from ctrader_open_api import Client, EndPoints, Protobuf, TcpProtocol
from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import ProtoHeartbeatEvent
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOAAccountAuthReq,
    ProtoOAAccountAuthRes,
    ProtoOAApplicationAuthReq,
    ProtoOAApplicationAuthRes,
    ProtoOAErrorRes,
    ProtoOASymbolsListReq,
    ProtoOASymbolsListRes,
)
from twisted.internet import reactor
from twisted.python.failure import Failure

from nds_bot.config import load_settings

AUTH_TIMEOUT_SECONDS = 20
SYMBOLS_TIMEOUT_SECONDS = 180

GOLD_KEYWORDS = (
    "XAU",
    "GOLD",
)

DOW_KEYWORDS = (
    "US30",
    "DJ30",
    "DOW",
    "WALLSTREET",
    "WALLST",
)


def select_host(environment: str) -> str:
    if environment == "demo":
        return EndPoints.PROTOBUF_DEMO_HOST

    if environment == "live":
        return EndPoints.PROTOBUF_LIVE_HOST

    raise ValueError("CTRADER_ENVIRONMENT must be either 'demo' or 'live'")


def normalize(value: str) -> str:
    return "".join(character for character in value.upper() if character.isalnum())


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

    def send_symbols_list_request(connected_client: Client) -> None:
        request = ProtoOASymbolsListReq()
        request.ctidTraderAccountId = account_id
        request.includeArchivedSymbols = False

        deferred = connected_client.send(
            request,
            clientMsgId="symbols-list",
            responseTimeoutInSeconds=SYMBOLS_TIMEOUT_SECONDS,
        )
        deferred.addErrback(on_request_error)

        print("Symbols list request sent; this can take a while...")

    def print_candidates(response: ProtoOASymbolsListRes) -> None:
        gold_candidates: list[tuple[int, str, str]] = []
        dow_candidates: list[tuple[int, str, str]] = []

        for symbol in response.symbol:
            name = getattr(symbol, "symbolName", "") or ""
            description = getattr(symbol, "description", "") or ""
            searchable = normalize(f"{name} {description}")
            candidate = (int(symbol.symbolId), name, description)

            if any(keyword in searchable for keyword in GOLD_KEYWORDS):
                gold_candidates.append(candidate)

            if any(keyword in searchable for keyword in DOW_KEYWORDS):
                dow_candidates.append(candidate)

        print()
        print("GOLD candidates")
        print("---------------")
        _print_candidate_rows(gold_candidates)

        print()
        print("DOW candidates")
        print("--------------")
        _print_candidate_rows(dow_candidates)

        print()
        print("Put the selected IDs in .env:")
        print("CTRADER_GOLD_SYMBOL_ID=<id>")
        print("CTRADER_DOW_SYMBOL_ID=<id>")

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
                reactor.callLater(0, send_symbols_list_request, connected_client)
                return

            if isinstance(response, ProtoOASymbolsListRes):
                print(f"Symbols received: {len(response.symbol)}")
                print_candidates(response)
                schedule_shutdown()
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


def _print_candidate_rows(candidates: list[tuple[int, str, str]]) -> None:
    if not candidates:
        print("No candidates found")
        return

    for symbol_id, name, description in candidates:
        description_text = f" | {description}" if description else ""
        print(f"{symbol_id}: {name}{description_text}")


if __name__ == "__main__":
    main()
