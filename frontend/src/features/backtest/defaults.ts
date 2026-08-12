import type { HKCostInput } from "../../api/types";

export const DEFAULT_HK_COSTS: HKCostInput = {
  broker_commission_rate: 0.00025,
  broker_minimum_commission: 100,
  stamp_duty_rate: 0.001,
  trading_fee_rate: 0.0000565,
  transaction_levy_rate: 0.000027,
  afrc_transaction_levy_rate: 0.0000015,
  settlement_fee_rate: 0.000042,
  slippage_rate: 0.0005,
};

export const DEFAULT_BENCHMARK_COSTS: HKCostInput = {
  ...DEFAULT_HK_COSTS,
  stamp_duty_rate: 0,
};
