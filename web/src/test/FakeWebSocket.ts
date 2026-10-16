// A WebSocket stand-in driven by the test: `open()`, `emit(event)`, and `serverClose(code)`.
import type { RunEvent } from "../api/types";

export class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static reset() {
    FakeWebSocket.instances = [];
  }
  static last(): FakeWebSocket {
    const socket = FakeWebSocket.instances.at(-1);
    if (!socket) throw new Error("no socket opened");
    return socket;
  }

  readyState = 0;
  closedByClient = false;
  /** Text messages the client sent. */
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((message: { data: string }) => void) | null = null;
  onclose: ((close: { code: number }) => void) | null = null;

  constructor(readonly url: string) {
    FakeWebSocket.instances.push(this);
  }

  open() {
    this.readyState = 1;
    this.onopen?.();
  }

  emit(...events: RunEvent[]) {
    for (const event of events) this.onmessage?.({ data: JSON.stringify(event) });
  }

  serverClose(code: number) {
    this.readyState = 3;
    this.onclose?.({ code });
  }

  send(data: string) {
    if (this.readyState !== 1) throw new Error("socket is not open");
    this.sent.push(data);
  }

  close() {
    this.closedByClient = true;
    this.readyState = 3;
  }
}
