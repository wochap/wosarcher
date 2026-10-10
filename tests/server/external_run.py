"""A stand-in for a `wosarcher run` an agent started next to the server: `external_run.py <run_id> <steps>`.

It creates the run directory (origin `cli`), waits for a slot in the shared run
queue, then writes `run.started`, one `stage.progress` and one report chunk per
step (`FAKE_STEP` seconds apart), and `run.done`. A cancel request, while
waiting or running, ends it with `run.cancelled` and exit code 130.
The runs directory is `WOSARCHER_RUN__RUNS_DIR`; the settings directory is
`$XDG_CONFIG_HOME/wosarcher`.
"""

import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from wosarcher.config import config_dir
from wosarcher.models import (
    RunCancelledData,
    RunDoneData,
    RunRecord,
    RunRequest,
    RunStartedData,
    SlotEntry,
    StageProgressData,
    StageStartedData,
    UsageTotals,
)
from wosarcher.store import RunStore


def main(run_id: str, steps: int) -> int:
    store = RunStore(Path(os.environ["WOSARCHER_RUN__RUNS_DIR"]), Path(), config_dir(os.environ))
    store.run_dir(run_id).mkdir(parents=True)
    record = RunRecord(
        run_id=run_id,
        created_at=datetime.now(UTC),
        request=RunRequest(query="q"),
        profile="p",
        settings={},
        origin="cli",
    )
    store.write_artifact(run_id, "request.json", record)
    step = float(os.environ.get("FAKE_STEP", "0.05"))
    ticket = store.slots.ticket(SlotEntry(run_id=run_id, origin="cli"))
    while (held := store.slots.grant(ticket)) is None:
        if store.slots.cancel_requested(run_id):
            store.append_event(run_id, "run.cancelled", None, RunCancelledData(stage=None))
            ticket.close()
            return 130
        time.sleep(0.05)
    started = RunStartedData(query="q", profile="p", parent_run_id=None, version=1, until=None)
    store.append_event(run_id, "run.started", None, started)
    store.append_event(run_id, "stage.started", "write", StageStartedData(device=None, provider="openai"))
    for n in range(steps):
        if store.slots.cancel_requested(run_id):
            store.append_event(run_id, "run.cancelled", None, RunCancelledData(stage="write"))
            held.close()
            return 130
        store.append_report(run_id, f"Part {n}. ")
        store.append_event(run_id, "stage.progress", "write", StageProgressData(done=n + 1, total=steps, failed=0))
        time.sleep(step)
    store.append_event(run_id, "run.done", None, RunDoneData(until=None, totals=UsageTotals()))
    held.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], int(sys.argv[2])))
