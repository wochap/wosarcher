import { describe, expect, it } from "vitest";
import type { RunDetail } from "../api/types";
import { providers } from "../test/fixtures/data";
import {
  changedCount,
  edit,
  type ForkContext,
  type ForkValues,
  forkModelBase,
  forkModelPatch,
  initialState,
  pickEntry,
  reset,
  sourceOf,
} from "./forkModel";

const detail = {
  run_id: "r_1",
  use: { llm: "omniroute" },
  model: "research-smart",
  request: {
    settings: {
      llm: {
        model: "research-smart",
        context_window: 1048576,
        max_output_tokens: 32768,
        reasoning: { write: "medium", extract: "low" },
      },
      select: { max_context_tokens: "auto" },
    },
  },
} as unknown as RunDetail;
const context: ForkContext = { profile: undefined, entries: providers.entries, step: "write" };
const base: ForkValues = forkModelBase(detail, "write");

describe("fork model group", () => {
  it("reads the base from the run", () => {
    expect(base).toEqual({
      llm: "omniroute",
      model: "research-smart",
      context_window: 1048576,
      max_output_tokens: 32768,
      effort: "medium",
      context_tokens: "auto",
    });
    expect(forkModelBase(detail, "extract").effort).toBe("low");
  });

  it("refills the unedited values for another model and sends only the model", () => {
    const state = edit(initialState(base), base, context, "model", "gemma-3-12b");
    expect(state.values).toMatchObject({
      context_window: 32768,
      max_output_tokens: 8192,
      effort: "none",
    });
    expect(sourceOf(state, "model", context)).toBe("edited");
    expect(sourceOf(state, "context_window", context)).toBe("");
    expect(forkModelPatch(state, base, "write")).toEqual({ llm: { model: "gemma-3-12b" } });
  });

  it("takes the default model and the entry's values for another entry", () => {
    const state = pickEntry(initialState(base), context, "agents");
    expect(state.values).toMatchObject({
      model: "qwen3-14b",
      context_window: 32768,
      max_output_tokens: 8192,
    });
    expect(sourceOf(state, "context_window", context)).toBe("from entry");
    expect(forkModelPatch(state, base, "write")).toEqual({ use: { llm: "agents" } });
  });

  it("keeps an edited limit across a model change", () => {
    let state = edit(initialState(base), base, context, "context_window", 65536);
    state = edit(state, base, context, "model", "gemma-3-12b");
    expect(state.values.context_window).toBe(65536);
    expect(state.values.max_output_tokens).toBe(8192);
    expect(sourceOf(state, "context_window", context)).toBe("edited");
    expect(forkModelPatch(state, base, "write")).toEqual({
      llm: { model: "gemma-3-12b", context_window: 65536 },
    });
  });

  it("resets the entry to the base entry and model", () => {
    let state = pickEntry(initialState(base), context, "agents");
    state = reset(state, base, context, "llm");
    expect(state.values).toEqual(base);
    expect(changedCount(state, base)).toBe(0);
    expect(forkModelPatch(state, base, "write")).toEqual({});
  });

  it("sends the step's thinking and the context budget when edited", () => {
    let state = edit(initialState(base), base, context, "effort", "high");
    state = edit(state, base, context, "context_tokens", 40000);
    expect(changedCount(state, base)).toBe(2);
    expect(forkModelPatch(state, base, "write")).toEqual({
      llm: { context_tokens: 40000, reasoning: { write: "high" } },
    });
  });

  it("drops an edit that returns to the base", () => {
    let state = edit(initialState(base), base, context, "context_window", 65536);
    state = edit(state, base, context, "context_window", 1048576);
    expect(state.edited.size).toBe(0);
  });
});
