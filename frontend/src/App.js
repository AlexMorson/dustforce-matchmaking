import { useState, useEffect } from "react";
import { Routes, Route, useParams } from "react-router-dom";

import Admin from "./Admin.js";
import Lobby from "./lobby/Lobby.js";

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
  round_timer: {
    start: new Date().getTime(),
    end: new Date().getTime() + 5 * 60 * 1000,
  },
  users: { 123: "hi", 789: "wow", 147: "longer" },
  scores: [
    {
      user_id: 789,
      user_name: "Youkaykayieasy",
      completion: 5,
      finesse: 1,
      time: 35821,
    },
    {
      user_id: 147,
      user_name: "AvengedRuler",
      completion: 3,
      finesse: 2,
      time: 8171,
    },
    {
      user_id: 123,
      user_name: "Alexspeedy",
      completion: 0,
      finesse: 0,
      time: 0,
    },
  ],
};

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
    console.debug("Connecting websocket");
    if (this.closed) {
      console.debug("Websocket is closed, not connecting");
      return;
    }

    this.ws = new WebSocket(this.url);
    this.ws.onmessage = (event) => {
      console.debug("Websocket onevent", event);
      this.heartbeat();
      this.onmessage(event);
    };
    this.ws.onopen = (event) => {
      console.debug("Websocket onopen", event);
      this.attempts = 0;
      this.heartbeat();
    };
    this.ws.onclose = (event) => {
      console.debug("Websocket onclose", event);
      this.reconnect();
    };
  }

  reconnect() {
    console.debug("Reconnecting websocket");
    clearTimeout(this.pingTimer);
    clearTimeout(this.pongTimer);
    this.ws.close();
    ++this.attempts;
    const delay = Math.min(30 * 1000, 100 * Math.pow(2, this.attempts - 1));
    console.debug(`Attempt ${this.attempts}, waiting ${delay}ms before reconnecting`);
    setTimeout(() => this.connect(), delay);
  }

  heartbeat() {
    console.debug("Got heartbeat");
    clearTimeout(this.pingTimer);
    clearTimeout(this.pongTimer);
    this.pingTimer = setTimeout(() => this.ping(), 5000);
  }

  ping() {
    console.debug("Sending ping");
    this.ws.send(JSON.stringify({ type: "ping" }));
    this.pongTimer = setTimeout(() => {
        console.warn("Did not receive pong, reconnecting");
        this.reconnect();
    }, 5000);
  }

  close() {
    console.debug("Closing websocket");
    if (this.closed) {
      console.debug("Websocket already closed");
      return;
    }
    this.closed = true;
    clearTimeout(this.pingTimer);
    clearTimeout(this.pongTimer);
    this.ws.close();
    this.onclose();
  }
}

function useSocket(lobby_id) {
  const [socket] = useState(() => {
    const url = new URL("../events", window.location.href);
    url.protocol = url.protocol.replace("http", "ws");
    url.searchParams.set("lobby", lobby_id);

    return new ReconnectingWebSocket(url);
  });
  return socket;
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<CreateLobby />} />
      <Route path="/lobby/:lobby_id" element={<Matchmaking />} />
    </Routes>
  );
}

function CreateLobby() {
  return (
    <form method="POST" action="api/create_lobby">
      <button>Create!</button>
    </form>
  );
}

function getUser() {
  const match = document.cookie.match(/(?:^|; )user=([^;]+)/);
  if (match) return match[1];
}

function Matchmaking() {
  const { lobby_id } = useParams();
  const socket = useSocket(lobby_id);

  const [state, setState] = useState({});
  const [user, setUser] = useState(getUser);

  const urlParams = new URL(window.location.href).searchParams;
  const adminPassword = urlParams.get("admin");

  // Subtract the scrollbar from the view width
  useEffect(() => {
    const updateWidth = () => {
      const vw = document.documentElement.clientWidth / 100;
      document.querySelector(":root").style.setProperty("--vw", `${vw}px`);
    };
    updateWidth();
    window.addEventListener("resize", updateWidth);
    return () => window.removeEventListener("resize", updateWidth);
  });

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
      console.info("Received new state", args);
      setState(args);
    } else {
      console.warn("Received unknown event type", data);
    }
  };

  const onJoin = () => {
    if (!user || !/^[1-9][0-9]{0,5}$/.test(user)) return;
    socket.send(JSON.stringify({ type: "login", user_id: parseInt(user) }));
  };

  // Ignore query params
  const lobbyUrl = window.location.origin + window.location.pathname;

  return (
    <div className={"center"}>
      {adminPassword && <Admin lobby_id={lobby_id} password={adminPassword} />}
      <label className={"user"}>
        Dustkid id:{" "}
        <input
          placeholder="eg. 292925"
          value={user}
          onInput={(e) => setUser(e.target.value)}
        />
      </label>
      <button onClick={onJoin}>Join</button>
      {state.lobby_id !== undefined && (
        <p className={"lobby"}>
          Share lobby: <a href={lobbyUrl}>{lobbyUrl}</a>
        </p>
      )}
      {state.level && (
        <p className={"links"}>
          <a href={state.level.atlas}>Atlas</a>{" "}
          <a href={state.level.dustkid}>Leaderboards</a>
        </p>
      )}
      <Lobby state={state} />
    </div>
  );
}

export default App;
