// Nocturne `.tag` with the prototype's spacing; `variant` picks a Nocturne tag class.
import type { ReactNode } from "react";
import css from "./Tag.module.css";

type Props = {
  variant?: "neutral" | "accent" | "outline";
  small?: boolean;
  className?: string;
  children: ReactNode;
};

export function Tag({ variant, small, className, children }: Props) {
  const classes = ["tag", variant && `tag-${variant}`, small ? css.small : css.tag, className];
  return <span className={classes.filter(Boolean).join(" ")}>{children}</span>;
}
