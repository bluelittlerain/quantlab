from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quant_lab.application.hk_exports import build_hk_export_bundle  # noqa: E402
from quant_lab.application.hk_smoke import run_offline_hk_smoke  # noqa: E402

OUTPUT = ROOT / "examples" / "hk-sma-fixed"
EXPECTED_RUN_ID = "ed34a165606e87cf"
EXPECTED_DATA_SHA256 = "6e6c98c856e19db59e4bfc4087278f232f6be3acb5d6c998153d0b07e7ea7276"


def main() -> None:
    result = run_offline_hk_smoke()
    if result["run_id"] != EXPECTED_RUN_ID:
        raise RuntimeError("The fixed HK example run_id changed.")
    if result["market_data"]["data_sha256"] != EXPECTED_DATA_SHA256:
        raise RuntimeError("The fixed HK example data fingerprint changed.")

    bundle = build_hk_export_bundle(result)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, payload in (
        ("report.html", bundle.report_html),
        ("trades.csv", bundle.trades_csv),
        ("manifest.json", bundle.manifest_json),
    ):
        (OUTPUT / name).write_bytes(payload)


if __name__ == "__main__":
    main()
