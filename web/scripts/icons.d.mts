import type { Plugin } from "vite";

export const ICONS: { fileName: string; size: number }[];
export function renderIcons(): Promise<{ fileName: string; size: number; png: Uint8Array }[]>;
export function icons(): Plugin;
