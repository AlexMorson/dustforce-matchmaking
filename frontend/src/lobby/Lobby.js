import Image from "./Image.js";
import Scores from "./Scores.js";
import Timer from "./Timer.js";

function Lobby({ state }) {
  return (
    <>
      {state.level && <Image level={state.level} />}
      {state.warmup_timer && (
        <Timer
          start={new Date(state.warmup_timer.start)}
          end={new Date(state.warmup_timer.end)}
          text={"Warmup:"}
        />
      )}
      {state.break_timer && (
        <Timer
          start={new Date(state.break_timer.start)}
          end={new Date(state.break_timer.end)}
          text={"Next round in:"}
        />
      )}
      {state.round_timer && (
        <Timer
          start={new Date(state.round_timer.start)}
          end={new Date(state.round_timer.end)}
          text={"Remaining time:"}
        />
      )}
      {state.hasOwnProperty("scores") && (
        <Scores scores={state.scores}></Scores>
      )}
    </>
  );
}

export default Lobby;
