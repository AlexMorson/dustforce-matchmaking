from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from operator import itemgetter

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

MAX_LOBBY_COUNT = 100

ROUND_TIME = timedelta(minutes=10)
BREAK_TIME = timedelta(seconds=30)


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


@dataclass
class User:
    id: int
    name: str
    lobby: Lobby
    socket: zmq.asyncio.Socket
    identity: bytes

    async def send(self, message: bytes) -> None:
        await self.socket.send_multipart([self.identity, message])


class Lobby:
    def __init__(self, id: int):
        logger.info("Lobby(%s) created", id)
        self.id = id
        self.users: dict[int, User] = {}
        self.scores: dict[int, Score] = {}

        self.deadline: datetime | None = None
        self.next_round: datetime | None = None
        self.level: Level | None = None
        self.winner: str | None = None

        self.loop = asyncio.create_task(self._run())

    def is_empty(self) -> bool:
        return not self.users

    async def _run(self) -> None:
        # Start the first round immediately
        await self._end_round(timedelta())
        while True:
            # Give a couple of seconds of leeway to account for network delays
            await asyncio.sleep(ROUND_TIME.seconds + 2)
            await self._end_round(BREAK_TIME)

    async def _end_round(self, break_time: timedelta) -> None:
        # Announce the winner
        self.deadline = None
        self.next_round = datetime.now(timezone.utc) + break_time
        if self.scores:
            self.winner = self.users[
                sorted(self.scores, key=lambda k: self.scores[k], reverse=True)[0]
            ].name
            logger.info("Lobby(%s) %s wins!", self.id, self.winner)
        await self._send_state()

        # Find a new level during the break
        new_level_task = asyncio.create_task(random_level(max_level_id=11_000))
        await asyncio.sleep(break_time.seconds)
        new_level = await new_level_task

        # Switch to new level
        logger.info(
            "Lobby(%s) starting new round with level %s", self.id, new_level.filename
        )
        self.winner = None
        self.scores = {}
        self.level = new_level
        self.deadline = datetime.now(timezone.utc) + ROUND_TIME
        self.next_round = None
        await self._send_state()

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
                self.scores.items(), key=itemgetter(1), reverse=True
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
                for user_id in self.users
                if user_id not in self.scores
            ]
        )

        state: messages.State = {
            "type": "state",
            "lobby_id": self.id,
            "level": None,
            "deadline": None,
            "next_round": None,
            "winner": self.winner,
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

        if self.deadline is not None:
            state["deadline"] = self.deadline.isoformat()

        if self.next_round is not None:
            state["next_round"] = self.next_round.isoformat()

        return state

    async def _send_state(self) -> None:
        message = json.dumps(self._state()).encode()
        for user in self.users.values():
            await user.send(message)

    async def on_join(self, user: User) -> bool:
        """Handle a new user joining."""
        if user.id in self.users:
            return False
        logger.info("Lobby(%s) user %s (%s) joined", self.id, user.id, user.name)
        self.users[user.id] = user
        await self._send_state()
        return True

    async def on_leave(self, user_id: int) -> None:
        """Handle a user leaving."""
        logger.info("Lobby(%s) user %s left", self.id, user_id)
        self.users.pop(user_id, None)
        self.scores.pop(user_id, None)

        if self.is_empty():
            self.loop.cancel()
            try:
                await self.loop
            except asyncio.CancelledError:
                pass
        else:
            await self._send_state()

    async def on_dustkid_event(self, event: Event) -> None:
        """Update scores and send state if this is a new best."""
        if event.user not in self.users:
            return

        if self.level is None or event.level != self.level.filename:
            return

        if (
            self.deadline is None
            or datetime.fromtimestamp(event.timestamp, timezone.utc) > self.deadline
        ):
            return

        old_score = self.scores.get(event.user)
        new_score = Score.from_dustkid_event(event)
        if old_score is None or old_score < new_score:
            logger.info(
                "Lobby(%s) User %s (%s) PB'd: %s",
                self.id,
                event.user,
                self.users[event.user].name,
                new_score,
            )
            self.scores[event.user] = new_score
            await self._send_state()


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
    def _key(self) -> tuple[int, int, int]:
        return self.completion + self.finesse, -self.time, -self.timestamp

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Score):
            return NotImplemented
        return self._key == other._key

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Score):
            return NotImplemented
        return self._key < other._key

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Score):
            return NotImplemented
        return self._key <= other._key


async def lookup_user(user_id: int) -> str | None:
    if not (1 <= user_id <= 1_000_000):
        return None
    url = f"https://df.hitboxteam.com/backend6/userSearch.php?userid={user_id}"
    async with ClientSession() as session:
        async with session.get(url) as response:
            result = await response.json()
            if len(result) != 1 or "name" not in result[0]:
                return None
            return result[0]["name"]


class Manager:
    def __init__(self, context: zmq.asyncio.Context) -> None:
        self.clients_socket = context.socket(zmq.ROUTER)
        self.events_socket = context.socket(zmq.SUB)

        # Socket identity -> User
        self.users: dict[bytes, User] = {}

        # Lobby id -> Lobby
        self.lobbies: dict[int, Lobby] = {}
        self.next_id = 0

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
        if message["type"] == "create":
            await self.handle_create(identity, message["user_id"])
        elif message["type"] == "join":
            await self.handle_join(identity, message["user_id"], message["lobby_id"])
        elif message["type"] == "leave":
            await self.handle_leave(identity)

    async def handle_create(self, identity: bytes, user_id: int) -> None:
        if len(self.lobbies) >= MAX_LOBBY_COUNT:
            logger.warning(
                "Ignoring lobby create because there are %s existing lobbies",
                len(self.lobbies),
            )
            return

        lobby_id = self.next_id
        self.next_id += 1

        lobby = Lobby(id=lobby_id)
        self.lobbies[lobby_id] = lobby

        await self.handle_join(identity, user_id, lobby_id)

    async def handle_join(self, identity: bytes, user_id: int, lobby_id: int) -> None:
        if lobby_id not in self.lobbies:
            # TODO: Send back BadRequest
            return
        lobby = self.lobbies[lobby_id]

        user_name = await lookup_user(user_id)
        if user_name is None:
            # TODO: Send back BadRequest
            return

        user = User(
            id=user_id,
            name=user_name,
            lobby=lobby,
            socket=self.clients_socket,
            identity=identity,
        )

        if not await lobby.on_join(user):
            # TODO: Send back BadRequest
            return

        self.users[identity] = user

    async def handle_leave(self, identity: bytes) -> None:
        if identity not in self.users:
            logger.warning("Unknown user left: identity=%s", identity)
            return

        user = self.users.pop(identity)
        lobby = user.lobby

        await lobby.on_leave(user.id)
        if lobby.is_empty():
            logger.info("Deleting empty lobby: id=%s", lobby.id)
            del self.lobbies[lobby.id]

    async def handle_dustkid_event(self, event: Event) -> None:
        logger.debug("Received dustkid event: %s", event)

        level_id = Level(event.level).id
        if level_id is not None and level_id > self.max_level_id:
            logger.info("Found more recently uploaded level: id=%s", level_id)
            self.max_level_id = level_id

        for lobby in list(self.lobbies.values()):
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
