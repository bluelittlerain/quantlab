import type { BacktestRequest, BacktestResult } from "../api/types";

export function requestFromResult(result: BacktestResult): BacktestRequest {
  return {
    symbol: result.symbol.normalized_symbol,
    benchmark_symbol: result.benchmark.normalized_symbol,
    start_date: result.date_range.requested_start,
    end_date: result.date_range.requested_end,
    short_window: result.strategy.short_window,
    long_window: result.strategy.long_window,
    initial_capital: result.initial_capital,
    board_lot: { lot_size: result.board_lot.lot_size, confirmed: true },
    benchmark_board_lot: {
      lot_size: result.benchmark_board_lot.lot_size,
      confirmed: true,
    },
    costs: result.cost_config,
    benchmark_costs: result.benchmark_cost_config,
  };
}
