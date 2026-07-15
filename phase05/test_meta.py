"""Fase 0.5 — Prueba de conexión Meta Ads (SOLO LECTURA).

Valida:
  - que el ACCESS_TOKEN responde y su alcance/caducidad (debug_token),
  - que las 2 cuentas publicitarias responden,
  - que llegan insights por date_preset.

No ejecuta ninguna escritura. Credenciales por variables de entorno:
  META_ACCESS_TOKEN, META_APP_ID, META_APP_SECRET (opcional para debug_token).
"""
import os

ACCOUNTS = {
    "Norte Digital [NDPE]": "act_4207138246212675",
    "Cuy Móvil (histórico)": "act_10159339378105150",
}
INSIGHT_FIELDS = ["spend", "impressions", "clicks", "ctr", "cpc", "reach", "frequency"]


def run(date_preset: str = "last_7d") -> dict:
    result = {
        "source": "Meta Ads",
        "connected": None,
        "evidence": "",
        "blocker": "",
        "feasible": None,
    }
    token = os.environ.get("META_ACCESS_TOKEN", "")
    if not token:
        result.update(connected=False, blocker="Falta META_ACCESS_TOKEN", feasible=None)
        return result

    try:
        import requests
        from facebook_business.api import FacebookAdsApi
        from facebook_business.adobjects.adaccount import AdAccount
    except ImportError as e:
        result.update(connected=False, blocker=f"Dependencia faltante: {e}", feasible=None)
        return result

    app_id = os.environ.get("META_APP_ID", "")
    app_secret = os.environ.get("META_APP_SECRET", "")

    # 1) Alcance y caducidad del token
    scope_info = ""
    try:
        if app_id and app_secret:
            r = requests.get(
                "https://graph.facebook.com/debug_token",
                params={"input_token": token, "access_token": f"{app_id}|{app_secret}"},
                timeout=30,
            ).json().get("data", {})
            scopes = ",".join(scope for scope in r.get("scopes", []))
            expires = r.get("expires_at", 0)
            exp_txt = "no expira" if expires == 0 else f"expira_ts={expires}"
            has_read = "ads_read" in r.get("scopes", []) or "ads_management" in r.get("scopes", [])
            scope_info = f"scopes=[{scopes}] ({exp_txt}); ads_read={'sí' if has_read else 'NO'}"
    except Exception as e:  # noqa: BLE001
        scope_info = f"debug_token no disponible: {e}"

    # 2) Cuentas + insights (lectura)
    try:
        if app_secret:
            FacebookAdsApi.init(app_id, app_secret, token)
        else:
            FacebookAdsApi.init(access_token=token)
        ok_accounts = []
        for label, acc_id in ACCOUNTS.items():
            ins = AdAccount(acc_id).get_insights(
                fields=INSIGHT_FIELDS, params={"date_preset": date_preset}
            )
            n = len(ins)
            ok_accounts.append(f"{label}: {n} filas de insights")
        result.update(
            connected=True,
            evidence=f"{scope_info} | " + " | ".join(ok_accounts),
            feasible=True,
        )
    except Exception as e:  # noqa: BLE001
        result.update(connected=False, blocker=str(e), evidence=scope_info, feasible=False)
    return result


if __name__ == "__main__":
    import json
    print(json.dumps(run(), ensure_ascii=False, indent=2))
