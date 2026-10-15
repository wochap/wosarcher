import { renderIcons } from "./icons.mjs";

const SIGNATURE = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];

describe("renderIcons", () => {
  it("renders a PNG at each icon size", async () => {
    const icons = await renderIcons();
    expect(icons.map((i) => i.fileName)).toEqual([
      "apple-touch-icon.png",
      "icon-192.png",
      "icon-512.png",
    ]);
    for (const { size, png } of icons) {
      expect([...png.subarray(0, 8)]).toEqual(SIGNATURE);
      const ihdr = Buffer.from(png.subarray(8, 32));
      expect(ihdr.toString("ascii", 4, 8)).toBe("IHDR");
      expect([ihdr.readUInt32BE(8), ihdr.readUInt32BE(12)]).toEqual([size, size]);
    }
  });
});
