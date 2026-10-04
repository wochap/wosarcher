import { describe, expect, it } from "vitest";
import { placeHelp } from "./helpPlacement";

const viewport = { width: 1440, height: 900 };
const button = (left: number, top: number) => ({ left, top, bottom: top + 16, width: 16 });

describe("placeHelp", () => {
  it("centres below the button", () => {
    expect(placeHelp(button(400, 200), viewport)).toEqual({
      x: 272,
      y: 225,
      below: true,
      arrowX: 131,
    });
  });

  it("flips above near the bottom right and stays 8px inside (figure D)", () => {
    const place = placeHelp(button(1440 - 20 - 16, 900 - 30 - 16), viewport);
    expect(place.below).toBe(false);
    expect(place.y).toBe(900 - 30 - 16 - 9);
    expect(place.x + 272).toBe(1440 - 8);
    expect(place.arrowX).toBe(247);
  });
});
