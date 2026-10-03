// Stand-in for the run screens until `frontend-run` builds them: only the title.
import css from "./Placeholder.module.css";

export function Placeholder({ title }: { title: string }) {
  return (
    <div className={css.page}>
      <div className={css.inner}>
        <h1 className={css.title}>{title}</h1>
      </div>
    </div>
  );
}
