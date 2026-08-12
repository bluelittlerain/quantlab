from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from quant_lab.storage.sqlite import SCHEMA_VERSION, SQLiteRepository


class HKStorageTests(unittest.TestCase):
    def test_schema_and_local_crud(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = SQLiteRepository(Path(directory) / "quantlab.db")
            self.assertEqual(SCHEMA_VERSION, 1)
            self.assertEqual(repository.get_settings(), {})
            self.assertEqual(repository.put_settings({"theme": "SYSTEM"}), {"theme": "SYSTEM"})
            preset = repository.create_preset("0700", {"symbol": "0700.HK"})
            self.assertEqual(repository.list_presets()[0], preset)
            self.assertTrue(
                repository.update_preset(preset.preset_id, "腾讯", {"symbol": "0700.HK"})
            )
            self.assertEqual(repository.list_presets()[0].name, "腾讯")
            self.assertTrue(repository.delete_preset(preset.preset_id))
            self.assertEqual(repository.list_presets(), [])


if __name__ == "__main__":
    unittest.main()
