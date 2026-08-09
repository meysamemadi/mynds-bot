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
    ProtoOAGetAccountListByAccessTokenReq,
    ProtoOAGetAccountListByAccessTokenRes,
)
from twisted.internet import reactor
from twisted.python.failure import Failure

from nds_bot.config import load_settings

REQUEST_TIMEOUT_SECONDS = 15


def select_host(environment: str) -> str:
    if environment == "demo":
        return EndPoints.PROTOBUF_DEMO_HOST

    if environment == "live":
        return EndPoints.PROTOBUF_LIVE_HOST

    raise ValueError("CTRADER_ENVIRONMENT must be either 'demo' or 'live'")


def main() -> None:
    settings = load_settings()

    if not settings.ctrader_access_token:
        raise RuntimeError("CTRADER_ACCESS_TOKEN is not configured in the .env file")

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

        # به Callback قطع اتصال فرصت اجرا می‌دهیم.
        reactor.callLater(0.5, stop_reactor)

    def schedule_shutdown() -> None:
        reactor.callLater(0, shutdown)

    def on_request_error(failure: Failure) -> None:
        print("Request failed")
        print("Error type:", type(failure.value).__name__)
        print("Error message:", failure.getErrorMessage())

        schedule_shutdown()

    def send_application_auth(
        connected_client: Client,
    ) -> None:
        request = ProtoOAApplicationAuthReq()
        request.clientId = settings.ctrader_client_id
        request.clientSecret = settings.ctrader_client_secret

        print(
            "Application request initialized:",
            request.IsInitialized(),
        )
        print(
            "Application request missing fields:",
            list(request.FindInitializationErrors()),
        )

        deferred = connected_client.send(
            request,
            clientMsgId="application-auth",
            responseTimeoutInSeconds=REQUEST_TIMEOUT_SECONDS,
        )
        deferred.addErrback(on_request_error)

        print("Application authentication request sent")

    def send_account_list_request(
        connected_client: Client,
    ) -> None:
        request = ProtoOAGetAccountListByAccessTokenReq()
        request.accessToken = settings.ctrader_access_token

        print(
            "Account list request initialized:",
            request.IsInitialized(),
        )
        print(
            "Account list request missing fields:",
            list(request.FindInitializationErrors()),
        )

        deferred = connected_client.send(
            request,
            clientMsgId="account-list",
            responseTimeoutInSeconds=REQUEST_TIMEOUT_SECONDS,
        )
        deferred.addErrback(on_request_error)

        print("Account list request sent")

    def send_account_auth_request(
        connected_client: Client,
        account_id: int,
    ) -> None:
        request = ProtoOAAccountAuthReq()
        request.ctidTraderAccountId = account_id
        request.accessToken = settings.ctrader_access_token

        print(
            "Account auth request initialized:",
            request.IsInitialized(),
        )
        print(
            "Account auth request missing fields:",
            list(request.FindInitializationErrors()),
        )

        deferred = connected_client.send(
            request,
            clientMsgId="account-auth",
            responseTimeoutInSeconds=REQUEST_TIMEOUT_SECONDS,
        )
        deferred.addErrback(on_request_error)

        print(
            "Account authentication request sent for account:",
            account_id,
        )

    def handle_account_list(
        connected_client: Client,
        response: ProtoOAGetAccountListByAccessTokenRes,
    ) -> None:
        accounts = list(response.ctidTraderAccount)

        print("Authorized accounts received:", len(accounts))

        if not accounts:
            print("No trading account is authorized for this access token")
            schedule_shutdown()
            return

        expected_is_live = settings.ctrader_environment == "live"

        matching_accounts = [
            account for account in accounts if bool(account.isLive) == expected_is_live
        ]

        print()
        print("Authorized account list:")

        for account in accounts:
            environment = "live" if account.isLive else "demo"

            broker = (
                getattr(
                    account,
                    "brokerTitleShort",
                    None,
                )
                or "(not available)"
            )

            trader_login = (
                getattr(
                    account,
                    "traderLogin",
                    None,
                )
                or "(not provided)"
            )

            print(
                "- account_id:",
                account.ctidTraderAccountId,
                "| trader_login:",
                trader_login,
                "| broker:",
                broker,
                "| environment:",
                environment,
            )

        print()

        if not matching_accounts:
            print(
                "No account matches CTRADER_ENVIRONMENT:",
                settings.ctrader_environment,
            )
            schedule_shutdown()
            return

        selected_account: Any | None = None

        if settings.ctrader_account_id is not None:
            selected_account = next(
                (
                    account
                    for account in matching_accounts
                    if int(account.ctidTraderAccountId) == settings.ctrader_account_id
                ),
                None,
            )

            if selected_account is None:
                print(
                    "CTRADER_ACCOUNT_ID was not found among "
                    "the authorized accounts for the selected "
                    "environment"
                )
                schedule_shutdown()
                return

        elif len(matching_accounts) == 1:
            selected_account = matching_accounts[0]

            print("One matching account found; selecting it automatically")

        else:
            print("More than one account matches the selected environment")
            print("Set the desired account ID in .env:")
            print("CTRADER_ACCOUNT_ID=<account_id>")
            schedule_shutdown()
            return

        selected_account_id = int(selected_account.ctidTraderAccountId)

        print(
            "Selected account:",
            selected_account_id,
        )

        reactor.callLater(
            0,
            send_account_auth_request,
            connected_client,
            selected_account_id,
        )

    def on_message_received(
        connected_client: Client,
        message: Any,
    ) -> None:
        try:
            payload_type = message.payloadType

            print()
            print(
                "Envelope received:",
                f"payload_type={payload_type}",
                f"client_msg_id={message.clientMsgId!r}",
            )

            if payload_type == ProtoOAApplicationAuthRes().payloadType:
                response = Protobuf.extract(message)

                print(
                    "Received message:",
                    type(response).__name__,
                )
                print("Application authentication successful")

                reactor.callLater(
                    0,
                    send_account_list_request,
                    connected_client,
                )
                return

            if payload_type == ProtoOAGetAccountListByAccessTokenRes().payloadType:
                response = Protobuf.extract(message)

                print(
                    "Received message:",
                    type(response).__name__,
                )

                handle_account_list(
                    connected_client,
                    response,
                )
                return

            if payload_type == ProtoOAAccountAuthRes().payloadType:
                response = Protobuf.extract(message)

                print(
                    "Received message:",
                    type(response).__name__,
                )
                print("Account authentication successful")
                print(
                    "Authenticated account:",
                    response.ctidTraderAccountId,
                )

                schedule_shutdown()
                return

            if payload_type == ProtoOAErrorRes().payloadType:
                response = Protobuf.extract(message)

                print(
                    "Received message:",
                    type(response).__name__,
                )
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

            response = Protobuf.extract(message)

            print(
                "Unhandled message:",
                type(response).__name__,
            )
            print(response)

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
            "Reason type:",
            type(reason).__name__,
        )
        print("Reason:", reason)

        stop_reactor()

    client.setConnectedCallback(on_connected)
    client.setDisconnectedCallback(on_disconnected)
    client.setMessageReceivedCallback(on_message_received)

    client.startService()
    reactor.run()


if __name__ == "__main__":
    main()
