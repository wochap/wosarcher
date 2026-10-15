// The "1a Distill" mark from design/project/Wosarcher Icon.dc.html. The stroke and
// dot get heavier as the mark gets smaller, as the icon file specifies.
type Props = {
  size: number;
  className?: string;
};

function weight(size: number): { stroke: number; dot: number } {
  if (size <= 16) return { stroke: 3.4, dot: 2.6 };
  if (size <= 24) return { stroke: 3, dot: 2.4 };
  if (size <= 40) return { stroke: 2.6, dot: 2 };
  return { stroke: 2.4, dot: 2 };
}

export function BrandMark({ size, className }: Props) {
  const { stroke, dot } = weight(size);
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      stroke="currentColor"
      strokeWidth={stroke}
      strokeLinecap="round"
      aria-hidden="true"
    >
      <path d="M5 8h22M9 15h14M13 22h6" />
      <circle cx="16" cy="28" r={dot} fill="currentColor" stroke="none" />
    </svg>
  );
}
