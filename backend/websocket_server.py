import asyncio
import logging
from urllib.parse import parse_qs, urlparse

import websockets
import zmq
import zmq.asyncio
from websockets.exceptions import ConnectionClosedError

import messages
from constants import CLIENTS_URL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def handle(websocket):
    try:
        params = parse_qs(urlparse(websocket.path).query)
    except ValueError as error:
        logger.warning("Could not parse path: %s\n%s", websocket.path, error)
        return

    if "user" not in params:
        return

    user_id: str = params["user"][0]
    lobby_id: str | None = params.get("lobby", [None])[0]

    context = zmq.asyncio.Context.instance()
    backend = context.socket(zmq.DEALER)
    backend.connect(CLIENTS_URL)

    if lobby_id is None:
        logger.info("Sending Create(%s)", user_id)
        await backend.send(messages.Create(int(user_id)).to_bytes())
    else:
        logger.info("Sending Join(%s, %s)", user_id, lobby_id)
        await backend.send(messages.Join(int(user_id), int(lobby_id)).to_bytes())

    try:
        wait_closed = asyncio.create_task(websocket.wait_closed())
        while True:
            read_event = backend.recv()
            done, _ = await asyncio.wait([wait_closed, read_event], return_when=asyncio.FIRST_COMPLETED)
            if wait_closed in done:
                return
            assert read_event in done
            data: bytes = await read_event  # type: ignore
            logger.info("Recieved event: %s", data.decode())
            await websocket.send(data.decode())
    except ConnectionClosedError:
        pass
    finally:
        logger.info("Sending Leave()")
        backend.send(messages.Leave().to_bytes())


async def main():
    async with websockets.serve(handle, host="0.0.0.0", port=80):  # type: ignore
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
