// The outline tag that names a run's depth; a run with none reads Standard.
import { depthLabel } from "../run/depth";
import css from "./DepthTag.module.css";

export function DepthTag({ depth }: { depth: string | null | undefined }) {
  return <span className={`tag tag-outline ${css.tag}`}>{depthLabel(depth)}</span>;
}
