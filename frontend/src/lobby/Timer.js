import { useState, useEffect, useRef } from "react";

import "./Timer.css";

function formatTime(ms) {
  ms = Math.max(0, ms);
  const milliseconds = ms % 1000;
  const seconds = Math.floor(ms / 1000) % 60;
  const minutes = Math.floor(ms / 1000 / 60); // % 60;
  // const hours = Math.floor(ms / 1000 / 60 / 60);

  const fraction = Math.floor(milliseconds / 100);

  return (
    minutes.toString() +
    ":" +
    seconds.toString().padStart(2, "0") +
    "." +
    fraction.toString()
  );
}

function useTime() {
  const [time, setTime] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => {
      setTime(new Date());
    }, 100);
    return () => clearInterval(id);
  }, []);
  return time;
}

function Timer({ start, end, text }) {
  const barRef = useRef(null);
  const time = useTime();

  useEffect(() => {
    const duration = end - start;
    const elapsed = new Date() - start;
    barRef.current.animate(
      {
        width: ["100%", "0%"],
        background: ["#0d0", "#dd0", "#d00"],
      },
      { duration, delay: -elapsed, fill: "forwards" }
    );
  }, [barRef, start, end]);

  return (
    <div className={"timer"}>
      <div ref={barRef} className={"timer-bar"}></div>
      <p className={"timer-text"}>
        {text}
        <span className={"timer-deadline"}>{formatTime(end - time)}</span>
      </p>
    </div>
  );
}

export default Timer;
