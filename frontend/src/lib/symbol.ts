import type { SymbolView } from "../api/types";

export function symbolLabel(symbol: SymbolView): string {
  const name = symbol.local_alias?.trim() || symbol.display_name?.trim();
  if (name) return `${symbol.normalized_symbol} ${name}`;
  if (symbol.normalized_symbol === "2800.HK") return "2800.HK 盈富基金";
  return symbol.normalized_symbol;
}
