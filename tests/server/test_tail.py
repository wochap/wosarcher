from datetime import UTC, datetime
from pathlib import Path

from wosarcher.models import Event, ReportDelta, ReportSnapshot, RunStartedData, make_event
from wosarcher.server.tail import RunTail

TS = datetime(2026, 1, 1, tzinfo=UTC)


def line(seq: int) -> bytes:
    data = RunStartedData(query="q", profile="p", parent_run_id=None, version=1, until=None)
    return (make_event(seq, "r", TS, "run.started", None, data).model_dump_json() + "\n").encode()


def drain(tail: RunTail) -> list[Event | None]:
    queue = tail.subscribers[0].queue
    return [queue.get_nowait() for _ in range(queue.qsize())]


def test_partial_line_held(tmp_path: Path) -> None:
    tail = RunTail("r", tmp_path)
    tail.subscribe()
    whole = line(1) + line(2)
    (tmp_path / "events.jsonl").write_bytes(whole[:-10])
    tail.poll()
    assert [e and e.seq for e in drain(tail)] == [1]
    (tmp_path / "events.jsonl").write_bytes(whole)
    tail.poll()
    assert [e and e.seq for e in drain(tail)] == [2]
    assert tail.last_seq == 2


def test_multibyte_split(tmp_path: Path) -> None:
    tail = RunTail("r", tmp_path)
    tail.subscribe()
    text = "é→x".encode()
    (tmp_path / "report.md").write_bytes(text[:1])
    tail.poll()
    assert drain(tail) == []
    (tmp_path / "report.md").write_bytes(text)
    tail.poll()
    [delta] = drain(tail)
    assert isinstance(delta, ReportDelta)
    assert delta.data.text == "é→x"
    assert tail.report_text == "é→x"


def test_rewrite_sends_snapshot(tmp_path: Path) -> None:
    tail = RunTail("r", tmp_path)
    (tmp_path / "report.md").write_text("streamed [1]")
    tail.poll()
    subscriber = tail.subscribe()
    assert subscriber.text == "streamed [1]"
    (tmp_path / "report.md").write_text("streamed ¹")
    tail.poll()
    [snapshot] = drain(tail)
    assert isinstance(snapshot, ReportSnapshot)
    assert snapshot.data.text == "streamed ¹"


def test_subscriber_overflow_marked(tmp_path: Path) -> None:
    tail = RunTail("r", tmp_path, max_behind=3)
    slow, fast = tail.subscribe(), tail.subscribe()
    log = tmp_path / "events.jsonl"
    log.write_bytes(line(1) + line(2))
    tail.poll()
    received = [fast.queue.get_nowait() for _ in range(fast.queue.qsize())]
    log.write_bytes(b"".join(line(n) for n in range(1, 5)))
    tail.poll()
    received += [fast.queue.get_nowait() for _ in range(fast.queue.qsize())]
    assert slow.overflowed
    assert not fast.overflowed
    assert [e and e.seq for e in received] == [1, 2, 3, 4]
    assert [slow.queue.get_nowait() for _ in range(slow.queue.qsize())][-1] is None
