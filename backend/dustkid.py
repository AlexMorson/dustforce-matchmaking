import asyncio
import logging

import zmq
import zmq.asyncio
from aiohttp import ClientSession, ClientTimeout
from constants import EVENTS_URL
from dustkid_schema import Event

logger = logging.getLogger("dustkid")

DUSTKID_URL = "http://dustkid.com/backend/events.php"
NO_TIMEOUT = ClientTimeout(total=None, connect=None, sock_read=None, sock_connect=None)

DEFAULT_BACKOFF_SECONDS = 1


async def dustkid_events(context: zmq.asyncio.Context) -> None:
    """Read events from dustkid and PUBlish them to a ZMQ socket."""

    socket = context.socket(zmq.PUB)
    socket.bind(EVENTS_URL)

    backoff_seconds = DEFAULT_BACKOFF_SECONDS

    while True:
        async with ClientSession(timeout=NO_TIMEOUT) as session:
            async with session.get(DUSTKID_URL) as response:
                buffer = b""
                async for chunk in response.content.iter_any():
                    if context.closed:
                        logger.info("Context closed, shutting down")
                        socket.close()
                        return

                    buffer += chunk
                    *events, buffer = buffer.split(b"\x1e")
                    for event in events:

                        if not event:
                            logger.debug("Got heartbeat")
                            continue
                        try:
                            parsed = Event.parse_raw(event)
                        except ValueError as error:
                            logger.warning(
                                "Could not parse event: %s\n%s", event, error
                            )
                            continue
                        logger.debug("Parsed event: %s", parsed)

                        try:
                            await socket.send(event)
                        except zmq.ContextTerminated:
                            logger.info("Context terminated, shutting down")
                            return

                    backoff_seconds = DEFAULT_BACKOFF_SECONDS

        logger.warning(
            "Dustkid event stream closed, trying again in %s seconds", backoff_seconds
        )
        await asyncio.sleep(backoff_seconds)
        backoff_seconds *= 2
