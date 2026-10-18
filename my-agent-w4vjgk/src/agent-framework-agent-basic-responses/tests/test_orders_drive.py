import io
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import orders_drive
from orders_lookup import DEFAULT_DATE_COLUMNS, buscar_pedido


class BusquedaCorreoTests(unittest.TestCase):
    headers = ["NV", "Estado Logistica", *DEFAULT_DATE_COLUMNS, "Correo", "Cliente", "Direccion"]

    def row(self, nv, estado="Bodega", correo="prueba@example.com", fecha="20-10-2026"):
        return [nv, estado, fecha, "", "", correo, "PRIVADO", "PRIVADO"]

    def test_numeric_nv_and_email_match(self):
        r = buscar_pedido(self.headers, [self.row(123.0)], correo=" Prueba@example.com ")
        self.assertEqual(r["numero_pedido"], "123")
        self.assertEqual(set(r), {"numero_pedido", "estado", "fecha_aproximada"})

    def test_multiple_orders_require_selection(self):
        rows = [self.row("001"), self.row("001"), self.row("002")]
        r = buscar_pedido(self.headers, rows, correo="prueba@example.com")
        self.assertEqual(r, {"resultado": "varios_pedidos", "numeros_pedido": ["001", "002"], "total": 2})
        self.assertEqual(buscar_pedido(self.headers, rows, "002", "prueba@example.com")["numero_pedido"], "002")

    def test_email_cannot_select_other_customer_order(self):
        r = buscar_pedido(self.headers, [self.row("001", correo="otro@example.com")], "001", "prueba@example.com")
        self.assertEqual(r, {"resultado": "no_encontrado"})

    def test_blank_email_does_not_match_empty_records(self):
        self.assertEqual(buscar_pedido(self.headers, [], correo="   "), {"resultado": "consulta_invalida"})

    def test_conflicting_lines_are_not_guessed(self):
        rows = [self.row("001"), self.row("001", "Entregado")]
        self.assertEqual(buscar_pedido(self.headers, rows, correo="prueba@example.com"), {"resultado": "requiere_revision"})

    def test_missing_email_header_has_specific_response(self):
        self.assertEqual(buscar_pedido(["NV"], [["001"]], correo="prueba@example.com"), {"resultado": "correo_no_disponible"})


class DescargaTests(unittest.TestCase):
    def setUp(self):
        orders_drive._cache = None

    def tearDown(self):
        orders_drive._cache = None

    def fixture(self):
        wb = Workbook()
        first = wb.active
        first.title = "Primera"
        first.append(["grupo"])
        first.append(["NV", "Estado Logistica", *DEFAULT_DATE_COLUMNS, "Correo", "Cliente"] + [f"extra{i}" for i in range(12)] + ["Previsto"])
        first.append([123, "Bodega", "20-10-2026", "", "", "prueba@example.com", "PRIVADO"] + [None] * 12 + ["20-10-2026"])
        wb.create_sheet("No consultar").append(["PRIVADO"])
        out = io.BytesIO()
        wb.save(out)
        wb.close()
        return out.getvalue()

    def test_first_sheet_cached_without_customer_columns(self):
        raw = self.fixture()
        with patch.object(orders_drive, "urlopen", side_effect=lambda *a, **k: io.BytesIO(raw)) as download:
            a = orders_drive.cargar_primera_hoja("abcdefghijk", 2)
            b = orders_drive.cargar_primera_hoja("abcdefghijk", 2)
        self.assertEqual(a, b)
        self.assertEqual(download.call_count, 1)
        self.assertNotIn("Cliente", a[0])
        self.assertNotIn("PRIVADO", str(a))

    def test_cache_refreshes_after_expiry(self):
        raw = self.fixture()
        with patch.object(orders_drive, "urlopen", side_effect=lambda *a, **k: io.BytesIO(raw)) as download:
            orders_drive.cargar_primera_hoja("abcdefghijk", 2)
            key, _, data = orders_drive._cache
            orders_drive._cache = (key, -1000000, data)
            orders_drive.cargar_primera_hoja("abcdefghijk", 2)
            self.assertEqual(download.call_count, 2)

    def test_access_failure_is_not_order_not_found(self):
        with patch.dict(os.environ, {"ROCKERS_SHEET_ID": "abcdefghijk", "ROCKERS_HEADER_ROW": "2"}):
            with patch.object(orders_drive, "urlopen", side_effect=HTTPError("", 403, "denied", {}, None)):
                self.assertEqual(orders_drive.consultar_estado_pedido("001"), {"resultado": "archivo_no_accesible"})
            with patch.object(orders_drive, "urlopen", side_effect=URLError("offline")):
                self.assertEqual(orders_drive.consultar_estado_pedido("001"), {"resultado": "error_consulta"})

    def test_html_response_is_rejected(self):
        with patch.dict(os.environ, {"ROCKERS_SHEET_ID": "abcdefghijk", "ROCKERS_HEADER_ROW": "2"}), \
             patch.object(orders_drive, "urlopen", return_value=io.BytesIO(b"<html>login</html>")):
            self.assertEqual(orders_drive.consultar_estado_pedido("001"), {"resultado": "estructura_no_valida"})


if __name__ == "__main__":
    unittest.main()
