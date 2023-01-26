import { Flipped, Flipper } from "react-flip-toolkit";

import "./Scores.css";

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

export default Scores;
