import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
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
      {view?.status} · {conn.state} · {view?.phases.plan.state}
    </p>
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
    expect(await screen.findByText("running · connected · done")).toBeTruthy();
    unmount();
    expect(socket.closedByClient).toBe(true);
  });
});
