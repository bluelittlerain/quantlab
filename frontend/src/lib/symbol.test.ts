import { describe, expect, it } from "vitest";

import type { SymbolView } from "../api/types";
import { symbolLabel } from "./symbol";

function symbol(normalized_symbol: string, display_name: string | null = null): SymbolView {
  return {
    normalized_symbol,
    exchange: "HKEX",
    currency: "HKD",
    display_name,
    local_alias: null,
  };
}

describe("symbolLabel", () => {
  it("names the default tradable benchmark without calling it an index", () => {
    expect(symbolLabel(symbol("2800.HK"))).toBe("2800.HK 盈富基金");
  });

  it("does not mislabel a custom benchmark as 盈富基金", () => {
    expect(symbolLabel(symbol("3033.HK"))).toBe("3033.HK");
  });

  it("uses provider metadata when a reliable name is available", () => {
    expect(symbolLabel(symbol("3033.HK", "南方恒生科技"))).toBe("3033.HK 南方恒生科技");
  });
});
