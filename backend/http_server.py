import logging

import messages
import zmq
import zmq.asyncio
from constants import CLIENTS_URL
from quart import Quart, redirect, request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def open_connection():
    context = zmq.asyncio.Context.instance()
    backend = context.socket(zmq.DEALER)
    backend.connect(CLIENTS_URL)
    return backend


app = Quart(__name__)


@app.route("/api/create_lobby", methods=["POST"])
async def create_lobby():
    logger.info(request)

    backend = open_connection()
    backend.send(messages.dump_bytes({"type": "create_lobby"}))
    response: bytes = await backend.recv()  # type: ignore
    message = messages.load(response)

    if message is None or message["type"] != "created_lobby":
        logger.warning("Create lobby got bad response: %s", response)
        return "Failed to create lobby", 500

    lobby_id = message["lobby_id"]
    password = message["password"]

    return redirect(f"../lobby/{lobby_id}?admin={password}")


@app.route("/api/start_round", methods=["POST"])
async def start_round():
    args = await request.form

    lobby_id = args.get("lobby_id")
    if lobby_id is None:
        return "Missing lobby_id", 400
    try:
        lobby_id = int(lobby_id)
    except ValueError:
        return "Invalid lobby id", 400

    password = args.get("password")
    if password is None:
        return "Missing password", 400

    level_id = args.get("level_id")
    if level_id is None:
        return "Missing level_id", 400
    try:
        level_id = int(level_id)
    except ValueError:
        return "Invalid level_id", 400

    mode = args.get("mode", "")
    if mode not in ("any", "ss"):
        return "Invalid mode", 400

    backend = open_connection()
    backend.send(
        messages.dump_bytes(
            {
                "type": "start_round",
                "lobby_id": lobby_id,
                "password": password,
                "level_id": level_id,
                "mode": mode,
            }
        )
    )

    return ""


if __name__ == "__main__":
    app.run(port=8001)
