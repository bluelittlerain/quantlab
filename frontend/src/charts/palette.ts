export interface ChartPalette {
  strategy: string;
  benchmark: string;
  excess: string;
  positive: string;
  negative: string;
  grid: string;
  text: string;
  muted: string;
}

export function chartPalette(dark: boolean): ChartPalette {
  return dark
    ? {
        strategy: "#6aa7ff",
        benchmark: "#4bd4a2",
        excess: "#f5c86b",
        positive: "#4bd4a2",
        negative: "#ff7b8c",
        grid: "#293749",
        text: "#e7edf6",
        muted: "#9dacbf",
      }
    : {
        strategy: "#1267e5",
        benchmark: "#13855c",
        excess: "#a66a00",
        positive: "#13855c",
        negative: "#ca3c4f",
        grid: "#dce5f0",
        text: "#26374d",
        muted: "#67778c",
      };
}
