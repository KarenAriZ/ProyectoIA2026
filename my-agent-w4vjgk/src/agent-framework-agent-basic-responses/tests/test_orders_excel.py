import os, sys, tempfile, unittest
from pathlib import Path
from datetime import datetime
from unittest.mock import patch
from openpyxl import Workbook
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orders_excel import consultar_estado_pedido
from orders_lookup import DEFAULT_DATE_COLUMNS

class ExcelTests(unittest.TestCase):
    def test_reads_updated_file_and_limits_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pedidos.xlsx"
            def save(status):
                workbook = Workbook()
                sheet = workbook.active
                sheet.title = "Pedidos"
                sheet.append(["numeracion"])
                sheet.append(["NV", "Estado Logistica", *DEFAULT_DATE_COLUMNS, "Cliente"] + [f"extra{i}" for i in range(13)] + ["Previsto"])
                sheet.append([6963, status, datetime(2026,10,20), None, datetime(2026,10,25), "Privado"] + [None] * 13 + [datetime(2026,10,20)])
                workbook.save(path)
                workbook.close()
            with patch.dict(os.environ, {"ROCKERS_EXCEL_PATH": str(path), "ROCKERS_SHEET_TAB":"Pedidos", "ROCKERS_HEADER_ROW":"2"}):
                save("Bodega")
                self.assertEqual(consultar_estado_pedido("6963"), {"numero_pedido":"6963", "estado":"Bodega", "fecha_aproximada":"23-10-2026"})
                save("Entregado")
                self.assertEqual(consultar_estado_pedido("6963")["estado"], "Entregado")
                self.assertEqual(consultar_estado_pedido("0000"), {"resultado":"no_encontrado"})
    def test_missing_file(self):
        with patch.dict(os.environ, {"ROCKERS_EXCEL_PATH": "no-existe.xlsx"}):
            self.assertEqual(consultar_estado_pedido("6963"), {"resultado":"archivo_no_encontrado"})

if __name__ == "__main__":
    unittest.main()
