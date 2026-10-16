import { act, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import type { ContinueRequest } from "../../api/types";
import { initialRunView, runReducer } from "../../run/reducer";
import { ev } from "../../test/events";
import { callsTo, fakeApi } from "../../test/fakeApi";
import {
  answeredEvent,
  clarifyLog,
  finishedTimeout,
  liveClarify,
  liveRoundInput,
  needed,
} from "../../test/fixtures/questions";
import { type Fixture, RUN_ID, summary } from "../../test/fixtures/sample";
import { renderWithHelp } from "../../test/help";
import { openScenario, play, socketsFor } from "../../test/scenario";
import { QuestionCard } from "./QuestionCard";
import { useQuestionCard } from "./useQuestionCard";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const card = () => screen.getByRole("region", { name: "Run questions" });
const radio = (name: string | RegExp) => screen.getByRole<HTMLInputElement>("radio", { name });
const checkbox = (name: string | RegExp) =>
  screen.getByRole<HTMLInputElement>("checkbox", { name });
const click = (name: string) =>
  act(() => {
    fireEvent.click(screen.getByRole("button", { name }));
  });

describe("question card", () => {
  it("shows the clarify pause with the recommended answers preselected", async () => {
    const { api } = await openScenario(liveClarify);
    expect(within(card()).getByRole("heading", { name: "Before searching" })).toBeTruthy();
    expect(within(card()).getByRole("img", { name: "Question 1 of 4" }).textContent).toBe("1 / 4");
    expect(
      within(card()).getByText(
        `I read the brief as: Peru executive branch: ministries, attached agencies, current heads`,
      ),
    ).toBeTruthy();
    expect(within(card()).getByText("Include regional and local governments?")).toBeTruthy();
    expect(radio(/^Yes, at summary depth/).checked).toBe(true);
    expect(within(card()).getAllByText("recommended")).toHaveLength(1);
    expect(within(card()).getByRole("radiogroup")).toBeTruthy();
    expect(within(card()).getByRole("button", { name: /Waiting for you/ })).toBeTruthy();
    expect(screen.getByText("Waiting")).toBeTruthy();
    expect(callsTo(api, "continueRun")).toEqual([]);
    // Presence goes out when the card opens.
    expect(socketsFor(RUN_ID)[0].sent).toContain(JSON.stringify({ type: "presence" }));
  });

  it("steps through the questions and keeps answers for Back", async () => {
    await openScenario(liveClarify);
    act(() => {
      fireEvent.click(radio(/^No/));
    });
    click("Next");
    expect(within(card()).getByRole("img", { name: "Question 2 of 4" }).textContent).toBe("2 / 4");
    expect(within(card()).getByRole("group")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Back" }) as HTMLButtonElement).disabled).toBe(
      false,
    );
    click("Back");
    expect(radio(/^No/).checked).toBe(true);
    expect(radio(/^Yes/).checked).toBe(false);
    // The Plan card waits and counts the questions answered so far.
    const plan = within(screen.getByRole("list", { name: "Phases" }))
      .getByText("Plan")
      .closest("li");
    expect(plan?.dataset.state).toBe("asking");
    expect(plan?.textContent).toContain("waiting for you");
  });

  it("shows 0 of 4 answered, then 1 of 4 on the second question", async () => {
    await openScenario(liveClarify);
    const plan = () =>
      within(screen.getByRole("list", { name: "Phases" }))
        .getByText("Plan")
        .closest("li");
    expect(plan()?.textContent).toContain("0 of 4 answered");
    click("Next");
    expect(plan()?.textContent).toContain("1 of 4 answered");
  });

  it("selects Other by typing and sends it as other", async () => {
    const { api } = await openScenario(liveClarify);
    click("Next");
    const other = screen.getByLabelText("Other: your own answer");
    expect((screen.getByLabelText("Other") as HTMLInputElement).checked).toBe(false);
    act(() => {
      fireEvent.change(other, { target: { value: "Congress site" } });
    });
    expect((screen.getByLabelText("Other") as HTMLInputElement).checked).toBe(true);
    expect(checkbox(/^gob\.pe/).checked).toBe(true);
    click("Next");
    click("Next");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    });
    const [id, body] = callsTo(api, "continueRun")[0] as [string, ContinueRequest];
    expect(id).toBe(RUN_ID);
    expect(body).toEqual({
      pause_id: 1,
      answers: [
        { question_id: "q1", option_ids: ["o1"] },
        { question_id: "q2", option_ids: ["o1"], other: "Congress site" },
        { question_id: "q3", option_ids: ["o1"] },
        { question_id: "q4", option_ids: ["o1"] },
      ],
    });
  });

  it("picks with the keys 1 to 9 and moves on with Enter", async () => {
    await openScenario(liveClarify);
    act(() => {
      fireEvent.keyDown(document.body, { key: "2" });
    });
    expect(radio(/^No/).checked).toBe(true);
    act(() => {
      fireEvent.keyDown(document.body, { key: "Enter" });
    });
    expect(within(card()).getByRole("img", { name: "Question 2 of 4" })).toBeTruthy();
    // 4 is the Other row of this question: it is selected and focused.
    act(() => {
      fireEvent.keyDown(document.body, { key: "4" });
    });
    expect((screen.getByLabelText("Other") as HTMLInputElement).checked).toBe(true);
    expect(document.activeElement).toBe(screen.getByLabelText("Other: your own answer"));
    // Typing digits in the Other input types them.
    act(() => {
      fireEvent.keyDown(document.activeElement as Element, { key: "3" });
    });
    expect(checkbox(/^Wikipedia/).checked).toBe(false);
  });

  it("posts the recommendations for the rest and the answers so far", async () => {
    const { api } = await openScenario(liveClarify);
    act(() => {
      fireEvent.click(radio(/^No/));
    });
    click("Next");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Use recommended for the rest" }));
    });
    const [, body] = callsTo(api, "continueRun")[0] as [string, ContinueRequest];
    expect(body.answers.map((a) => a.option_ids)).toEqual([["o2"], ["o1"], ["o1"], ["o1"]]);
  });

  it("shows the server's detail under the footer and keeps the card", async () => {
    const api = fakeApi(liveClarify.data);
    api.continueRun = async () => {
      throw new ApiError(422, "invalid_request", "answers: unknown option 'o9' for q2");
    };
    await openScenario(liveClarify, { api });
    click("Next");
    click("Next");
    click("Next");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    });
    expect(within(card()).getByRole("alert").textContent).toBe(
      "answers: unknown option 'o9' for q2",
    );
    expect(within(card()).getByRole("img", { name: "Question 4 of 4" })).toBeTruthy();
  });

  it("closes on input.answered, also when answered elsewhere, and notes the answers", async () => {
    await openScenario(liveClarify);
    click("Next");
    click("Next");
    await play(RUN_ID, [answeredEvent(5, "agent", 4, { seconds: 12 }, "plan")]);
    expect(screen.queryByRole("region", { name: "Run questions" })).toBeNull();
    const plan = within(screen.getByRole("list", { name: "Phases" }))
      .getByText("Plan")
      .closest("li");
    expect(plan?.dataset.state).not.toBe("asking");
    expect(plan?.textContent).toContain("4 answers");
    expect(screen.getByText("Running")).toBeTruthy();
  });

  it("titles a round pause and shows it above the grid with the Gap card waiting", async () => {
    await openScenario(liveRoundInput);
    expect(within(card()).getByRole("heading", { name: "After round 2" })).toBeTruthy();
    expect(within(card()).getByText("Search these next?")).toBeTruthy();
    expect(checkbox(/^site:gob\.pe/).checked).toBe(true);
    const gap = within(screen.getByRole("list", { name: "Phases" }))
      .getByText("Gap")
      .closest("li");
    expect(gap?.dataset.state).toBe("asking");
    expect(gap?.textContent).toContain("0 of 2 answered");
    click("Next");
    click("Continue");
  });

  it("replaces the Progress tab content on a phone", async () => {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query.includes("max-width"),
      addEventListener() {},
      removeEventListener() {},
    }));
    await openScenario(liveClarify);
    expect(card()).toBeTruthy();
    expect(screen.queryByRole("list", { name: "Phases" })).toBeNull();
    act(() => {
      fireEvent.click(screen.getByRole("tab", { name: /Sources/ }));
    });
    expect(screen.queryByRole("region", { name: "Run questions" })).toBeNull();
  });
});

describe("timeline notes", () => {
  it("shows the timeout note on the Gap card and under round 2", async () => {
    await openScenario(finishedTimeout);
    const note = "continued with recommended answers after 1:00";
    const gap = within(screen.getByRole("list", { name: "Phases" }))
      .getByText("Gap")
      .closest("li");
    const detail = within(gap as HTMLElement).getByText(note);
    expect(detail.getAttribute("data-tone")).toBe("warn");
    const rounds = screen.getByRole("region", { name: "Research rounds" });
    expect(within(rounds).getByText(note).getAttribute("data-tone")).toBe("warn");
    expect(screen.queryByRole("region", { name: "Run questions" })).toBeNull();
  });
});

describe("catalog pauses", () => {
  const events = (kind: "clarify" | "round", stage: string) => [
    ev(
      1,
      "run.started",
      { query: "b", kind: "catalog", profile: "p", parent_run_id: null, version: 1, until: null },
      null,
      RUN_ID,
    ),
    needed(2, kind, { after: 3 }, stage),
  ];
  const fixture = (kind: "clarify" | "round", stage: string): Fixture => ({
    screen: "live",
    runId: RUN_ID,
    data: {
      runs: [summary({ status: "waiting", kind: "catalog", duration_s: null, cost: null })],
      events: { [RUN_ID]: events(kind, stage) },
    },
  });

  it("waits on the Draft card before the structure", async () => {
    await openScenario(fixture("clarify", "draft"));
    expect(within(card()).getByRole("heading", { name: "Before searching" })).toBeTruthy();
    const draft = within(screen.getByRole("list", { name: "Phases" }))
      .getByText("Draft")
      .closest("li");
    expect(draft?.dataset.state).toBe("asking");
    expect(draft?.textContent).toContain("0 of 4 answered");
  });

  it("titles a wave pause and waits on the Extract card", async () => {
    await openScenario(fixture("round", "extract"));
    expect(within(card()).getByRole("heading", { name: "After wave 3" })).toBeTruthy();
    const extract = within(screen.getByRole("list", { name: "Phases" }))
      .getByText("Extract")
      .closest("li");
    expect(extract?.dataset.state).toBe("asking");
    await play(RUN_ID, [answeredEvent(3, "timeout", 2, { seconds: 75 }, "extract")]);
    expect(extract?.dataset.state).not.toBe("asking");
    expect(extract?.textContent).toContain("continued with recommended answers after 1:15");
  });
});

/** The card on its own, fed the clarify pause, to run its timers on fake clocks. */
function Harness({ presence, timeout }: { presence: () => void; timeout: number }) {
  const pause = clarifyLog({ timeout }).reduce(runReducer, initialRunView("r")).pause;
  const state = useQuestionCard(pause, async () => {});
  return state ? <QuestionCard card={state} onPresence={presence} /> : null;
}

describe("timeout chip", () => {
  it("counts down from the full timeout once idle and resets on activity", () => {
    vi.useFakeTimers();
    const presence = vi.fn();
    renderWithHelp(<Harness presence={presence} timeout={60} />);
    const chip = () => within(card()).getByRole("button", { name: /Timeout/ });
    expect(chip().textContent).toBe("waiting for you");
    act(() => {
      vi.advanceTimersByTime(10_000);
    });
    expect(chip().textContent).toBe("1:00");
    expect(chip().getAttribute("aria-label")).toBe(
      "Continues with recommended answers in 1:00. Help: Timeout",
    );
    act(() => {
      vi.advanceTimersByTime(13_000);
    });
    expect(chip().textContent).toBe("0:47");
    expect(presence).toHaveBeenCalledTimes(1);
    act(() => {
      window.dispatchEvent(new Event("pointermove"));
    });
    expect(chip().textContent).toBe("waiting for you");
    expect(presence).toHaveBeenCalledTimes(2);
    act(() => {
      vi.advanceTimersByTime(10_000);
    });
    expect(chip().textContent).toBe("1:00");
  });

  it("draws the 3px line full while active, draining when idle, full again on activity", () => {
    vi.useFakeTimers();
    const { container } = renderWithHelp(<Harness presence={() => {}} timeout={60} />);
    const fill = () => container.querySelector<HTMLElement>('[class*="fill"]');
    expect(container.querySelector('[class*="track"]')).toBeTruthy();
    expect(fill()?.style.width).toBe("100%");
    act(() => {
      vi.advanceTimersByTime(10_000);
    });
    expect(fill()?.style.width).toBe("100%");
    act(() => {
      vi.advanceTimersByTime(30_000);
    });
    const idle = Number.parseFloat(fill()?.style.width ?? "100");
    expect(idle).toBeLessThan(100);
    act(() => {
      window.dispatchEvent(new Event("pointermove"));
    });
    expect(fill()?.style.width).toBe("100%");
  });

  it("draws no line for a timeout of 0", () => {
    vi.useFakeTimers();
    const { container } = renderWithHelp(<Harness presence={() => {}} timeout={0} />);
    expect(container.querySelector('[class*="track"]')).toBeNull();
  });

  it("shows no chip for a timeout of 0", () => {
    vi.useFakeTimers();
    renderWithHelp(<Harness presence={() => {}} timeout={0} />);
    expect(within(card()).queryByRole("button", { name: /Timeout/ })).toBeNull();
  });
});
