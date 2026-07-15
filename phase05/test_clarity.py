"""Fase 0.5 — Prueba de conexión Microsoft Clarity (SOLO LECTURA).

Lectura mínima: métricas (rage clicks / dead clicks / scroll) de un rango
reciente vía Data Export API.

Variable de entorno:
  CLARITY_API_TOKEN   (token de proyecto — Clarity → Settings → Data Export)

Nota: la Data Export API entrega los últimos 1–3 días agregados; el parámetro
numOfDays admite 1, 2 o 3.
"""
import os

ENDPOINT = "https://www.clarity.ms/export-data/api/v1/project-live-insights"


def run(num_days: int = 3) -> dict:
    result = {"source": "Clarity", "connected": None, "evidence": "",
              "blocker": "", "feasible": None}

    token = os.environ.get("CLARITY_API_TOKEN", "")
    if not token:
        result.update(connected=False, blocker="Falta CLARITY_API_TOKEN", feasible=None)
        return result

    try:
        import requests
    except ImportError as e:
        result.update(connected=False, blocker=f"Instala requests: {e}", feasible=None)
        return result

    try:
        resp = requests.get(
            ENDPOINT,
            headers={"Authorization": f"Bearer {token}"},
            params={"numOfDays": num_days,
                    "dimension1": "URL"},
            timeout=60,
        )
        if resp.status_code == 401:
            result.update(connected=False, blocker="401 token inválido/expirado", feasible=False)
            return result
        if resp.status_code == 429:
            result.update(connected=False,
                          blocker="429 límite de tasa (máx. 10 req/proyecto/día)", feasible=True)
            return result
        resp.raise_for_status()
        data = resp.json()
        metrics = [d.get("metricName") for d in data] if isinstance(data, list) else []
        wanted = [m for m in metrics if m and (
            "Rage" in m or "Dead" in m or "Scroll" in m or "click" in m.lower())]
        result.update(
            connected=True,
            evidence=f"{len(metrics)} métricas; relevantes: {wanted or metrics[:5]}",
            feasible=True,
        )
    except Exception as e:  # noqa: BLE001
        result.update(connected=False, blocker=str(e), feasible=False)
    return result


if __name__ == "__main__":
    import json
    print(json.dumps(run(), ensure_ascii=False, indent=2))
