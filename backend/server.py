from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import string
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import messages
import pydantic
import zmq
import zmq.asyncio
from aiohttp import ClientSession
from constants import CLIENTS_URL, EVENTS_URL
from dustkid import dustkid_events
from dustkid_schema import Event, Leaderboard

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("server")

# How long until an empty lobby is deleted
EMPTY_LOBBY_TIMEOUT = timedelta(minutes=5)

MAX_LOBBY_COUNT = 100


async def get_level_filename(id: int) -> str | None:
    url = f"https://atlas.dustforce.com/gi/downloader.php?id={id}"
    async with ClientSession() as session, session.head(url) as response:
        content_disposition = response.headers.get("Content-Disposition")
        if content_disposition is None:
            return None

        m = re.search('filename="([^"]*)"', content_disposition)
        if m is None:
            return None

        return m.group(1)


@dataclass
class Level:
    filename: str

    @staticmethod
    async def from_id(level_id: int) -> Level | None:
        filename = await get_level_filename(level_id)
        if filename is None:
            return None
        return Level(filename)

    @property
    def id(self) -> int | None:
        parts = self.filename.rsplit("-", 1)
        if len(parts) != 2:
            # Stock maps do not have ids
            return None
        try:
            return int(parts[1])
        except ValueError:
            logger.error("Could not parse level id: filename=%s", self.filename)
            return None

    @property
    def name(self) -> str:
        return self.filename.rsplit("-", 1)[0].replace("-", " ")

    @property
    def image(self) -> str:
        return f"https://atlas.dustforce.com/gi/maps/{self.filename}.png"

    @property
    def install_play(self) -> str:
        parts = self.filename.rsplit("-", 1)
        if len(parts) != 2:
            # Stock maps do not have ids
            return f"dustforce://installPlay/0/{self.filename}"
        name, id = parts
        return f"dustforce://installPlay/{id}/{name}"

    @property
    def atlas(self) -> str | None:
        parts = self.filename.rsplit("-", 1)
        if len(parts) != 2:
            # Stock maps do not have ids
            return None
        name, id = parts
        return f"https://atlas.dustforce.com/{id}/{name}"

    @property
    def dustkid(self) -> str:
        return f"https://dustkid.com/level/{self.filename}"

    async def stats(self) -> LevelStats:
        url = f"https://dustkid.com/json/level/{self.filename}"
        async with ClientSession() as session, session.get(url) as response:
            data = await response.read()
            leaderboard = Leaderboard.parse_raw(data)

        ss_count = 0
        fastest_ss = None
        for score in leaderboard.scores.values():
            if score.score_completion != 5 or score.score_finesse != 5:
                continue

            ss_count += 1
            if fastest_ss is None or score.time < fastest_ss:
                fastest_ss = score.time

        return LevelStats(ss_count, fastest_ss)


@dataclass
class LevelStats:
    ss_count: int
    fastest_ss: int | None


async def random_level(
    max_level_id: int, min_ss_count: int = 5, max_fastest_ss: int = 45_000
) -> Level:
    while True:
        level_id = random.randint(100, max_level_id)
        logger.debug("Chose random level id %s", level_id)

        filename = await get_level_filename(level_id)
        if filename is None:
            logger.debug("Skipping level id %s because it has no filename", level_id)
            continue

        level = Level(filename)
        try:
            stats = await level.stats()
        except pydantic.ValidationError:
            logger.exception("Could not parse level data: filename=%s", filename)
            continue

        if (
            stats.ss_count < min_ss_count
            or stats.fastest_ss is None
            or stats.fastest_ss > max_fastest_ss
        ):
            logger.debug(
                "Skipping level %s because it is does not satisfy the constraints",
                filename,
            )
            continue

        return level


@dataclass(frozen=True)
class User:
    id: int
    name: str

    @staticmethod
    async def create(id: int) -> User | None:
        name = await User._fetch_name(id)
        if not name:
            return None
        return User(id, name)

    @staticmethod
    async def _fetch_name(id: int) -> str | None:
        if not (1 <= id <= 1_000_000):
            return None
        url = f"https://df.hitboxteam.com/backend6/userSearch.php?userid={id}"
        async with ClientSession() as session:
            async with session.get(url) as response:
                result = await response.json()
                if len(result) != 1 or "name" not in result[0]:
                    return None
                return result[0]["name"]


@dataclass
class Client:
    socket: zmq.asyncio.Socket
    identity: bytes
    user: User | None
    lobby: Lobby

    async def send(self, message: bytes) -> None:
        await self.socket.send_multipart([self.identity, message])

    async def login(self, user: User) -> None:
        self.user = user
        await self.lobby.on_login(self)

    async def logout(self) -> None:
        self.user = None
        await self.lobby.on_logout(self)


class BaseLobby(ABC):
    def __init__(self, id: int):
        logger.info("Lobby(%s) created", id)
        self.id = id

        self.closing: asyncio.Task | None = None
        self.on_close = asyncio.Event()

        self.clients: dict[bytes, Client] = {}
        self.round_end: datetime | None = None

        self._check_empty()

    @abstractmethod
    async def _run(self) -> None:
        ...

    @abstractmethod
    def _state(self) -> messages.State:
        ...

    async def send_state(self) -> None:
        """Send the current state to all connected clients."""
        if not self.clients:
            return
        message = json.dumps(self._state()).encode()
        await asyncio.wait(
            [
                asyncio.create_task(client.send(message))
                for client in self.clients.values()
            ]
        )

    def _check_empty(self) -> None:
        """If no clients remain, schedule the lobby to be closed."""
        if self.clients:
            return

        async def close():
            await asyncio.sleep(EMPTY_LOBBY_TIMEOUT.seconds)
            self.on_close.set()

        self.closing = asyncio.create_task(close())

    async def run(self) -> None:
        """Run the lobby, returning when the lobby should be closed."""
        actual_run = asyncio.create_task(self._run())
        on_close = asyncio.create_task(self.on_close.wait())
        _, pending = await asyncio.wait(
            [actual_run, on_close],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for future in pending:
            future.cancel()

    async def on_join(self, client: Client) -> None:
        """Handle a new client joining."""
        self.clients[client.identity] = client
        if self.closing:
            self.closing.cancel()
            self.closing = None
        await self.send_state()

    async def on_leave(self, client: Client) -> None:
        """Handle a client leaving."""
        self.clients.pop(client.identity)
        self._check_empty()
        await self.send_state()


class Lobby(BaseLobby):

    # Lobby id -> Lobby
    lobbies: dict[int, Lobby] = {}
    next_id: int = 0

    @staticmethod
    def create(id: int | None = None) -> Lobby | None:
        if len(Lobby.lobbies) >= MAX_LOBBY_COUNT:
            logger.warning(
                "Ignoring lobby create because there are %s existing lobbies",
                len(Lobby.lobbies),
            )
            return

        if id in Lobby.lobbies:
            logger.warning("Ignoring lobby create because lobby %s already exists", id)
            return None

        while id is None or id in Lobby.lobbies:
            id = Lobby.next_id
            Lobby.next_id += 1

        lobby = Lobby(id=id)
        Lobby.lobbies[id] = lobby

        async def run_lobby():
            """Run the new lobby, deleting it when it closes."""
            try:
                await lobby.run()
            finally:
                del Lobby.lobbies[id]

        asyncio.create_task(run_lobby())
        return lobby

    def __init__(self, id: int):
        super().__init__(id)

        self.password = "".join(
            random.choices(string.ascii_lowercase + string.digits, k=20)
        )

        self.condition = None

        self.warmup_time = timedelta(minutes=4)
        self.break_time = timedelta(seconds=15)
        self.round_time = timedelta(minutes=1)

        self.warmup_end = None
        self.break_end = None
        self.round_end = None

        # User id -> User
        self.users: dict[int, User] = {}
        self.allow_joining = True

        self.level: Level | None = None
        self.scores: dict[int, Score] = {}

        self.start_round = asyncio.Event()
        self.eliminated: set[int] = set()

    async def on_start_round(self, password: str, level_id: int, mode: str) -> None:
        if password != self.password:
            logger.warning("Wrong password! Not starting round")
            return

        new_level = None
        if self.level is not None and self.level.id == level_id:
            new_level = self.level
        else:
            new_level = await Level.from_id(level_id)
            if new_level is None:
                logger.warning(
                    "Could not find level with id: %s. Not starting round", level_id
                )
                return

        if self.start_round.is_set():
            logger.warning("A round is already in progress. Not starting round")
            return

        logger.info("Starting new round of level: %s", new_level.filename)
        if mode == "any":
            self.condition = lambda _: True
        elif mode == "ss":
            self.condition = (
                lambda event: event.score_completion == 5 and event.score_finesse == 5
            )
        self.level = new_level
        self.start_round.set()

    async def on_login(self, client: Client) -> None:
        assert client.user is not None

        if self.allow_joining:
            user = client.user
            self.users[user.id] = user
            await self.send_state()

    async def on_logout(self, client: Client) -> None:
        pass

    async def on_dustkid_event(self, event: Event) -> None:
        """Update scores and send state if this is a new best."""
        if self.level is None or event.level != self.level.filename:
            return

        if self.condition is None or not self.condition(event):
            return

        event_time = datetime.fromtimestamp(event.timestamp, timezone.utc)
        if (
            self.round_end is None
            or event_time < self.round_end - self.round_time
            or event_time > self.round_end
        ):
            return

        old_score = self.scores.get(event.user)
        new_score = Score.from_dustkid_event(event)
        if old_score is None or old_score.timestamp > new_score.timestamp:
            logger.info("Lobby(%s) User %s PB'd: %s", self.id, event.user, new_score)
            self.scores[event.user] = new_score
            await self.send_state()

    @property
    def remaining(self):
        return set(self.users) - self.eliminated

    async def _run(self) -> None:
        while True:
            # Wait for the signal to start
            await self.start_round.wait()
            self.allow_joining = False

            await self._run_game()

            # Reset for a new level
            await self.send_state()
            self.start_round.clear()
            self.allow_joining = True

    async def _run_game(self) -> None:
        # Warmup time
        self.warmup_end = datetime.now(timezone.utc) + self.warmup_time
        asyncio.create_task(self.send_state())
        logger.info("Warmup starting")
        await asyncio.sleep(self.warmup_time.seconds)
        logger.info("Warmup ended")
        self.warmup_end = None

        # Do rounds until one player remains
        while len(self.remaining) > 1:
            logger.info("Remaining users: %s", self.remaining)
            # Give the client both to eliminate any delay when the round starts
            self.break_end = datetime.now(timezone.utc) + self.break_time
            self.round_end = self.break_end + self.round_time

            asyncio.create_task(self.send_state())
            logger.info("Break started")
            await asyncio.sleep(self.break_time.seconds)
            logger.info("Break ended")
            logger.info("Round started")
            await asyncio.sleep(self.round_time.seconds + 2)
            logger.info("Round ended")

            # Eliminate any players without a score, or the last scoring player
            out = self.remaining - set(self.scores)
            if not out:
                # Abuse ordered dictionaries and stable sorting to ensure that
                # scores with equal timestamps maintain their ordering
                sorted_scores = sorted(
                    [
                        (user_id, score)
                        for user_id, score in self.scores.items()
                        if user_id in self.remaining
                    ],
                    key=lambda user_score: user_score[1].timestamp,
                )
                out = {sorted_scores[-1][0]}
            # Don't allow everyone to go out in the same round (we want a winner)
            if out == self.remaining:
                out = set()
            logger.info("Eliminating users: %s", out)
            self.eliminated |= out

            # Reset for the next round
            self.scores = {}

        self.break_end = None
        self.round_end = None
        await self.send_state()
        await asyncio.sleep(10)

        # Reset for the next game
        self.eliminated = set()
        await self.send_state()

    def _state(self) -> messages.State:
        scores: list[messages.Score] = [
            {
                "user_id": user_id,
                "user_name": self.users[user_id].name,
                "completion": score.completion,
                "finesse": score.finesse,
                "time": score.time,
            }
            for user_id, score in sorted(
                [
                    (user_id, score)
                    for user_id, score in self.scores.items()
                    if user_id in self.remaining
                ],
                key=lambda user_score: user_score[1].timestamp,
            )
        ]
        scores.extend(
            [
                {
                    "user_id": user_id,
                    "user_name": self.users[user_id].name,
                    "completion": 0,
                    "finesse": 0,
                    "time": 0,
                }
                for user_id in self.remaining - set(self.scores)
            ]
        )

        state: messages.State = {
            "type": "state",
            "lobby_id": self.id,
            "level": None,
            "warmup_timer": None,
            "round_timer": None,
            "break_timer": None,
            "users": {user.id: user.name for user in self.users.values()},
            "scores": scores,
        }

        if self.level is not None:
            state["level"] = {
                "name": self.level.name,
                "play": self.level.install_play,
                "image": self.level.image,
                "atlas": self.level.atlas,
                "dustkid": self.level.dustkid,
            }

        if self.warmup_end is not None:
            state["warmup_timer"] = {
                "start": (self.warmup_end - self.warmup_time).isoformat(),
                "end": self.warmup_end.isoformat(),
            }

        if self.round_end is not None:
            state["round_timer"] = {
                "start": (self.round_end - self.round_time).isoformat(),
                "end": self.round_end.isoformat(),
            }

        if self.break_end is not None:
            state["break_timer"] = {
                "start": (self.break_end - self.break_time).isoformat(),
                "end": self.break_end.isoformat(),
            }

        return state


@dataclass
class Score:
    completion: int
    finesse: int
    time: int
    timestamp: int

    @staticmethod
    def from_dustkid_event(event: Event) -> Score:
        return Score(
            event.score_completion,
            event.score_finesse,
            event.time,
            event.timestamp,
        )

    @property
    def ss_key(self) -> tuple[int, int, int]:
        return self.completion + self.finesse, -self.time, -self.timestamp


class Manager:
    def __init__(self, context: zmq.asyncio.Context) -> None:
        self.clients_socket = context.socket(zmq.ROUTER)
        self.events_socket = context.socket(zmq.SUB)

        # Socket identity -> Client
        self.clients: dict[bytes, Client] = {}

        self.max_level_id = 10_000

    async def run(self) -> None:
        self.clients_socket.bind(CLIENTS_URL)
        self.events_socket.connect(EVENTS_URL)
        self.events_socket.subscribe(b"")

        poller = zmq.asyncio.Poller()
        poller.register(self.clients_socket, zmq.POLLIN)
        poller.register(self.events_socket, zmq.POLLIN)

        while True:
            events = dict(await poller.poll())

            if events.get(self.clients_socket) == zmq.POLLIN:
                identity, data = await self.clients_socket.recv_multipart()
                message = messages.load(data)
                if message is not None:
                    await self.handle_message(identity, message)
                else:
                    logger.warning("Received invalid message: %s", message)

            if events.get(self.events_socket) == zmq.POLLIN:
                (data,) = await self.events_socket.recv_multipart()
                event = Event.parse_raw(data)
                await self.handle_dustkid_event(event)

    async def handle_message(self, identity: bytes, message: messages.Message):
        logger.debug(
            "Handling frontend message: identity=%s message=%s", identity, message
        )
        if message["type"] == "create_lobby":
            await self.handle_create_lobby(identity)
        if message["type"] == "start_round":
            await self.handle_start_round(
                identity,
                message["lobby_id"],
                message["password"],
                message["level_id"],
                message["mode"],
            )
        elif message["type"] == "join":
            await self.handle_join(identity, message["lobby_id"])
        elif message["type"] == "leave":
            await self.handle_leave(identity)
        elif message["type"] == "login":
            await self.handle_login(identity, message["user_id"])
        elif message["type"] == "logout":
            await self.handle_logout(identity)
        else:
            logger.warning("Received unknown message type: %s", message)

    async def handle_create_lobby(self, identity: bytes) -> None:
        lobby = Lobby.create()

        response: messages.Error | messages.CreatedLobby
        if lobby is None:
            response = {"type": "error"}
        else:
            response = {
                "type": "created_lobby",
                "lobby_id": lobby.id,
                "password": lobby.password,
            }

        await self.clients_socket.send_multipart(
            [identity, messages.dump_bytes(response)]
        )

    async def handle_start_round(
        self, identity: bytes, lobby_id: int, password: str, level_id: int, mode: str
    ) -> None:
        if lobby_id not in Lobby.lobbies:
            # TODO: Send back BadRequest
            return

        lobby = Lobby.lobbies[lobby_id]

        await lobby.on_start_round(password, level_id, mode)

    async def handle_join(self, identity: bytes, lobby_id: int) -> None:
        if identity in self.clients:
            logger.warning(
                "Duplicate client join: identity=%s lobby_id=%s", identity, lobby_id
            )
            return

        if lobby_id not in Lobby.lobbies:
            # TODO: Send back BadRequest
            return

        lobby = Lobby.lobbies[lobby_id]

        client = Client(
            socket=self.clients_socket,
            identity=identity,
            user=None,
            lobby=lobby,
        )
        self.clients[identity] = client

        await lobby.on_join(client)
        # TODO: Send back success response

    async def handle_leave(self, identity: bytes) -> None:
        if identity not in self.clients:
            logger.warning("Unknown client left: identity=%s", identity)
            return

        client = self.clients.pop(identity)
        lobby = client.lobby

        await lobby.on_leave(client)

    async def handle_login(self, identity: bytes, user_id: int) -> None:
        if identity not in self.clients:
            logger.warning(
                "Unknown client logged in: identity=%s user_id=%s", identity, user_id
            )
            return

        client = self.clients[identity]

        user = await User.create(user_id)
        if user is None:
            # TODO: Send back BadRequest
            return

        await client.login(user)

    async def handle_logout(self, identity: bytes) -> None:
        if identity not in self.clients:
            logger.warning("Unknown client logged out: identity=%s", identity)
            return

        client = self.clients[identity]
        await client.logout()

    async def handle_dustkid_event(self, event: Event) -> None:
        logger.debug("Received dustkid event: %s", event)

        level_id = Level(event.level).id
        if level_id is not None and level_id > self.max_level_id:
            logger.info("Found more recently uploaded level: id=%s", level_id)
            self.max_level_id = level_id

        for lobby in list(Lobby.lobbies.values()):
            await lobby.on_dustkid_event(event)


async def main() -> None:
    with zmq.asyncio.Context() as context:
        done, _ = await asyncio.wait(
            [
                asyncio.create_task(dustkid_events(context)),
                asyncio.create_task(Manager(context).run()),
            ],
            return_when=asyncio.FIRST_COMPLETED,
        )

    for future in done:
        try:
            await future
        except:
            logger.exception(future)


if __name__ == "__main__":
    asyncio.run(main())
