"""A stand-in for a direct `wosarcherd run` next to the server: `external_run.py <run_id> <steps>`.

It creates the run directory (origin `cli`) holding the run lock, then writes
`run.started`, one `stage.progress` and one report chunk per step (`FAKE_STEP`
seconds apart), and `run.done`. The runs directory is `WOSARCHER_RUN__RUNS_DIR`.
"""

import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from wosarcher.models import (
    RunDoneData,
    RunRecord,
    RunRequest,
    RunStartedData,
    StageProgressData,
    StageStartedData,
    UsageTotals,
)
from wosarcher.store import RunStore


def main(run_id: str, steps: int) -> int:
    store = RunStore(Path(os.environ["WOSARCHER_RUN__RUNS_DIR"]), Path())
    store.run_dir(run_id).mkdir(parents=True)
    store.lock(run_id)
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
    started = RunStartedData(query="q", profile="p", parent_run_id=None, version=1, until=None)
    store.append_event(run_id, "run.started", None, started)
    store.append_event(run_id, "stage.started", "write", StageStartedData(device=None, provider="openai"))
    for n in range(steps):
        store.append_report(run_id, f"Part {n}. ")
        store.append_event(run_id, "stage.progress", "write", StageProgressData(done=n + 1, total=steps, failed=0))
        time.sleep(step)
    store.append_event(run_id, "run.done", None, RunDoneData(until=None, totals=UsageTotals()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], int(sys.argv[2])))
