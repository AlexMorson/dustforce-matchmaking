from pydantic import BaseModel


class Tag(BaseModel):
    version: str
    release: str | None
    mode: str
    filth: str | None
    collected: str
    apples: str | None
    genocide: str | None


class Event(BaseModel):
    rid: str
    user: int
    level: str
    time: int
    character: int
    score_completion: int
    score_finesse: int
    apples: int
    timestamp: int
    replay_id: int
    validated: int
    dustkid: int
    input_jumps: int
    input_dashes: int
    input_lights: int
    input_heavies: int
    input_super: int
    input_directions: int
    tag: Tag | list[object]
    numplayers: int
    rank_all_score: int
    rank_all_time: int
    rank_char_score: int
    rank_char_time: int
    username: str
    levelname: str
    pb: bool


class Score(BaseModel):
    user: int
    timestamp: int
    level: str
    time: int
    character: int
    score_completion: int
    score_finesse: int
    apples: int
    replay_id: int
    validated: int
    dustkid: int
    input_jumps: int
    input_dashes: int
    input_lights: int
    input_heavies: int
    input_super: int
    input_directions: int
    tag: Tag | list[object]
    numplayers: int
    replay: int


class Leaderboard(BaseModel):
    scores: dict[str, Score]
    times: dict[str, Score]
