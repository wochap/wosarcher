// The Report screen's downloads: three buttons on desktop, one "Download" menu on a phone.
// Markdown is built in the browser; PDF and DOCX are converted by the server.
import {
  CaretDown,
  CircleNotch,
  DownloadSimple,
  FileDoc,
  FilePdf,
  FileText,
  type Icon,
} from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import type { ExportFormat } from "../../api/client";
import { useApi, useUi } from "../../app/context";
import css from "./Downloads.module.css";
import { download } from "./exportReport";

type Ext = "md" | ExportFormat;
const FORMATS: { ext: Ext; desc: string; icon: Icon }[] = [
  { ext: "md", desc: "Markdown", icon: FileText },
  { ext: "pdf", desc: "PDF", icon: FilePdf },
  { ext: "docx", desc: "Word", icon: FileDoc },
];

export function Downloads({
  runId,
  markdown,
}: {
  runId: string;
  /** Saves `<run id>.md`; resolves once saved or failed. */
  markdown: () => Promise<void>;
}) {
  const api = useApi();
  const { toast, isPhone } = useUi();
  const [busy, setBusy] = useState<ExportFormat[]>([]);
  const [open, setOpen] = useState(false);
  const menu = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const outside = (e: PointerEvent) => {
      if (!menu.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  async function go(ext: Ext) {
    setOpen(false);
    if (ext === "md") return markdown();
    setBusy((b) => [...b, ext]);
    try {
      download(`${runId}.${ext}`, await api.exportRun(runId, ext));
      toast(`Downloaded ${runId}.${ext}`);
    } catch (e) {
      toast((e as Error).message, { error: true });
    } finally {
      setBusy((b) => b.filter((f) => f !== ext));
    }
  }

  if (!isPhone) {
    return FORMATS.map(({ ext }) => {
      const exporting = (busy as Ext[]).includes(ext);
      return (
        <button
          key={ext}
          type="button"
          className="btn btn-secondary"
          disabled={exporting}
          aria-busy={exporting}
          onClick={() => void go(ext)}
        >
          {exporting ? (
            <CircleNotch className="spin" aria-hidden="true" />
          ) : (
            <DownloadSimple aria-hidden="true" />
          )}
          {exporting ? "Exporting…" : `Download .${ext}`}
        </button>
      );
    });
  }

  const exporting = busy.length > 0;
  return (
    <div ref={menu} className={css.anchor}>
      <button
        type="button"
        className="btn btn-secondary"
        aria-haspopup="menu"
        aria-expanded={open}
        disabled={exporting}
        aria-busy={exporting}
        onClick={() => setOpen(!open)}
      >
        {exporting ? (
          <CircleNotch className="spin" aria-hidden="true" />
        ) : (
          <DownloadSimple aria-hidden="true" />
        )}
        {exporting ? "Exporting…" : "Download"}
        <CaretDown className={css.caret} aria-hidden="true" />
      </button>
      {open && !exporting && (
        <div role="menu" aria-label="Download format" className={css.menu}>
          {FORMATS.map(({ ext, desc, icon: FileIcon }) => (
            <button
              key={ext}
              type="button"
              role="menuitem"
              className={css.item}
              onClick={() => void go(ext)}
            >
              <FileIcon className={css.fileIcon} aria-hidden="true" />
              <span className={css.ext}>.{ext}</span>
              <span className={css.desc}>{desc}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
