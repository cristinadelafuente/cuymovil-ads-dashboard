"""Fase 0.5 — Prueba de conexión Google Ads (SOLO LECTURA).

Lectura mínima: 1 campaña con metrics.cost_micros, impressions, clicks, ctr.

Requiere OAuth de solo lectura + developer token + login-customer-id.
Credenciales por variables de entorno (o google-ads.yaml):
  GOOGLE_ADS_DEVELOPER_TOKEN, GOOGLE_ADS_CLIENT_ID, GOOGLE_ADS_CLIENT_SECRET,
  GOOGLE_ADS_REFRESH_TOKEN, GOOGLE_ADS_LOGIN_CUSTOMER_ID, GOOGLE_ADS_CUSTOMER_ID
"""
import os

REQUIRED = [
    "GOOGLE_ADS_DEVELOPER_TOKEN", "GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET",
    "GOOGLE_ADS_REFRESH_TOKEN", "GOOGLE_ADS_LOGIN_CUSTOMER_ID", "GOOGLE_ADS_CUSTOMER_ID",
]

GAQL = """
    SELECT campaign.id, campaign.name,
           metrics.cost_micros, metrics.impressions,
           metrics.clicks, metrics.ctr
    FROM campaign
    WHERE segments.date DURING LAST_7_DAYS
    ORDER BY metrics.cost_micros DESC
    LIMIT 1
"""


def run() -> dict:
    result = {"source": "Google Ads", "connected": None, "evidence": "",
              "blocker": "", "feasible": None}

    missing = [k for k in REQUIRED if not os.environ.get(k)]
    if missing:
        result.update(connected=False,
                      blocker="Faltan credenciales: " + ", ".join(missing),
                      feasible=None)
        return result

    try:
        from google.ads.googleads.client import GoogleAdsClient
    except ImportError as e:
        result.update(connected=False, blocker=f"Instala google-ads: {e}", feasible=None)
        return result

    try:
        client = GoogleAdsClient.load_from_dict({
            "developer_token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
            "client_id": os.environ["GOOGLE_ADS_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_ADS_CLIENT_SECRET"],
            "refresh_token": os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
            "login_customer_id": os.environ["GOOGLE_ADS_LOGIN_CUSTOMER_ID"],
            "use_proto_plus": True,
        })
        ga_service = client.get_service("GoogleAdsService")
        stream = ga_service.search_stream(
            customer_id=os.environ["GOOGLE_ADS_CUSTOMER_ID"], query=GAQL
        )
        row_txt = "sin campañas en el rango"
        for batch in stream:
            for row in batch.results:
                row_txt = (f"campaign='{row.campaign.name}' "
                           f"cost={row.metrics.cost_micros/1e6:.2f} "
                           f"impr={row.metrics.impressions} "
                           f"clicks={row.metrics.clicks} "
                           f"ctr={row.metrics.ctr:.4f}")
                break
            break
        result.update(connected=True, evidence=row_txt, feasible=True)
    except Exception as e:  # noqa: BLE001
        result.update(connected=False, blocker=str(e), feasible=False)
    return result


if __name__ == "__main__":
    import json
    print(json.dumps(run(), ensure_ascii=False, indent=2))
