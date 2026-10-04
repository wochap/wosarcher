import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { SocketFactory } from "../api/events";
import { ApiContext } from "../app/context";
import { ev, stageDone } from "../test/events";
import { FakeWebSocket } from "../test/FakeWebSocket";
import { fakeApi } from "../test/fakeApi";
import { useRun } from "./useRun";

function Probe({ runId }: { runId: string }) {
  const { view, conn } = useRun(runId);
  return (
    <p>
      {view?.status} · {conn.state} · {view?.phases.plan.state} · {view?.phases.fetch.state}{" "}
      {view?.failure?.error}
    </p>
  );
}

const startedEvent = ev(1, "run.started", {
  query: "q",
  profile: "p",
  parent_run_id: null,
  version: 1,
  until: null,
});

/** A fake API whose run r1 failed at fetch with "no output". */
function failedApi() {
  const api = fakeApi();
  api.getRun = vi.fn(async () => ({
    ...(await fakeApi().getRun(api.data.runs[0].run_id)),
    run_id: "r1",
    status: "failed" as const,
    end_stage: "fetch" as const,
    error: "no output",
    last_seq: 0,
  }));
  return api;
}

function mount(api: ReturnType<typeof fakeApi>) {
  const services = { api, Socket: FakeWebSocket as unknown as SocketFactory };
  return render(
    <ApiContext.Provider value={services}>
      <Probe runId="r1" />
    </ApiContext.Provider>,
  );
}

beforeEach(() => FakeWebSocket.reset());

describe("useRun", () => {
  it("shows the status after fixture events and closes on unmount", async () => {
    const services = { api: fakeApi(), Socket: FakeWebSocket as unknown as SocketFactory };
    const { unmount } = render(
      <ApiContext.Provider value={services}>
        <Probe runId="r1" />
      </ApiContext.Provider>,
    );
    const socket = FakeWebSocket.last();
    act(() => {
      socket.open();
      socket.emit(
        ev(1, "run.started", {
          query: "q",
          profile: "p",
          parent_run_id: null,
          version: 1,
          until: null,
        }),
        stageDone(2, "plan"),
      );
    });
    expect(await screen.findByText(/^running · connected · done/)).toBeTruthy();
    unmount();
    expect(socket.closedByClient).toBe(true);
  });

  it("shows a failed run from its summary when the socket never opens", async () => {
    mount(failedApi());
    act(() => FakeWebSocket.last().serverClose(1006));
    expect(
      await screen.findByText("failed · reconnecting · pending · failed no output"),
    ).toBeTruthy();
  });

  it("keeps a failed summary when replayed run.started arrives afterwards", async () => {
    mount(failedApi());
    await screen.findByText(/^failed/);
    const socket = FakeWebSocket.last();
    act(() => {
      socket.open();
      socket.emit(startedEvent, ev(2, "stage.started", { device: null } as never, "plan"));
    });
    expect(screen.getByText(/^failed · connected/)).toBeTruthy();
  });
});
