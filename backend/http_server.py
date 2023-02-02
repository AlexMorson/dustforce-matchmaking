import messages
import zmq
import zmq.asyncio
from constants import CLIENTS_URL
from quart import Quart, redirect

app = Quart(__name__)


@app.route("/api/create_lobby", methods=["POST"])
async def create_lobby():
    context = zmq.asyncio.Context.instance()
    backend = context.socket(zmq.DEALER)
    backend.connect(CLIENTS_URL)

    backend.send(messages.dump_bytes({"type": "create_lobby"}))
    response: bytes = await backend.recv()  # type: ignore
    message = messages.load(response)

    if message is None or message["type"] != "created_lobby":
        return "Failed to create lobby", 500

    lobby_id = message["lobby_id"]

    return redirect(f"../lobby/{lobby_id}")


if __name__ == "__main__":
    app.run(port=8001)
