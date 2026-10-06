// Outline tags for a run's thinking steps, after the depth tag; none when every step is none.
import type { ReasoningOptions } from "../api/types";
import { thinkingTags } from "../run/thinking";
import css from "./DepthTag.module.css";

export function ThinkingTag({
  reasoning,
}: {
  reasoning: Partial<ReasoningOptions> | null | undefined;
}) {
  return thinkingTags(reasoning).map((text) => (
    <span key={text} className={`tag tag-outline ${css.tag}`}>
      {text}
    </span>
  ));
}
