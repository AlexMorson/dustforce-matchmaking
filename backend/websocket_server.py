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

        user_id: str | None = params.get("user", [None])[0]
        lobby_id: str | None = params.get("lobby", [None])[0]

        if user_id is None:
            return

        if lobby_id is None:
            logger.info("Sending Create(%s)", user_id)
            await self.backend.send(messages.to_bytes(messages.create(int(user_id))))
        else:
            logger.info("Sending Join(%s, %s)", user_id, lobby_id)
            await self.backend.send(
                messages.to_bytes(messages.join(int(user_id), int(lobby_id)))
            )

        try:
            wait_closed = asyncio.create_task(self.websocket.wait_closed())
            read_backend = self.backend.recv()
            pending = [wait_closed, read_backend]
            while True:
                done, pending = await asyncio.wait(
                    pending, return_when=asyncio.FIRST_COMPLETED
                )

                if wait_closed in done:
                    break

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
            self.backend.send(messages.to_bytes(messages.leave()))

    async def handle_backend_event(self, data: bytes) -> None:
        logger.debug("Recieved event: %s", data.decode())
        await self.websocket.send(data.decode())


async def main():
    async with websockets.serve(WebsocketHandler.create, host="0.0.0.0", port=80):  # type: ignore
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
