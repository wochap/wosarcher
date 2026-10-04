// The New run drop zone: drag and drop or browse for .md and .txt files, listed with size.
import { FileArrowUp, FileText, Warning, X } from "@phosphor-icons/react";
import { useRef, useState } from "react";
import { HelpTip } from "../../components/HelpTip";
import { fmtBytes } from "../../run/format";
import css from "./Attachments.module.css";

const ALLOWED = /\.(md|txt)$/i;

type Props = { files: File[]; onChange: (files: File[]) => void };

export function Attachments({ files, onChange }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [skipped, setSkipped] = useState("");

  function add(list: FileList | null) {
    const picked = [...(list ?? [])];
    const ok = picked.filter((f) => ALLOWED.test(f.name));
    const bad = picked.filter((f) => !ALLOWED.test(f.name));
    const names = new Set(files.map((f) => f.name));
    const added: File[] = [];
    for (const f of ok) {
      if (names.has(f.name)) continue;
      names.add(f.name);
      added.push(f);
    }
    onChange([...files, ...added]);
    setSkipped(
      bad.length
        ? `Skipped ${bad.map((f) => f.name).join(", ")} — only .md and .txt are supported.`
        : "",
    );
    setOver(false);
  }

  return (
    <div className={css.attachments}>
      <div className={css.label}>
        Attachments
        <HelpTip help="attach" />
      </div>
      {/* biome-ignore lint/a11y/useSemanticElements: the prototype's drop zone is a div with button role around a two-line description */}
      <div
        role="button"
        tabIndex={0}
        aria-label="Add .md or .txt files"
        className={css.drop}
        data-over={over}
        onClick={() => input.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            input.current?.click();
          }
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          add(e.dataTransfer.files);
        }}
      >
        <FileArrowUp className={css.icon} aria-hidden="true" />
        <div className={css.text}>
          <span>
            Drop <span className={css.ext}>.md</span> or <span className={css.ext}>.txt</span>{" "}
            files, or <span className={css.browse}>browse</span>
          </span>
          <span className={css.hint}>Chunked locally and searched alongside the web.</span>
        </div>
      </div>
      <input
        ref={input}
        type="file"
        accept=".md,.txt"
        multiple
        hidden
        data-testid="attachments-input"
        onChange={(e) => {
          add(e.target.files);
          e.target.value = "";
        }}
      />
      {skipped && (
        <div role="alert" className={css.error}>
          <Warning aria-hidden="true" />
          {skipped}
        </div>
      )}
      {files.length > 0 && (
        <ul className={css.list}>
          {files.map((f) => (
            <li key={f.name} className={css.file}>
              <FileText className={css.fileIcon} aria-hidden="true" />
              <span className={css.name}>{f.name}</span>
              <span className={css.size}>{fmtBytes(f.size)}</span>
              <button
                type="button"
                className={`btn btn-ghost btn-icon ${css.remove}`}
                aria-label={`Remove ${f.name}`}
                onClick={() => onChange(files.filter((x) => x.name !== f.name))}
              >
                <X aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
