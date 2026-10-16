import { describe, expect, it } from "vitest";
import type { RunEvent } from "../api/types";
import {
  answeredEvent,
  CLARIFY,
  clarifyLog,
  needed,
  ROUND,
  roundLog,
} from "../test/fixtures/questions";
import {
  answered,
  answeredNote,
  askState,
  clock,
  continueBody,
  pauseTitle,
  pickOption,
  recommended,
  startDrafts,
  toAnswer,
  toggleOther,
  typeOther,
} from "./questions";
import { initialRunView, type OpenPause, runReducer } from "./reducer";

const fold = (events: RunEvent[]) => events.reduce(runReducer, initialRunView("r_8c21"));

function openPause(): OpenPause {
  const pause = fold(clarifyLog()).pause;
  if (!pause) throw new Error("no pause");
  return pause;
}

describe("pause events in the reducer", () => {
  it("opens the card on input.needed and marks the run waiting", () => {
    const state = fold(clarifyLog({ timeout: 90 }));
    expect(state.status).toBe("waiting");
    expect(state.pause).toMatchObject({
      pauseId: 1,
      kind: "clarify",
      stage: "plan",
      after: null,
      timeout: 90,
      maxWait: 1800,
    });
    expect(state.pause?.questions).toHaveLength(4);
    expect(pauseTitle(state.pause as OpenPause)).toBe("Before searching");
  });

  it("closes it on input.answered, whoever answered, and keeps the note", () => {
    const state = fold([...clarifyLog(), answeredEvent(5, "agent", 4, { seconds: 12 })]);
    expect(state.status).toBe("running");
    expect(state.pause).toBeNull();
    expect(state.answered).toEqual([
      {
        pauseId: 1,
        kind: "clarify",
        stage: "plan",
        after: null,
        count: 4,
        answeredBy: "agent",
        secondsWaited: 12,
      },
    ]);
  });

  it("titles a round pause by its round, or its wave in a catalog run", () => {
    const round = fold(roundLog()).pause as OpenPause;
    expect(round).toMatchObject({ kind: "round", stage: "gap", after: 2 });
    expect(pauseTitle(round)).toBe("After round 2");
    expect(pauseTitle({ ...round, stage: "extract", after: 3 })).toBe("After wave 3");
  });

  it("clears the pause when the run ends", () => {
    const cancelled = runReducer(fold(clarifyLog()), {
      seq: 5,
      type: "run.cancelled",
      data: { stage: "plan" },
      stage: null,
      run_id: "r_8c21",
      ts: "2026-10-03T14:00:05Z",
    } as RunEvent);
    expect(cancelled.status).toBe("cancelled");
    expect(cancelled.pause).toBeNull();
  });
});

describe("answer state", () => {
  const [confirm, multi, single] = CLARIFY;

  it("preselects the recommended options", () => {
    expect(recommended(confirm)).toEqual({ picked: ["o1"], other: "", otherOn: false });
    expect(startDrafts(ROUND)[0].picked).toEqual(["o1", "o2", "o3"]);
  });

  it("replaces the choice for confirm and single, toggles for multi", () => {
    expect(pickOption(confirm, recommended(confirm), "o2").picked).toEqual(["o2"]);
    expect(pickOption(single, recommended(single), "o3").picked).toEqual(["o3"]);
    const draft = recommended(multi);
    const two = pickOption(multi, draft, "o2");
    expect(two.picked).toEqual(["o1", "o2"]);
    expect(pickOption(multi, two, "o1").picked).toEqual(["o2"]);
  });

  it("selects Other by typing: it replaces a single choice and joins a multi one", () => {
    const one = typeOther(confirm, recommended(confirm), "Only the south");
    expect(one).toEqual({ picked: [], other: "Only the south", otherOn: true });
    const many = typeOther(multi, recommended(multi), "Congress");
    expect(many).toEqual({ picked: ["o1"], other: "Congress", otherOn: true });
    expect(typeOther(multi, many, "  ").otherOn).toBe(false);
    expect(toAnswer(multi, many)).toEqual({
      question_id: "q2",
      option_ids: ["o1"],
      other: "Congress",
    });
  });

  it("needs an option or non-blank Other text", () => {
    expect(answered({ picked: [], other: "", otherOn: false })).toBe(false);
    expect(answered(toggleOther(confirm, { picked: [], other: "  ", otherOn: false }))).toBe(false);
    expect(answered({ picked: [], other: "x", otherOn: true })).toBe(true);
  });

  it("builds the continue body from every question", () => {
    const pause = openPause();
    const drafts = startDrafts(pause.questions);
    drafts[0] = pickOption(confirm, drafts[0], "o2");
    expect(continueBody(pause, drafts)).toEqual({
      pause_id: 1,
      answers: [
        { question_id: "q1", option_ids: ["o2"] },
        { question_id: "q2", option_ids: ["o1"] },
        { question_id: "q3", option_ids: ["o1"] },
        { question_id: "q4", option_ids: ["o1"] },
      ],
    });
  });

  it("fills the questions after the current one with the recommendations", () => {
    const pause = openPause();
    const drafts = startDrafts(pause.questions);
    drafts[0] = pickOption(confirm, drafts[0], "o2");
    drafts[2] = pickOption(single, drafts[2], "o3");
    const body = continueBody(pause, drafts, { index: 1 });
    expect(body.answers.map((a) => a.option_ids)).toEqual([["o2"], ["o1"], ["o1"], ["o1"]]);
  });
});

describe("notes", () => {
  it("reads the answers count or the timeout, from the events", () => {
    const user = fold([...clarifyLog(), answeredEvent(5, "user", 4)]).answered[0];
    expect(answeredNote(user)).toBe("4 answers");
    const timed = fold([...clarifyLog(), answeredEvent(5, "timeout", 4, { seconds: 60 })])
      .answered[0];
    expect(answeredNote(timed)).toBe("continued with recommended answers after 1:00");
    expect(clock(59.2)).toBe("1:00");
    expect(clock(0)).toBe("0:00");
  });

  it("derives the waiting card, stage notes, and round notes", () => {
    const waiting = askState(fold(clarifyLog()), 2);
    expect(waiting.waiting).toEqual({ stage: "plan", answered: 2, total: 4 });
    const after = fold([...clarifyLog(), answeredEvent(5, "timeout", 4, { seconds: 60 })]);
    const state = askState(after, 0);
    expect(state.waiting).toBeNull();
    expect(state.stages.plan).toEqual({
      text: "continued with recommended answers after 1:00",
      warn: true,
    });
    expect(state.rounds[1].warn).toBe(true);
    expect(needed(9, "round").seq).toBe(9);
  });
});
