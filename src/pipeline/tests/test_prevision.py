"""Contrato de la lógica pura del mapa de orígenes (spec 004, RF-4 y RF-5).

Sin red, sin pandas y sin reloj: `hoy` entra siempre como parámetro. La puerta
`node --test` descubre esta suite a través de `gate.test.mjs`.

Lo que se protege aquí es la honestidad del vector de mañana: una ventana
toma cada día de la observación si existe y de la previsión si no, declarando
cuántos días aporta cada origen; sin dato la variable queda no disponible y no
se rellena; el valor real solo puede salir de `generacion`, jamás de una
previsión archivada.
"""

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "src" / "pipeline"))

import prevision  # noqa: E402

INICIO = date(2026, 1, 1)
OBJETIVO = date(2026, 1, 16)
HOY = date(2026, 1, 15)


def serie(desde, hasta, valor, salvo=None):
    """Mapa fecha → valor para los días del rango, con huecos opcionales."""
    salvo = salvo or {}
    dias = (hasta - desde).days + 1
    return {
        desde + timedelta(days=desplazamiento): salvo.get(
            desde + timedelta(days=desplazamiento), valor)
        for desplazamiento in range(dias)
        if (desde + timedelta(days=desplazamiento)) not in salvo.get("_fuera", set())
    }


def mapa_completo():
    """Entradas completas: observación hasta hoy y previsión hasta el objetivo."""
    obs_meteo = {
        dia: {"velmedia": 5.0, "racha": 10.0}
        for dia in serie(date(2026, 1, 2), HOY, 0.0)
    }
    prev = {
        "viento": serie(date(2026, 1, 2), date(2026, 1, 20), 6.0),
        "racha": serie(date(2026, 1, 2), date(2026, 1, 20), 12.0),
        "sol": serie(date(2026, 1, 2), date(2026, 1, 20), 9.0),
        "tmed": serie(date(2026, 1, 2), date(2026, 1, 20), 13.0),
        "generacion": serie(date(2026, 1, 2), date(2026, 1, 20), 2000.0),
    }
    obs_solar = {HOY: {"sol": 8.0, "tmed": 12.0}}
    obs_gen = serie(date(2026, 1, 1), HOY, 1000.0)
    return obs_meteo, obs_solar, obs_gen, prev


class TestVentanaMixta(unittest.TestCase):
    def test_una_ventana_completa_de_observacion(self):
        obs = {date(2026, 1, 1): 10.0, date(2026, 1, 2): 20.0,
               date(2026, 1, 3): 30.0}
        resultado = prevision.ventana_mixta(
            obs, {}, date(2026, 1, 3), 3, date(2026, 1, 3))
        self.assertEqual(resultado, (20.0, "observacion"))

    def test_una_ventana_completa_de_prevision(self):
        prev = {date(2026, 1, 1): 100.0, date(2026, 1, 2): 200.0,
                date(2026, 1, 3): 300.0}
        resultado = prevision.ventana_mixta(
            {}, prev, date(2026, 1, 3), 3, date(2026, 1, 3))
        self.assertEqual(resultado, (200.0, "prevision"))

    def test_cada_hueco_se_completa_con_la_prevision_oficial(self):
        obs = {date(2026, 1, 2): 20.0, date(2026, 1, 3): 30.0}
        prev = {date(2026, 1, 1): 100.0, date(2026, 1, 2): 200.0,
                date(2026, 1, 3): 300.0}
        self.assertEqual(
            prevision.ventana_mixta(obs, prev, date(2026, 1, 3), 3,
                                    date(2026, 1, 3)),
            (50.0, "mixta"),
        )

    def test_una_ventana_incompleta_en_las_dos_series_es_no_disponible(self):
        obs = {date(2026, 1, 3): 30.0}
        prev = {date(2026, 1, 1): 100.0, date(2026, 1, 3): 300.0}
        self.assertIsNone(
            prevision.ventana_mixta(obs, prev, date(2026, 1, 3), 3,
                                    date(2026, 1, 3))
        )

    def test_la_ventana_no_se_acorta(self):
        obs = serie(date(2026, 1, 1), date(2026, 1, 13), 5.0)   # 13 días
        self.assertIsNone(
            prevision.ventana_mixta(obs, {}, date(2026, 1, 14), 14,
                                    date(2026, 1, 14))
        )

    def test_la_observacion_no_puede_venir_de_despues_de_hoy(self):
        obs = serie(date(2026, 1, 1), date(2026, 1, 3), 5.0)
        prev = serie(date(2026, 1, 1), date(2026, 1, 3), 9.0)
        # Aunque la serie traiga una observación del 3, hoy es el 2: esa celda
        # no se puede leer y se toma la previsión del 3.
        self.assertEqual(
            prevision.ventana_mixta(obs, prev, date(2026, 1, 3), 3,
                                    date(2026, 1, 2)),
            ((5.0 + 5.0 + 9.0) / 3, "mixta"),
        )

    def test_la_prevision_si_puede_cubrir_dias_futuros(self):
        prev = serie(date(2026, 1, 1), date(2026, 1, 3), 9.0)
        self.assertEqual(
            prevision.ventana_mixta({}, prev, date(2026, 1, 3), 3,
                                    date(2026, 1, 2)),
            (9.0, "prevision"),
        )

    def test_el_caso_real_toma_dos_dias_observados_y_cinco_previstos(self):
        obs = serie(date(2026, 11, 1), date(2026, 11, 7), 5.0)
        prev = serie(date(2026, 11, 7), date(2026, 11, 17), 9.0)
        valor, origen = prevision.ventana_mixta(
            obs, prev, date(2026, 11, 12), 7, date(2026, 11, 11))
        self.assertAlmostEqual(valor, (2 * 5.0 + 5 * 9.0) / 7)
        self.assertEqual(origen, "mixta")


class TestOrigenVariable(unittest.TestCase):
    def test_el_calendario_es_siempre_observacion(self):
        for nombre in ("mes", "dia_semana", "dia_año"):
            self.assertEqual(
                prevision.origen_variable(nombre, None, None), "observacion")

    def test_el_viento_del_objetivo_es_siempre_prevision(self):
        # Aunque exista una observación reciente, el día objetivo no se observa.
        for nombre in ("velmedia", "racha"):
            self.assertEqual(
                prevision.origen_variable(nombre, 5.0, 6.0), "prevision")

    def test_el_sol_previsto_se_declara_estimado(self):
        self.assertEqual(
            prevision.origen_variable("sol_lag1", None, 8.0), "estimada")

    def test_la_temperatura_prevista_es_prevision(self):
        self.assertEqual(
            prevision.origen_variable("tmed_lag1", None, 15.0), "prevision")

    def test_la_generacion_observada_es_observacion(self):
        self.assertEqual(
            prevision.origen_variable("eolica_lag1", 1000.0, None),
            "observacion")

    def test_la_generacion_prevista_es_prevision(self):
        self.assertEqual(
            prevision.origen_variable("eolica_lag1", None, 1000.0),
            "prevision")

    def test_sin_valor_no_hay_origen(self):
        self.assertIsNone(prevision.origen_variable("vel_ma3", None, None))


class TestMapaOrigenes(unittest.TestCase):
    def test_el_mapa_tiene_las_18_variables_del_modelo(self):
        mapa = prevision.resolver_origenes(*mapa_completo(), OBJETIVO, HOY)
        self.assertEqual(len(mapa), 18)
        self.assertEqual(
            set(mapa),
            {
                "mes", "dia_semana", "dia_año",
                "velmedia", "racha",
                "vel_ma3", "vel_ma7", "vel_ma14",
                "racha_ma3", "racha_ma7", "racha_ma14",
                "sol_lag1", "tmed_lag1",
                "eolica_lag1", "eolica_lag2", "eolica_lag3",
                "eolica_lag7", "eolica_ma7",
            },
        )

    def test_el_calendario_sale_del_dia_objetivo(self):
        mapa = prevision.resolver_origenes(*mapa_completo(), OBJETIVO, HOY)
        self.assertEqual(mapa["mes"]["valor"], 1)
        self.assertEqual(mapa["dia_semana"]["valor"], 4)   # viernes
        self.assertEqual(mapa["dia_año"]["valor"], 16)
        for nombre in ("mes", "dia_semana", "dia_año"):
            self.assertEqual(mapa[nombre]["origen"], "observacion")

    def test_el_viento_del_objetivo_viene_de_la_prevision(self):
        mapa = prevision.resolver_origenes(*mapa_completo(), OBJETIVO, HOY)
        self.assertEqual(mapa["velmedia"], {"valor": 6.0, "origen": "prevision"})
        self.assertEqual(mapa["racha"], {"valor": 12.0, "origen": "prevision"})

    def test_las_medias_moviles_declaran_su_desglose_mixto(self):
        mapa = prevision.resolver_origenes(*mapa_completo(), OBJETIVO, HOY)
        desgloses = {
            "vel_ma3": (2, 1), "vel_ma7": (6, 1), "vel_ma14": (13, 1),
            "racha_ma3": (2, 1), "racha_ma7": (6, 1), "racha_ma14": (13, 1),
        }
        for nombre, (observados, previstos) in desgloses.items():
            self.assertEqual(mapa[nombre]["origen"], "mixta", nombre)
            self.assertEqual(mapa[nombre]["dias_observados"], observados, nombre)
            self.assertEqual(mapa[nombre]["dias_previstos"], previstos, nombre)
            self.assertIsNotNone(mapa[nombre]["valor"], nombre)

    def test_una_ventana_entera_no_declara_desglose_mixto(self):
        obs_meteo, obs_solar, obs_gen, prev = mapa_completo()
        mapa = prevision.resolver_origenes(
            obs_meteo, obs_solar, obs_gen, prev, HOY, HOY)
        self.assertEqual(mapa["vel_ma3"], {"valor": 5.0, "origen": "observacion"})

    def test_sin_prevision_para_manana_las_variables_quedan_no_disponibles(self):
        obs_meteo, obs_solar, obs_gen, prev = mapa_completo()
        prev = dict(prev)
        prev["viento"] = serie(date(2026, 1, 2), HOY, 6.0)
        prev["racha"] = serie(date(2026, 1, 2), HOY, 12.0)

        mapa = prevision.resolver_origenes(
            obs_meteo, obs_solar, obs_gen, prev, OBJETIVO, HOY)
        self.assertEqual(mapa["velmedia"], {"valor": None, "origen": None})
        self.assertEqual(mapa["racha"], {"valor": None, "origen": None})
        self.assertIsNone(mapa["vel_ma3"]["valor"])

    def test_el_sol_del_dia_anterior_es_observacion(self):
        mapa = prevision.resolver_origenes(*mapa_completo(), OBJETIVO, HOY)
        self.assertEqual(mapa["sol_lag1"], {"valor": 8.0, "origen": "observacion"})
        self.assertEqual(mapa["tmed_lag1"], {"valor": 12.0, "origen": "observacion"})

    def test_sin_observacion_solar_el_sol_previsto_es_estimado(self):
        obs_meteo, _, obs_gen, prev = mapa_completo()
        mapa = prevision.resolver_origenes(
            obs_meteo, {}, obs_gen, prev, OBJETIVO, HOY)
        self.assertEqual(mapa["sol_lag1"], {"valor": 9.0, "origen": "estimada"})
        self.assertEqual(mapa["tmed_lag1"], {"valor": 13.0, "origen": "prevision"})

    def test_la_generacion_se_ancla_en_el_ultimo_dia_completo(self):
        obs_meteo, obs_solar, obs_gen, prev = mapa_completo()
        obs_gen = dict(obs_gen)
        obs_gen[HOY] = 100.0   # 10 % de la mediana: día incompleto

        mapa = prevision.resolver_origenes(
            obs_meteo, obs_solar, obs_gen, prev, OBJETIVO, HOY)
        self.assertEqual(mapa["eolica_lag1"], {"valor": 1000.0, "origen": "observacion"})

    def test_un_hueco_de_generacion_no_se_rellena_sin_prevision(self):
        obs_meteo, obs_solar, obs_gen, prev = mapa_completo()
        obs_gen = dict(obs_gen)
        obs_gen.pop(date(2026, 1, 13))   # eolica_lag3

        mapa = prevision.resolver_origenes(
            obs_meteo, obs_solar, obs_gen, prev, OBJETIVO, HOY)
        self.assertEqual(mapa["eolica_lag3"], {"valor": None, "origen": None})
        self.assertIsNone(mapa["eolica_ma7"]["valor"])

    def test_el_hueco_de_generacion_solo_se_rellena_si_se_permite(self):
        obs_meteo, obs_solar, obs_gen, prev = mapa_completo()
        obs_gen = dict(obs_gen)
        obs_gen.pop(date(2026, 1, 13))

        mapa = prevision.resolver_origenes(
            obs_meteo, obs_solar, obs_gen, prev, OBJETIVO, HOY,
            permitir_prev_gen=True,
        )
        self.assertEqual(
            mapa["eolica_lag3"], {"valor": 2000.0, "origen": "prevision"})
        self.assertEqual(mapa["eolica_ma7"]["origen"], "mixta")
        self.assertEqual(mapa["eolica_ma7"]["dias_observados"], 6)
        self.assertEqual(mapa["eolica_ma7"]["dias_previstos"], 1)


class TestRealesPendientes(unittest.TestCase):
    def test_solo_devuelve_predicciones_sin_real_con_generacion(self):
        predicciones = [
            {"fecha_objetivo": date(2026, 1, 10), "real_mwh": None},
            {"fecha_objetivo": date(2026, 1, 11), "real_mwh": None},
            {"fecha_objetivo": date(2026, 1, 12), "real_mwh": 900.0},
        ]
        generacion = {
            date(2026, 1, 10): 1000.0,
            date(2026, 1, 12): 1200.0,
        }
        pendientes = prevision.reales_pendientes(
            predicciones, generacion, date(2026, 1, 12))
        self.assertEqual(
            pendientes,
            [{"fecha_objetivo": date(2026, 1, 10), "real_mwh": 1000.0}],
        )

    def test_una_prevision_archivada_nunca_hace_de_real(self):
        predicciones = [{"fecha_objetivo": date(2026, 1, 10), "real_mwh": None}]
        self.assertEqual(
            prevision.reales_pendientes(
                predicciones, {}, date(2026, 1, 10)),
            [],
        )

    def test_un_dia_incompleto_no_se_usa_como_real(self):
        predicciones = [{"fecha_objetivo": date(2026, 1, 10), "real_mwh": None}]
        generacion = serie(date(2026, 1, 1), date(2026, 1, 10), 1000.0)
        generacion[date(2026, 1, 10)] = 100.0   # incompleto
        self.assertEqual(
            prevision.reales_pendientes(
                predicciones, generacion, date(2026, 1, 10)),
            [],
        )


class TestErrorYMAE(unittest.TestCase):
    def test_el_error_es_real_menos_prediccion(self):
        self.assertEqual(prevision.con_error(5000.0, 5300.0), 300.0)
        self.assertEqual(prevision.con_error(5000.0, 4700.0), -300.0)

    def test_sin_real_no_hay_error(self):
        self.assertIsNone(prevision.con_error(5000.0, None))

    def test_el_mae_usa_solo_las_que_tienen_real(self):
        predicciones = [
            {"fecha_objetivo": date(2026, 1, 1),
             "prediccion_mwh": 100.0, "real_mwh": 110.0},
            {"fecha_objetivo": date(2026, 1, 2),
             "prediccion_mwh": 200.0, "real_mwh": 180.0},
            {"fecha_objetivo": date(2026, 1, 3),
             "prediccion_mwh": 300.0, "real_mwh": None},
        ]
        resumen = prevision.mae_produccion(predicciones, limite=30)
        self.assertEqual(resumen["n"], 2)
        self.assertEqual(resumen["mae"], 15.0)
        self.assertEqual(resumen["desde"], date(2026, 1, 1))
        self.assertEqual(resumen["hasta"], date(2026, 1, 2))

    def test_el_mae_respeta_el_limite_de_las_ultimas(self):
        predicciones = [
            {"fecha_objetivo": date(2026, 1, dia),
             "prediccion_mwh": 100.0, "real_mwh": 100.0 + dia}
            for dia in range(1, 6)
        ]
        resumen = prevision.mae_produccion(predicciones, limite=2)
        self.assertEqual(resumen["n"], 2)
        self.assertEqual(resumen["desde"], date(2026, 1, 4))
        self.assertEqual(resumen["mae"], 4.5)


class TestNanDePandas(unittest.TestCase):
    """`NaN` es un hueco, no un valor: la frontera con pandas no debe colarse.

    El notebook lee el archivo con pandas y una celda SQL NULL llega como
    `float('nan')`. Si la lógica pura lo trata como número, la media sale NaN y
    la predicción acaba con un valor que no es ni observación ni previsión.
    """

    def test_un_nan_no_es_un_valor_de_la_ventana(self):
        obs = {date(2026, 1, 2): float("nan"), date(2026, 1, 3): 30.0}
        prev = {date(2026, 1, 1): 100.0, date(2026, 1, 2): 200.0,
                date(2026, 1, 3): 300.0}
        self.assertEqual(
            prevision.ventana_mixta(
                obs, prev, date(2026, 1, 3), 3, date(2026, 1, 3)),
            (110.0, "mixta"),
        )

    def test_un_nan_en_la_prevision_del_dia_es_no_disponible(self):
        obs_meteo, obs_solar, obs_gen, prev = mapa_completo()
        prev = dict(prev)
        prev["viento"] = dict(prev["viento"])
        prev["viento"][OBJETIVO] = float("nan")

        mapa = prevision.resolver_origenes(
            obs_meteo, obs_solar, obs_gen, prev, OBJETIVO, HOY)
        self.assertEqual(mapa["velmedia"], {"valor": None, "origen": None})

    def test_un_nan_de_sol_no_se_declara_estimado(self):
        obs_meteo, _, obs_gen, prev = mapa_completo()
        prev = dict(prev)
        prev["sol"] = dict(prev["sol"])
        prev["sol"][HOY] = float("nan")

        mapa = prevision.resolver_origenes(
            obs_meteo, {}, obs_gen, prev, OBJETIVO, HOY)
        self.assertEqual(mapa["sol_lag1"], {"valor": None, "origen": None})

    def test_un_nan_de_generacion_no_hace_de_real(self):
        predicciones = [{"fecha_objetivo": date(2026, 1, 10), "real_mwh": None}]
        generacion = {date(2026, 1, 10): float("nan")}
        self.assertEqual(
            prevision.reales_pendientes(
                predicciones, generacion, date(2026, 1, 10)),
            [],
        )

    def test_un_nan_en_el_mae_no_cuenta_como_dia(self):
        predicciones = [
            {"fecha_objetivo": date(2026, 1, 1),
             "prediccion_mwh": 100.0, "real_mwh": 110.0},
            {"fecha_objetivo": date(2026, 1, 2),
             "prediccion_mwh": 200.0, "real_mwh": float("nan")},
        ]
        resumen = prevision.mae_produccion(predicciones)
        self.assertEqual(resumen["n"], 1)
        self.assertEqual(resumen["mae"], 10.0)


class TestSeriePrevisionGeneracion(unittest.TestCase):
    """Lectura del archivo de REE con la regla de elaboración (T-12).

    Lo que se protege: una revisión de hoy no puede usarse como valor de
    anteayer (fuga), sin elaboración declarada no hay fila elegible y un hueco
    sigue siendo un hueco.
    """

    def fila(self, objetivo, valor, elaborado, ubicacion="peninsula"):
        return {
            "objetivo": objetivo,
            "ubicacion": ubicacion,
            "uso": "eolica",
            "eolica_mwh": valor,
            "elaborado": elaborado,
        }

    def test_una_elaboracion_valida_es_la_del_dia(self):
        serie = prevision.serie_prevision_generacion([
            self.fila(date(2026, 11, 7), 61829.9, "2026-11-06T11:00:00+01:00"),
        ])
        self.assertEqual(serie, {date(2026, 11, 7): 61829.9})

    def test_gana_la_elaboracion_mas_reciente(self):
        serie = prevision.serie_prevision_generacion([
            self.fila(date(2026, 11, 8), 100.0, "2026-11-07T10:50:22+01:00"),
            self.fila(date(2026, 11, 8), 200.0, "2026-11-07T18:30:00+01:00"),
        ])
        self.assertEqual(serie, {date(2026, 11, 8): 200.0})

    def test_una_elaboracion_posterior_al_objetivo_es_una_fuga(self):
        serie = prevision.serie_prevision_generacion([
            self.fila(date(2026, 11, 7), 100.0, "2026-11-07T10:00:00+01:00"),
            self.fila(date(2026, 11, 7), 999.0, "2026-11-08T10:00:00+01:00"),
        ])
        self.assertEqual(serie, {date(2026, 11, 7): 100.0})

    def test_si_la_unica_elaboracion_es_posterior_el_dia_queda_ausente(self):
        serie = prevision.serie_prevision_generacion([
            self.fila(date(2026, 11, 7), 999.0, "2026-11-08T10:00:00+01:00"),
        ])
        self.assertEqual(serie, {})

    def test_sin_elaboracion_declarada_no_es_elegible(self):
        for elaborado in ("", None):
            with self.subTest(elaborado=elaborado):
                serie = prevision.serie_prevision_generacion([
                    self.fila(date(2026, 11, 7), 100.0, elaborado),
                ])
                self.assertEqual(serie, {})

    def test_un_valor_ausente_o_nan_no_entra(self):
        for valor in (None, float("nan")):
            with self.subTest(valor=valor):
                serie = prevision.serie_prevision_generacion([
                    self.fila(date(2026, 11, 7), valor, "2026-11-06T11:00:00"),
                ])
                self.assertEqual(serie, {})

    def test_otra_ubicacion_no_es_la_peninsula(self):
        serie = prevision.serie_prevision_generacion([
            self.fila(date(2026, 11, 7), 100.0, "2026-11-06T11:00:00", "canarias"),
        ])
        self.assertEqual(serie, {})

    def test_sin_filas_no_hay_serie(self):
        self.assertEqual(prevision.serie_prevision_generacion([]), {})
        self.assertEqual(prevision.serie_prevision_generacion(None), {})

    def test_devuelve_los_dias_en_orden(self):
        serie = prevision.serie_prevision_generacion([
            self.fila(date(2026, 11, 8), 2.0, "2026-11-07T11:00:00"),
            self.fila(date(2026, 11, 7), 1.0, "2026-11-06T11:00:00"),
        ])
        self.assertEqual(list(serie), [date(2026, 11, 7), date(2026, 11, 8)])

    def test_una_elaboracion_naive_y_otra_aware_se_comparan(self):
        serie = prevision.serie_prevision_generacion([
            self.fila(date(2026, 11, 8), 100.0, "2026-11-07T10:00:00"),
            self.fila(date(2026, 11, 8), 200.0, "2026-11-07T18:00:00+01:00"),
        ])
        self.assertEqual(serie, {date(2026, 11, 8): 200.0})


if __name__ == "__main__":
    unittest.main()
