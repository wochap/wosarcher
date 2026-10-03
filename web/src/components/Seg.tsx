// Nocturne segmented radio group (`.seg`), as the prototype's options, filters, and tones.
type Option<T extends string> = { value: T; label: string };

type Props<T extends string> = {
  label: string;
  name: string;
  value: T;
  options: Option<T>[];
  onChange: (value: T) => void;
  disabled?: boolean;
};

export function Seg<T extends string>({
  label,
  name,
  value,
  options,
  onChange,
  disabled,
}: Props<T>) {
  return (
    <div className="seg" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <label key={o.value} className="seg-opt">
          <input
            type="radio"
            name={name}
            checked={value === o.value}
            disabled={disabled}
            onChange={() => onChange(o.value)}
          />
          {o.label}
        </label>
      ))}
    </div>
  );
}
