import { explicitAspectRatioOptions, type AspectRatioOptions } from "@/lib/aspect-ratio";

export function AspectRatioSelect({ options, value, onChange, disabled = false }: {
  options: AspectRatioOptions;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  const values = explicitAspectRatioOptions(options.aspect_ratio_options);
  if (!values.length) return null;
  return <label className="field">
    <span className="label">Соотношение сторон{options.aspect_ratio_required ? " *" : ""}</span>
    <select className="control" value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
      <option value="">Выберите</option>
      {values.map((ratio) => <option key={ratio} value={ratio}>{ratio}</option>)}
    </select>
  </label>;
}
