import asyncio
import logging
from urllib.parse import parse_qs, urlparse

import messages
import websockets
import zmq
import zmq.asyncio
from constants import CLIENTS_URL
from websockets.exceptions import ConnectionClosedError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WebsocketHandler:
    @classmethod
    async def create(cls, websocket):
        await cls(websocket).run()

    def __init__(self, websocket):
        self.websocket = websocket

        context = zmq.asyncio.Context.instance()
        self.backend = context.socket(zmq.DEALER)
        self.backend.connect(CLIENTS_URL)

    async def run(self) -> None:
        try:
            params = parse_qs(urlparse(self.websocket.path).query)
        except ValueError as error:
            logger.warning("Could not parse path: %s\n%s", self.websocket.path, error)
            return

        lobby_id: int | None
        try:
            lobby_id = int(params["lobby"][0])
        except (ValueError, KeyError, IndexError):
            lobby_id = None

        if lobby_id is None:
            logger.info("Sending Create()")
            await self.backend.send(messages.dump_bytes({"type": "create"}))
        else:
            logger.info("Sending Join(%s)", lobby_id)
            await self.backend.send(
                messages.dump_bytes({"type": "join", "lobby_id": lobby_id})
            )

        try:
            wait_closed = asyncio.create_task(self.websocket.wait_closed())
            read_websocket = asyncio.create_task(self.websocket.recv())
            read_backend = self.backend.recv()
            pending = {wait_closed, read_websocket, read_backend}
            while True:
                done, pending = await asyncio.wait(
                    pending, return_when=asyncio.FIRST_COMPLETED
                )
                if wait_closed in done:
                    break

                if read_websocket in done:
                    await self.handle_websocket_event(await read_websocket)
                    read_websocket = asyncio.create_task(self.websocket.recv())
                    pending.add(read_websocket)

                if read_backend in done:
                    await self.handle_backend_event(await read_backend)  # type: ignore
                    read_backend = self.backend.recv()
                    pending.add(read_backend)

            for future in pending:
                future.cancel()
        except ConnectionClosedError:
            pass
        finally:
            logger.info("Sending Leave()")
            self.backend.send(messages.dump_bytes({"type": "leave"}))

    async def handle_websocket_event(self, data: bytes | str) -> None:
        message = messages.load(data)
        if message is None:
            logger.warning("Recieved invalid websocket event: %s", data)
            return

        logger.debug("Recieved websocket event: %s", message)
        if message["type"] == "ping":
            await self.websocket.send(messages.dump_str({"type": "pong"}))
        else:
            await self.backend.send(messages.dump_bytes(message))

    async def handle_backend_event(self, data: bytes) -> None:
        message = messages.load(data)
        if message is None:
            logger.warning("Recieved invalid backend event: %s", data)
            return

        logger.debug("Recieved backend event: %s", message)
        await self.websocket.send(messages.dump_str(message))


async def main() -> None:
    async with websockets.serve(WebsocketHandler.create, host="0.0.0.0", port=80):  # type: ignore
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
