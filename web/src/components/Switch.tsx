// The prototype's on/off switch: a button with `role="switch"`, named by `label` or `labelledBy`.
import css from "./Switch.module.css";

type Props = {
  on: boolean;
  onToggle: () => void;
  label?: string;
  /** The ID of the visible label, when it is not `label`. */
  labelledBy?: string;
};

export function Switch({ on, onToggle, label, labelledBy }: Props) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      aria-labelledby={labelledBy}
      className={css.switch}
      onClick={onToggle}
    >
      <span className={css.knob} />
    </button>
  );
}
