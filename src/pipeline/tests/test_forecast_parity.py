"""Paridad entre la lógica canónica y la copia del backend (spec 003, RNF-1).

Los dos desplegables no comparten árbol (`render.yaml` usa `rootDir: backend`),
así que la copia existe, pero no puede derivar: si alguien cambia una y no la
otra, esta suite lo delata.
"""

import ast
import json
import sys
import unittest
from datetime import date, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "src" / "pipeline"))
sys.path.insert(0, str(RAIZ / "backend"))

import forecast  # noqa: E402
from app.services import forecast_db, forecast_logic  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CANONICO = RAIZ / "src" / "pipeline" / "forecast.py"
COPIA = RAIZ / "backend" / "app" / "services" / "forecast_logic.py"


def parte(nombre: str) -> dict:
    return json.loads((FIXTURES / f"prediccion_{nombre}.json").read_text(encoding="utf-8"))


def sin_docstrings(ruta: Path) -> str:
    """AST sin docstrings: la copia puede explicar su origen, pero no cambiar reglas."""
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Module, ast.ClassDef, ast.FunctionDef)) and nodo.body:
            primero = nodo.body[0]
            if isinstance(primero, ast.Expr) and isinstance(primero.value, ast.Constant):
                if isinstance(primero.value.value, str):
                    nodo.body = nodo.body[1:] or [ast.Pass()]
    return ast.dump(arbol, annotate_fields=False)


class TestParidadDelCodigo(unittest.TestCase):
    def test_la_copia_existe(self):
        self.assertTrue(COPIA.exists(), COPIA)

    def test_la_copia_tiene_exactamente_las_mismas_reglas(self):
        self.assertEqual(
            sin_docstrings(CANONICO),
            sin_docstrings(COPIA),
            "la copia del backend se ha separado del módulo canónico",
        )

    def test_el_catalogo_es_el_mismo(self):
        self.assertEqual(forecast.UBICACIONES, forecast_logic.UBICACIONES)

    def test_los_factores_de_cielo_son_los_mismos(self):
        self.assertEqual(forecast.FACTORES_CIELO, forecast_logic.FACTORES_CIELO)


class TestParidadDeComportamiento(unittest.TestCase):
    """Mismas entradas, mismas salidas; no basta con que el texto se parezca."""

    def setUp(self):
        self.diario = parte("diaria")
        self.horario = parte("horaria")

    def test_el_parseo_del_parte_diario_coincide(self):
        self.assertEqual(
            forecast.parse_daily_parte(self.diario),
            forecast_logic.parse_daily_parte(self.diario),
        )

    def test_el_parseo_del_parte_horario_coincide(self):
        self.assertEqual(
            forecast.parse_hourly_parte(self.horario),
            forecast_logic.parse_hourly_parte(self.horario),
        )

    def test_las_filas_de_archivo_coinciden(self):
        argumentos = ("Gecama (Cuenca)", "eolica", 39.4085, datetime(2026, 11, 2, 15, 50))
        self.assertEqual(
            forecast.forecast_rows(
                forecast.parse_daily_parte(self.diario),
                forecast.parse_hourly_parte(self.horario),
                *argumentos,
            ),
            forecast_logic.forecast_rows(
                forecast_logic.parse_daily_parte(self.diario),
                forecast_logic.parse_hourly_parte(self.horario),
                *argumentos,
            ),
        )

    def test_la_insolacion_estimada_coincide_en_todo_el_ano(self):
        for mes in range(1, 13):
            fecha = date(2026, mes, 15)
            for codigo in ("11", "12", "13", "14", "15", "16", None):
                tramos = [(8, 18, codigo)]
                self.assertEqual(
                    forecast.estimate_sun(tramos, 39.4, fecha),
                    forecast_logic.estimate_sun(tramos, 39.4, fecha),
                    (mes, codigo),
                )


class TestParidadDeLaEleccion(unittest.TestCase):
    """`choose_forecast` puro y la consulta SQL deben responder lo mismo (RF-5)."""

    HOY = date(2026, 11, 2)

    def setUp(self):
        self.conn = forecast_db.connect(":memory:")
        forecast_db.ensure_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def archivar(self, filas):
        forecast_db.save_forecast(self.conn, filas, parte("diaria"))

    def comparar(self, filas, objetivo, ubicacion):
        puro = forecast.choose_forecast(filas, objetivo, ubicacion, self.HOY)
        sql = forecast_db.choose_forecast(self.conn, objetivo, ubicacion, self.HOY)
        if puro is None:
            self.assertIsNone(sql)
            return
        self.assertIsNotNone(sql)
        self.assertEqual(sql["elaborado"], puro["elaborado"])
        self.assertEqual(sql["antiguedad_dias"], puro["antiguedad_dias"])
        self.assertEqual(sql["valores"]["viento_ms"], puro["valores"]["viento_ms"])

    def base(self, elaborado, viento_ms=5.0, objetivo=date(2026, 11, 1)):
        return {
            "elaborado": elaborado,
            "objetivo": objetivo,
            "ubicacion": "Gecama (Cuenca)",
            "uso": "eolica",
            "viento_ms": viento_ms,
            "racha_ms": 9.0,
            "tmax": 18.0,
            "tmin": 6.0,
            "tmed": 12.0,
            "sol": None,
            "tramos_cielo": [(0, 24, "11")],
            "orto": 8.0,
            "ocaso": 18.0,
            "uv_max": 2,
            "capturado_en": datetime(2026, 11, 2, 3, 0),
        }

    def test_sin_registros_las_dos_vias_dicen_no_disponible(self):
        self.comparar([], date(2026, 11, 1), "Gecama (Cuenca)")

    def test_elaboracion_anterior_coincide(self):
        filas = [self.base(datetime(2026, 10, 31, 8, 0))]
        self.archivar(filas)
        self.comparar(filas, date(2026, 11, 1), "Gecama (Cuenca)")

    def test_elaboracion_el_mismo_dia_coincide(self):
        filas = [self.base(datetime(2026, 11, 1, 8, 59))]
        self.archivar(filas)
        self.comparar(filas, date(2026, 11, 1), "Gecama (Cuenca)")

    def test_elaboracion_posterior_queda_fuera_en_las_dos(self):
        filas = [self.base(datetime(2026, 11, 2, 8, 0))]
        self.archivar(filas)
        self.comparar(filas, date(2026, 11, 1), "Gecama (Cuenca)")

    def test_gana_la_mas_reciente_en_las_dos(self):
        filas = [
            self.base(datetime(2026, 10, 30, 8, 0), viento_ms=1.0),
            self.base(datetime(2026, 10, 31, 8, 0), viento_ms=2.0),
        ]
        self.archivar(filas)
        self.comparar(filas, date(2026, 11, 1), "Gecama (Cuenca)")

    def test_sin_elaboracion_no_es_elegible_en_las_dos(self):
        filas = [self.base(None)]
        self.archivar(filas)
        self.comparar(filas, date(2026, 11, 1), "Gecama (Cuenca)")

    def test_otra_ubicacion_no_sirve_en_las_dos(self):
        filas = [self.base(datetime(2026, 10, 31, 8, 0))]
        self.archivar(filas)
        self.comparar(filas, date(2026, 11, 1), "Mula (Murcia)")

    def test_el_objetivo_manda_en_las_dos(self):
        filas = [
            self.base(datetime(2026, 10, 31, 8, 0), viento_ms=1.0, objetivo=date(2026, 10, 31)),
            self.base(datetime(2026, 10, 31, 8, 0), viento_ms=2.0, objetivo=date(2026, 11, 1)),
        ]
        self.archivar(filas)
        self.comparar(filas, date(2026, 11, 1), "Gecama (Cuenca)")


if __name__ == "__main__":
    unittest.main()
