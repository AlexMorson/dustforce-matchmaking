import { useState, useEffect } from "react";
import { Flipped, Flipper } from "react-flip-toolkit";

import "./App.css";

const EXAMPLE_STATE = {
  lobby_id: 123,
  level: {
    name: "How Do I Boost",
    play: "dustforce://installPlay/5518/How-Do-I-Boost",
    image: "http://atlas.dustforce.com/gi/maps/How-Do-I-Boost-5518.png",
    atlas: "http://atlas.dustforce.com/5518/How-Do-I-Boost",
    dustkid: "http://dustkid.com/level/How-Do-I-Boost-5518",
  },
  users: { 123: "hi", 789: "wow", 147: "longer" },
  scores: [
    {
      user_id: 123,
      user_name: "hi",
      completion: 0,
      finesse: 0,
      time: 0,
    },
    {
      user_id: 789,
      user_name: "wow",
      completion: 5,
      finesse: 1,
      time: 35821,
    },
    {
      user_id: 147,
      user_name: "longer",
      completion: 3,
      finesse: 2,
      time: 8171,
    },
  ],
};

function useTime() {
  const [time, setTime] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => {
      setTime(new Date());
    }, 1000);
    return () => clearInterval(id);
  }, []);
  return time;
}

function formatTime(ms) {
  ms = Math.max(0, ms);
  // const milliseconds = ms % 1000;
  const seconds = Math.floor(ms / 1000) % 60;
  const minutes = Math.floor(ms / 1000 / 60); // % 60;
  // const hours = Math.floor(ms / 1000 / 60 / 60);

  return minutes.toString() + ":" + seconds.toString().padStart(2, "0");
}

class ReconnectingWebSocket {
  constructor(url) {
    this.url = url;
    this.ws = null;

    this.attempts = 0;
    this.closed = false;

    this.pingTimer = null;
    this.pongTimer = null;

    this.onmessage = () => {};
    this.onclose = () => {};

    this.connect();
  }

  send(data) {
    this.ws.send(data);
  }

  connect() {
    if (this.closed) return;

    this.ws = new WebSocket(this.url);
    this.ws.onmessage = (event) => {
      this.heartbeat();
      this.onmessage(event);
    };
    this.ws.onopen = (event) => {
      this.attempts = 0;
      this.heartbeat();
    };
    this.ws.onclose = (event) => {
      if (event.wasClean) this.close();
      else if (!this.closed) this.reconnect();
    };
  }

  reconnect() {
    clearTimeout(this.pingTimer);
    clearTimeout(this.pongTimer);
    this.ws.close();
    ++this.attempts;
    setTimeout(
      () => this.connect(),
      1000 * Math.min(30, Math.pow(2, this.attempts - 1))
    );
  }

  heartbeat() {
    clearTimeout(this.pingTimer);
    clearTimeout(this.pongTimer);
    this.pingTimer = setTimeout(() => this.ping(), 5000);
  }

  ping() {
    this.ws.send(JSON.stringify({ type: "ping" }));
    this.pongTimer = setTimeout(() => this.reconnect(), 5000);
  }

  close() {
    if (this.closed) return;
    this.closed = true;
    clearTimeout(this.pingTimer);
    clearTimeout(this.pongTimer);
    this.ws.close();
    this.onclose();
  }
}

function useSocket() {
  const [socket, setSocket] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    const lobby = params.get("lobby");

    const url = new URL("/", window.location.href);
    url.protocol = url.protocol.replace("http", "ws");
    if (lobby) url.searchParams.set("lobby", lobby);

    return new ReconnectingWebSocket(url);
  });
  useEffect(() => () => socket.close(), []);
  return socket;
}

function App() {
  const [state, setState] = useState({});
  const [user, setUser] = useState("");
  const socket = useSocket();
  const time = useTime();
  const [joined, setJoined] = useState(false);

  socket.onmessage = (event) => {
    let data;
    try {
      data = JSON.parse(event.data);
    } catch (error) {
      console.warn("Could not parse websocket event data", event.data);
      return;
    }

    if (!data.hasOwnProperty("type")) {
      console.warn("Websocket event is missing field 'type'", data);
      return;
    }

    const { type, ...args } = data;

    if (type === "pong") {
      console.debug("Got pong");
    } else if (type === "state") {
      console.debug("Received new state", args);
      setState(args);
    } else {
      console.warn("Received unknown event type", data);
    }
  };

  const onJoin = () => {
    if (!user || !/^[1-9][0-9]{0,5}$/.test(user)) return;
    socket.send(JSON.stringify({ type: "login", user_id: parseInt(user) }));
    setJoined(true);
  };

  const onLeave = () => {
    socket.send(JSON.stringify({ type: "logout" }));
    setJoined(false);
  };

  const lobbyUrl = new URL(window.location.href);
  lobbyUrl.searchParams.set("lobby", state.lobby_id);

  return (
    <div className={"center"}>
      <label className={"user"}>
        Dustkid id:{" "}
        <input
          placeholder="eg. 292925"
          value={user}
          onInput={(e) => setUser(e.target.value)}
        />
      </label>
      {joined ? (
        <button onClick={onLeave}>Leave</button>
      ) : (
        <button onClick={onJoin}>Join</button>
      )}
      {state.lobby_id !== undefined && (
        <p className={"lobby"}>
          Share lobby: <a href={lobbyUrl.toString()}>{lobbyUrl.toString()}</a>
        </p>
      )}
      {state.deadline && (
        <p className={"timer"}>
          Remaining time: {formatTime(new Date(state.deadline) - time)}
        </p>
      )}
      {state.winner && <p className={"winner"}>{state.winner} wins!</p>}
      {state.next_round && (
        <p className={"timer"}>
          Next round in: {formatTime(new Date(state.next_round) - time)}
        </p>
      )}
      {state.level && (
        <>
          <p className={"links"}>
            <a href={state.level.atlas}>Atlas</a>{" "}
            <a href={state.level.dustkid}>Leaderboards</a>
          </p>
          <div className={"image"}>
            <a href={state.level.play}>
              <img alt={state.level.name} src={state.level.image} />
            </a>
            <span>{state.level.name}</span>
          </div>
        </>
      )}
      {state.hasOwnProperty("scores") && (
        <Scores scores={state.scores}></Scores>
      )}
    </div>
  );
}

function Scores({ scores }) {
  const grade = (score) => "DCBAS".charAt(score - 1);
  let rows = [];
  for (const score of scores) {
    const time = score.time ? (score.time / 1000).toFixed(3) : "";

    const completion = score.completion ? grade(score.completion) : "";
    const finesse = score.finesse ? grade(score.finesse) : "";

    const completionClass = completion ? " grade" + completion : "";
    const finesseClass = finesse ? " grade" + finesse : "";

    rows.push(
      <Flipped key={score.user_id} flipId={score.user_id}>
        <div className={"row"}>
          <span className={"name"}>{score.user_name}</span>
          <span className={"score" + completionClass}>{completion}</span>
          <span className={"score" + finesseClass}>{finesse}</span>
          <span className={"time"}>{time}</span>
        </div>
      </Flipped>
    );
  }
  return (
    <Flipper className={"scores"} flipKey={JSON.stringify(scores)}>
      {rows}
    </Flipper>
  );
}

export default App;
