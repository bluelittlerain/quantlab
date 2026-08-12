const hkdFormatter = new Intl.NumberFormat("zh-HK", {
  style: "currency",
  currency: "HKD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const numberFormatter = new Intl.NumberFormat("zh-CN", {
  maximumFractionDigits: 2,
});

export function formatHKD(value: number): string {
  return hkdFormatter.format(value).replace("HK$", "HK$ ");
}

export function formatPercent(value: number | null): string {
  if (value === null) return "N/A";
  return `${(value * 100).toFixed(2)}%`;
}

export function formatNumber(value: number): string {
  return numberFormatter.format(value);
}
