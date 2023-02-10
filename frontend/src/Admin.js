function formSubmit(path, event) {
  var request = new XMLHttpRequest();
  const url = new URL(path, window.location.href);
  request.open("POST", url, true);
  request.send(new FormData(event.target));
  event.preventDefault();
}

function Admin({ lobby_id, password }) {
  return (
    <>
      <form onSubmit={(event) => formSubmit("../api/start_game", event)}>
        <input type="hidden" name="lobby_id" value={lobby_id} />
        <input type="hidden" name="password" value={password} />
        <label>
          Level id: <input name="level_id" placeholder="eg. 10643" />
        </label>
        <br />
        <label>
          Mode:{" "}
          <select name="mode">
            <option value="any">Any%</option>
            <option value="ss">SS</option>
          </select>
        </label>
        <br />
        <label>
          Warmup time: <input name="warmup_seconds" defaultValue="240" />
        </label>
        <br />
        <label>
          Countdown time: <input name="countdown_seconds" defaultValue="5" />
        </label>
        <br />
        <label>
          Round time: <input name="round_seconds" defaultValue="60" />
        </label>
        <br />
        <button>Start game</button>
      </form>
      <br />
      <form onSubmit={(event) => formSubmit("../api/start_round", event)}>
        <input type="hidden" name="lobby_id" value={lobby_id} />
        <input type="hidden" name="password" value={password} />
        <button>Start round</button>
      </form>
      <br />
    </>
  );
}

export default Admin;
