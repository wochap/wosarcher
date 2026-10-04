import { describe, expect, it } from "vitest";
import { HELP, helpFor } from "./help";

describe("help texts", () => {
  it("copies the prototype's texts", () => {
    expect(HELP.recipe.body).toBe(
      "Report writes a cited report. Context stops after selecting passages and returns them with sources and scores, for agents or your own answer. Faster and cheaper.",
    );
    expect(HELP["ph-select"].body).toBe(
      "Picks the best passages that fit the writer's context budget.",
    );
    expect(HELP.scorer).toEqual({
      title: "Scorer",
      body: "Which scorer ranked the passages. “fallback” means the configured scorer failed and a simpler one took over.",
      example: "jev · rerank · bm25 · fallback",
    });
  });

  it("composes the waiting phase entry", () => {
    expect(helpFor("wait-score")).toEqual({
      title: "Score · waiting for GPU",
      body: "Another model is unloading from the same GPU. This stage starts when it is free. Rates how useful each passage is for its question.",
    });
  });

  it("composes the retry entry for stages other than score", () => {
    expect(helpFor("retry-fetch")).toEqual({
      title: "Retry from Fetch",
      body: "Reruns fetch and the stages after it on the saved results of earlier stages.",
    });
    expect(helpFor("retry").title).toBe("Retry from Score");
  });
});
