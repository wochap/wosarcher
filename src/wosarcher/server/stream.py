"""`WS /api/runs/{id}/events?since=<seq>`: replay, report snapshot, then live events until the run ends.

Live-only events (`report.delta`, `report.snapshot`, `run.queued`, and the
`run.cancelled` of a dequeued run, which has `seq` 0) carry the last logged
`seq` sent to this client, so resuming from the highest `seq` seen never
skips a logged event.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from wosarcher.models import Event, ReportSnapshot, ReportTextData, RunQueued, RunQueuedData
from wosarcher.server.state import get_state
from wosarcher.server.tail import TERMINAL, Subscriber

router = APIRouter(prefix="/api")

CLOSE_UNKNOWN = 4404
CLOSE_SLOW = 4408
LIVE_ONLY = {"report.delta", "report.snapshot", "run.queued"}


class Client:
    def __init__(self, socket: WebSocket, since: int) -> None:
        self.socket = socket
        self.last = since

    async def send(self, event: Event) -> bool:
        """Send one event; True when it ends the stream."""
        if event.type in LIVE_ONLY or event.seq == 0:
            event = event.model_copy(update={"seq": self.last})
        elif event.seq <= self.last:
            return False
        else:
            self.last = event.seq
        await self.socket.send_text(event.model_dump_json())
        return event.type in TERMINAL


@router.websocket("/runs/{run_id}/events")
async def events(socket: WebSocket, run_id: str, since: int = 0) -> None:
    state = get_state(socket)
    active = state.manager.active(run_id)
    known = not run_id.startswith(".") and (state.runs_dir / run_id / "request.json").is_file()
    await socket.accept()
    if active is None and not known:
        await socket.close(CLOSE_UNKNOWN)
        return
    subscriber = active.tail.subscribe() if active else None
    try:
        await stream(socket, run_id, since, subscriber, state.manager.queue_position(run_id))
    except WebSocketDisconnect:
        pass
    finally:
        if active and subscriber:
            active.tail.unsubscribe(subscriber)


async def stream(
    socket: WebSocket, run_id: str, since: int, subscriber: Subscriber | None, position: int | None
) -> None:
    state = get_state(socket)
    client = Client(socket, since)
    if subscriber is not None:
        last, text = subscriber.last_seq, subscriber.text
    else:
        last = None
        path = state.runs_dir / run_id / "report.md"
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
    ended = False
    for event in state.store.read_events(run_id, since):
        if last is not None and event.seq > last:
            break
        ended = await client.send(event) or ended
    now = datetime.now(UTC)
    if text:
        await client.send(ReportSnapshot(seq=0, run_id=run_id, ts=now, stage="write", data=ReportTextData(text=text)))
    if position is not None:
        await client.send(RunQueued(seq=0, run_id=run_id, ts=now, data=RunQueuedData(position=position)))
    if subscriber is None or ended:
        await socket.close(1000)
        return
    while True:
        event = await subscriber.queue.get()
        if event is None:
            await socket.close(CLOSE_SLOW if subscriber.overflowed else 1000)
            return
        if await client.send(event):
            await socket.close(1000)
            return
