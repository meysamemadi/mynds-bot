from __future__ import annotations

import traceback
from typing import Any

from ctrader_open_api import Client, EndPoints, Protobuf, TcpProtocol
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOAAccountAuthReq,
    ProtoOAAccountAuthRes,
    ProtoOAApplicationAuthReq,
    ProtoOAApplicationAuthRes,
    ProtoOAErrorRes,
    ProtoOASymbolByIdReq,
    ProtoOASymbolByIdRes,
    ProtoOASymbolsListReq,
    ProtoOASymbolsListRes,
)
from twisted.internet import reactor
from twisted.python.failure import Failure

from nds_bot.config import load_settings

REQUEST_TIMEOUT_SECONDS = 15
TARGET_SYMBOL = "EURUSD"


def select_host(environment: str) -> str:
    if environment == "demo":
        return EndPoints.PROTOBUF_DEMO_HOST

    if environment == "live":
        return EndPoints.PROTOBUF_LIVE_HOST

    raise ValueError("CTRADER_ENVIRONMENT must be either 'demo' or 'live'")


def normalize_symbol_name(name: str) -> str:
    return (
        name.upper().replace("/", "").replace("-", "").replace("_", "").replace(" ", "")
    )


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

    def send_application_auth(
        connected_client: Client,
    ) -> None:
        request = ProtoOAApplicationAuthReq()
        request.clientId = settings.ctrader_client_id
        request.clientSecret = settings.ctrader_client_secret

        deferred = connected_client.send(
            request,
            clientMsgId="application-auth",
            responseTimeoutInSeconds=REQUEST_TIMEOUT_SECONDS,
        )
        deferred.addErrback(
            on_request_error,
        )

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
            responseTimeoutInSeconds=REQUEST_TIMEOUT_SECONDS,
        )
        deferred.addErrback(
            on_request_error,
        )

        print("Account authentication request sent")

    def send_symbols_list_request(
        connected_client: Client,
    ) -> None:
        request = ProtoOASymbolsListReq()
        request.ctidTraderAccountId = account_id
        request.includeArchivedSymbols = False

        deferred = connected_client.send(
            request,
            clientMsgId="symbols-list",
            responseTimeoutInSeconds=REQUEST_TIMEOUT_SECONDS,
        )
        deferred.addErrback(
            on_request_error,
        )

        print("Symbols list request sent")

    def send_symbol_by_id_request(
        connected_client: Client,
        symbol_id: int,
    ) -> None:
        request = ProtoOASymbolByIdReq()
        request.ctidTraderAccountId = account_id

        # symbolId یک repeated field است.
        request.symbolId.append(
            symbol_id,
        )

        deferred = connected_client.send(
            request,
            clientMsgId="symbol-by-id",
            responseTimeoutInSeconds=REQUEST_TIMEOUT_SECONDS,
        )
        deferred.addErrback(
            on_request_error,
        )

        print(
            "Full symbol request sent for symbol ID:",
            symbol_id,
        )

    def handle_symbols_list(
        connected_client: Client,
        response: ProtoOASymbolsListRes,
    ) -> None:
        symbols = list(response.symbol)

        print(
            "Symbols received:",
            len(symbols),
        )

        target = normalize_symbol_name(TARGET_SYMBOL)

        matching_symbol = next(
            (
                symbol
                for symbol in symbols
                if normalize_symbol_name(
                    getattr(
                        symbol,
                        "symbolName",
                        "",
                    )
                )
                == target
            ),
            None,
        )

        if matching_symbol is None:
            print(f"Symbol {TARGET_SYMBOL!r} was not found")

            print()
            print("First available symbols:")

            for symbol in symbols[:20]:
                print(
                    "-",
                    getattr(
                        symbol,
                        "symbolName",
                        "(unknown)",
                    ),
                    "| ID:",
                    symbol.symbolId,
                )

            schedule_shutdown()
            return

        symbol_id = int(matching_symbol.symbolId)

        symbol_name = getattr(
            matching_symbol,
            "symbolName",
            TARGET_SYMBOL,
        )

        print()
        print("Target symbol found")
        print(
            "Name:",
            symbol_name,
        )
        print(
            "Symbol ID:",
            symbol_id,
        )

        reactor.callLater(
            0,
            send_symbol_by_id_request,
            connected_client,
            symbol_id,
        )

    def handle_full_symbol(
        response: ProtoOASymbolByIdRes,
    ) -> None:
        symbols = list(response.symbol)

        if not symbols:
            print("Full symbol information was not returned")
            schedule_shutdown()
            return

        symbol = symbols[0]

        print()
        print("Full symbol information")
        print(
            "Symbol ID:",
            symbol.symbolId,
        )
        print(
            "Digits:",
            getattr(
                symbol,
                "digits",
                "(not available)",
            ),
        )
        print(
            "Pip position:",
            getattr(
                symbol,
                "pipPosition",
                "(not available)",
            ),
        )

        print()
        print("Available full-symbol fields:")
        print([field.name for field in symbol.DESCRIPTOR.fields])

        schedule_shutdown()

    def on_message_received(
        connected_client: Client,
        message: Any,
    ) -> None:
        try:
            response = Protobuf.extract(message)

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
                    send_symbols_list_request,
                    connected_client,
                )
                return

            if isinstance(
                response,
                ProtoOASymbolsListRes,
            ):
                handle_symbols_list(
                    connected_client,
                    response,
                )
                return

            if isinstance(
                response,
                ProtoOASymbolByIdRes,
            ):
                handle_full_symbol(response)
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

            send_application_auth(
                connected_client,
            )

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
