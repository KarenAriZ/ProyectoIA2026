import io
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orders_lookup import (
    DEFAULT_DATE_COLUMNS, ESTADO_RECEPCIONADO, ESTADO_PRODUCCION, ESTADO_CONTACTO, ESTADO_STOCK_FABRICA,
    buscar_pedido, lookup_rockers_order,
)
from orders_guard import redactar
from orders_dates import COLUMNA_PREVISTO
import orders_drive


class ProductionTests(unittest.TestCase):
    headers = ["NV", "Estado Logistica", "Produccion", *DEFAULT_DATE_COLUMNS, "Correo"]

    def row(self, stage, logistic="", nv="TEST-001"):
        return [nv, logistic, stage, "20-10-2026", "", "", "prueba@example.com"]

    def result(self, stage, logistic=""):
        return lookup_rockers_order(self.headers, [self.row(stage, logistic)], "TEST-001")

    def test_cut_means_successfully_received(self):
        r = self.result("Corte")
        self.assertEqual(r["estado"], ESTADO_RECEPCIONADO)
        self.assertIn("Recibimos tu pedido correctamente.", redactar(r))

    def test_every_production_stage(self):
        for stage in ["Plegado", "Partes y Piezas", "Armado", "Mig", "Entregado a Pintura", "Pintura", "Montaje"]:
            with self.subTest(stage=stage):
                r = self.result(stage)
                self.assertEqual(r["estado"], ESTADO_PRODUCCION)
                self.assertIn("Tu pedido ya está en producción.", redactar(r))

    def test_stock_factory_uses_confirmed_message(self):
        for stage in ["Stock Fabrica", "STOCK FÁBRICA", "  Stock  Fabrica "]:
            with self.subTest(stage=stage):
                r = self.result(stage)
                self.assertEqual(r["estado"], ESTADO_STOCK_FABRICA)
                self.assertIn("Ya recibimos tu pedido. Te contactaremos cuando avance a la etapa de entrega.", redactar(r))

    def test_quality_and_warehouse_mean_upcoming_contact(self):
        for stage in ["Calidad", "Bodega"]:
            with self.subTest(stage=stage):
                r = self.result(stage)
                self.assertEqual(r["estado"], ESTADO_CONTACTO)
                self.assertIn("En los próximos días deberían contactarte.", redactar(r))

    def test_delivery_cancellation_and_route_override_production(self):
        for logistic in ["ENTREGADO", "CANCELADO", "EN RUTA", "COORDINACION"]:
            for stage in ["Corte", "Pintura", "Calidad", "Bodega", "Stock Fabrica"]:
                with self.subTest(logistic=logistic, stage=stage):
                    r = self.result(stage, logistic)
                    self.assertEqual(r["estado"], logistic)
                    self.assertNotIn("deberían contactarte", redactar(r))

    def test_unassigned_or_rejected_stage_does_not_make_promises(self):
        for stage in ["Rechazado Calidad", "", None, "Etapa desconocida"]:
            with self.subTest(stage=stage):
                self.assertEqual(self.result(stage)["estado"], "Pendiente de confirmar")

    def test_stage_case_accents_and_spaces(self):
        self.assertEqual(self.result("  PARTES  Y  PIEZAS ")["estado"], ESTADO_PRODUCCION)
        headers = ["NV", "Estado Logistica", "PRODUCCIÓN", *DEFAULT_DATE_COLUMNS]
        r = lookup_rockers_order(headers, [self.row("Corte")], "TEST-001")
        self.assertEqual(r["estado"], ESTADO_RECEPCIONADO)

    def test_email_uses_the_same_stage_rules(self):
        r = buscar_pedido(self.headers, [self.row("Montaje")], correo="prueba@example.com")
        self.assertEqual(r["estado"], ESTADO_PRODUCCION)
        self.assertEqual(set(r), {"numero_pedido", "estado", "fecha_aproximada"})

    def test_lines_in_different_status_groups_require_review(self):
        rows = [self.row("Corte"), self.row("Pintura")]
        self.assertEqual(lookup_rockers_order(self.headers, rows, "TEST-001"), {"resultado": "requiere_revision"})

    def test_lines_in_same_production_group_can_be_consolidated(self):
        rows = [self.row("Mig"), self.row("Pintura")]
        self.assertEqual(lookup_rockers_order(self.headers, rows, "TEST-001")["estado"], ESTADO_PRODUCCION)

    def test_marked_columns_do_not_override_summary_stage(self):
        headers = [*self.headers, "Corte", "Bodega", "Calidad"]
        row = [*self.row("Mig"), "Ok", "Ok", "Ok"]
        self.assertEqual(lookup_rockers_order(headers, [row], "TEST-001")["estado"], ESTADO_PRODUCCION)

    def test_column_t_policy_replaces_reprogramming(self):
        row = self.row("Corte")
        row[5] = "25-10-2026"
        r = lookup_rockers_order([*self.headers, COLUMNA_PREVISTO], [[*row, "20-10-2026"]], "TEST-001")
        self.assertEqual(r["fecha_aproximada"], "23-10-2026")

    def test_drive_retains_and_uses_production_column(self):
        wb = Workbook()
        ws = wb.active
        ws.append(["grupos"])
        ws.append(self.headers + [f"extra{i}" for i in range(19 - len(self.headers))] + ["Previsto"])
        ws.append(self.row("Calidad") + [None] * (19 - len(self.headers)) + ["20-10-2026"])
        raw = io.BytesIO()
        wb.save(raw)
        wb.close()
        orders_drive._cache = None
        try:
            with patch.dict(os.environ, {"ROCKERS_SHEET_ID": "abcdefghijk", "ROCKERS_HEADER_ROW": "2"}), \
                 patch.object(orders_drive, "urlopen", return_value=io.BytesIO(raw.getvalue())):
                r = orders_drive.consultar_estado_pedido(nv="TEST-001")
                self.assertEqual(r["estado"], ESTADO_CONTACTO)
        finally:
            orders_drive._cache = None


if __name__ == "__main__":
    unittest.main()
