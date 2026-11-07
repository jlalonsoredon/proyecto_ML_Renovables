"""Contrato de la lógica pura del archivo de previsiones (spec 003).

Se ejecuta con `python -m unittest discover` y la puerta real es `node --test`
(gate.test.mjs). Sin red: los partes se leen de `fixtures/`.
"""

import json
import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import forecast  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def parte(nombre: str) -> dict:
    return json.loads((FIXTURES / f"prediccion_{nombre}.json").read_text(encoding="utf-8"))


def fila(**cambios):
    """Fila de archivo mínima; cada test cambia solo lo que le importa."""
    base = {
        "elaborado": datetime(2026, 10, 30, 8, 59),
        "objetivo": date(2026, 11, 1),
        "ubicacion": "Gecama (Cuenca)",
        "uso": "eolica",
        "viento_ms": 5.0,
        "racha_ms": 9.0,
        "tmed": 12.0,
        "sol": None,
        "capturado_en": datetime(2026, 10, 30, 9, 5),
    }
    base.update(cambios)
    return base


# ─────────────────────────────────────────────
# T-02 · Catálogo
# ─────────────────────────────────────────────

class TestCatalogo(unittest.TestCase):
    def test_hay_doce_ubicaciones_con_su_uso(self):
        self.assertEqual(len(forecast.UBICACIONES), 12)
        usos = [u["uso"] for u in forecast.UBICACIONES]
        self.assertEqual(usos.count("eolica"), 7)
        self.assertEqual(usos.count("solar"), 5)

    def test_las_claves_son_unicas_y_los_codigos_validos(self):
        claves = [u["clave"] for u in forecast.UBICACIONES]
        self.assertEqual(len(claves), len(set(claves)))
        for ubicacion in forecast.UBICACIONES:
            self.assertRegex(ubicacion["municipio"], r"^\d{5}$", ubicacion["clave"])
            self.assertIsInstance(ubicacion["lat"], float)
            self.assertIn(ubicacion["uso"], ("eolica", "solar"))

    def test_validate_locations_rechaza_un_catalogo_incompleto(self):
        with self.assertRaises(ValueError):
            forecast.validate_locations(forecast.UBICACIONES[:11])
        repetido = [dict(u) for u in forecast.UBICACIONES]
        repetido[1]["clave"] = repetido[0]["clave"]
        with self.assertRaises(ValueError):
            forecast.validate_locations(repetido)


# ─────────────────────────────────────────────
# T-03 · Parseo de los partes
# ─────────────────────────────────────────────

class TestParseoDiario(unittest.TestCase):
    def setUp(self):
        self.parte = forecast.parse_daily_parte(parte("diaria"))

    def test_elaborado_sale_del_propio_parte(self):
        self.assertEqual(self.parte["elaborado"], datetime(2026, 11, 2, 15, 45, 8))

    def test_devuelve_los_siete_dias_del_horizonte(self):
        fechas = [dia["fecha"] for dia in self.parte["dias"]]
        self.assertEqual(fechas[0], date(2026, 11, 2))
        self.assertEqual(fechas[-1], date(2026, 11, 8))
        self.assertEqual(len(fechas), 7)

    def test_viento_medio_en_kmh_y_extremos(self):
        dia = self.parte["dias"][0]
        self.assertAlmostEqual(dia["viento_kmh"], (15 + 5 + 10 + 15) / 4)
        self.assertEqual(dia["tmax"], 19.0)
        self.assertEqual(dia["tmin"], 3.0)

    def test_racha_vacia_es_ausente_no_cero(self):
        for dia in self.parte["dias"]:
            self.assertIsNone(dia["racha_kmh"])

    def test_cielo_en_tramos_de_seis_horas(self):
        tramos = self.parte["dias"][0]["tramos_cielo"]
        self.assertEqual([(i, f) for i, f, _ in tramos], [(0, 6), (6, 12), (12, 18), (18, 24)])
        self.assertIsNone(tramos[0][2])
        self.assertEqual(tramos[1][2], "12")
        self.assertEqual(tramos[3][2], "12n")

    def test_los_dias_lejanos_resumen_el_dia_en_un_unico_tramo(self):
        # AEMET omite el periodo cuando el valor vale para las 24 horas (11-06).
        dia = self.parte["dias"][4]
        self.assertEqual(dia["fecha"], date(2026, 11, 6))
        self.assertAlmostEqual(dia["viento_kmh"], 5.0)
        self.assertEqual(dia["tramos_cielo"], [(0.0, 24.0, "13")])

    def test_un_dia_lejano_todavia_tiene_sol_estimado(self):
        sol = forecast.estimate_sun([(0.0, 24.0, "13")], 39.4085, date(2026, 11, 6))
        self.assertIsNotNone(sol)
        self.assertGreater(sol, 0.0)


class TestParseoHorario(unittest.TestCase):
    def setUp(self):
        self.parte = forecast.parse_hourly_parte(parte("horaria"))

    def test_elaborado_y_horizonte_de_tres_dias(self):
        self.assertEqual(self.parte["elaborado"], datetime(2026, 11, 2, 15, 45, 8))
        self.assertEqual(len(self.parte["dias"]), 3)

    def test_temperaturas_y_vientos_por_hora(self):
        dia = self.parte["dias"][0]
        self.assertEqual(len(dia["temperaturas"]), 16)
        self.assertAlmostEqual(dia["temperaturas"][0], 6.0)
        self.assertEqual(len(dia["vientos_kmh"]), 16)
        self.assertEqual(len(dia["rachas_kmh"]), 16)
        self.assertAlmostEqual(dia["rachas_kmh"][0], 20.0)

    def test_orto_y_ocaso_en_horas_decimales(self):
        dia = self.parte["dias"][0]
        self.assertAlmostEqual(dia["orto"], 7 + 38 / 60)
        self.assertAlmostEqual(dia["ocaso"], 18 + 5 / 60)

    def test_cielo_horario(self):
        tramos = self.parte["dias"][0]["tramos_cielo"]
        self.assertEqual(tramos[0], (7, 8, "17n"))
        self.assertEqual(tramos[1], (8, 9, "11"))


# ─────────────────────────────────────────────
# T-09 · Temperatura
# ─────────────────────────────────────────────

class TestTemperatura(unittest.TestCase):
    def test_usa_la_media_horaria_cuando_cubre_el_dia(self):
        self.assertAlmostEqual(forecast.mean_temperature([10.0] * 12 + [20.0] * 12), 15.0)

    def test_cae_a_la_media_de_extremos_sin_horario(self):
        self.assertAlmostEqual(forecast.mean_temperature([], tmax=20.0, tmin=4.0), 12.0)

    def test_una_muestra_parcial_no_se_hace_pasar_por_la_media_del_dia(self):
        # Siete horas nocturnas darían 2,6 °C cuando el día promedia 8 °C.
        parcial = [0.0, 1.0, 1.0, 2.0, 3.0, 4.0, 6.0]
        self.assertAlmostEqual(forecast.mean_temperature(parcial, tmax=15.0, tmin=1.0), 8.0)

    def test_sin_extremos_se_usa_lo_que_haya(self):
        self.assertAlmostEqual(forecast.mean_temperature([10.0, 12.0]), 11.0)

    def test_sin_horario_ni_extremos_no_hay_valor(self):
        self.assertIsNone(forecast.mean_temperature([], tmax=20.0, tmin=None))
        self.assertIsNone(forecast.mean_temperature([]))


# ─────────────────────────────────────────────
# T-09 · Horas de luz y estado del cielo
# ─────────────────────────────────────────────

class TestHorasDeLuz(unittest.TestCase):
    def test_solsticio_de_invierno_y_de_verano(self):
        invierno = forecast.daylight_hours(39.4, date(2026, 12, 21))
        verano = forecast.daylight_hours(39.4, date(2026, 6, 21))
        self.assertTrue(9.0 < invierno < 9.6, invierno)
        self.assertTrue(14.6 < verano < 15.2, verano)

    def test_es_simetrica_respecto_al_ecuador_astronomico(self):
        equinoccio_primavera = forecast.daylight_hours(39.4, date(2026, 3, 20))
        equinoccio_otono = forecast.daylight_hours(39.4, date(2026, 9, 22))
        self.assertLess(abs(equinoccio_primavera - equinoccio_otono), 0.3)

    def test_nunca_sale_del_intervalo(self):
        for lat in (-60.0, 0.0, 39.4, 60.0):
            for mes in (1, 6, 12):
                horas = forecast.daylight_hours(lat, date(2026, mes, 15))
                self.assertTrue(0.0 <= horas <= 24.0, (lat, mes, horas))


class TestFusionDeTramos(unittest.TestCase):
    @staticmethod
    def codigo_en(tramos, hora):
        for inicio, fin, codigo in tramos:
            if inicio <= hora < fin:
                return codigo
        return "fuera"

    def test_donde_el_horario_tiene_dato_manda_el_horario(self):
        diario = [(0, 12, "15"), (12, 24, "44")]
        horario = [(0, 6, "12n"), (6, 7, "12")]
        tramos = forecast.merge_tramos(diario, horario)
        self.assertEqual(self.codigo_en(tramos, 2), "12n")
        self.assertEqual(self.codigo_en(tramos, 6), "12")
        self.assertEqual(self.codigo_en(tramos, 8), "15")

    def test_el_diario_rellena_las_horas_que_el_horario_no_cubre(self):
        diario = [(0, 12, "15"), (12, 24, "44")]
        horario = [(0, 6, "12n")]
        tramos = forecast.merge_tramos(diario, horario)
        self.assertEqual(self.codigo_en(tramos, 7), "15")
        self.assertEqual(self.codigo_en(tramos, 20), "44")

    def test_lo_que_ninguno_declara_sigue_siendo_un_hueco(self):
        tramos = forecast.merge_tramos([(6, 12, "11")], [(0, 6, None)])
        self.assertIsNone(self.codigo_en(tramos, 2))
        self.assertEqual(self.codigo_en(tramos, 7), "11")

    def test_los_tramos_fusionados_cubren_el_dia_sin_solapes(self):
        tramos = forecast.merge_tramos([(0, 24, "13")], [(7, 8, "11"), (8, 9, "11")])
        self.assertEqual(tramos[0][0], 0.0)
        self.assertEqual(tramos[-1][1], 24.0)
        for anterior, siguiente in zip(tramos, tramos[1:]):
            self.assertEqual(anterior[1], siguiente[0])


class TestFactorCielo(unittest.TestCase):
    def test_despejado_y_cubierto(self):
        self.assertEqual(forecast.sky_factor("11"), 1.0)
        self.assertLess(forecast.sky_factor("16"), 0.2)

    def test_el_codigo_nocturno_tiene_el_mismo_factor(self):
        self.assertEqual(forecast.sky_factor("12n"), forecast.sky_factor("12"))

    def test_codigos_conocidos_en_orden(self):
        cadena = ["11", "12", "13", "14", "15", "16"]
        factores = [forecast.sky_factor(c) for c in cadena]
        self.assertEqual(factores, sorted(factores, reverse=True))

    def test_desconocido_o_vacio_no_se_inventa(self):
        self.assertIsNone(forecast.sky_factor(""))
        self.assertIsNone(forecast.sky_factor(None))
        self.assertIsNone(forecast.sky_factor("1"))


# ─────────────────────────────────────────────
# T-09 · Insolación estimada
# ─────────────────────────────────────────────

class TestSolEstimado(unittest.TestCase):
    def test_dia_despejado_igual_a_las_horas_de_luz(self):
        tramos = [(0, 24, "11")]
        sol = forecast.estimate_sun(tramos, 39.4, date(2026, 6, 21))
        self.assertAlmostEqual(sol, forecast.daylight_hours(39.4, date(2026, 6, 21)), places=2)

    def test_dia_cubierto_es_cero_y_no_un_hueco(self):
        self.assertEqual(forecast.estimate_sun([(0, 24, "16")], 39.4, date(2026, 12, 21)), 0.0)

    def test_tramo_de_dia_sin_estado_deja_el_dia_sin_dato(self):
        tramos = [(0, 6, "11"), (6, 12, "11"), (12, 18, None), (18, 24, "11")]
        self.assertIsNone(forecast.estimate_sun(tramos, 39.4, date(2026, 12, 21), 8.0, 18.0))

    def test_tramo_nocturno_sin_estado_no_invalida_el_dia(self):
        # 00-06 no solapa la ventana de luz: su hueco no importa.
        tramos = [(0, 6, None), (6, 12, "11"), (12, 18, "11"), (18, 24, "11")]
        sol = forecast.estimate_sun(tramos, 39.4, date(2026, 6, 21), 6.5, 21.5)
        self.assertIsNotNone(sol)

    def test_nunca_supera_las_horas_de_luz_ni_baja_de_cero(self):
        for codigo in ("11", "13", "16"):
            sol = forecast.estimate_sun([(0, 24, codigo)], 39.4, date(2026, 3, 20))
            self.assertGreaterEqual(sol, 0.0)
            self.assertLessEqual(sol, forecast.daylight_hours(39.4, date(2026, 3, 20)))

    def test_sin_tramos_en_la_ventana_de_luz_no_hay_valor(self):
        self.assertIsNone(forecast.estimate_sun([(0, 6, "11")], 39.4, date(2026, 6, 21), 9.0, 18.0))


# ─────────────────────────────────────────────
# T-03 · Fila de archivo derivada del parte
# ─────────────────────────────────────────────

class TestFilasDeArchivo(unittest.TestCase):
    def setUp(self):
        self.diario = forecast.parse_daily_parte(parte("diaria"))
        self.horario = forecast.parse_hourly_parte(parte("horaria"))
        self.filas = forecast.forecast_rows(
            self.diario, self.horario, "Gecama (Cuenca)", "eolica", 39.4085,
            datetime(2026, 11, 2, 15, 50),
        )

    def test_una_fila_por_dia_del_parte(self):
        self.assertEqual(len(self.filas), 7)
        self.assertEqual(self.filas[0]["objetivo"], date(2026, 11, 2))
        self.assertEqual(self.filas[0]["elaborado"], datetime(2026, 11, 2, 15, 45, 8))

    def test_viento_pasa_de_kmh_a_ms(self):
        self.assertAlmostEqual(self.filas[0]["viento_ms"], 11.25 / 3.6, places=3)

    def test_racha_sale_del_parte_horario(self):
        esperada = max(self.horario["dias"][0]["rachas_kmh"]) / 3.6
        self.assertAlmostEqual(self.filas[0]["racha_ms"], esperada, places=3)

    def test_temperatura_media_horaria_y_extremos_como_respaldo(self):
        self.assertAlmostEqual(self.filas[0]["tmed"], sum(
            [6, 8, 10, 12, 15, 17, 18, 18, 19, 17, 16, 14, 12, 11, 9, 8]
        ) / 16, places=2)
        # El 11-05 queda fuera del parte horario (3 días): respaldo de extremos.
        self.assertAlmostEqual(self.filas[3]["tmed"], (15.0 + 3.0) / 2, places=2)

    def test_el_sol_es_una_estimacion_coherente(self):
        sol = self.filas[0]["sol"]
        self.assertIsNotNone(sol)
        self.assertGreater(sol, 0.0)
        self.assertLessEqual(sol, forecast.daylight_hours(39.4085, date(2026, 11, 2)))

    def test_sin_elaboracion_las_filas_quedan_marcadas(self):
        sin = dict(self.diario)
        sin["elaborado"] = None
        filas = forecast.forecast_rows(
            sin, self.horario, "Gecama (Cuenca)", "eolica", 39.4085,
            datetime(2026, 11, 2, 15, 50),
        )
        self.assertTrue(all(f["elaborado"] is None for f in filas))

    def test_el_horario_incompleto_se_completa_con_el_diario(self):
        # El 11-04 el parte horario solo alcanza de 00 a 06: sin el diario, ese
        # día se quedaba sin insolación aunque el diario sí la trae.
        self.assertIsNotNone(self.filas[2]["sol"])
        self.assertGreater(self.filas[2]["sol"], 0.0)

    def test_la_temperatura_del_dia_incompleto_sale_de_los_extremos(self):
        # Siete horas nocturnas no representan el día (15/1).
        self.assertAlmostEqual(self.filas[2]["tmed"], 8.0, places=2)

    def test_los_dias_del_horario_llevan_su_detalle_hora_a_hora(self):
        tramos = self.filas[0]["tramos_cielo"]
        self.assertGreater(len(tramos), 2)
        self.assertEqual(
            [codigo for inicio, _, codigo in tramos if inicio == 10.0], ["12"],
        )


# ─────────────────────────────────────────────
# T-08 · Elección de la previsión válida (anti-fuga)
# ─────────────────────────────────────────────

class TestEleccion(unittest.TestCase):
    HOY = date(2026, 11, 2)

    def test_elaboracion_anterior_al_objetivo_es_valida(self):
        elegida = forecast.choose_forecast(
            [fila(elaborado=datetime(2026, 10, 31, 8, 0))],
            date(2026, 11, 1), "Gecama (Cuenca)", self.HOY,
        )
        self.assertIsNotNone(elegida)
        self.assertEqual(elegida["antiguedad_dias"], 1)

    def test_elaboracion_el_mismo_dia_es_valida(self):
        elegida = forecast.choose_forecast(
            [fila(elaborado=datetime(2026, 11, 1, 8, 59))],
            date(2026, 11, 1), "Gecama (Cuenca)", self.HOY,
        )
        self.assertIsNotNone(elegida)
        self.assertEqual(elegida["antiguedad_dias"], 0)

    def test_elaboracion_posterior_se_descarta_aunque_sea_la_unica(self):
        self.assertIsNone(forecast.choose_forecast(
            [fila(elaborado=datetime(2026, 11, 2, 8, 0))],
            date(2026, 11, 1), "Gecama (Cuenca)", self.HOY,
        ))

    def test_gana_la_elaboracion_mas_reciente(self):
        filas = [
            fila(elaborado=datetime(2026, 10, 30, 8, 0), viento_ms=1.0),
            fila(elaborado=datetime(2026, 10, 31, 8, 0), viento_ms=2.0),
        ]
        elegida = forecast.choose_forecast(filas, date(2026, 11, 1), "Gecama (Cuenca)", self.HOY)
        self.assertEqual(elegida["valores"]["viento_ms"], 2.0)
        self.assertEqual(elegida["antiguedad_dias"], 1)

    def test_sin_elaboracion_no_es_elegible(self):
        self.assertIsNone(forecast.choose_forecast(
            [fila(elaborado=None)], date(2026, 11, 1), "Gecama (Cuenca)", self.HOY,
        ))

    def test_otra_ubicacion_no_sirve_de_respaldo(self):
        self.assertIsNone(forecast.choose_forecast(
            [fila()], date(2026, 11, 1), "Mula (Murcia)", self.HOY,
        ))

    def test_nunca_usa_una_elaboracion_futura_respecto_a_hoy(self):
        self.assertIsNone(forecast.choose_forecast(
            [fila(elaborado=datetime(2026, 11, 5, 8, 0))],
            date(2026, 11, 10), "Gecama (Cuenca)", self.HOY,
        ))

    def test_antiguedad_negativa_si_la_elaboracion_es_posterior(self):
        self.assertEqual(
            forecast.forecast_age_days(datetime(2026, 11, 3, 8, 0), date(2026, 11, 1)), -2,
        )


# ─────────────────────────────────────────────
# T-07 · Objetivos de captura y recuperación
# ─────────────────────────────────────────────

class TestCaptura(unittest.TestCase):
    HOY = date(2026, 11, 2)

    def test_los_objetivos_incluyen_hoy_futuro_y_recuperable(self):
        objetivos = forecast.capture_targets(self.HOY, set(), horizonte=7)
        self.assertIn(self.HOY, objetivos)
        self.assertIn(self.HOY + timedelta(days=6), objetivos)
        self.assertIn(self.HOY - timedelta(days=6), objetivos)
        self.assertEqual(objetivos, sorted(objetivos))

    def test_lo_ya_archivado_no_se_pide(self):
        archivados = {self.HOY, self.HOY + timedelta(days=1)}
        objetivos = forecast.capture_targets(self.HOY, archivados, horizonte=7)
        self.assertNotIn(self.HOY, objetivos)
        self.assertNotIn(self.HOY + timedelta(days=1), objetivos)

    def test_pendiente_recuperable_frente_a_perdido(self):
        esperados = [self.HOY - timedelta(days=d) for d in range(0, 8)]
        estado = forecast.pending_days(self.HOY, esperados, {self.HOY}, horizonte=7)
        self.assertIn(self.HOY - timedelta(days=6), estado["recuperables"])
        self.assertIn(self.HOY - timedelta(days=7), estado["perdidos"])

    def test_un_dia_archivado_no_esta_pendiente(self):
        estado = forecast.pending_days(self.HOY, [self.HOY], {self.HOY}, horizonte=7)
        self.assertEqual(estado["recuperables"], [])
        self.assertEqual(estado["perdidos"], [])


# ─────────────────────────────────────────────
# T-10 · Serie nacional y medias móviles
# ─────────────────────────────────────────────

class TestSerieYMedias(unittest.TestCase):
    def test_la_serie_nacional_promedia_ubicaciones_con_dato(self):
        filas = [
            fila(ubicacion="A", viento_ms=4.0),
            fila(ubicacion="B", viento_ms=8.0),
            fila(ubicacion="C", viento_ms=None),
        ]
        serie = forecast.national_series(filas, "eolica")
        self.assertEqual(len(serie), 1)
        self.assertEqual(serie[0]["viento_ms"], 6.0)
        self.assertEqual(serie[0]["n"], 2)

    def test_la_media_movil_exige_la_ventana_completa(self):
        base = date(2026, 11, 1)
        valores = {base - timedelta(days=d): 10.0 + d for d in range(14)}
        self.assertAlmostEqual(forecast.moving_average(valores, base, 14), 16.5)

    def test_con_trece_dias_la_ventana_de_catorce_no_existe(self):
        base = date(2026, 11, 1)
        valores = {base - timedelta(days=d): 10.0 for d in range(13)}
        self.assertIsNone(forecast.moving_average(valores, base, 14))

    def test_un_hueco_interno_invalida_la_media(self):
        base = date(2026, 11, 1)
        valores = {base - timedelta(days=d): 10.0 for d in range(3)}
        valores[base - timedelta(days=1)] = None
        self.assertIsNone(forecast.moving_average(valores, base, 3))

    def test_la_media_movil_no_se_acorta(self):
        base = date(2026, 11, 1)
        valores = {base - timedelta(days=d): 10.0 for d in range(6)}
        self.assertIsNone(forecast.moving_average(valores, base, 7))

    def test_ventana_no_positiva_es_un_error(self):
        with self.assertRaises(ValueError):
            forecast.moving_average({}, date(2026, 11, 1), 0)


# ─────────────────────────────────────────────
# T-13 · Cobertura y ventanas de evaluación
# ─────────────────────────────────────────────

class TestCobertura(unittest.TestCase):
    HOY = date(2026, 11, 10)

    def test_archivo_vacio(self):
        resumen = forecast.coverage_summary([], self.HOY, ["A", "B"])
        self.assertEqual(resumen["dias"], 0)
        self.assertEqual(sorted(resumen["ubicaciones_sin_dato"]), ["A", "B"])

    def test_cuenta_huecos_y_antiguedad(self):
        filas = [
            fila(objetivo=date(2026, 11, 2), ubicacion="A", elaborado=datetime(2026, 11, 2, 8, 0)),
            fila(objetivo=date(2026, 11, 4), ubicacion="A", elaborado=datetime(2026, 11, 3, 8, 0)),
        ]
        resumen = forecast.coverage_summary(filas, self.HOY, ["A", "B"])
        self.assertEqual(resumen["dias"], 3)
        self.assertEqual(resumen["con_dato"], 2)
        self.assertEqual(resumen["huecos"], [date(2026, 11, 3)])
        self.assertEqual(resumen["ubicaciones_sin_dato"], ["B"])
        self.assertAlmostEqual(resumen["antiguedad_media"], 0.5)

    def test_no_cuenta_dias_futuros(self):
        filas = [fila(objetivo=date(2026, 11, 20), ubicacion="A")]
        resumen = forecast.coverage_summary(filas, self.HOY, ["A"])
        self.assertEqual(resumen["dias"], 0)


class TestVentanas(unittest.TestCase):
    def test_ventanas_de_21_dias_que_avanzan_de_siete(self):
        ventanas = forecast.evaluation_windows(
            date(2026, 9, 1), date(2026, 12, 1), date(2026, 12, 1),
        )
        self.assertGreaterEqual(len(ventanas), 3)
        primera = ventanas[0]
        self.assertEqual((primera["hasta"] - primera["desde"]).days, 20)
        self.assertEqual((ventanas[1]["desde"] - primera["desde"]).days, 7)
        self.assertLess(primera["train"][1], primera["test"][0])

    def test_las_ventanas_no_se_solapan_en_la_prueba(self):
        ventanas = forecast.evaluation_windows(
            date(2026, 9, 1), date(2026, 12, 1), date(2026, 12, 1),
        )
        for anterior, siguiente in zip(ventanas, ventanas[1:]):
            self.assertLess(anterior["test"][1], siguiente["test"][0])

    def test_la_ultima_ventana_cabe_entera_en_el_ultimo_dia(self):
        ventanas = forecast.evaluation_windows(
            date(2026, 9, 1), date(2026, 9, 30), date(2026, 12, 1),
        )
        self.assertEqual(ventanas[-1]["desde"], date(2026, 9, 8))
        self.assertEqual(ventanas[-1]["hasta"], date(2026, 9, 28))

    def test_sin_dias_suficientes_no_hay_ventanas(self):
        self.assertEqual(forecast.evaluation_windows(
            date(2026, 9, 1), date(2026, 9, 10), date(2026, 12, 1),
        ), [])


class TestCriterio(unittest.TestCase):
    def test_mejora_del_dos_por_ciento_en_mas_de_la_mitad(self):
        decision = forecast.decide_improvement(
            [100.0, 100.0, 100.0, 100.0], [97.0, 98.0, 120.0, 97.0],
        )
        self.assertTrue(decision["aceptada"])
        self.assertEqual(decision["ventanas_ganadas"], 3)
        self.assertEqual(decision["ventanas_evaluadas"], 4)

    def test_mejora_en_la_mitad_exacta_no_basta(self):
        decision = forecast.decide_improvement(
            [100.0, 100.0, 100.0, 100.0], [97.0, 97.0, 120.0, 120.0],
        )
        self.assertFalse(decision["aceptada"])

    def test_mejora_por_debajo_del_umbral_no_cuenta(self):
        decision = forecast.decide_improvement(
            [100.0, 100.0, 100.0], [98.1, 98.1, 98.1],
        )
        self.assertFalse(decision["aceptada"])
        self.assertEqual(decision["ventanas_ganadas"], 0)

    def test_empatar_no_cuenta_como_mejora(self):
        decision = forecast.decide_improvement([100.0, 100.0, 100.0], [100.0, 100.0, 100.0])
        self.assertFalse(decision["aceptada"])

    def test_con_menos_de_tres_ventanas_no_se_decide(self):
        decision = forecast.decide_improvement([100.0, 100.0], [90.0, 90.0])
        self.assertFalse(decision["aceptada"])
        self.assertTrue(decision["evidencia_insuficiente"])


class TestFrescuraGeneracion(unittest.TestCase):
    """RF-12: los retardos del target no se recortan a la última fecha meteorológica."""

    def serie(self, dias=10, valor=100.0):
        inicio = date(2026, 10, 1)
        return {
            inicio + timedelta(days=desplazamiento): valor
            for desplazamiento in range(dias)
        }

    def test_ancla_en_el_ultimo_dia_publicado(self):
        serie = self.serie(dias=10)          # 1 → 10 de octubre
        objetivo = date(2026, 10, 11)
        serie[date(2026, 10, 10)] = 700.0

        informe = forecast.generation_lags(serie, objetivo)

        self.assertEqual(informe["ancla"], date(2026, 10, 10))
        self.assertEqual(informe["retraso_dias"], 1)
        self.assertEqual(informe["valores"]["eolica_lag1"], 700.0)
        self.assertEqual(informe["valores"]["eolica_lag2"], 100.0)
        self.assertEqual(informe["valores"]["eolica_lag3"], 100.0)
        self.assertEqual(informe["valores"]["eolica_lag7"], 100.0)
        self.assertAlmostEqual(informe["eolica_ma7"], 100.0 + 600.0 / 7)
        self.assertEqual(informe["ausentes"], [])

    def test_usa_la_generacion_mas_reciente_aunque_la_meteorologia_vaya_por_detras(self):
        # La serie de generación llega al día 10 y el objetivo es el 15: el
        # ancla es el 10 (frescura), no el último día meteorológico (día 7).
        serie = self.serie(dias=10)

        informe = forecast.generation_lags(serie, date(2026, 10, 15))

        self.assertEqual(informe["ancla"], date(2026, 10, 10))
        self.assertEqual(informe["retraso_dias"], 5)
        self.assertEqual(informe["frescura"]["retraso_dias"], 5)
        self.assertIsNotNone(informe["valores"]["eolica_lag1"])

    def test_hueco_deja_el_retardo_ausente_sin_rellenar(self):
        serie = self.serie(dias=10)
        del serie[date(2026, 10, 9)]          # falta el penúltimo día

        informe = forecast.generation_lags(serie, date(2026, 10, 11))

        self.assertIsNone(informe["valores"]["eolica_lag2"])
        self.assertIsNone(informe["eolica_ma7"])   # ventana de 7 incompleta
        self.assertIn("eolica_lag2", informe["ausentes"])
        self.assertIn("eolica_ma7", informe["ausentes"])
        self.assertEqual(informe["valores"]["eolica_lag1"], 100.0)

    def test_un_hueco_no_se_convierte_en_cero(self):
        serie = self.serie(dias=10)
        serie[date(2026, 10, 8)] = None

        informe = forecast.generation_lags(serie, date(2026, 10, 11))

        self.assertIsNone(informe["valores"]["eolica_lag3"])
        self.assertNotEqual(informe["valores"]["eolica_lag3"], 0.0)

    def test_serie_vacia_no_inventa_retardos(self):
        informe = forecast.generation_lags({}, date(2026, 10, 11))

        self.assertIsNone(informe["ancla"])
        self.assertIsNone(informe["eolica_ma7"])
        self.assertTrue(all(valor is None for valor in informe["valores"].values()))
        self.assertEqual(len(informe["ausentes"]), 5)
        self.assertIsNone(informe["frescura"]["ultimo"])

    def test_dia_muy_por_debajo_de_su_entorno_se_senala(self):
        serie = self.serie(dias=10)
        serie[date(2026, 10, 10)] = 30.0      # 30 % de la mediana

        informe = forecast.generation_lags(serie, date(2026, 10, 11))

        self.assertTrue(informe["frescura"]["anomalo"])
        self.assertAlmostEqual(informe["frescura"]["ratio"], 0.3)
        self.assertIn("incompleta", informe["frescura"]["aviso"])
        # El día incompleto no puede ser el ancla: se retrocede al anterior.
        self.assertEqual(informe["ancla"], date(2026, 10, 9))
        self.assertEqual(informe["valores"]["eolica_lag1"], 100.0)
        self.assertEqual(len(informe["frescura"]["descartados"]), 1)

    def test_varios_dias_incompletos_se_descartan_hasta_el_ultimo_completo(self):
        serie = self.serie(dias=10)
        serie[date(2026, 10, 10)] = 30.0
        serie[date(2026, 10, 9)] = 35.0

        informe = forecast.generation_lags(serie, date(2026, 10, 11))

        self.assertEqual(informe["ancla"], date(2026, 10, 8))
        self.assertEqual(informe["valores"]["eolica_lag1"], 100.0)
        self.assertEqual(
            [descartado["fecha"] for descartado in informe["frescura"]["descartados"]],
            [date(2026, 10, 10), date(2026, 10, 9)],
        )
        self.assertIn("se ancla en 2026-10-08", informe["frescura"]["aviso"])

    def test_dia_normal_no_avisa(self):
        serie = self.serie(dias=10)
        serie[date(2026, 10, 10)] = 95.0

        informe = forecast.generation_lags(serie, date(2026, 10, 11))

        self.assertFalse(informe["frescura"]["anomalo"])
        self.assertIsNone(informe["frescura"]["aviso"])
        self.assertEqual(informe["frescura"]["descartados"], [])
        self.assertEqual(informe["ancla"], date(2026, 10, 10))

    def test_sin_entorno_suficiente_no_se_avisa(self):
        serie = self.serie(dias=3)

        informe = forecast.generation_lags(serie, date(2026, 10, 4))

        self.assertIsNone(informe["frescura"]["mediana_entorno"])
        self.assertFalse(informe["frescura"]["anomalo"])
        self.assertEqual(informe["frescura"]["n_entorno"], 2)

    def test_el_dia_objetivo_publicado_no_se_usa_como_retardo(self):
        # Si REE ya publicó el total del día objetivo, no puede entrar como
        # lag1: sería usar el target. El ancla se queda en el día anterior.
        serie = self.serie(dias=11)
        serie[date(2026, 10, 11)] = 9_999.0

        informe = forecast.generation_lags(serie, date(2026, 10, 11))

        self.assertEqual(informe["ancla"], date(2026, 10, 10))
        self.assertEqual(informe["valores"]["eolica_lag1"], 100.0)


class TestFidelidad(unittest.TestCase):
    def test_mae_y_sesgo_de_la_prevision_frente_a_la_observacion(self):
        informe = forecast.truthfulness_report([(12.0, 10.0), (8.0, 10.0)])
        self.assertAlmostEqual(informe["mae"], 2.0)
        self.assertAlmostEqual(informe["sesgo"], 0.0)
        self.assertEqual(informe["n"], 2)

    def test_sin_pares_no_se_inventa_un_error(self):
        self.assertIsNone(forecast.truthfulness_report([])["mae"])


if __name__ == "__main__":
    unittest.main()
