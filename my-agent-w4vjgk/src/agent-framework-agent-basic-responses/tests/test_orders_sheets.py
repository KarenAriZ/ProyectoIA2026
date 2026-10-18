import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orders_sheets import consultar_estado_pedido

class SheetsConfigTests(unittest.TestCase):
    def test_missing_credentials_returns_configuration_pending(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(consultar_estado_pedido("6.963"), {"resultado": "configuracion_pendiente"})
    def test_invalid_nv_is_rejected_before_access(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(consultar_estado_pedido(""), {"resultado": "nv_invalido"})

if __name__ == "__main__":
    unittest.main()
