// Vite build plugin: renders scripts/icon-tile.svg to the PNG head icons
// (apple-touch-icon and the manifest icons) so no PNG is committed.
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { initWasm, Resvg } from "@resvg/resvg-wasm";

const require = createRequire(import.meta.url);
const tile = resolve(dirname(fileURLToPath(import.meta.url)), "icon-tile.svg");

export const ICONS = [
  { fileName: "apple-touch-icon.png", size: 180 },
  { fileName: "icon-192.png", size: 192 },
  { fileName: "icon-512.png", size: 512 },
];

let ready;
function init() {
  ready ??= readFile(require.resolve("@resvg/resvg-wasm/index_bg.wasm")).then(initWasm);
  return ready;
}

/** Renders the tile at each icon size; returns `{ fileName, size, png }`. */
export async function renderIcons() {
  await init();
  const svg = await readFile(tile, "utf8");
  return ICONS.map(({ fileName, size }) => {
    const resvg = new Resvg(svg, { fitTo: { mode: "width", value: size } });
    const png = resvg.render().asPng();
    return { fileName, size, png };
  });
}

export function icons() {
  return {
    name: "wosarcher-icons",
    apply: "build",
    async generateBundle() {
      for (const { fileName, png } of await renderIcons()) {
        this.emitFile({ type: "asset", fileName, source: png });
      }
    },
  };
}
