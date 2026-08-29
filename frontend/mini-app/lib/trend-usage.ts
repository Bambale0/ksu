export function trendUsageLabel(value?: number | null): string {
  const parsed = Number(value ?? 0);
  const count = Number.isFinite(parsed) ? Math.max(0, Math.trunc(parsed)) : 0;
  const mod100 = count % 100;
  const mod10 = count % 10;

  const noun = mod100 >= 11 && mod100 <= 14
    ? "запусков"
    : mod10 === 1
      ? "запуск"
      : mod10 >= 2 && mod10 <= 4
        ? "запуска"
        : "запусков";

  return `🔥 ${count.toLocaleString("ru-RU")} ${noun}`;
}
