from ctrader_open_api import Client, EndPoints, Protobuf, TcpProtocol
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOAApplicationAuthReq,
    ProtoOAApplicationAuthRes,
    ProtoOAErrorRes,
)
from twisted.internet import reactor
from twisted.python.failure import Failure

from nds_bot.config import load_settings


def select_host(environment: str) -> str:
    if environment == "demo":
        return EndPoints.PROTOBUF_DEMO_HOST

    if environment == "live":
        return EndPoints.PROTOBUF_LIVE_HOST

    raise ValueError("CTRADER_ENVIRONMENT must be 'demo' or 'live'")


def main() -> None:
    settings = load_settings()
    host = select_host(settings.ctrader_environment)

    client = Client(
        host,
        EndPoints.PROTOBUF_PORT,
        TcpProtocol,
    )

    shutdown_started = False

    def shutdown() -> None:
        nonlocal shutdown_started

        if shutdown_started:
            return

        shutdown_started = True
        client.stopService()

        if reactor.running:
            reactor.stop()

    def schedule_shutdown() -> None:
        # اجازه می‌دهیم Callback فعلی کامل شود، سپس اتصال بسته شود.
        reactor.callLater(0, shutdown)

    def on_request_timeout(failure: Failure) -> None:
        print("No correlated response was received in time")
        print("Error type:", type(failure.value).__name__)
        print("Error message:", failure.getErrorMessage())
        schedule_shutdown()

    def on_message_received(
        connected_client: Client,
        message: object,
    ) -> None:
        del connected_client

        response = Protobuf.extract(message)

        print(
            "Received message:",
            type(response).__name__,
        )

        if isinstance(response, ProtoOAApplicationAuthRes):
            print("Application authentication successful")
            print(
                "Environment:",
                settings.ctrader_environment,
            )
            print("Host:", host)
            schedule_shutdown()
            return

        if isinstance(response, ProtoOAErrorRes):
            print("cTrader returned an error")
            print("Error code:", response.errorCode)
            print(
                "Description:",
                response.description or "(no description)",
            )
            schedule_shutdown()
            return

        print("Unexpected response:")
        print(response)

    def on_connected(connected_client: Client) -> None:
        print(f"Connected to {host}")

        request = ProtoOAApplicationAuthReq()
        request.clientId = settings.ctrader_client_id
        request.clientSecret = settings.ctrader_client_secret

        deferred = connected_client.send(
            request,
            responseTimeoutInSeconds=15,
        )
        deferred.addErrback(on_request_timeout)

        print("Application authentication request sent")

    def on_disconnected(
        disconnected_client: Client,
        reason: object,
    ) -> None:
        del disconnected_client

        if shutdown_started:
            print("Disconnected from cTrader")
            return

        print("Unexpected disconnection from cTrader")
        print(reason)

        if reactor.running:
            reactor.stop()

    client.setConnectedCallback(on_connected)
    client.setDisconnectedCallback(on_disconnected)
    client.setMessageReceivedCallback(on_message_received)

    client.startService()
    reactor.run()


if __name__ == "__main__":
    main()
