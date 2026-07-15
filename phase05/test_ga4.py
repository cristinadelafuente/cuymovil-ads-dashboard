"""Fase 0.5 — Prueba de conexión GA4 (SOLO LECTURA).

Lectura mínima: sesiones y eventos por fecha vía Google Analytics Data API (runReport).
Requiere proyecto GCP + service account con rol Viewer sobre la propiedad GA4.

Variables de entorno:
  GA4_PROPERTY_ID                 (solo el número, sin 'properties/')
  GOOGLE_APPLICATION_CREDENTIALS  (ruta al JSON de la service account)
"""
import os


def run() -> dict:
    result = {"source": "GA4", "connected": None, "evidence": "",
              "blocker": "", "feasible": None}

    prop = os.environ.get("GA4_PROPERTY_ID", "")
    creds = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if not prop or not creds:
        miss = [k for k, v in {"GA4_PROPERTY_ID": prop,
                               "GOOGLE_APPLICATION_CREDENTIALS": creds}.items() if not v]
        result.update(connected=False, blocker="Faltan: " + ", ".join(miss), feasible=None)
        return result
    if not os.path.exists(creds):
        result.update(connected=False,
                      blocker=f"No existe el JSON de service account: {creds}", feasible=None)
        return result

    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import (
            DateRange, Dimension, Metric, RunReportRequest,
        )
    except ImportError as e:
        result.update(connected=False,
                      blocker=f"Instala google-analytics-data: {e}", feasible=None)
        return result

    try:
        client = BetaAnalyticsDataClient()
        req = RunReportRequest(
            property=f"properties/{prop}",
            dimensions=[Dimension(name="date")],
            metrics=[Metric(name="sessions"), Metric(name="eventCount")],
            date_ranges=[DateRange(start_date="7daysAgo", end_date="yesterday")],
            limit=5,
        )
        resp = client.run_report(req)
        n = len(resp.rows)
        first = ""
        if n:
            r0 = resp.rows[0]
            first = (f" ej.: fecha={r0.dimension_values[0].value} "
                     f"sesiones={r0.metric_values[0].value} "
                     f"eventos={r0.metric_values[1].value}")
        result.update(connected=True, evidence=f"{n} filas devueltas.{first}", feasible=True)
    except Exception as e:  # noqa: BLE001
        result.update(connected=False, blocker=str(e), feasible=False)
    return result


if __name__ == "__main__":
    import json
    print(json.dumps(run(), ensure_ascii=False, indent=2))
