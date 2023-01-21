"""Messages for communicating between processes and with the client."""

from __future__ import annotations

import json
from typing import Literal, TypedDict, cast


def dump_str(message: Message) -> str:
    """Convert a message to a string."""
    return json.dumps(message)

def dump_bytes(message: Message) -> bytes:
    """Convert a message to bytes."""
    return json.dumps(message).encode()

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


# Frontend -> Backend


class Create(TypedDict):
    type: Literal["create"]
    user_id: int


def create(user_id: int) -> Create:
    return {"type": "create", "user_id": user_id}


class Join(TypedDict):
    type: Literal["join"]
    user_id: int
    lobby_id: int


def join(user_id: int, lobby_id: int) -> Join:
    return {"type": "join", "user_id": user_id, "lobby_id": lobby_id}


class Leave(TypedDict):
    type: Literal["leave"]


def leave() -> Leave:
    return {"type": "leave"}


# Frontend <-> Client


class Ping(TypedDict):
    type: Literal["ping"]


def ping() -> Ping:
    return {"type": "ping"}


class Pong(TypedDict):
    type: Literal["pong"]


def pong() -> Pong:
    return {"type": "pong"}


# Backend -> Client


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


class State(TypedDict):
    type: Literal["state"]
    lobby_id: int
    level: Level | None
    deadline: str | None
    winner: str | None
    next_round: str | None
    users: dict[int, str]
    scores: list[Score]


Message = Create | Join | Leave | State | Ping | Pong
