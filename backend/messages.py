from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import TypedDict, TypeVar

from bidict import bidict

MESSAGE_NAMES: bidict[type[Message], str] = bidict()


class Message:
    def to_bytes(self) -> bytes:
        dictionary = asdict(self)
        dictionary["type"] = MESSAGE_NAMES[type(self)]
        return json.dumps(dictionary).encode()

    @staticmethod
    def from_bytes(data: bytes) -> Message:
        parsed = json.loads(data)
        cls = MESSAGE_NAMES.inverse[parsed.pop("type")]
        return cls(**parsed)


M = TypeVar("M", bound=type[Message])


def message(cls: M) -> M:
    MESSAGE_NAMES[cls] = re.sub(r"(?<!^)(?=[A-Z])", "_", cls.__name__).lower()
    return cls


# Frontend -> Backend


@message
@dataclass
class Create(Message):
    user_id: int


@message
@dataclass
class Join(Message):
    user_id: int
    lobby_id: int


@message
@dataclass
class Leave(Message):
    pass


# Backend -> Frontend


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
    lobby_id: int
    level: Level | None
    deadline: str | None
    winner: str | None
    next_round: str | None
    users: dict[int, str]
    scores: list[Score]
