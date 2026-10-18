import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orders_lookup import lookup_order, lookup_rockers_order, DEFAULT_DATE_COLUMNS

class OrdersTests(unittest.TestCase):
    headers = ["NV", "Cliente", "Estado Logistica", "Fecha Entrega", "Direccion Cliente"]
    def test_only_allowed_fields(self):
        result = lookup_order(self.headers, [["6.963", "Privado", "Preparación", "20-10-2026", "Privada"]], "6.963", "Fecha Entrega")
        self.assertEqual(result, {"numero_pedido": "6.963", "estado": "Preparación", "fecha_aproximada": "20-10-2026"})
    def test_exact_nv(self):
        self.assertEqual(lookup_order(self.headers, [["6.963"]], "6963"), {"resultado": "no_encontrado"})
    def test_conflicting_duplicate_requires_review(self):
        rows = [["01", "", "Bodega"], ["01", "", "Entregado"]]
        self.assertEqual(lookup_order(self.headers, rows, "01"), {"resultado": "requiere_revision"})
    def test_repeated_product_lines_with_same_status(self):
        rows = [["01", "A", "Bodega"], ["01", "B", "Bodega"]]
        self.assertEqual(lookup_order(self.headers, rows, "01")["estado"], "Bodega")
    def test_unconfigured_date_is_not_guessed(self):
        result = lookup_order(self.headers, [["01", "", "Bodega", "20-10-2026"]], "01")
        self.assertEqual(result["fecha_aproximada"], "Pendiente de confirmar")
    def test_missing_configured_column_fails(self):
        with self.assertRaises(ValueError):
            lookup_order(self.headers, [], "01", "No existe")
    def test_duplicate_headers_fail(self):
        with self.assertRaises(ValueError):
            lookup_order(["NV", "NV", "Estado Logistica"], [], "01")

class GenericLegacyDatePriorityTests(unittest.TestCase):
    headers = ["NV", "Estado Logistica", *DEFAULT_DATE_COLUMNS]

    def test_last_nonempty_reprogramming_wins(self):
        cases = [
            (["20-10-2026", "", ""], "20-10-2026"),
            (["20-10-2026", "22-10-2026", ""], "22-10-2026"),
            (["20-10-2026", "22-10-2026", "25-10-2026"], "25-10-2026"),
            (["", "", "25-10-2026"], "25-10-2026"),
            (["20-10-2026", "   ", None], "20-10-2026"),
            (["", "", ""], "Pendiente de confirmar"),
        ]
        for dates, expected in cases:
            with self.subTest(dates=dates):
                result = lookup_order(self.headers, [["01", "Bodega", *dates]], "01", date_columns=DEFAULT_DATE_COLUMNS)
                self.assertEqual(result["fecha_aproximada"], expected)
                self.assertEqual(set(result), {"numero_pedido", "estado", "fecha_aproximada"})

    def test_different_effective_dates_require_review(self):
        rows = [["01", "Bodega", "20-10-2026", "", ""],
                ["01", "Bodega", "20-10-2026", "22-10-2026", ""]]
        self.assertEqual(lookup_order(self.headers, rows, "01", date_columns=DEFAULT_DATE_COLUMNS), {"resultado": "requiere_revision"})

    def test_header_whitespace_is_accepted(self):
        headers = [name + " " for name in self.headers]
        result = lookup_order(headers, [["01", "Bodega", "20-10-2026"]], "01", date_columns=DEFAULT_DATE_COLUMNS)
        self.assertEqual(result["fecha_aproximada"], "20-10-2026")

if __name__ == "__main__":
    unittest.main()
