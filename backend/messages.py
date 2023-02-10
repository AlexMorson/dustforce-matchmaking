"""Messages for communicating between processes and with the client."""

from __future__ import annotations

import json
from typing import Literal, TypedDict, cast


def dump_str(message: Message) -> str:
    """Convert a message to a string."""
    return json.dumps(message)


def dump_bytes(message: Message) -> bytes:
    """Convert a message to bytes."""
    return dump_str(message).encode()


def load(data: bytes | str) -> Message | None:
    """Parse and validate a message from bytes or a string."""
    try:
        event = json.loads(data)
    except ValueError:
        return None
    if not isinstance(event, dict):
        return None
    if "type" not in event:
        return None
    # FIXME: Should definitely be doing more validation to justify this cast
    return cast(Message, event)


# Client -> Frontend -> Backend


class Login(TypedDict):
    type: Literal["login"]
    user_id: int


class Logout(TypedDict):
    type: Literal["logout"]


# Frontend -> Backend


class CreateLobby(TypedDict):
    type: Literal["create_lobby"]


class CreatedLobby(TypedDict):
    type: Literal["created_lobby"]
    lobby_id: int
    password: str


class Error(TypedDict):
    type: Literal["error"]


class StartGame(TypedDict):
    type: Literal["start_game"]
    lobby_id: int
    password: str
    level_id: int
    mode: str
    warmup_seconds: int
    countdown_seconds: int
    round_seconds: int


class StartRound(TypedDict):
    type: Literal["start_round"]
    lobby_id: int
    password: str


class Join(TypedDict):
    type: Literal["join"]
    lobby_id: int


class Leave(TypedDict):
    type: Literal["leave"]


# Frontend <-> Client


class Ping(TypedDict):
    type: Literal["ping"]


class Pong(TypedDict):
    type: Literal["pong"]


# Backend -> Frontend -> Client


class Score(TypedDict):
    user_id: int
    user_name: str
    completion: int
    finesse: int
    time: int


class Level(TypedDict):
    name: str
    play: str
    image: str
    atlas: str | None
    dustkid: str


class Timer(TypedDict):
    start: str
    end: str


class State(TypedDict):
    type: Literal["state"]
    lobby_id: int
    level: Level | None
    warmup_timer: Timer | None
    countdown_timer: Timer | None
    round_timer: Timer | None
    users: dict[int, str]
    scores: list[Score]


Message = (
    CreateLobby | CreatedLobby | Error | StartGame | StartRound | Join | Leave | State | Ping | Pong
)
