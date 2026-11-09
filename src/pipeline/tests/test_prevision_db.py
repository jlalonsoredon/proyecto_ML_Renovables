"""Contrato de persistencia de previsiones y predicciones propias (spec 004).

Cubre RF-1 (archivo de fuentes) y RF-2 (predicción propia). Sin red y sin
pandas: se usa una base SQLite en memoria. La puerta `node --test` descubre esta
suite a través de `gate.test.mjs`.

La regla que se comprueba en todas partes: una elaboración nueva se añade, la
misma elaboración recapturada se sustituye, y nunca se borra ni se rellena un
hueco con un valor por defecto.
"""

import json
import sys
import unittest
from datetime import date, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "src" / "pipeline"))

import forecast  # noqa: E402
import prevision_db  # noqa: E402


def fila_aemet(**extra):
    """Fila de previsión AEMET tal y como la devuelve `forecast.forecast_rows`."""
    fila = {
        "elaborado": datetime(2026, 1, 1, 9, 0),
        "objetivo": date(2026, 1, 2),
        "ubicacion": "Gecama (Cuenca)",
        "uso": "eolica",
        "viento_ms": 5.0,
        "racha_ms": 9.0,
        "tmax": 20.0,
        "tmin": 10.0,
        "tmed": 15.0,
        "sol": 7.0,
        "tramos_cielo": [(0.0, 24.0, "11")],
        "orto": 8.0,
        "ocaso": 18.0,
        "uv_max": 3.0,
        "capturado_en": datetime(2026, 1, 1, 10, 0),
    }
    fila.update(extra)
    return fila


def fila_ree(**extra):
    """Fila de previsión de generación de REE (CA-1.1)."""
    fila = {
        "elaborado": datetime(2026, 1, 1, 8, 0),
        "objetivo": date(2026, 1, 2),
        "ubicacion": "peninsula",
        "uso": "generacion",
        "eolica_mwh": 5000.0,
        "capturado_en": datetime(2026, 1, 1, 10, 0),
    }
    fila.update(extra)
    return fila


def prediccion(**extra):
    """Predicción propia emitida por el modelo (CA-2.1)."""
    fila = {
        "fecha_objetivo": date(2026, 1, 2),
        "emitida_en": datetime(2026, 1, 1, 3, 0),
        "prediccion_mwh": 5000.0,
        "modelo": "LinearRegression",
        "n_variables": 18,
        "vector_entrada": {"velmedia": 5.0, "racha": 9.0},
        "origenes": {"velmedia": "prevision", "racha": "prevision"},
    }
    fila.update(extra)
    return fila


class BaseTablas(unittest.TestCase):
    def setUp(self):
        self.conn = prevision_db.connect(":memory:")
        prevision_db.ensure_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def tablas(self):
        return {
            fila[0] for fila in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

    def claves(self, tabla):
        return [
            fila[1] for fila in sorted(
                self.conn.execute(f"PRAGMA table_info({tabla})"),
                key=lambda fila: fila[5],
            )
            if fila[5] > 0
        ]


class TestEsquema(BaseTablas):
    def test_crear_el_esquema_dos_veces_no_falla(self):
        prevision_db.ensure_schema(self.conn)
        self.assertIn("prediccion_diaria", self.tablas())
        self.assertIn("prediccion_propia", self.tablas())

    def test_el_esquema_no_crea_las_tablas_de_observacion(self):
        self.assertNotIn("generacion", self.tablas())
        self.assertNotIn("aemet_diario", self.tablas())

    def test_la_clave_de_prediccion_diaria_incluye_la_fuente(self):
        self.assertEqual(
            self.claves("prediccion_diaria"),
            ["fuente", "elaborado", "objetivo", "ubicacion"],
        )

    def test_la_clave_de_prediccion_propia_es_objetivo_y_emision(self):
        self.assertEqual(
            self.claves("prediccion_propia"),
            ["fecha_objetivo", "fecha_emision"],
        )

    def test_prediccion_diaria_tiene_las_columnas_de_la_spec_003_mas_las_nuevas(self):
        columnas = {fila[1] for fila in self.conn.execute(
            "PRAGMA table_info(prediccion_diaria)")}
        for columna in (
            "fuente", "elaborado", "objetivo", "ubicacion", "uso", "viento_ms",
            "racha_ms", "tmax", "tmin", "tmed", "sol", "tramos_cielo", "orto",
            "ocaso", "uv_max", "eolica_mwh", "parte_json", "capturado_en",
        ):
            self.assertIn(columna, columnas)

    def test_prediccion_propia_guarda_vector_y_origenes(self):
        columnas = {fila[1] for fila in self.conn.execute(
            "PRAGMA table_info(prediccion_propia)")}
        for columna in (
            "fecha_objetivo", "fecha_emision", "emitida_en", "prediccion_mwh",
            "modelo", "n_variables", "vector_entrada", "origenes",
            "real_mwh", "error_mwh",
        ):
            self.assertIn(columna, columnas)


class TestArchivoFuentes(BaseTablas):
    def test_una_captura_aemet_guarda_sus_filas(self):
        guardadas = prevision_db.save_forecast_rows(
            self.conn, [fila_aemet()], "aemet", parte={"elaborado": "2026-01-01T09:00:00"})
        self.assertEqual(guardadas, 1)
        filas = prevision_db.rows_between(self.conn, "aemet")
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]["fuente"], "aemet")

    def test_recapturar_la_misma_elaboracion_no_duplica(self):
        prevision_db.save_forecast_rows(self.conn, [fila_aemet()], "aemet")
        prevision_db.save_forecast_rows(self.conn, [fila_aemet()], "aemet")
        self.assertEqual(len(prevision_db.rows_between(self.conn, "aemet")), 1)

    def test_la_misma_elaboracion_sustituye_sus_valores(self):
        prevision_db.save_forecast_rows(self.conn, [fila_aemet()], "aemet")
        prevision_db.save_forecast_rows(
            self.conn, [fila_aemet(viento_ms=1.234)], "aemet")
        filas = prevision_db.rows_between(self.conn, "aemet")
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]["viento_ms"], 1.234)

    def test_una_elaboracion_nueva_se_anade_y_conserva_la_anterior(self):
        prevision_db.save_forecast_rows(self.conn, [fila_aemet()], "aemet")
        prevision_db.save_forecast_rows(
            self.conn,
            [fila_aemet(elaborado=datetime(2026, 1, 2, 9, 0), viento_ms=7.0)],
            "aemet",
        )
        filas = prevision_db.rows_between(self.conn, "aemet")
        self.assertEqual(len(filas), 2)
        self.assertEqual({fila["viento_ms"] for fila in filas}, {5.0, 7.0})

    def test_una_elaboracion_sin_declarar_se_guarda_y_no_es_elegible(self):
        prevision_db.save_forecast_rows(
            self.conn, [fila_aemet(elaborado=None)], "aemet")
        filas = prevision_db.rows_between(self.conn, "aemet")
        self.assertEqual(len(filas), 1)
        self.assertIsNone(filas[0]["elaborado"])
        self.assertIsNone(
            forecast.choose_forecast(
                filas, date(2026, 1, 2), "Gecama (Cuenca)", date(2026, 1, 2))
        )

    def test_la_fuente_forma_parte_de_la_clave(self):
        prevision_db.save_forecast_rows(self.conn, [fila_aemet()], "aemet")
        prevision_db.save_forecast_rows(self.conn, [fila_aemet()], "ree")
        self.assertEqual(len(prevision_db.rows_between(self.conn)), 2)
        self.assertEqual(len(prevision_db.rows_between(self.conn, "aemet")), 1)
        self.assertEqual(len(prevision_db.rows_between(self.conn, "ree")), 1)

    def test_ree_guarda_la_generacion_y_deja_las_meteorologicas_vacias(self):
        prevision_db.save_forecast_rows(self.conn, [fila_ree()], "ree")
        fila = prevision_db.rows_between(self.conn, "ree")[0]
        self.assertEqual(fila["eolica_mwh"], 5000.0)
        self.assertEqual(fila["uso"], "generacion")
        self.assertIsNone(fila["viento_ms"])
        self.assertIsNone(fila["sol"])

    def test_los_valores_ausentes_siguen_siendo_ausentes(self):
        prevision_db.save_forecast_rows(
            self.conn, [fila_aemet(racha_ms=None, sol=None)], "aemet")
        fila = prevision_db.rows_between(self.conn, "aemet")[0]
        self.assertIsNone(fila["racha_ms"])
        self.assertIsNone(fila["sol"])

    def test_el_parte_original_queda_guardado(self):
        parte = {"elaborado": "2026-01-01T09:00:00", "prediccion": {"dia": []}}
        prevision_db.save_forecast_rows(self.conn, [fila_aemet()], "aemet", parte=parte)
        guardado = self.conn.execute(
            "SELECT parte_json FROM prediccion_diaria").fetchone()[0]
        self.assertEqual(json.loads(guardado), parte)

    def test_la_lectura_por_rango_no_devuelve_fuera_del_rango(self):
        prevision_db.save_forecast_rows(self.conn, [
            fila_aemet(),
            fila_aemet(objetivo=date(2026, 1, 10)),
        ], "aemet")
        filas = prevision_db.rows_between(
            self.conn, "aemet", date(2026, 1, 9), date(2026, 1, 11))
        self.assertEqual([fila["objetivo"] for fila in filas], [date(2026, 1, 10)])

    def test_objetivos_cubiertos_cuenta_cada_dia_una_vez(self):
        prevision_db.save_forecast_rows(self.conn, [
            fila_ree(),
            fila_ree(elaborado=datetime(2026, 1, 1, 9, 0), eolica_mwh=5100.0),
            fila_ree(objetivo=date(2026, 1, 3)),
        ], "ree")
        self.assertEqual(
            prevision_db.objetivos_cubiertos(self.conn, "ree"),
            {date(2026, 1, 2), date(2026, 1, 3)},
        )

    def test_objetivos_cubiertos_respeta_fuente_y_rango(self):
        prevision_db.save_forecast_rows(self.conn, [fila_aemet()], "aemet")
        prevision_db.save_forecast_rows(self.conn, [
            fila_ree(),
            fila_ree(objetivo=date(2026, 1, 10)),
        ], "ree")
        self.assertEqual(
            prevision_db.objetivos_cubiertos(
                self.conn, "ree", date(2026, 1, 5), date(2026, 1, 31)),
            {date(2026, 1, 10)},
        )
        self.assertEqual(
            prevision_db.objetivos_cubiertos(self.conn, "aemet"),
            {date(2026, 1, 2)},
        )


class TestPrediccionPropia(BaseTablas):
    def test_guardar_una_prediccion_propia(self):
        prevision_db.save_own_prediction(self.conn, prediccion())
        filas = prevision_db.own_predictions(self.conn)
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]["prediccion_mwh"], 5000.0)
        self.assertEqual(filas[0]["n_variables"], 18)

    def test_reejecutar_el_mismo_dia_sustituye_sin_duplicar(self):
        prevision_db.save_own_prediction(self.conn, prediccion())
        prevision_db.save_own_prediction(
            self.conn, prediccion(prediccion_mwh=5100.0))
        filas = prevision_db.own_predictions(self.conn)
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]["prediccion_mwh"], 5100.0)

    def test_emisiones_de_dias_distintos_conviven(self):
        prevision_db.save_own_prediction(self.conn, prediccion())
        prevision_db.save_own_prediction(
            self.conn,
            prediccion(emitida_en=datetime(2026, 1, 2, 3, 0), prediccion_mwh=5200.0),
        )
        self.assertEqual(len(prevision_db.own_predictions(self.conn)), 2)

    def test_objetivos_distintos_el_mismo_dia_conviven(self):
        prevision_db.save_own_prediction(self.conn, prediccion())
        prevision_db.save_own_prediction(
            self.conn, prediccion(fecha_objetivo=date(2026, 1, 3)))
        self.assertEqual(len(prevision_db.own_predictions(self.conn)), 2)

    def test_el_vector_y_los_origenes_se_leen_como_diccionarios(self):
        prevision_db.save_own_prediction(self.conn, prediccion())
        fila = prevision_db.own_predictions(self.conn)[0]
        self.assertEqual(fila["vector_entrada"], {"velmedia": 5.0, "racha": 9.0})
        self.assertEqual(fila["origenes"]["velmedia"], "prevision")

    def test_una_prediccion_sin_real_no_inventa_error(self):
        prevision_db.save_own_prediction(self.conn, prediccion())
        fila = prevision_db.own_predictions(self.conn)[0]
        self.assertIsNone(fila["real_mwh"])
        self.assertIsNone(fila["error_mwh"])


class TestRealYError(BaseTablas):
    def test_actualizar_el_real_calcula_el_error_sin_tocar_la_prediccion(self):
        prevision_db.save_own_prediction(self.conn, prediccion(prediccion_mwh=5000.0))
        prevision_db.update_real(self.conn, date(2026, 1, 2), 5300.0)

        fila = prevision_db.own_predictions(self.conn)[0]
        self.assertEqual(fila["prediccion_mwh"], 5000.0)
        self.assertEqual(fila["real_mwh"], 5300.0)
        self.assertEqual(fila["error_mwh"], 300.0)

    def test_el_real_llega_a_todas_las_emisiones_del_mismo_objetivo(self):
        prevision_db.save_own_prediction(self.conn, prediccion(prediccion_mwh=5000.0))
        prevision_db.save_own_prediction(
            self.conn,
            prediccion(
                emitida_en=datetime(2026, 1, 2, 3, 0),
                prediccion_mwh=5100.0,
            ),
        )
        prevision_db.update_real(self.conn, date(2026, 1, 2), 5300.0)
        filas = prevision_db.own_predictions(self.conn)
        self.assertEqual({fila["real_mwh"] for fila in filas}, {5300.0})
        self.assertEqual({fila["error_mwh"] for fila in filas}, {300.0, 200.0})

    def test_una_correccion_del_real_recalcula_el_error(self):
        prevision_db.save_own_prediction(self.conn, prediccion(prediccion_mwh=5000.0))
        prevision_db.update_real(self.conn, date(2026, 1, 2), 5300.0)
        prevision_db.update_real(self.conn, date(2026, 1, 2), 5400.0)
        self.assertEqual(prevision_db.own_predictions(self.conn)[0]["error_mwh"], 400.0)

    def test_pendientes_solo_incluye_objetivos_de_hoy_o_anteriores(self):
        prevision_db.save_own_prediction(self.conn, prediccion())              # 01-02
        prevision_db.save_own_prediction(
            self.conn, prediccion(fecha_objetivo=date(2026, 1, 5)))
        pendientes = prevision_db.predictions_without_real(self.conn, date(2026, 1, 3))
        self.assertEqual(
            [fila["fecha_objetivo"] for fila in pendientes], [date(2026, 1, 2)])

    def test_las_recientes_con_real_se_ordenan_por_objetivo(self):
        for dia, real in ((3, 300.0), (2, 200.0), (1, 100.0)):
            prevision_db.save_own_prediction(
                self.conn,
                prediccion(fecha_objetivo=date(2026, 1, dia), prediccion_mwh=50.0),
            )
            prevision_db.update_real(self.conn, date(2026, 1, dia), real)
        recientes = prevision_db.recent_with_real(self.conn, limite=2)
        self.assertEqual(
            [fila["fecha_objetivo"] for fila in recientes],
            [date(2026, 1, 2), date(2026, 1, 3)],
        )


if __name__ == "__main__":
    unittest.main()
