"""Tests de la lógica pura del bloque solar (spec 001-fotovoltaicas).

Se ejecutan con la biblioteca estándar: `python -m unittest discover`.
La puerta real del proyecto es `node --test`, que lanza esta suite (gate.test.mjs).
"""

import math
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import solar  # noqa: E402


# ─────────────────────────────────────────────
# Utilidades de los tests
# ─────────────────────────────────────────────

def catalogo_valido():
    """Cinco pares planta–estación como los del notebook."""
    return [
        {"planta": "Francisco Pizarro", "indicativo": "3469A", "nombre": "CÁCERES",
         "lat": 39.47, "lon": -6.37, "planta_lat": 39.57, "planta_lon": -5.70, "distancia_km": 56},
        {"planta": "Núñez de Balboa", "indicativo": "4452", "nombre": "BADAJOZ",
         "lat": 38.88, "lon": -6.81, "planta_lat": 38.45, "planta_lon": -6.22, "distancia_km": 70},
        {"planta": "Mula", "indicativo": "7228", "nombre": "MURCIA/ALCANTARILLA",
         "lat": 37.95, "lon": -1.23, "planta_lat": 37.95, "planta_lon": -1.40, "distancia_km": 16},
        {"planta": "Don Rodrigo", "indicativo": "5783", "nombre": "SEVILLA/SAN PABLO",
         "lat": 37.41, "lon": -5.87, "planta_lat": 37.22, "planta_lon": -5.86, "distancia_km": 22},
        {"planta": "Chiprana-Samper", "indicativo": "9434", "nombre": "ZARAGOZA/AEROPUERTO",
         "lat": 41.66, "lon": -1.00, "planta_lat": 41.26, "planta_lon": -0.17, "distancia_km": 82},
    ]


def mapa_descarga():
    return {
        "Planta Francisco Pizarro (Cáceres)": "3469A",
        "Planta Núñez de Balboa (Badajoz)": "4452",
        "Planta Solar de Mula (Murcia)": "7228",
        "Complejo Don Rodrigo (Sevilla)": "5783",
        "Chiprana-Samper (Zaragoza)": "9434",
    }


def dias(inicio, n):
    """Lista de fechas ISO consecutivas."""
    from datetime import timedelta
    base = date.fromisoformat(inicio)
    return [(base + timedelta(days=i)).isoformat() for i in range(n)]


def serie(estacion, inicio, n, sol=10.0, nulos=(), tmed=20.0):
    filas = []
    for i, fecha in enumerate(dias(inicio, n)):
        filas.append({
            "fecha": fecha,
            "indicativo": estacion,
            "sol": None if i in nulos else sol,
            "tmed": tmed,
        })
    return filas


# ─────────────────────────────────────────────
# RF-1 — Catálogo (T-05)
# ─────────────────────────────────────────────

class TestCatalogo(unittest.TestCase):
    def test_catalogo_valido_no_lanza(self):
        solar.validate_catalog(catalogo_valido(), mapa_descarga())

    def test_indicativo_duplicado(self):
        catalogo = catalogo_valido()
        catalogo[1]["indicativo"] = "3469A"
        with self.assertRaises(solar.CatalogError) as ctx:
            solar.validate_catalog(catalogo, mapa_descarga())
        self.assertIn("3469A", str(ctx.exception))

    def test_catalogo_incompleto(self):
        with self.assertRaises(solar.CatalogError) as ctx:
            solar.validate_catalog(catalogo_valido()[:4], mapa_descarga())
        self.assertIn("5", str(ctx.exception))

    def test_falta_distancia_o_coordenadas(self):
        catalogo = catalogo_valido()
        del catalogo[2]["distancia_km"]
        with self.assertRaises(solar.CatalogError) as ctx:
            solar.validate_catalog(catalogo, mapa_descarga())
        self.assertIn("distancia_km", str(ctx.exception))

    def test_catalogo_incoherente_con_la_descarga(self):
        mapa = mapa_descarga()
        mapa["Planta Solar de Mula (Murcia)"] = "7012C"
        with self.assertRaises(solar.CatalogError) as ctx:
            solar.validate_catalog(catalogo_valido(), mapa)
        self.assertIn("descarga", str(ctx.exception).lower())


# ─────────────────────────────────────────────
# RF-3 / CE-3 / CE-4 — Valores de insolación (T-06)
# ─────────────────────────────────────────────

class TestValores(unittest.TestCase):
    def test_cero_es_valido(self):
        solar.validate_sol_values(serie("5783", "2026-06-01", 5, sol=0.0))

    def test_sol_imposible(self):
        filas = serie("5783", "2026-06-01", 3, sol=30.0)
        with self.assertRaises(solar.InsolationError) as ctx:
            solar.validate_sol_values(filas)
        self.assertIn("24", str(ctx.exception))

    def test_sol_negativo(self):
        filas = serie("5783", "2026-06-01", 3, sol=-1.0)
        with self.assertRaises(solar.InsolationError):
            solar.validate_sol_values(filas)

    def test_huecos_y_nan_no_son_error(self):
        filas = serie("5783", "2026-06-01", 5, nulos=(1, 3))
        filas.append({"fecha": "2026-06-06", "indicativo": "5783", "sol": float("nan"), "tmed": 1.0})
        solar.validate_sol_values(filas)

    def test_sol_no_numerico_no_es_un_hueco(self):
        filas = serie("5783", "2026-06-01", 3)
        filas[1]["sol"] = "s/n"
        with self.assertRaises(solar.InsolationError) as ctx:
            solar.validate_sol_values(filas)
        # El mensaje distingue "valor imposible" de "dato ausente" (T-06).
        self.assertIn("no num", str(ctx.exception).lower())
        self.assertIn("2026-06-02", str(ctx.exception))


# ─────────────────────────────────────────────
# RF-4 — Diagnóstico de cobertura (T-07)
# ─────────────────────────────────────────────

class TestCobertura(unittest.TestCase):
    def test_porcentaje_y_hueco(self):
        filas = serie("5783", "2026-06-01", 30, nulos=(9, 10, 11))
        informe = solar.coverage_report(filas, ["5783"])

        est = informe["5783"]["sol"]
        self.assertEqual(est["days"], 30)
        self.assertEqual(est["with_data"], 27)
        self.assertAlmostEqual(est["missing_pct"], 10.0, places=1)
        self.assertEqual(est["max_gap_days"], 3)

    def test_informe_incluye_las_cinco_estaciones(self):
        filas = []
        for est in ["3469A", "4452", "7228", "5783", "9434"]:
            filas += serie(est, "2026-06-01", 10, nulos=(0,))
        informe = solar.coverage_report(filas, ["3469A", "4452", "7228", "5783", "9434"])
        self.assertEqual(len(informe), 5)
        for est in informe:
            self.assertAlmostEqual(informe[est]["sol"]["missing_pct"], 10.0, places=1)

    def test_estacion_sin_filas(self):
        informe = solar.coverage_report(serie("5783", "2026-06-01", 5), ["5783", "9434"])
        self.assertEqual(informe["9434"]["sol"]["days"], 0)
        self.assertEqual(informe["9434"]["sol"]["missing_pct"], 100.0)

    def test_dos_llamadas_seguidas_dan_lo_mismo(self):
        filas = serie("5783", "2026-06-01", 30, nulos=(9, 10, 11))
        self.assertEqual(
            solar.coverage_report(filas, ["5783"]),
            solar.coverage_report(filas, ["5783"]),
        )

    def test_las_filas_ausentes_cuentan_como_ausencia(self):
        # Sólo hay 5 días de una ventana de 10: la mitad del periodo no tiene dato.
        filas = serie("5783", "2026-06-01", 5)
        informe = solar.coverage_report(
            filas, ["5783"], desde=date(2026, 6, 1), hasta=date(2026, 6, 10)
        )

        est = informe["5783"]["sol"]
        self.assertEqual(est["days"], 10)
        self.assertEqual(est["with_data"], 5)
        self.assertAlmostEqual(est["missing_pct"], 50.0, places=1)
        self.assertEqual(est["max_gap_days"], 5)

    def test_la_ventana_no_altera_el_calculo_sin_huecos(self):
        filas = serie("5783", "2026-06-01", 10)
        con_ventana = solar.coverage_report(
            filas, ["5783"], desde=date(2026, 6, 1), hasta=date(2026, 6, 10)
        )
        sin_ventana = solar.coverage_report(filas, ["5783"])
        self.assertEqual(con_ventana, sin_ventana)


# ─────────────────────────────────────────────
# RF-3 — Puerta de insolación (T-08)
# ─────────────────────────────────────────────

class TestPuerta(unittest.TestCase):
    def test_estacion_sin_insolacion_aborta(self):
        filas = serie("9434", "2026-06-01", 60, nulos=tuple(range(60)))
        informe = solar.coverage_report(filas, ["9434"])
        catalogo = [e for e in catalogo_valido() if e["indicativo"] == "9434"]

        with self.assertRaises(solar.InsolationError) as ctx:
            solar.assert_insolation(informe, catalogo)
        mensaje = str(ctx.exception)
        self.assertIn("9434", mensaje)
        self.assertIn("Chiprana-Samper", mensaje)
        self.assertIn("sustituir", mensaje.lower())

    def test_cobertura_insuficiente_aborta(self):
        # Caspe real: 52,8 % de nulos
        filas = serie("9574B", "2026-06-01", 100, nulos=tuple(range(53)))
        informe = solar.coverage_report(filas, ["9574B"])
        catalogo = [{"planta": "Chiprana-Samper", "indicativo": "9574B"}]

        with self.assertRaises(solar.InsolationError) as ctx:
            solar.assert_insolation(informe, catalogo)
        self.assertIn("47.0", str(ctx.exception).replace(",", "."))

    def test_hueco_excesivo_aborta(self):
        filas = serie("5783", "2026-06-01", 40, nulos=tuple(range(5, 25)))
        informe = solar.coverage_report(filas, ["5783"])
        catalogo = [{"planta": "Don Rodrigo", "indicativo": "5783"}]

        with self.assertRaises(solar.InsolationError) as ctx:
            solar.assert_insolation(informe, catalogo)
        self.assertIn("20", str(ctx.exception))

    def test_sevilla_real_pasa(self):
        # 94,6 % de cobertura y hueco máximo de 3 días
        filas = serie("5783", "2026-06-01", 100, nulos=(1, 2, 3, 4, 50))
        informe = solar.coverage_report(filas, ["5783"])
        catalogo = [{"planta": "Don Rodrigo", "indicativo": "5783"}]

        solar.assert_insolation(informe, catalogo)


# ─────────────────────────────────────────────
# RF-5 — Serie diaria nacional (T-09)
# ─────────────────────────────────────────────

class TestSerieDiaria(unittest.TestCase):
    def test_media_de_las_estaciones_disponibles(self):
        filas = []
        for est, valor in [("3469A", 10.0), ("4452", 20.0), ("7228", None),
                           ("5783", 30.0), ("9434", None)]:
            filas.append({"fecha": "2026-06-01", "indicativo": est, "sol": valor, "tmed": 20.0})

        diario = solar.daily_national_series(filas)

        self.assertEqual(len(diario), 1)
        self.assertAlmostEqual(diario[0]["sol"], 20.0)
        self.assertEqual(diario[0]["n_estaciones"], 3)

    def test_dia_sin_ninguna_estacion_aborta(self):
        filas = [
            {"fecha": "2026-06-01", "indicativo": est, "sol": None, "tmed": None}
            for est in ["3469A", "4452", "7228", "5783", "9434"]
        ]
        with self.assertRaises(solar.InsolationError) as ctx:
            solar.daily_national_series(filas)
        self.assertIn("2026-06-01", str(ctx.exception))

    def test_nan_de_pandas_se_trata_como_ausente(self):
        filas = [
            {"fecha": "2026-06-01", "indicativo": "5783", "sol": float("nan"), "tmed": 20.0},
            {"fecha": "2026-06-01", "indicativo": "9434", "sol": 12.0, "tmed": 18.0},
        ]
        diario = solar.daily_national_series(filas)
        self.assertAlmostEqual(diario[0]["sol"], 12.0)
        self.assertEqual(diario[0]["n_estaciones"], 1)


# ─────────────────────────────────────────────
# RF-5 / RF-6 — Variables (T-10)
# ─────────────────────────────────────────────

def diario_sintetico(n=20):
    return [
        {"fecha": fecha, "sol": float(i % 10), "tmed": 20.0 + (i % 5), "n_estaciones": 5}
        for i, fecha in enumerate(dias("2026-01-01", n))
    ]


def objetivo_sintetico(n=20):
    return [{"fecha": fecha, "valor": 100.0 + 10 * i} for i, fecha in enumerate(dias("2026-01-01", n))]


class TestVariables(unittest.TestCase):
    def test_lista_exacta_de_16_features(self):
        registros, features, _ = solar.build_features(diario_sintetico(), objetivo_sintetico())

        self.assertEqual(features, [
            "sol", "tmed", "mes", "dia_semana", "dia_año",
            "solar_lag1", "solar_lag2", "solar_lag3", "solar_lag7",
            "sol_ma3", "sol_ma7", "sol_ma14",
            "tmed_ma3", "tmed_ma7", "tmed_ma14",
            "solar_ma7",
        ])
        self.assertEqual(len(registros[0]), len(features) + 2)  # fecha + objetivo

    def test_lag7_apunta_a_siete_dias_naturales_antes(self):
        diario = diario_sintetico(20)
        objetivo = objetivo_sintetico(20)
        registros, _, _ = solar.build_features(diario, objetivo)

        por_fecha = {r["fecha"]: r for r in registros}
        fila = por_fecha["2026-01-17"]  # día 17
        self.assertAlmostEqual(fila["solar_lag7"], 100.0 + 10 * 9)  # 10 de enero (día 10)

    def test_sin_fuga_de_datos(self):
        diario = diario_sintetico(20)
        objetivo = objetivo_sintetico(20)
        registros, _, _ = solar.build_features(diario, objetivo)

        por_fecha = {r["fecha"]: r for r in registros}
        fila = por_fecha["2026-01-17"]
        # solar_ma7 = media del objetivo de los 7 días ANTERIORES (10..16)
        esperado = sum(100.0 + 10 * i for i in range(9, 16)) / 7
        self.assertAlmostEqual(fila["solar_ma7"], esperado)

    def test_hueco_interno_no_desplaza_los_retardos(self):
        diario = diario_sintetico(20)
        diario = [r for r in diario if r["fecha"] != "2026-01-06"]  # hueco real
        objetivo = objetivo_sintetico(20)

        registros, _, resumen = solar.build_features(diario, objetivo)

        por_fecha = {r["fecha"]: r for r in registros}
        self.assertNotIn("2026-01-06", por_fecha)
        self.assertAlmostEqual(por_fecha["2026-01-17"]["solar_lag7"], 100.0 + 10 * 9)
        self.assertGreater(resumen["descartados"], 0)

    def test_sin_objetivo_no_hay_fila(self):
        diario = diario_sintetico(20)
        objetivo = objetivo_sintetico(15)  # se corta antes
        registros, _, resumen = solar.build_features(diario, objetivo)

        self.assertEqual(max(r["fecha"] for r in registros), "2026-01-15")
        self.assertGreater(resumen["recorte_dias"], 0)

    def test_objetivo_con_fecha_repetida_aborta(self):
        objetivo = objetivo_sintetico(20)
        objetivo.append({"fecha": "2026-01-05", "valor": 999.0})

        with self.assertRaises(ValueError) as ctx:
            solar.build_features(diario_sintetico(20), objetivo)
        self.assertIn("duplicad", str(ctx.exception).lower())

    def test_meteorologia_con_fecha_repetida_aborta(self):
        diario = diario_sintetico(20)
        diario.append(dict(diario[3]))

        with self.assertRaises(ValueError) as ctx:
            solar.build_features(diario, objetivo_sintetico(20))
        self.assertIn("duplicad", str(ctx.exception).lower())

    def test_media_movil_promedia_solo_la_ventana_natural(self):
        diario = diario_sintetico(20)
        diario = [r for r in diario if r["fecha"] != "2026-01-17"]  # falta el día 17
        registros, _, _ = solar.build_features(diario, objetivo_sintetico(20))

        por_fecha = {r["fecha"]: r for r in registros}
        # sol del 1 al 19: i%10 → día 15 = 4, 16 = 5, 17 ausente, 18 = 7.
        # La ventana es de 3 días NATURALES (16, 17, 18), no de los 3 últimos
        # valores disponibles: si se estirara hacia atrás, un hueco largo
        # metería días de otra estación del año en la media.
        self.assertAlmostEqual(por_fecha["2026-01-18"]["sol_ma3"], (5 + 7) / 2)


# ─────────────────────────────────────────────
# RF-8 — Partición (T-11)
# ─────────────────────────────────────────────

class TestSplit(unittest.TestCase):
    def test_ochenta_veinte(self):
        self.assertEqual(solar.temporal_split_index(10), 8)
        self.assertEqual(solar.temporal_split_index(1635), 1308)

    def test_serie_demasiado_corta(self):
        with self.assertRaises(ValueError):
            solar.temporal_split_index(0)


# ─────────────────────────────────────────────
# RF-9 — Métricas (T-12, T-13)
# ─────────────────────────────────────────────

class TestMetricas(unittest.TestCase):
    def test_bordes_por_interpolacion_lineal(self):
        bordes = solar.quintile_edges([10, 20, 30, 40, 50])
        self.assertEqual(bordes[0], -math.inf)
        self.assertEqual(bordes[-1], math.inf)
        self.assertEqual(bordes[1:5], [18.0, 26.0, 34.0, 42.0])

    def test_metricas_calculadas_a_mano(self):
        bordes = solar.quintile_edges([10, 20, 30, 40, 50])
        m = solar.regression_metrics([10, 20, 30, 40], [12, 18, 33, 37], bordes)

        self.assertAlmostEqual(m["rmse"], math.sqrt(6.5), places=4)
        self.assertAlmostEqual(m["mae"], 2.5, places=4)
        self.assertAlmostEqual(m["r2"], 0.948, places=4)
        self.assertAlmostEqual(m["mape"], 11.875, places=3)
        self.assertAlmostEqual(m["accuracy"], 100.0, places=1)
        self.assertEqual(m["mape_excluidos"], 0)

    def test_objetivo_cero_no_rompe_el_mape(self):
        bordes = solar.quintile_edges([0, 10, 20, 30, 40])
        m = solar.regression_metrics([0, 20, 30], [1, 18, 33], bordes)

        self.assertEqual(m["mape_excluidos"], 1)
        self.assertTrue(math.isfinite(m["mape"]))

    def test_metricas_reproducibles(self):
        bordes = solar.quintile_edges([10, 20, 30, 40, 50])
        a = solar.regression_metrics([10, 20, 30, 40], [12, 18, 33, 37], bordes)
        b = solar.regression_metrics([10, 20, 30, 40], [12, 18, 33, 37], bordes)
        self.assertEqual(a, b)


# ─────────────────────────────────────────────
# RF-2 / RF-11 — Ventana y trazabilidad (T-04, T-14)
# ─────────────────────────────────────────────

class TestVentanaYRegistro(unittest.TestCase):
    def test_fin_es_tres_dias_antes_de_hoy(self):
        inicio, fin = solar.study_window(date(2026, 6, 27))
        self.assertEqual(inicio, date(2022, 1, 1))
        self.assertEqual(fin, date(2026, 6, 24))

    def test_el_fin_nunca_es_hoy_ni_posterior(self):
        for dia in (1, 15, 28):
            hoy = date(2026, 6, dia)
            _, fin = solar.study_window(hoy)
            self.assertLess(fin, hoy)

    def test_registro_de_trazabilidad(self):
        catalogo = catalogo_valido()
        cobertura = {e["indicativo"]: {"sol": {"missing_pct": 1.0, "max_gap_days": 0,
                                               "days": 100, "with_data": 99}} for e in catalogo}
        metricas = {"rmse": 1.0, "mae": 1.0, "r2": 0.9, "mape": 10.0, "accuracy": 50.0}

        informe = solar.solar_report(catalogo, cobertura, metricas, date(2026, 6, 27))

        self.assertEqual(len(informe["estaciones"]), 5)
        self.assertEqual(informe["fecha_ejecucion"], "2026-06-27")
        self.assertEqual(informe["metricas"]["r2"], 0.9)
        primera = informe["estaciones"][0]
        self.assertEqual(primera["planta"], "Francisco Pizarro")
        self.assertEqual(primera["indicativo"], "3469A")
        self.assertEqual(primera["distancia_km"], 56)
        self.assertIn("sol", primera["cobertura"])

    def test_registro_es_serializable(self):
        import json
        catalogo = catalogo_valido()
        cobertura = {e["indicativo"]: {"sol": {"missing_pct": 0.0, "max_gap_days": 0,
                                               "days": 1, "with_data": 1}} for e in catalogo}
        informe = solar.solar_report(catalogo, cobertura, {"r2": 0.5}, date(2026, 6, 27))
        json.dumps(informe)

    def test_dos_llamadas_dan_el_mismo_registro(self):
        catalogo = catalogo_valido()
        cobertura = {e["indicativo"]: {"sol": {"missing_pct": 0.5, "max_gap_days": 1,
                                               "days": 10, "with_data": 10}} for e in catalogo}

        primero = solar.solar_report(catalogo, cobertura, {"r2": 0.9}, date(2026, 6, 27))
        segundo = solar.solar_report(catalogo, cobertura, {"r2": 0.9}, date(2026, 6, 27))

        self.assertEqual(primero, segundo)


class TestLagSeries(unittest.TestCase):
    """RF-4: el retardo es el día natural anterior, nunca el último día con dato."""

    def serie(self, registros):
        return [{"fecha": fecha, "sol": sol} for fecha, sol in registros]

    def test_dia_anterior_con_dato(self):
        serie = self.serie([("2026-01-01", 5.0), ("2026-01-02", 7.0)])
        self.assertEqual(solar.lag_series(serie, "sol"), [None, 5.0])

    def test_primer_dia_sin_anterior(self):
        serie = self.serie([("2026-01-01", 5.0)])
        self.assertIsNone(solar.lag_series(serie, "sol")[0])

    def test_dia_anterior_ausente_no_arrastra_el_ultimo_dato(self):
        serie = self.serie([("2026-01-01", 5.0), ("2026-01-03", 7.0)])
        self.assertEqual(solar.lag_series(serie, "sol"), [None, None])

    def test_dia_anterior_con_valor_nulo(self):
        serie = self.serie([("2026-01-01", None), ("2026-01-02", 7.0)])
        self.assertIsNone(solar.lag_series(serie, "sol")[1])

    def test_cambio_de_mes(self):
        serie = self.serie([("2026-01-31", 4.0), ("2026-02-01", 6.0)])
        self.assertEqual(solar.lag_series(serie, "sol"), [None, 4.0])

    def test_cambio_de_ano(self):
        serie = self.serie([("2025-12-31", 4.0), ("2026-01-01", 6.0)])
        self.assertEqual(solar.lag_series(serie, "sol"), [None, 4.0])

    def test_bisiesto(self):
        serie = self.serie([("2024-02-28", 3.0), ("2024-02-29", 4.0), ("2024-03-01", 5.0)])
        self.assertEqual(solar.lag_series(serie, "sol"), [None, 3.0, 4.0])

    def test_misma_longitud_que_la_entrada(self):
        serie = self.serie([(f"2026-01-{dia:02d}", float(dia)) for dia in range(1, 11)])
        self.assertEqual(len(solar.lag_series(serie, "sol")), len(serie))

    def test_serie_vacia_devuelve_lista_vacia(self):
        self.assertEqual(solar.lag_series([], "sol"), [])

    def test_variable_inexistente_lanza_error(self):
        serie = self.serie([("2026-01-01", 5.0)])
        with self.assertRaises(ValueError):
            solar.lag_series(serie, "tmed")


if __name__ == "__main__":
    unittest.main()
