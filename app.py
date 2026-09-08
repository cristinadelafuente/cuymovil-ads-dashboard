import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.campaign import Campaign
from facebook_business.adobjects.adset import AdSet
from facebook_business.adobjects.adimage import AdImage
from facebook_business.adobjects.adcreative import AdCreative
from facebook_business.adobjects.ad import Ad
from facebook_business.adobjects.targetingsearch import TargetingSearch
import json
import os
import tempfile
import requests
from io import BytesIO
from PIL import Image
from datetime import datetime, timezone, date, timedelta
from zoneinfo import ZoneInfo

PERU_TZ = ZoneInfo("America/Lima")

# ── Configuración de página ──────────────────────────────────────────────────
st.set_page_config(
    page_title="Cuy Móvil · Meta Ads",
    page_icon="🐹",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Identidad de marca (Cuy Visual Guidelines) ────────────────────────────────
BRAND = {
    "purple":        "#5543CE",
    "purple_dark":   "#150C54",
    "purple_darker": "#261A7C",
    "purple_light":  "#9F91FF",
    "purple_pale":   "#F1EFFF",
    "lemon":         "#DCFE6D",
    "lemon_dark":    "#6E8426",
    "lemon_pale":    "#F1FFC5",
    "white":         "#FFFFFF",
}

# Escalas continuas de marca para gráficos Plotly
PURPLE_SCALE = ["#F1EFFF", "#C8C0FF", "#9F91FF", "#735FF7", "#5543CE", "#3C2CA5", "#150C54"]
LEMON_SCALE  = ["#FBFFF0", "#F1FFC5", "#E7FF99", "#DCFE6D", "#B6D552", "#92AC3A", "#4B5B16"]

def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

def _lerp_color(c1: str, c2: str, t: float) -> str:
    """Interpola entre dos colores hex — usado para degradados de marca que garantizan buen
    contraste con texto blanco (solo interpola dentro del rango oscuro/medio de morados)."""
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    r, g, b = int(r1 + (r2 - r1) * t), int(g1 + (g2 - g1) * t), int(b1 + (b2 - b1) * t)
    return f"#{r:02x}{g:02x}{b:02x}"

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap');

html, body, [class*="css"], .stApp, [data-testid="stAppViewContainer"] {{
    font-family: 'Outfit', sans-serif !important;
}}

h1, h2, h3, h4, h5, h6 {{
    font-family: 'Outfit', sans-serif !important;
    font-weight: 600 !important;
    color: {BRAND["purple_dark"]} !important;
}}

/* Sidebar con acento de marca */
[data-testid="stSidebar"] {{
    background-color: {BRAND["purple_pale"]};
    border-right: 2px solid {BRAND["purple"]};
}}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {{
    color: {BRAND["purple_dark"]} !important;
}}

/* Botones — forma de cuadrado redondeado (motivo de la "Y" del logo) */
.stButton > button, .stDownloadButton > button {{
    border-radius: 14px !important;
    font-family: 'Outfit', sans-serif !important;
    font-weight: 500 !important;
    border: none !important;
}}
.stButton > button[kind="primary"] {{
    background-color: {BRAND["purple"]} !important;
    color: {BRAND["white"]} !important;
}}
.stButton > button[kind="primary"]:hover {{
    background-color: {BRAND["purple_dark"]} !important;
}}
.stButton > button[kind="secondary"] {{
    background-color: {BRAND["lemon"]} !important;
    color: {BRAND["purple_dark"]} !important;
}}

/* Tarjetas de métricas (st.metric) con esquinas redondeadas */
[data-testid="stMetric"] {{
    background-color: {BRAND["purple_pale"]};
    border: 1px solid {BRAND["purple_light"]};
    border-radius: 16px;
    padding: 14px 16px;
}}
[data-testid="stMetricLabel"] {{
    color: {BRAND["purple_dark"]} !important;
}}
[data-testid="stMetricValue"] {{
    color: {BRAND["purple"]} !important;
    font-weight: 700 !important;
}}

/* Tabs con acento lima al estar activas */
.stTabs [aria-selected="true"] {{
    color: {BRAND["purple"]} !important;
    border-bottom-color: {BRAND["lemon_dark"]} !important;
}}
.stTabs [data-baseweb="tab-highlight"] {{
    background-color: {BRAND["lemon"]} !important;
}}

/* Contenedores, expanders y dataframes con esquinas redondeadas */
[data-testid="stExpander"], .stDataFrame, [data-testid="stDataFrame"] {{
    border-radius: 16px !important;
    overflow: hidden;
}}

/* Radio de navegación del sidebar como "botones" */
[data-testid="stSidebar"] .stRadio > div {{
    gap: 8px;
}}
[data-testid="stSidebar"] .stRadio label {{
    background-color: {BRAND["white"]};
    border-radius: 12px;
    padding: 8px 12px;
    border: 1px solid {BRAND["purple_light"]};
}}
</style>
""", unsafe_allow_html=True)

# ── Secrets ──────────────────────────────────────────────────────────────────
def get_secret(key):
    try:
        return st.secrets[key]
    except Exception:
        return os.environ.get(key, "")

ACCESS_TOKEN = get_secret("ACCESS_TOKEN")
APP_ID       = get_secret("APP_ID") or "1605641477375351"
APP_SECRET   = get_secret("APP_SECRET")
PAGE_ID      = get_secret("PAGE_ID")
GA_PROPERTY_ID = get_secret("GA_PROPERTY_ID") or "255486373"
CLARITY_API_TOKEN = get_secret("CLARITY_API_TOKEN")
GOOGLE_ADS_CLIENT_ID = get_secret("GOOGLE_ADS_CLIENT_ID")
GOOGLE_ADS_CLIENT_SECRET = get_secret("GOOGLE_ADS_CLIENT_SECRET")
GOOGLE_ADS_REFRESH_TOKEN = get_secret("GOOGLE_ADS_REFRESH_TOKEN")
GOOGLE_ADS_DEVELOPER_TOKEN = get_secret("GOOGLE_ADS_DEVELOPER_TOKEN")
GOOGLE_ADS_LOGIN_CUSTOMER_ID = get_secret("GOOGLE_ADS_LOGIN_CUSTOMER_ID")
GOOGLE_ADS_CUSTOMER_ID = get_secret("GOOGLE_ADS_CUSTOMER_ID") or "9778403348"

# ── Usuarios y roles (control de acceso) ──────────────────────────────────────
_USERS_RAW = get_secret("USERS")
try:
    USERS = {str(k).strip().lower(): dict(v) for k, v in _USERS_RAW.items()} if _USERS_RAW else {}
except Exception:
    USERS = {}

# ── Constantes ───────────────────────────────────────────────────────────────
ACCOUNTS = {
    "Norte Digital [NDPE] — Cuy Móvil": "act_4207138246212675",
    "Cuy Móvil (histórico)":            "act_10159339378105150",
}

DATE_OPTIONS = {
    "Últimos 7 días":  "last_7d",
    "Últimos 14 días": "last_14d",
    "Últimos 30 días": "last_30d",
    "Últimos 90 días": "last_90d",
    "Este mes":        "this_month",
    "Mes anterior":    "last_month",
    "Personalizado":   "custom",
}

INSIGHT_FIELDS = ["spend", "impressions", "clicks", "ctr", "cpc", "reach", "frequency"]

OBJECTIVES = {
    "Ventas / Conversiones":    "OUTCOME_SALES",
    "Tráfico al sitio web":     "OUTCOME_TRAFFIC",
    "Interacción / Engagement": "OUTCOME_ENGAGEMENT",
    "Captación de leads":       "OUTCOME_LEADS",
    "Reconocimiento de marca":  "OUTCOME_AWARENESS",
}

CTA_OPTIONS = {
    "Más información": "LEARN_MORE",
    "Comprar ahora":   "SHOP_NOW",
    "Contáctanos":     "CONTACT_US",
    "Registrarse":     "SIGN_UP",
    "Ver más":         "SEE_MORE",
    "Obtener oferta":  "GET_OFFER",
    "Llamar ahora":    "CALL_NOW",
    "Suscribirse":     "SUBSCRIBE",
}

COUNTRIES_ES = {
    "Perú":          "PE",
    "México":        "MX",
    "Colombia":      "CO",
    "Argentina":     "AR",
    "Chile":         "CL",
    "Ecuador":       "EC",
    "Bolivia":       "BO",
    "Venezuela":     "VE",
    "Estados Unidos":"US",
}

# ── API helpers ───────────────────────────────────────────────────────────────
def init_api():
    if APP_SECRET:
        FacebookAdsApi.init(APP_ID, APP_SECRET, ACCESS_TOKEN)
    else:
        FacebookAdsApi.init(access_token=ACCESS_TOKEN)

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_campaigns(account_id: str, date_preset: str, since: str = "", until: str = "") -> pd.DataFrame:
    init_api()
    account   = AdAccount(account_id)
    campaigns = account.get_campaigns(fields=[
        Campaign.Field.id,
        Campaign.Field.name,
        Campaign.Field.effective_status,
        Campaign.Field.objective,
        Campaign.Field.daily_budget,
        Campaign.Field.bid_strategy,
    ])
    if date_preset == "custom" and since and until:
        insight_time_params = {"time_range": {"since": since, "until": until}}
    else:
        insight_time_params = {"date_preset": date_preset}

    rows = []
    for c in campaigns:
        status   = c.get(Campaign.Field.effective_status, "")
        insights = c.get_insights(
            fields=INSIGHT_FIELDS,
            params={**insight_time_params, "breakdowns": ["publisher_platform"]},
        )
        if not insights:
            continue

        # Sumar todas las filas (una por plataforma: facebook, instagram, audience_network, messenger)
        # y además guardar el desglose completo (no solo gasto) por Facebook e Instagram.
        totals = {"spend": 0.0, "impressions": 0, "clicks": 0, "reach": 0}
        per_platform = {
            "facebook":  {"spend": 0.0, "impressions": 0, "clicks": 0, "reach": 0},
            "instagram": {"spend": 0.0, "impressions": 0, "clicks": 0, "reach": 0},
        }
        for ins_row in insights:
            sp  = float(ins_row.get("spend", 0))
            imp = int(ins_row.get("impressions", 0))
            cl  = int(ins_row.get("clicks", 0))
            rc  = int(ins_row.get("reach", 0))
            totals["spend"]       += sp
            totals["impressions"] += imp
            totals["clicks"]      += cl
            totals["reach"]       += rc
            plat = ins_row.get("publisher_platform", "")
            if plat in per_platform:
                per_platform[plat]["spend"]       += sp
                per_platform[plat]["impressions"] += imp
                per_platform[plat]["clicks"]       += cl
                per_platform[plat]["reach"]        += rc

        start_raw = c.get(Campaign.Field.start_time, "")
        try:
            start_dt    = datetime.fromisoformat(start_raw)
            dias_activa = (datetime.now(tz=start_dt.tzinfo) - start_dt).days
        except Exception:
            dias_activa = 0

        row = {
            "id":          c[Campaign.Field.id],
            "Campaña":     c[Campaign.Field.name],
            "Estado":      status,
            "Objetivo":    c.get(Campaign.Field.objective, ""),
            "Presupuesto": int(c.get(Campaign.Field.daily_budget, 0)) / 100,
            "Días activa": dias_activa,
            "Gasto_Total":       totals["spend"],
            "Impresiones_Total": totals["impressions"],
            "Clics_Total":       totals["clicks"],
            "Alcance_Total":     totals["reach"],
        }
        for plat, key in (("facebook", "FB"), ("instagram", "IG")):
            row[f"Gasto_{key}"]       = per_platform[plat]["spend"]
            row[f"Impresiones_{key}"] = per_platform[plat]["impressions"]
            row[f"Clics_{key}"]       = per_platform[plat]["clicks"]
            row[f"Alcance_{key}"]     = per_platform[plat]["reach"]
        rows.append(row)
    return pd.DataFrame(rows)

# ── Aplica el filtro de plataforma a TODAS las métricas (no solo el gasto) ────
def apply_platform_filter(df: pd.DataFrame, platform_filter: str) -> pd.DataFrame:
    if df.empty:
        return df
    if platform_filter == "Solo Facebook":
        suf = "FB"
    elif platform_filter == "Solo Instagram":
        suf = "IG"
    else:
        suf = "Total"

    d = df.copy()
    d["Gasto"]       = d[f"Gasto_{suf}"]
    d["Impresiones"] = d[f"Impresiones_{suf}"]
    d["Clics"]       = d[f"Clics_{suf}"]
    d["Alcance"]     = d[f"Alcance_{suf}"]
    d["CTR"]        = d.apply(lambda r: (r["Clics"] / r["Impresiones"] * 100) if r["Impresiones"] else 0.0, axis=1)
    d["CPC"]        = d.apply(lambda r: (r["Gasto"] / r["Clics"]) if r["Clics"] else 0.0, axis=1)
    d["Frecuencia"] = d.apply(lambda r: (r["Impresiones"] / r["Alcance"]) if r["Alcance"] else 0.0, axis=1)
    return d

# ── Acciones sobre campañas ───────────────────────────────────────────────────
def pause_campaign(campaign_id: str):
    init_api()
    Campaign(campaign_id).api_update(fields=[], params={"status": "PAUSED"})

def set_daily_budget(campaign_id: str, budget_usd: float):
    init_api()
    Campaign(campaign_id).api_update(fields=[], params={"daily_budget": str(int(budget_usd * 100))})

LEARNING_STAGE_LABELS = {
    "LEARNING":         "🧪 En aprendizaje",
    "LEARNING_LIMITED": "⚠️ Aprendizaje limitado",
    "SUCCESS":          "✅ Aprendizaje completado",
}

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_learning_status(account_id: str) -> pd.DataFrame:
    """Trae la fase de aprendizaje de cada conjunto de anuncios (ad set) activo/pausado de la cuenta,
    usando el campo learning_stage_info de la API de Meta."""
    init_api()
    account = AdAccount(account_id)
    campaigns = account.get_campaigns(fields=["id", "name"])
    campaign_names = {c["id"]: c.get("name", "") for c in campaigns}

    adsets = account.get_ad_sets(fields=[
        "id", "name", "campaign_id", "effective_status", "learning_stage_info", "daily_budget",
    ])
    rows = []
    for a in adsets:
        status = a.get("effective_status", "")
        if status not in ("ACTIVE", "PAUSED"):
            continue
        info = a.get("learning_stage_info") or {}
        stage = info.get("status", "") if isinstance(info, dict) else ""
        rows.append({
            "Conjunto de anuncios": a.get("name", ""),
            "Campaña":              campaign_names.get(a.get("campaign_id", ""), a.get("campaign_id", "")),
            "Estado":                status,
            "Fase":                  stage,
            "Fase (texto)":          LEARNING_STAGE_LABELS.get(stage, "— (sin datos de aprendizaje)"),
            "Presupuesto diario":    (int(a.get("daily_budget", 0)) / 100) if a.get("daily_budget") else 0.0,
        })
    return pd.DataFrame(rows)

def _learning_action_plan(freq: float = None, ctr: float = None, spend: float = None) -> list:
    """Checklist genérico de causas/soluciones típicas cuando un conjunto de anuncios no logra salir
    (o le cuesta salir) de la fase de aprendizaje de Meta."""
    tips = [
        "**Muy pocos eventos de optimización:** Meta recomienda ~50 conversiones (u otro evento de "
        "optimización) por conjunto de anuncios en 7 días. Si tu campaña opera por conjuntos separados en "
        "FB e IG, intenta consolidarlos en un solo conjunto (Advantage+ / mismo conjunto, ambas plataformas) "
        "para acumular eventos más rápido en vez de dividirlos.",
        "**Ediciones frecuentes:** cambiar presupuesto, creativo, público o puja mientras está en aprendizaje "
        "reinicia el conteo. Evita tocarla por al menos 3-4 días o hasta acumular eventos suficientes.",
        "**Segmentación muy angosta:** si el público es muy chico o muy específico, hay pocas oportunidades "
        "de conversión. Prueba ampliar edad/intereses o usar una audiencia Advantage+ (menos restrictiva).",
        "**Evento de optimización muy 'profundo' (ej. compra) y poco frecuente:** si tarda en acumular compras, "
        "prueba optimizar temporalmente por un evento más alto en el funnel (ej. 'Agregar al carrito' o "
        "'Iniciar checkout') para salir del aprendizaje más rápido, y luego evalúa volver a 'Compra'.",
        "**Presupuesto muy bajo para el costo por resultado de tu nicho:** si el presupuesto diario no alcanza "
        "para generar suficientes eventos, sube el presupuesto (en incrementos de 20-50%, no de golpe).",
        "**Puja restrictiva (costo tope / puja manual):** si usas 'costo tope' o puja manual muy ajustada, Meta "
        "tiene menos flexibilidad para encontrar resultados. Prueba con 'Menor costo' (sin tope) durante el aprendizaje.",
    ]
    tailored = []
    if freq is not None and freq > 3:
        tailored.append(f"En tu caso la frecuencia ya está en {freq:.1f}x — la audiencia se está agotando, lo que reduce las probabilidades de nuevas conversiones. Amplía audiencia o rota creativo.")
    if ctr is not None and ctr < 1.5:
        tailored.append(f"Tu CTR actual ({ctr:.2f}%) es bajo — si pocas personas hacen clic, es más difícil acumular los eventos necesarios para salir del aprendizaje. Revisa creativo/copy antes de tocar presupuesto.")
    if spend is not None and spend < 50:
        tailored.append(f"El gasto acumulado (${spend:,.2f}) es bajo para el período — puede que el presupuesto no esté generando suficiente volumen de eventos.")
    return tailored + tips

def generate_meta_ai_answer(question: str, view_df: pd.DataFrame, learning_df: pd.DataFrame) -> str:
    """Responde preguntas sobre las campañas de Meta Ads y da recomendaciones — basado en reglas
    (sin costo de API), usando los mismos datos que ya se muestran en el dashboard."""
    q = question.lower()
    lines = []

    has_meta   = view_df is not None and not view_df.empty
    has_learn  = learning_df is not None and not learning_df.empty
    mentions_learning = any(k in q for k in ["aprendizaje", "learning", "fase"])

    # ── Campaña específica mencionada por nombre (se revisa PRIMERO, incluso si la pregunta
    # también menciona "aprendizaje" — así respondemos sobre ESA campaña, no sobre toda la cuenta) ──
    matched = pd.DataFrame()
    if has_meta:
        matched = view_df[view_df["Campaña"].str.lower().apply(lambda n: n in q or q in n)]

    if not matched.empty:
        r = matched.iloc[0]
        lines.append(
            f"**{r['Campaña']}** ({r['Estado']}): gasto ${r['Gasto']:,.2f}, CTR {r['CTR']:.2f}%, "
            f"CPC ${r['CPC']:.3f}, frecuencia {r['Frecuencia']:.1f}x, presupuesto diario ${r['Presupuesto']:.2f}."
        )

        # Si tenemos datos de aprendizaje, muestra los conjuntos de anuncios de ESTA campaña
        learn_rows = pd.DataFrame()
        if has_learn:
            learn_rows = learning_df[learning_df["Campaña"].str.lower() == str(r["Campaña"]).lower()]
            if not learn_rows.empty:
                lines.append(f"Conjuntos de anuncios de esta campaña ({len(learn_rows)}):")
                for _, lr in learn_rows.iterrows():
                    lines.append(f"- **{lr['Conjunto de anuncios']}** — {lr['Fase (texto)']} (presupuesto diario ${lr['Presupuesto diario']:.2f})")

        if mentions_learning:
            if not learn_rows.empty and (learn_rows["Fase"] == "LEARNING_LIMITED").any():
                lines.append("⚠️ Al menos un conjunto está en **aprendizaje limitado** — es poco probable que salga sin cambios.")
            elif has_learn and learn_rows.empty:
                lines.append(
                    "No encontré datos de fase de aprendizaje para esta campaña específica en la API "
                    "(puede que Meta no esté devolviendo `learning_stage_info` para sus conjuntos de anuncios "
                    "en este momento, lo cual pasa a veces incluso cuando la campaña sigue sin salir del aprendizaje)."
                )
            lines.append("**Plan de acción para salir del aprendizaje:**")
            for tip in _learning_action_plan(freq=r["Frecuencia"], ctr=r["CTR"], spend=r["Gasto"]):
                lines.append(f"- {tip}")
        else:
            if r["Frecuencia"] > 4:
                lines.append("⚠️ Frecuencia alta — la misma audiencia ya vio el anuncio muchas veces. Conviene rotar la creatividad o ampliar audiencia.")
            if r["CTR"] < 3:
                lines.append("⚠️ CTR bajo — revisa creatividad, copy o segmentación.")
            elif r["CTR"] > 5:
                lines.append("✅ CTR sólido — es candidata a escalar presupuesto gradualmente (+20-50%, no de golpe).")
        return "\n\n".join(lines)

    # ── Fase de aprendizaje (pregunta general, sin campaña específica) ─────────
    if mentions_learning:
        if not has_learn:
            return (
                "No pude traer la fase de aprendizaje de tus conjuntos de anuncios (puede que la cuenta "
                "no tenga permisos para el campo `learning_stage_info`, o que no haya conjuntos activos/pausados)."
            )
        en_aprendizaje = learning_df[learning_df["Fase"] == "LEARNING"]
        limitado       = learning_df[learning_df["Fase"] == "LEARNING_LIMITED"]
        completado     = learning_df[learning_df["Fase"] == "SUCCESS"]
        sin_dato       = learning_df[~learning_df["Fase"].isin(["LEARNING", "LEARNING_LIMITED", "SUCCESS"])]

        lines.append(
            f"De {len(learning_df)} conjunto(s) de anuncios activos/pausados: "
            f"**{len(en_aprendizaje)} en aprendizaje**, **{len(limitado)} en aprendizaje limitado**, "
            f"**{len(completado)} ya salieron del aprendizaje**"
            + (f", **{len(sin_dato)} sin dato de fase** (Meta no devolvió `learning_stage_info` para ellos)." if not sin_dato.empty else ".")
        )
        if not limitado.empty:
            lines.append("⚠️ **Aprendizaje limitado** (es poco probable que salgan del aprendizaje sin cambios):")
            for _, r in limitado.iterrows():
                lines.append(f"- **{r['Conjunto de anuncios']}** (campaña: {r['Campaña']}) — presupuesto diario ${r['Presupuesto diario']:.2f}")
        if not en_aprendizaje.empty:
            lines.append(
                f"Los {len(en_aprendizaje)} conjunto(s) en aprendizaje necesitan generalmente **~50 eventos de "
                "optimización en 7 días** para salir. Evita pausar, editar el presupuesto o el targeting mientras "
                "estén en esta fase — cada cambio importante reinicia el contador."
            )
        if en_aprendizaje.empty and limitado.empty and not completado.empty and sin_dato.empty:
            lines.append("✅ Todos tus conjuntos de anuncios ya salieron de la fase de aprendizaje.")
        if not sin_dato.empty and en_aprendizaje.empty and limitado.empty:
            lines.append(
                "Ninguno de tus conjuntos tiene actualmente un estado de aprendizaje reportado por la API — "
                "esto es normal si llevan tiempo sin cambios recientes, o si el volumen de eventos es bajo. "
                "Si una campaña en particular no te está dando resultados, dime su nombre y la reviso con más detalle."
            )
        return "\n\n".join(lines)

    if not has_meta:
        return "No hay datos de Meta Ads cargados en este momento para responder tu pregunta."

    # ── Pausar / bajo rendimiento ───────────────────────────────────────────────
    if any(k in q for k in ["pausar", "pause", "bajo rendimiento", "mal", "detener"]):
        malas = view_df[(view_df["CTR"] < 3) | (view_df["Frecuencia"] > 4)]
        if malas.empty:
            return "No encuentro campañas con señales claras de bajo rendimiento (CTR < 3% o frecuencia > 4x) en el período actual."
        lines.append("Candidatas a pausar o ajustar:")
        for _, r in malas.iterrows():
            motivo = "frecuencia alta" if r["Frecuencia"] > 4 else "CTR bajo"
            lines.append(f"- **{r['Campaña']}** — {motivo} (CTR {r['CTR']:.2f}%, frecuencia {r['Frecuencia']:.1f}x, gasto ${r['Gasto']:,.2f})")
        return "\n\n".join(lines)

    # ── Frecuencia ───────────────────────────────────────────────────────────────
    if "frecuencia" in q:
        alta = view_df[view_df["Frecuencia"] > 4].sort_values("Frecuencia", ascending=False)
        if alta.empty:
            return "Ninguna campaña supera una frecuencia de 4x — no hay señales de fatiga de anuncio por ahora."
        lines.append("Campañas con frecuencia alta (fatiga de audiencia):")
        for _, r in alta.iterrows():
            lines.append(f"- **{r['Campaña']}**: {r['Frecuencia']:.1f}x")
        lines.append("Recomendación: rota las creatividades o amplía la audiencia para bajar la frecuencia.")
        return "\n\n".join(lines)

    # ── Presupuesto ────────────────────────────────────────────────────────────
    if any(k in q for k in ["presupuesto", "budget", "escalar", "aumentar", "subir gasto"]):
        buenas = view_df[(view_df["CTR"] > 5) & (view_df["Gasto"] < 200)]
        if buenas.empty:
            return "No encuentro campañas con CTR alto (>5%) y gasto bajo (<$200) que sean candidatas claras a escalar presupuesto ahora mismo."
        lines.append("Candidatas a subir presupuesto (buen CTR, gasto todavía bajo):")
        for _, r in buenas.iterrows():
            lines.append(f"- **{r['Campaña']}**: CTR {r['CTR']:.2f}%, gasto actual ${r['Gasto']:,.2f}, presupuesto diario ${r['Presupuesto']:.2f}")
        lines.append("Sugerencia: sube el presupuesto en incrementos de 20-50% cada pocos días, no de golpe, para no reiniciar el aprendizaje.")
        return "\n\n".join(lines)

    # ── CTR general ────────────────────────────────────────────────────────────
    if "ctr" in q:
        best  = view_df.loc[view_df["CTR"].idxmax()]
        worst = view_df.loc[view_df["CTR"].idxmin()]
        return (
            f"La campaña con mejor CTR es **{best['Campaña']}** ({best['CTR']:.2f}%). "
            f"La de menor CTR es **{worst['Campaña']}** ({worst['CTR']:.2f}%) — revisa creatividad o segmentación ahí."
        )

    # ── Fallback: recomendaciones generales ────────────────────────────────────
    suggestions = get_suggestions(view_df)
    if not suggestions:
        lines.append("✅ No encuentro alertas urgentes en tus campañas con los datos actuales.")
    else:
        lines.append("Recomendaciones generales según tus datos actuales:")
        for s in suggestions:
            lines.append(f"- **{s['campaign_name']}** ({s['urgency']}): {s['reason']}")
    if has_learn and not learning_df[learning_df["Fase"] == "LEARNING_LIMITED"].empty:
        lines.append("⚠️ También tienes conjuntos de anuncios en **aprendizaje limitado** — pregúntame por 'aprendizaje' para más detalle.")
    lines.append(
        "\n_Puedes preguntarme cosas como: '¿qué campañas están en aprendizaje?', '¿qué debería pausar?', "
        "'¿cómo está mi frecuencia?', '¿cuáles puedo escalar de presupuesto?' o el nombre de una campaña específica._"
    )
    return "\n\n".join(lines)

# ── Análisis con reglas ───────────────────────────────────────────────────────
def get_suggestions(df: pd.DataFrame) -> list:
    suggestions = []
    for _, row in df.iterrows():
        cid    = row["id"]
        name   = row["Campaña"]
        ctr    = row["CTR"]
        freq   = row["Frecuencia"]
        gasto  = row["Gasto"]
        dias   = row.get("Días activa", 0)
        budget = row["Presupuesto"]

        if freq > 4:
            suggestions.append({
                "campaign_id": cid, "campaign_name": name,
                "action": "REFRESH_CREATIVE", "urgency": "ALTA",
                "reason": f"Frecuencia {freq:.1f}x — la audiencia ya vio el anuncio demasiadas veces. Rota la creatividad.",
                "new_budget_usd": None,
            })
        elif ctr < 3:
            suggestions.append({
                "campaign_id": cid, "campaign_name": name,
                "action": "DECREASE_BUDGET", "urgency": "ALTA",
                "reason": f"CTR {ctr:.2f}% por debajo del mínimo (3%). Reducir presupuesto hasta mejorar la segmentación.",
                "new_budget_usd": round(budget * 0.5, 2) if budget > 0 else None,
            })
        elif ctr > 5 and gasto < 200:
            suggestions.append({
                "campaign_id": cid, "campaign_name": name,
                "action": "INCREASE_BUDGET", "urgency": "MEDIA",
                "reason": f"CTR {ctr:.2f}% excelente con gasto bajo. Escalar para aprovechar el rendimiento.",
                "new_budget_usd": round(budget * 1.5, 2) if budget > 0 else None,
            })
        elif dias > 45:
            suggestions.append({
                "campaign_id": cid, "campaign_name": name,
                "action": "REFRESH_CREATIVE", "urgency": "BAJA",
                "reason": f"Lleva {dias} días activa. Revisar si la creatividad sigue siendo relevante.",
                "new_budget_usd": None,
            })

    order = {"ALTA": 0, "MEDIA": 1, "BAJA": 2}
    suggestions.sort(key=lambda x: order.get(x["urgency"], 3))
    return suggestions[:5]

# ── IA de segmentación (basada en reglas, granularidad fina) ──────────────────
def ai_suggest_segmentation(description: str) -> dict:
    desc = description.lower()
    result = {
        "countries": ["PE"],
        "age_min": 18,
        "age_max": 45,
        "gender": "all",
        "interest_keywords": [],   # términos a resolver contra intereses reales de Meta
        "brand_keywords": [],      # marcas mencionadas — se resuelven aparte
        "notes": [],
        "narrow_logic": False,     # si True, se sugiere combinar intereses en AND (audiencia más chica)
    }

    # Detección de marcas específicas de competencia (targeting más fino: la marca exacta, no la categoría)
    brand_map = {
        "claro":     "Claro",
        "entel":     "Entel",
        "bitel":     "Bitel",
        "movistar":  "Movistar",
        "wom":       "WOM",
    }
    mentioned_brands = [name for kw, name in brand_map.items() if kw in desc]
    if mentioned_brands:
        result["brand_keywords"].extend(mentioned_brands)
        result["notes"].append(
            "⚠️ **Meta no permite apuntar directamente a seguidores de páginas de competidores.** "
            f"En su lugar se buscarán los intereses reales de marca para {', '.join(mentioned_brands)} "
            "(cuando Meta los tenga catalogados como interés) — esto es más fino que apuntar a 'telecomunicaciones' en general."
        )
        result["notes"].append("→ Para algo aún más preciso: sube tu lista de clientes actuales y crea un **Lookalike 1%** — Meta encontrará perfiles con comportamiento similar al de tus mejores clientes, no solo por interés declarado.")

    if any(kw in desc for kw in ["competencia", "competidor", "otras marcas", "paginas similares",
                                  "páginas similares", "interactuan", "interactúan"]) and not mentioned_brands:
        result["notes"].append("⚠️ No mencionaste marcas específicas de competencia. Si las nombras (ej. 'Claro', 'Entel', 'Bitel', 'Movistar') puedo buscar sus intereses exactos en vez de categorías genéricas.")
        result["interest_keywords"].extend(["Telefonía móvil de prepago", "Comparación de planes móviles"])

    # Telco / datos / planes — desglose fino por sub-necesidad, no solo "telefonía móvil" genérico
    if any(kw in desc for kw in ["ilimitado", "datos ilimitados"]):
        result["interest_keywords"].extend(["Planes de datos ilimitados", "4G LTE", "Internet móvil de alta velocidad"])
        result["narrow_logic"] = True
    if any(kw in desc for kw in ["prepago", "chip", "recarga"]):
        result["interest_keywords"].extend(["Telefonía prepago", "Recargas móviles"])
    if any(kw in desc for kw in ["postpago", "contrato", "plan mensual"]):
        result["interest_keywords"].extend(["Planes postpago", "Contratos de telefonía"])
    if any(kw in desc for kw in ["celular", "móvil", "movil", "teléfono", "telefono", "smartphone"]) and not any(
        kw in desc for kw in ["ilimitado", "prepago", "postpago"]
    ):
        result["interest_keywords"].extend(["Smartphones", "Compra de celulares nuevos"])

    # Edad — bandas más angostas y específicas en vez de rangos amplios genéricos
    if any(kw in desc for kw in ["adolescentes", "teens", "13 a 17", "colegio", "secundaria"]):
        result["age_min"], result["age_max"] = 13, 17
        result["interest_keywords"].extend(["TikTok", "Videojuegos móviles"])
    elif any(kw in desc for kw in ["universitarios", "estudiantes universitarios", "gen z"]):
        result["age_min"], result["age_max"] = 18, 24
        result["interest_keywords"].extend(["Vida universitaria", "TikTok", "Instagram Reels"])
    elif any(kw in desc for kw in ["jóvenes", "jovenes", "millennials"]):
        result["age_min"], result["age_max"] = 22, 32
        result["interest_keywords"].extend(["Instagram", "Streaming de video", "Trabajo remoto"])
    elif any(kw in desc for kw in ["padres", "madres", "familias", "hijos"]):
        result["age_min"], result["age_max"] = 30, 50
        result["interest_keywords"].extend(["Crianza de hijos", "Educación de hijos", "Familia"])
    elif any(kw in desc for kw in ["profesionales", "ejecutivos", "empresarios", "trabajadores"]):
        result["age_min"], result["age_max"] = 28, 50
        result["interest_keywords"].extend(["Negocios pequeños", "Productividad en el trabajo", "Liderazgo"])
    elif any(kw in desc for kw in ["adultos mayores", "tercera edad", "jubilados"]):
        result["age_min"], result["age_max"] = 55, 65
        result["interest_keywords"].extend(["Salud y bienestar", "Noticias"])

    # Género
    if any(kw in desc for kw in ["mujeres", "femenino", "mamás", "madre"]):
        result["gender"] = "female"
    if any(kw in desc for kw in ["hombres", "masculino", "hombre"]):
        result["gender"] = "male"

    # Gamers — más específico por plataforma
    if any(kw in desc for kw in ["gamers", "gaming", "videojuegos", "esports"]):
        if any(kw in desc for kw in ["móvil", "movil", "celular"]):
            result["interest_keywords"].extend(["Mobile gaming", "Free-to-play"])
        else:
            result["interest_keywords"].extend(["Videojuegos", "eSports"])
        result["narrow_logic"] = True

    # Redes sociales — por plataforma específica, no "redes sociales" en general
    if "tiktok" in desc:
        result["interest_keywords"].append("TikTok")
    if "instagram" in desc:
        result["interest_keywords"].append("Instagram")
    if "youtube" in desc:
        result["interest_keywords"].append("YouTube")

    # Precio / ahorro — sensibilidad al precio como señal de comportamiento, no solo interés
    if any(kw in desc for kw in ["precio", "barato", "económico", "economico",
                                  "oferta", "descuento", "ahorro", "promo"]):
        result["interest_keywords"].extend(["Cupones y descuentos", "Compras de ofertas online"])
        result["narrow_logic"] = True

    # Deportes — por disciplina específica cuando se menciona
    if "fútbol" in desc or "futbol" in desc:
        result["interest_keywords"].append("Fútbol")
    elif any(kw in desc for kw in ["gym", "fitness", "running"]):
        result["interest_keywords"].extend(["Fitness y bienestar", "Entrenamiento físico"])
    elif "deportes" in desc:
        result["interest_keywords"].append("Deportes")

    # LATAM
    if any(kw in desc for kw in ["latinoamérica", "latinoamerica", "latam",
                                  "sudamérica", "toda la región"]):
        result["countries"] = ["PE", "MX", "CO", "AR", "CL", "EC"]
        result["notes"].append("→ Se sugiere apuntar a múltiples países de LATAM (audiencia amplia — considera separar por país para mensajes más relevantes).")

    # Deduplicar y fallback
    result["interest_keywords"] = list(dict.fromkeys(result["interest_keywords"]))
    if not result["interest_keywords"] and not result["brand_keywords"]:
        result["interest_keywords"] = ["Telefonía móvil", "Smartphones"]
        result["notes"].append("La descripción fue muy general — agregué intereses base de telco. Cuanto más específica sea tu descripción (edad, comportamiento, marca, plataforma), más fina será la segmentación.")

    return result

# ── Búsqueda de intereses en Meta ─────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def search_meta_interests(query: str) -> list:
    try:
        init_api()
        results = TargetingSearch.search(params={"q": query, "type": "adinterest", "limit": 8})
        return [{"id": r["id"], "name": r["name"],
                 "audience": r.get("audience_size_lower_bound", 0)} for r in results]
    except Exception:
        return []

def resolve_best_interest(query: str):
    """Busca un término en Meta y devuelve el interés real más específico (mayor coincidencia, no el más masivo)."""
    matches = search_meta_interests(query)
    if not matches:
        return None
    exact = [m for m in matches if m["name"].strip().lower() == query.strip().lower()]
    return exact[0] if exact else matches[0]

@st.cache_data(ttl=120, show_spinner=False)
def get_audience_estimate(account_id, countries, age_min, age_max, genders, interest_ids):
    """Devuelve un estimado real de tamaño de audiencia para la segmentación armada, para medir qué tan fina quedó."""
    try:
        init_api()
        targeting = {
            "geo_locations": {"countries": countries},
            "age_min": age_min,
            "age_max": age_max,
        }
        if genders:
            targeting["genders"] = genders
        if interest_ids:
            targeting["flexible_spec"] = [{"interests": [{"id": str(iid)} for iid in interest_ids]}]
        est = AdAccount(account_id).get_delivery_estimate(
            fields=["estimate_mau", "estimate_dau"],
            params={"optimization_goal": "REACH", "targeting_spec": targeting},
        )
        if est:
            return int(est[0].get("estimate_mau", 0))
    except Exception:
        return None
    return None

# ── Audiencias Lookalike ───────────────────────────────────────────────────────
@st.cache_data(ttl=600, show_spinner=False)
def fetch_lookalike_audiences(account_id: str) -> list:
    try:
        init_api()
        from facebook_business.adobjects.customaudience import CustomAudience
        audiences = AdAccount(account_id).get_custom_audiences(
            fields=[CustomAudience.Field.id, CustomAudience.Field.name,
                    CustomAudience.Field.subtype, CustomAudience.Field.approximate_count_upper_bound]
        )
        return [
            {"id": a["id"], "name": a["name"], "size": a.get("approximate_count_upper_bound", 0)}
            for a in audiences if a.get("subtype") == "LOOKALIKE"
        ]
    except Exception:
        return []

# ── Subir imagen (reutilizable para preview y creación final) ─────────────────
def upload_ad_image(account_id: str, image_bytes: bytes, image_ext: str) -> str:
    ext = ("." + image_ext.lower().replace("jpeg", "jpg")) if image_ext else ".jpg"
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(image_bytes)
        tmp_path = tmp.name
    try:
        init_api()
        img_obj = AdImage(parent_id=account_id)
        img_obj[AdImage.Field.filename] = tmp_path
        img_obj.remote_create()
        return img_obj[AdImage.Field.hash]
    finally:
        os.unlink(tmp_path)

# ── Vista previa del anuncio (sin publicar nada) ──────────────────────────────
def get_ad_preview_html(account_id, page_id, image_hash, primary_text, headline,
                         ad_description, destination_url, cta_type, ad_format):
    init_api()
    creative_spec = {
        "object_story_spec": {
            "page_id": page_id,
            "link_data": {
                "image_hash":     image_hash,
                "link":           destination_url,
                "message":        primary_text,
                "name":           headline,
                "description":    ad_description,
                "call_to_action": {"type": cta_type, "value": {"link": destination_url}},
            }
        }
    }
    result = AdAccount(account_id).get_generate_previews(params={
        "creative": creative_spec,
        "ad_format": ad_format,
    })
    if result:
        return result[0].get("body", "")
    return None

def get_carousel_preview_html(account_id, page_id, cards, primary_text, destination_url, cta_type, ad_format):
    """cards: lista de {"image_hash","headline","description"} — vista previa de un anuncio de carrusel."""
    init_api()
    child_attachments = [{
        "link":        destination_url,
        "image_hash":  c["image_hash"],
        "name":        c.get("headline") or "",
        "description": c.get("description") or "",
    } for c in cards]
    creative_spec = {
        "object_story_spec": {
            "page_id": page_id,
            "link_data": {
                "link":              destination_url,
                "message":           primary_text,
                "child_attachments": child_attachments,
                "call_to_action":    {"type": cta_type, "value": {"link": destination_url}},
                "multi_share_optimized": True,
            }
        }
    }
    result = AdAccount(account_id).get_generate_previews(params={
        "creative": creative_spec,
        "ad_format": ad_format,
    })
    if result:
        return result[0].get("body", "")
    return None

# Parámetros UTM que Meta agrega automáticamente al link de destino al momento de servir el anuncio
# (no modifican el link guardado en la creatividad). {{site_source_name}} resuelve dinámicamente a
# "fb", "ig", "an" (Audience Network) o "msg" (Messenger) según donde se haya mostrado el anuncio —
# así GA4 puede distinguir Facebook de Instagram automáticamente en sessionSourceMedium.
META_UTM_TAGS = (
    "utm_source={{site_source_name}}"
    "&utm_medium=paidsocial"
    "&utm_campaign={{campaign.name}}"
    "&utm_content={{ad.name}}"
    "&utm_term={{adset.name}}"
)

# ── Creación completa de anuncio (soporta 1 o varios conjuntos por plataforma) ─
def create_full_ad(
    account_id, page_id, camp_name, objective,
    adset_configs,  # lista: [{"platforms": ["facebook","instagram"], "budget": 10.0, "suffix": ""}]
    countries, age_min, age_max, genders, interest_ids, custom_audience_ids,
    image_bytes, image_ext, primary_text, headline, ad_description,
    destination_url, cta_type, start_date,
    carousel_cards=None,  # opcional: lista de {"image_bytes","image_ext","headline","description"} — si se
                          # pasa (2 a 10 tarjetas), se crea un anuncio de carrusel en vez de imagen única.
):
    init_api()

    # 1. Campaña (una sola, compartida por todos los conjuntos)
    camp = AdAccount(account_id).create_campaign(
        fields=[Campaign.Field.id],
        params={
            Campaign.Field.name:                 camp_name,
            Campaign.Field.objective:             objective,
            Campaign.Field.status:                "PAUSED",
            Campaign.Field.special_ad_categories: [],
            "is_adset_budget_sharing_enabled":     False,
        }
    )
    camp_id = camp[Campaign.Field.id]

    # 2. Imagen(es) y creatividad (una sola, compartida por todos los conjuntos)
    if carousel_cards:
        child_attachments = []
        for card in carousel_cards:
            card_hash = upload_ad_image(account_id, card["image_bytes"], card["image_ext"])
            child_attachments.append({
                "link":        destination_url,
                "image_hash":  card_hash,
                "name":        card.get("headline") or headline,
                "description": card.get("description") or ad_description,
            })
        creative = AdAccount(account_id).create_ad_creative(
            fields=[AdCreative.Field.id],
            params={
                AdCreative.Field.name: f"Creative_{camp_name[:50]}",
                AdCreative.Field.object_story_spec: {
                    "page_id": page_id,
                    "link_data": {
                        "link":               destination_url,
                        "message":            primary_text,
                        "child_attachments":  child_attachments,
                        "call_to_action":     {"type": cta_type, "value": {"link": destination_url}},
                        "multi_share_optimized": True,
                    }
                }
            }
        )
        creative_id = creative[AdCreative.Field.id]
    else:
        image_hash = upload_ad_image(account_id, image_bytes, image_ext)

        creative = AdAccount(account_id).create_ad_creative(
            fields=[AdCreative.Field.id],
            params={
                AdCreative.Field.name: f"Creative_{camp_name[:50]}",
                AdCreative.Field.object_story_spec: {
                    "page_id": page_id,
                    "link_data": {
                        "image_hash":     image_hash,
                        "link":           destination_url,
                        "message":        primary_text,
                        "name":           headline,
                        "description":    ad_description,
                        "call_to_action": {"type": cta_type, "value": {"link": destination_url}},
                    }
                }
            }
        )
        creative_id = creative[AdCreative.Field.id]

    start_ts = int(datetime.combine(start_date, datetime.min.time()).timestamp())

    # 3. Un conjunto de anuncios + un anuncio por cada plataforma/presupuesto configurado
    results = []
    for cfg in adset_configs:
        targeting = {
            "geo_locations": {"countries": countries},
            "age_min": age_min,
            "age_max": age_max,
            "targeting_automation": {"advantage_audience": 0},
            "publisher_platforms": cfg["platforms"],
        }
        if genders:
            targeting["genders"] = genders
        if interest_ids:
            targeting["flexible_spec"] = [{"interests": [{"id": str(iid)} for iid in interest_ids]}]
        if custom_audience_ids:
            targeting["custom_audiences"] = [{"id": str(cid)} for cid in custom_audience_ids]

        suffix = cfg.get("suffix", "")
        adset_name_final = f"{camp_name}_Conjunto{('_' + suffix) if suffix else ''}"

        adset = AdAccount(account_id).create_ad_set(
            fields=[AdSet.Field.id],
            params={
                AdSet.Field.name:              adset_name_final,
                AdSet.Field.campaign_id:       camp_id,
                AdSet.Field.daily_budget:      int(cfg["budget"] * 100),
                AdSet.Field.billing_event:     "IMPRESSIONS",
                AdSet.Field.optimization_goal: "LINK_CLICKS",
                AdSet.Field.bid_strategy:      "LOWEST_COST_WITHOUT_CAP",
                AdSet.Field.targeting:         targeting,
                AdSet.Field.status:            "PAUSED",
                AdSet.Field.start_time:        start_ts,
            }
        )
        adset_id = adset[AdSet.Field.id]

        ad = AdAccount(account_id).create_ad(
            fields=[Ad.Field.id],
            params={
                Ad.Field.name:     f"{camp_name}{('_' + suffix) if suffix else ''}",
                Ad.Field.adset_id: adset_id,
                Ad.Field.creative: {"creative_id": creative_id},
                Ad.Field.status:   "PAUSED",
                "url_tags":        META_UTM_TAGS,
            }
        )
        results.append({
            "platforms": cfg["platforms"],
            "budget":    cfg["budget"],
            "adset_id":  adset_id,
            "ad_id":     ad[Ad.Field.id],
        })

    return {
        "campaign_id": camp_id,
        "creative_id": creative_id,
        "adsets":      results,
    }

# ══════════════════════════════════════════════════════════════════════════════
# GOOGLE ANALYTICS (GA4) — métricas de la web
# ══════════════════════════════════════════════════════════════════════════════
def get_ga_date_range(date_preset: str, since_str: str = "", until_str: str = ""):
    """Traduce el mismo filtro de período del sidebar a fechas concretas para GA4."""
    hoy = datetime.now(PERU_TZ).date()
    if date_preset == "custom" and since_str and until_str:
        return since_str, until_str
    if date_preset == "last_7d":
        start, end = hoy - timedelta(days=7), hoy - timedelta(days=1)
    elif date_preset == "last_14d":
        start, end = hoy - timedelta(days=14), hoy - timedelta(days=1)
    elif date_preset == "last_30d":
        start, end = hoy - timedelta(days=30), hoy - timedelta(days=1)
    elif date_preset == "last_90d":
        start, end = hoy - timedelta(days=90), hoy - timedelta(days=1)
    elif date_preset == "this_month":
        start, end = hoy.replace(day=1), hoy
    elif date_preset == "last_month":
        first_this_month = hoy.replace(day=1)
        last_day_prev = first_this_month - timedelta(days=1)
        start, end = last_day_prev.replace(day=1), last_day_prev
    else:
        start, end = hoy - timedelta(days=30), hoy
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

def init_ga_client():
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.oauth2 import service_account
    creds_dict = dict(st.secrets["gcp_service_account"])
    credentials = service_account.Credentials.from_service_account_info(creds_dict)
    return BetaAnalyticsDataClient(credentials=credentials)

# Dominios que reportan a la misma propiedad GA4 — se pueden filtrar por separado
HOST_OPTIONS = {"Todos los dominios": None, "🐹 cuy.pe": "cuy.pe", "🔒 secure.guinea.pe": "secure.guinea.pe"}

# Pasos del funnel de compra en secure.guinea.pe, en orden (de arriba hacia abajo = pirámide invertida)
FUNNEL_PAGES_SECURE = [
    "/cuy/plan",
    "/cuy/personal-data",
    "/cuy/address",
    "/cuy/subscription",
    "/cuy/successful",
]

def _ga_host_filter(host_filter: str):
    """Construye un FilterExpression de GA4 para filtrar por hostName exacto, o None si no aplica."""
    if not host_filter:
        return None
    from google.analytics.data_v1beta.types import FilterExpression, Filter
    return FilterExpression(
        filter=Filter(
            field_name="hostName",
            string_filter=Filter.StringFilter(value=host_filter, match_type=Filter.StringFilter.MatchType.EXACT),
        )
    )

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_ga_summary(property_id: str, start_date: str, end_date: str, host_filter: str = None) -> dict:
    from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Metric
    client = init_ga_client()
    request = RunReportRequest(
        property=f"properties/{property_id}",
        metrics=[
            Metric(name="sessions"), Metric(name="activeUsers"), Metric(name="screenPageViews"),
            Metric(name="conversions"), Metric(name="bounceRate"), Metric(name="averageSessionDuration"),
        ],
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        dimension_filter=_ga_host_filter(host_filter),
    )
    response = client.run_report(request)
    if not response.rows:
        return {"sessions": 0, "users": 0, "pageviews": 0, "conversions": 0, "bounce_rate": 0.0, "avg_duration": 0.0}
    v = [float(m.value) for m in response.rows[0].metric_values]
    bounce = v[4] * 100 if v[4] <= 1 else v[4]
    return {"sessions": v[0], "users": v[1], "pageviews": v[2], "conversions": v[3],
            "bounce_rate": bounce, "avg_duration": v[5]}

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_ga_timeseries(property_id: str, start_date: str, end_date: str) -> pd.DataFrame:
    from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Dimension, Metric, OrderBy
    client = init_ga_client()
    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name="date")],
        metrics=[Metric(name="sessions"), Metric(name="activeUsers")],
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        order_bys=[OrderBy(dimension=OrderBy.DimensionOrderBy(dimension_name="date"))],
    )
    response = client.run_report(request)
    rows = []
    for r in response.rows:
        d = r.dimension_values[0].value  # formato YYYYMMDD
        rows.append({
            "Fecha": datetime.strptime(d, "%Y%m%d").date(),
            "Sesiones": float(r.metric_values[0].value),
            "Usuarios": float(r.metric_values[1].value),
        })
    return pd.DataFrame(rows)

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_ga_channels(property_id: str, start_date: str, end_date: str, host_filter: str = None) -> pd.DataFrame:
    from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Dimension, Metric, OrderBy
    client = init_ga_client()
    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name="sessionDefaultChannelGroup")],
        metrics=[Metric(name="sessions"), Metric(name="conversions")],
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
        dimension_filter=_ga_host_filter(host_filter),
    )
    response = client.run_report(request)
    rows = [{
        "Canal": r.dimension_values[0].value or "(sin asignar)",
        "Sesiones": float(r.metric_values[0].value),
        "Conversiones": float(r.metric_values[1].value),
    } for r in response.rows]
    return pd.DataFrame(rows)

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_ga_traffic_origin(property_id: str, start_date: str, end_date: str, host_filter: str = None, limit: int = 12) -> pd.DataFrame:
    """Trae el origen (fuente/medio) de las sesiones que llegan a un dominio — ej. 'cuy.pe / referral',
    'blog.cuy.pe / referral', 'facebook / paid social', 'google / cpc', '(direct) / (none)'."""
    from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Dimension, Metric, OrderBy
    client = init_ga_client()
    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name="sessionSourceMedium")],
        metrics=[Metric(name="sessions"), Metric(name="activeUsers")],
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
        limit=limit,
        dimension_filter=_ga_host_filter(host_filter),
    )
    response = client.run_report(request)
    rows = [{
        "Origen": r.dimension_values[0].value or "(sin asignar)",
        "Sesiones": float(r.metric_values[0].value),
        "Usuarios": float(r.metric_values[1].value),
    } for r in response.rows]
    return pd.DataFrame(rows)

def _traffic_origin_icon(origen: str) -> str:
    """Asigna un ícono según el origen del tráfico (Ads pagado, sitios propios de Cuy, orgánico, directo, etc.)."""
    o = origen.lower()
    if any(k in o for k in ["cpc", "ppc", "paid"]):
        return "📣"
    if "cuy.pe" in o and "blog" not in o:
        return "🐹"
    if "blog.cuy.pe" in o:
        return "📝"
    if "referral" in o:
        return "🔗"
    if "organic" in o:
        return "🌱"
    if "(direct)" in o or "none" in o:
        return "➡️"
    if any(k in o for k in ["facebook", "instagram", "ig", "fb"]):
        return "📱"
    return "🌐"

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_ga_top_pages(property_id: str, start_date: str, end_date: str, limit: int = 10, host_filter: str = None) -> pd.DataFrame:
    from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Dimension, Metric, OrderBy
    client = init_ga_client()
    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name="pagePath")],
        metrics=[Metric(name="screenPageViews"), Metric(name="activeUsers")],
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="screenPageViews"), desc=True)],
        limit=limit,
        dimension_filter=_ga_host_filter(host_filter),
    )
    response = client.run_report(request)
    rows = [{
        "Página": r.dimension_values[0].value,
        "Vistas": float(r.metric_values[0].value),
        "Usuarios": float(r.metric_values[1].value),
    } for r in response.rows]
    return pd.DataFrame(rows)

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_ga_funnel_pages(property_id: str, start_date: str, end_date: str, host_filter: str, pages: list) -> pd.DataFrame:
    """Trae vistas/usuarios para un conjunto fijo de páginas (embudo), devueltas en el orden dado —
    pensado para graficarse como pirámide invertida (funnel) en vez de ordenarse por más visitadas."""
    from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Dimension, Metric
    client = init_ga_client()
    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name="pagePath")],
        metrics=[Metric(name="screenPageViews"), Metric(name="activeUsers")],
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        limit=100000,
        dimension_filter=_ga_host_filter(host_filter),
    )
    response = client.run_report(request)
    raw = [{
        "path": r.dimension_values[0].value or "",
        "Vistas": float(r.metric_values[0].value),
        "Usuarios": float(r.metric_values[1].value),
    } for r in response.rows]

    rows = []
    for p in pages:
        vistas   = sum(r["Vistas"] for r in raw if p in r["path"])
        usuarios = sum(r["Usuarios"] for r in raw if p in r["path"])
        rows.append({"Página": p, "Vistas": vistas, "Usuarios": usuarios})
    return pd.DataFrame(rows)

def fetch_ga_by_domain(property_id: str, start_date: str, end_date: str, top_limit: int = 5) -> dict:
    """Trae el desglose de métricas de Web Analytics separado por dominio (cuy.pe / secure.guinea.pe).
    Para secure.guinea.pe, las páginas se devuelven como embudo de compra en orden fijo (pirámide invertida)
    en vez de ordenarse por número de vistas."""
    result = {}
    for host in ["cuy.pe", "secure.guinea.pe"]:
        if host == "secure.guinea.pe":
            top_pages = fetch_ga_funnel_pages(property_id, start_date, end_date, host, FUNNEL_PAGES_SECURE)
        else:
            top_pages = fetch_ga_top_pages(property_id, start_date, end_date, limit=top_limit, host_filter=host)
        result[host] = {
            "summary":       fetch_ga_summary(property_id, start_date, end_date, host_filter=host),
            "top_pages":     top_pages,
            "is_funnel":     host == "secure.guinea.pe",
            "traffic_origin": fetch_ga_traffic_origin(property_id, start_date, end_date, host_filter=host),
        }
    return result

def render_funnel_boxes(tp: pd.DataFrame, value_col: str, unit_label: str):
    """Dibuja el embudo de pasos como recuadros con flechas (pirámide invertida), usando la columna
    de valor indicada (p.ej. 'Vistas' o 'Usuarios') — mismo diseño visual para cualquier métrica."""
    n = len(tp)
    total_top = tp[value_col].iloc[0] if tp[value_col].iloc[0] else 0
    # Degradado dentro del rango oscuro/medio de morado de marca — siempre con buen contraste
    # para texto blanco (nunca cae en tonos pálidos como el primer/segundo color de PURPLE_SCALE).
    colors = [_lerp_color(BRAND["purple_darker"], BRAND["purple"], i / max(n - 1, 1)) for i in range(n)]

    cells = []
    for i, (_, row) in enumerate(tp.iterrows()):
        pct = (row[value_col] / total_top * 100) if total_top else 0
        cells.append(
            f'<div style="flex:1 1 0;min-width:130px;background:{colors[i]};border-radius:14px;'
            f'padding:16px 12px;text-align:center;color:#FFFFFF;'
            f'box-shadow:0 2px 6px rgba(21,12,84,0.25);">'
            f'<div style="font-size:13px;font-weight:600;letter-spacing:.03em;opacity:.85;margin-bottom:6px;">'
            f'PASO {i + 1}</div>'
            f'<div style="font-size:16px;font-weight:700;margin-bottom:10px;word-break:break-word;">'
            f'{row["Página"]}</div>'
            f'<div style="font-size:24px;font-weight:800;line-height:1.1;">{row[value_col]:,.0f}</div>'
            f'<div style="font-size:13px;opacity:.9;margin-top:2px;">{unit_label} · {pct:.0f}% del paso 1</div>'
            f'</div>'
        )
        if i < n - 1:
            cells.append(
                f'<div style="display:flex;align-items:center;justify-content:center;flex:0 0 auto;'
                f'font-size:30px;font-weight:700;color:{BRAND["lemon_dark"]};padding:0 2px;">&#10132;</div>'
            )

    html = (
        '<div style="display:flex;align-items:stretch;gap:6px;flex-wrap:wrap;margin-bottom:8px;">'
        + "".join(cells) +
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)

def render_domain_top_pages(tp: pd.DataFrame, is_funnel: bool = False, height: int = 200):
    """Muestra las páginas top de un dominio. Si es_funnel=True, las grafica como pirámide invertida
    (funnel de compra) en vez de tabla, siguiendo el orden fijo en el que llegan los datos —
    primero con vistas totales y luego con usuarios únicos por paso."""
    if tp is None or tp.empty or tp["Vistas"].sum() == 0:
        st.caption("Sin páginas registradas para este dominio en el período.")
        return
    if is_funnel:
        render_funnel_boxes(tp, "Vistas", "vistas")
        st.caption("👤 Usuarios únicos por paso")
        render_funnel_boxes(tp, "Usuarios", "usuarios únicos")
    else:
        st.dataframe(
            tp.style.format({"Vistas": "{:,.0f}", "Usuarios": "{:,.0f}"}),
            use_container_width=True, hide_index=True, height=height,
        )

def render_traffic_origin(origin_df: pd.DataFrame, height: int = 260):
    """Grafica de dónde vienen las sesiones (Ads, cuy.pe, blog.cuy.pe, orgánico, directo, etc.)."""
    if origin_df is None or origin_df.empty or origin_df["Sesiones"].sum() == 0:
        st.caption("Sin datos de origen de tráfico para este período.")
        return
    df = origin_df.copy()
    df["Etiqueta"] = df.apply(lambda r: f"{_traffic_origin_icon(r['Origen'])} {r['Origen']}", axis=1)
    df = df.sort_values("Sesiones")
    max_sesiones = df["Sesiones"].max()
    fig = px.bar(
        df, x="Sesiones", y="Etiqueta", orientation="h",
        color="Sesiones", color_continuous_scale=PURPLE_SCALE, text="Sesiones",
    )
    fig.update_traces(texttemplate="%{text:.0f}", textposition="outside", cliponaxis=False)
    fig.update_layout(
        height=height, margin=dict(l=0, r=60, t=0, b=0), yaxis_title="", xaxis_title="Sesiones",
        xaxis=dict(range=[0, max_sesiones * 1.2]), coloraxis_showscale=False,
        font=dict(size=13),
    )
    st.plotly_chart(fig, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# MICROSOFT CLARITY — Data Export API (10 llamadas/día por proyecto, máx. 3 días)
# ══════════════════════════════════════════════════════════════════════════════
CLARITY_DIMENSIONS = {
    "Ninguna (agregado)": None,
    "Navegador": "Browser",
    "Dispositivo": "Device",
    "País/Región": "Country/Region",
    "Sistema operativo": "OS",
    "Fuente (Source)": "Source",
    "Medio (Medium)": "Medium",
    "Campaña": "Campaign",
    "Canal": "Channel",
    "URL": "URL",
}

CLARITY_METRIC_LABELS = {
    "Traffic": "🚦 Tráfico",
    "Popular Pages": "📄 Páginas populares",
    "Engagement Time": "⏱️ Tiempo de interacción",
    "Scroll Depth": "📜 Profundidad de scroll",
    "Dead Click Count": "💀 Clics muertos (sin respuesta)",
    "Rage Click Count": "😤 Clics de frustración (rage clicks)",
    "Quickback Click": "↩️ Regresos inmediatos (quickback)",
    "Excessive Scroll": "🔄 Scroll excesivo",
    "Script Error Count": "⚠️ Errores de script",
    "Error Click Count": "🚫 Clics con error",
}

CLARITY_PROJECT_URL = get_secret("CLARITY_PROJECT_URL") or "https://clarity.microsoft.com/projects"

@st.cache_data(ttl=14400, show_spinner=False)  # 4h de caché — Clarity limita a 10 llamadas/día por proyecto
def fetch_clarity_insights(num_days: int = 3, dimension1: str = None, dimension2: str = None) -> list:
    """Trae los datos crudos de la Clarity Data Export API."""
    if not CLARITY_API_TOKEN:
        return []
    url = "https://www.clarity.ms/export-data/api/v1/project-live-insights"
    params = {"numOfDays": num_days}
    if dimension1:
        params["dimension1"] = dimension1
    if dimension2:
        params["dimension2"] = dimension2
    headers = {
        "Authorization": f"Bearer {CLARITY_API_TOKEN}",
        "Content-Type": "application/json",
    }
    response = requests.get(url, params=params, headers=headers, timeout=20)
    if response.status_code == 429:
        raise RuntimeError("Se alcanzó el límite diario de 10 llamadas a la API de Clarity. Los datos se actualizarán automáticamente mañana.")
    if response.status_code == 401:
        raise RuntimeError("Token de Clarity inválido o vencido. Verifica CLARITY_API_TOKEN en Secrets.")
    response.raise_for_status()
    return response.json()

def clarity_metric_df(clarity_data: list, metric_name: str) -> pd.DataFrame:
    """Extrae el bloque de una métrica específica de la respuesta de Clarity y lo convierte en DataFrame."""
    for block in clarity_data or []:
        if str(block.get("metricName", "")).lower() == metric_name.lower():
            return pd.DataFrame(block.get("information", []))
    return pd.DataFrame()

def _clarity_col(df: pd.DataFrame, *candidates) -> pd.Series:
    """Busca la primera columna existente entre varios nombres posibles (la API de Clarity varía nombres/mayúsculas)."""
    for c in candidates:
        if c in df.columns:
            return pd.to_numeric(df[c], errors="coerce").fillna(0)
    return pd.Series([0] * len(df))

def clarity_traffic_summary(clarity_data: list) -> dict:
    """Suma las filas de la métrica 'Traffic' para obtener totales generales de sesiones y usuarios."""
    df = clarity_metric_df(clarity_data, "Traffic")
    if df.empty:
        return {}
    sessions = _clarity_col(df, "totalSessionCount", "TotalSessionCount").sum()
    bots     = _clarity_col(df, "totalBotSessionCount", "TotalBotSessionCount").sum()
    users    = _clarity_col(df, "distinctUserCount", "distantUserCount", "DistinctUserCount").sum()
    return {"sessions": sessions, "bot_sessions": bots, "users": users}

# ══════════════════════════════════════════════════════════════════════════════
# GOOGLE ADS — Google Ads API (google-ads client library)
# ══════════════════════════════════════════════════════════════════════════════
GOOGLE_ADS_READY = bool(
    GOOGLE_ADS_CLIENT_ID and GOOGLE_ADS_CLIENT_SECRET and GOOGLE_ADS_REFRESH_TOKEN and GOOGLE_ADS_DEVELOPER_TOKEN
)

def init_google_ads_client():
    from google.ads.googleads.client import GoogleAdsClient
    config = {
        "client_id": GOOGLE_ADS_CLIENT_ID,
        "client_secret": GOOGLE_ADS_CLIENT_SECRET,
        "refresh_token": GOOGLE_ADS_REFRESH_TOKEN,
        "developer_token": GOOGLE_ADS_DEVELOPER_TOKEN,
        "use_proto_plus": True,
    }
    if GOOGLE_ADS_LOGIN_CUSTOMER_ID:
        config["login_customer_id"] = str(GOOGLE_ADS_LOGIN_CUSTOMER_ID).replace("-", "")
    return GoogleAdsClient.load_from_dict(config)

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_google_ads_campaigns(customer_id: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Trae métricas de campañas de Google Ads agregadas en el rango de fechas dado, vía GAQL."""
    client = init_google_ads_client()
    ga_service = client.get_service("GoogleAdsService")
    customer_id_clean = str(customer_id).replace("-", "")
    query = f"""
        SELECT
            campaign.id,
            campaign.name,
            campaign.status,
            campaign.advertising_channel_type,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions,
            metrics.ctr,
            metrics.average_cpc
        FROM campaign
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        ORDER BY metrics.cost_micros DESC
    """
    response = ga_service.search(customer_id=customer_id_clean, query=query)
    rows = []
    for row in response:
        rows.append({
            "Campaña": row.campaign.name,
            "Estado": row.campaign.status.name,
            "Tipo": row.campaign.advertising_channel_type.name,
            "Impresiones": row.metrics.impressions,
            "Clics": row.metrics.clicks,
            "Gasto": row.metrics.cost_micros / 1_000_000,
            "Conversiones": row.metrics.conversions,
            "CTR": row.metrics.ctr * 100,
            "CPC": row.metrics.average_cpc / 1_000_000 if row.metrics.average_cpc else 0,
        })
    return pd.DataFrame(rows)

# ══════════════════════════════════════════════════════════════════════════════
# GOOGLE ADS — Recomendaciones de contenido para Display (IA basada en reglas)
# ══════════════════════════════════════════════════════════════════════════════
DISPLAY_HEADLINES_BANK = [
    "Internet Ilimitado Ya",
    "Planes Desde S/19.90",
    "Cuy Móvil, Sin Límites",
    "Cambia Hoy, Paga Menos",
    "Activación 100% Digital",
    "La Red Que Te Conviene",
    "Datos Que No Se Acaban",
    "Tu Plan Ideal Te Espera",
    "Sin Permanencia Forzada",
    "Recarga Fácil y Rápido",
]  # Cada uno ≤ 30 caracteres (límite de Google para títulos de anuncios responsivos)

DISPLAY_LONG_HEADLINE = "Internet ilimitado desde S/19.90 al mes, sin permanencia forzada"  # ≤ 90 caracteres

DISPLAY_DESCRIPTIONS_BANK = [
    "Activa tu plan Cuy en minutos, 100% online y sin hacer fila.",
    "Cambia de operador gratis y conserva tu mismo número.",
    "Planes ilimitados pensados para ti, sin letra chica.",
    "Miles de personas ya se cambiaron a Cuy Móvil este mes.",
    "Conéctate sin límites con la red que se adapta a ti.",
]  # Cada una ≤ 90 caracteres

DISPLAY_IMAGE_SPECS = [
    ("Imagen horizontal (paisaje)", "1200 × 628 px", "Relación 1.91:1 · mínimo 600×314"),
    ("Imagen cuadrada",             "1200 × 1200 px", "Relación 1:1 · mínimo 300×300"),
    ("Logo cuadrado",               "1200 × 1200 px", "Relación 1:1 · mínimo 128×128, fondo sólido o transparente"),
    ("Logo horizontal",             "1200 × 300 px",  "Relación 4:1 · mínimo 512×128"),
]

DISPLAY_CTA_OPTIONS = ["Más información", "Comprar ahora", "Regístrate", "Solicitar", "Descargar"]

GOOGLE_LOCATION_IDS = {
    "Perú":            "2604",
    "México":          "2484",
    "Colombia":        "2170",
    "Argentina":       "2032",
    "Chile":           "2152",
    "Ecuador":         "2218",
    "Bolivia":         "2068",
    "Venezuela":       "2862",
    "Estados Unidos":  "2840",
}
GOOGLE_LANGUAGE_IDS = {"Español": "1003", "Inglés": "1000", "Portugués": "1014"}

GOOGLE_AGE_RANGE_OPTIONS = {
    "18-24": "AGE_RANGE_18_24",
    "25-34": "AGE_RANGE_25_34",
    "35-44": "AGE_RANGE_35_44",
    "45-54": "AGE_RANGE_45_54",
    "55-64": "AGE_RANGE_55_64",
    "65+":   "AGE_RANGE_65_UP",
    "Desconocida": "AGE_RANGE_UNDETERMINED",
}
GOOGLE_GENDER_OPTIONS = {"Hombres": "MALE", "Mujeres": "FEMALE", "Desconocido": "UNDETERMINED"}

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_google_user_lists(customer_id: str) -> pd.DataFrame:
    """Trae las listas de remarketing/audiencias ya existentes en la cuenta de Google Ads."""
    client = init_google_ads_client()
    ga_service = client.get_service("GoogleAdsService")
    customer_id_clean = str(customer_id).replace("-", "")
    query = """
        SELECT user_list.id, user_list.name, user_list.type, user_list.size_for_display
        FROM user_list
        WHERE user_list.membership_status = 'OPEN'
        ORDER BY user_list.name
    """
    response = ga_service.search(customer_id=customer_id_clean, query=query)
    rows = [{
        "id":            row.user_list.id,
        "resource_name": f"customers/{customer_id_clean}/userLists/{row.user_list.id}",
        "Nombre":        row.user_list.name,
        "Tipo":          row.user_list.type_.name,
        "Tamaño (Display)": row.user_list.size_for_display,
    } for row in response]
    return pd.DataFrame(rows)

@st.cache_data(ttl=3600, show_spinner=False)
def search_google_user_interests(query_text: str, limit: int = 15) -> pd.DataFrame:
    """Busca categorías de audiencia de Google (afinidad / in-market) que coincidan con el texto —
    equivalente al buscador de intereses de Meta, pero contra la taxonomía de Google Ads."""
    client = init_google_ads_client()
    customer_id_clean = str(GOOGLE_ADS_CUSTOMER_ID).replace("-", "")
    ga_service = client.get_service("GoogleAdsService")
    safe_text = query_text.replace("'", "")
    gaql = f"""
        SELECT user_interest.id, user_interest.name, user_interest.taxonomy_type, user_interest.resource_name
        FROM user_interest
        WHERE user_interest.name LIKE '%{safe_text}%'
        LIMIT {limit}
    """
    response = ga_service.search(customer_id=customer_id_clean, query=gaql)
    rows = [{
        "id":            row.user_interest.id,
        "resource_name": row.user_interest.resource_name,
        "Nombre":        row.user_interest.name,
        "Tipo":          row.user_interest.taxonomy_type.name,
    } for row in response]
    return pd.DataFrame(rows)

def _gads_fit_image_to_ratio(image_bytes: bytes, target_size: tuple) -> bytes:
    """Recorta (crop centrado) y reescala la imagen a un tamaño exacto en píxeles (p. ej.
    1200x1200 para cuadrada/logo, 1200x628 para horizontal), garantizando el ratio exacto
    que exige Google Ads y evitando el error ASPECT_RATIO_NOT_ALLOWED."""
    target_w, target_h = target_size
    target_ratio = target_w / target_h
    img = Image.open(BytesIO(image_bytes))
    img = img.convert("RGB")
    w, h = img.size
    current_ratio = w / h
    if current_ratio > target_ratio:
        new_h = h
        new_w = int(round(h * target_ratio))
    else:
        new_w = w
        new_h = int(round(w / target_ratio))
    new_w = min(new_w, w)
    new_h = min(new_h, h)
    left = (w - new_w) // 2
    top = (h - new_h) // 2
    img = img.crop((left, top, left + new_w, top + new_h))
    img = img.resize((target_w, target_h), Image.LANCZOS)
    out = BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()

def _gads_upload_image_asset(client, customer_id: str, image_bytes: bytes, asset_name: str) -> str:
    """Sube una imagen como Asset de Google Ads y devuelve su resource_name."""
    asset_service = client.get_service("AssetService")
    operation = client.get_type("AssetOperation")
    asset = operation.create
    asset.name = asset_name
    asset.type_ = client.enums.AssetTypeEnum.IMAGE
    asset.image_asset.data = image_bytes
    response = asset_service.mutate_assets(customer_id=customer_id, operations=[operation])
    return response.results[0].resource_name

def create_display_campaign(
    customer_id: str, campaign_name: str, daily_budget_usd: float, final_url: str,
    headlines: list, long_headline: str, descriptions: list, business_name: str,
    marketing_image_bytes: bytes, square_image_bytes: bytes, logo_image_bytes: bytes = None,
    location_ids: list = None, language_id: str = "1003", start_date=None,
    age_range_keys: list = None, gender_keys: list = None,
    user_list_resource_names: list = None, user_interest_resource_names: list = None,
) -> dict:
    """Crea una campaña de Display de Google Ads completa (presupuesto → campaña → segmentación →
    grupo de anuncios → imágenes → anuncio de Display responsivo), en estado PAUSADO."""
    client = init_google_ads_client()
    customer_id_clean = str(customer_id).replace("-", "")
    location_ids = location_ids or ["2604"]

    # 1. Presupuesto
    budget_service = client.get_service("CampaignBudgetService")
    budget_operation = client.get_type("CampaignBudgetOperation")
    budget = budget_operation.create
    budget.name = f"Budget_{campaign_name[:40]}_{int(datetime.now().timestamp())}"
    budget.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD
    budget.amount_micros = int(daily_budget_usd * 1_000_000)
    budget_response = budget_service.mutate_campaign_budgets(customer_id=customer_id_clean, operations=[budget_operation])
    budget_resource_name = budget_response.results[0].resource_name

    # 2. Campaña de Display
    campaign_service = client.get_service("CampaignService")
    campaign_operation = client.get_type("CampaignOperation")
    campaign = campaign_operation.create
    campaign.name = campaign_name
    campaign.advertising_channel_type = client.enums.AdvertisingChannelTypeEnum.DISPLAY
    campaign.status = client.enums.CampaignStatusEnum.PAUSED
    campaign.campaign_budget = budget_resource_name
    campaign.manual_cpc.enhanced_cpc_enabled = False
    campaign.network_settings.target_google_search = False
    campaign.network_settings.target_search_network = False
    campaign.network_settings.target_content_network = True
    campaign.network_settings.target_partner_search_network = False
    campaign.contains_eu_political_advertising = (
        client.enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
    )
    # Nota: la fecha de inicio no se fija por API — la campaña queda en PAUSADO y arranca a correr
    # (según su fecha de inicio real en Google Ads, por defecto "hoy") recién cuando la actives ahí.
    campaign_response = campaign_service.mutate_campaigns(customer_id=customer_id_clean, operations=[campaign_operation])
    campaign_resource_name = campaign_response.results[0].resource_name

    # 3. Segmentación geográfica e idioma
    criterion_service = client.get_service("CampaignCriterionService")
    criterion_ops = []
    for loc_id in location_ids:
        op = client.get_type("CampaignCriterionOperation")
        crit = op.create
        crit.campaign = campaign_resource_name
        crit.location.geo_target_constant = f"geoTargetConstants/{loc_id}"
        criterion_ops.append(op)
    lang_op = client.get_type("CampaignCriterionOperation")
    lang_crit = lang_op.create
    lang_crit.campaign = campaign_resource_name
    lang_crit.language.language_constant = f"languageConstants/{language_id}"
    criterion_ops.append(lang_op)

    # Demografía: edad y género (opcional)
    for age_key in (age_range_keys or []):
        age_op = client.get_type("CampaignCriterionOperation")
        age_crit = age_op.create
        age_crit.campaign = campaign_resource_name
        age_crit.age_range.type_ = getattr(client.enums.AgeRangeTypeEnum, GOOGLE_AGE_RANGE_OPTIONS[age_key])
        criterion_ops.append(age_op)
    for gender_key in (gender_keys or []):
        gender_op = client.get_type("CampaignCriterionOperation")
        gender_crit = gender_op.create
        gender_crit.campaign = campaign_resource_name
        gender_crit.gender.type_ = getattr(client.enums.GenderTypeEnum, GOOGLE_GENDER_OPTIONS[gender_key])
        criterion_ops.append(gender_op)

    # Audiencias: listas de remarketing e intereses de afinidad/in-market (opcional)
    for ul_resource in (user_list_resource_names or []):
        ul_op = client.get_type("CampaignCriterionOperation")
        ul_crit = ul_op.create
        ul_crit.campaign = campaign_resource_name
        ul_crit.user_list.user_list = ul_resource
        criterion_ops.append(ul_op)
    for ui_resource in (user_interest_resource_names or []):
        ui_op = client.get_type("CampaignCriterionOperation")
        ui_crit = ui_op.create
        ui_crit.campaign = campaign_resource_name
        ui_crit.user_interest.user_interest_category = ui_resource
        criterion_ops.append(ui_op)

    criterion_service.mutate_campaign_criteria(customer_id=customer_id_clean, operations=criterion_ops)

    # 4. Grupo de anuncios
    ad_group_service = client.get_service("AdGroupService")
    ad_group_operation = client.get_type("AdGroupOperation")
    ad_group = ad_group_operation.create
    ad_group.name = f"{campaign_name}_AdGroup"
    ad_group.campaign = campaign_resource_name
    ad_group.status = client.enums.AdGroupStatusEnum.ENABLED
    ad_group.type_ = client.enums.AdGroupTypeEnum.DISPLAY_STANDARD
    ad_group_response = ad_group_service.mutate_ad_groups(customer_id=customer_id_clean, operations=[ad_group_operation])
    ad_group_resource_name = ad_group_response.results[0].resource_name

    # 5. Imágenes como Assets (se ajustan al ratio exacto que exige Google Ads antes de subirlas)
    _ts = int(datetime.now().timestamp())
    marketing_image_fitted = _gads_fit_image_to_ratio(marketing_image_bytes, (1200, 628))
    square_image_fitted    = _gads_fit_image_to_ratio(square_image_bytes, (1200, 1200))
    marketing_image_asset = _gads_upload_image_asset(client, customer_id_clean, marketing_image_fitted, f"{campaign_name}_marketing_{_ts}")
    square_image_asset    = _gads_upload_image_asset(client, customer_id_clean, square_image_fitted, f"{campaign_name}_square_{_ts}")
    logo_image_asset = None
    if logo_image_bytes:
        logo_image_fitted = _gads_fit_image_to_ratio(logo_image_bytes, (1200, 1200))
        logo_image_asset = _gads_upload_image_asset(client, customer_id_clean, logo_image_fitted, f"{campaign_name}_logo_{_ts}")

    # 6. Anuncio de Display responsivo
    ad_group_ad_service = client.get_service("AdGroupAdService")
    ad_group_ad_operation = client.get_type("AdGroupAdOperation")
    ad_group_ad = ad_group_ad_operation.create
    ad_group_ad.ad_group = ad_group_resource_name
    ad_group_ad.status = client.enums.AdGroupAdStatusEnum.PAUSED

    rda = ad_group_ad.ad.responsive_display_ad
    for h in headlines[:5]:
        text_asset = client.get_type("AdTextAsset")
        text_asset.text = h
        rda.headlines.append(text_asset)
    rda.long_headline.text = long_headline
    for d in descriptions[:5]:
        text_asset = client.get_type("AdTextAsset")
        text_asset.text = d
        rda.descriptions.append(text_asset)
    rda.business_name = business_name

    mkt_img = client.get_type("AdImageAsset")
    mkt_img.asset = marketing_image_asset
    rda.marketing_images.append(mkt_img)

    sq_img = client.get_type("AdImageAsset")
    sq_img.asset = square_image_asset
    rda.square_marketing_images.append(sq_img)

    if logo_image_asset:
        logo_img = client.get_type("AdImageAsset")
        logo_img.asset = logo_image_asset
        rda.logo_images.append(logo_img)

    ad_group_ad.ad.final_urls.append(final_url)

    ad_response = ad_group_ad_service.mutate_ad_group_ads(customer_id=customer_id_clean, operations=[ad_group_ad_operation])

    return {
        "campaign_resource_name": campaign_resource_name,
        "ad_group_resource_name": ad_group_resource_name,
        "ad_resource_name":       ad_response.results[0].resource_name,
    }

def _gads_upload_text_asset(client, customer_id: str, text: str, asset_name: str) -> str:
    """Sube un texto como Asset de Google Ads (usado en Performance Max) y devuelve su resource_name."""
    asset_service = client.get_service("AssetService")
    operation = client.get_type("AssetOperation")
    asset = operation.create
    asset.name = asset_name
    asset.type_ = client.enums.AssetTypeEnum.TEXT
    asset.text_asset.text = text
    response = asset_service.mutate_assets(customer_id=customer_id, operations=[operation])
    return response.results[0].resource_name

def create_performance_max_campaign(
    customer_id: str, campaign_name: str, daily_budget_usd: float, final_url: str,
    headlines: list, long_headline: str, descriptions: list, business_name: str,
    marketing_images_bytes: list, square_images_bytes: list,
    logo_images_bytes: list = None, portrait_images_bytes: list = None,
    location_ids: list = None, language_id: str = "1003", search_themes: list = None,
) -> dict:
    """Crea una campaña de Performance Max de Google Ads completa (presupuesto → campaña →
    segmentación → grupo de recursos con textos e imágenes → señales de tema de búsqueda),
    en estado PAUSADO."""
    client = init_google_ads_client()
    customer_id_clean = str(customer_id).replace("-", "")
    location_ids = location_ids or ["2604"]
    _ts = int(datetime.now().timestamp())

    # 1. Presupuesto
    budget_service = client.get_service("CampaignBudgetService")
    budget_operation = client.get_type("CampaignBudgetOperation")
    budget = budget_operation.create
    budget.name = f"Budget_{campaign_name[:40]}_{_ts}"
    budget.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD
    budget.amount_micros = int(daily_budget_usd * 1_000_000)
    # Performance Max exige un presupuesto exclusivo (no compartido con otras campañas).
    budget.explicitly_shared = False
    budget_response = budget_service.mutate_campaign_budgets(customer_id=customer_id_clean, operations=[budget_operation])
    budget_resource_name = budget_response.results[0].resource_name

    # 2. Campaña de Performance Max
    campaign_service = client.get_service("CampaignService")
    campaign_operation = client.get_type("CampaignOperation")
    campaign = campaign_operation.create
    campaign.name = campaign_name
    campaign.advertising_channel_type = client.enums.AdvertisingChannelTypeEnum.PERFORMANCE_MAX
    campaign.status = client.enums.CampaignStatusEnum.PAUSED
    campaign.campaign_budget = budget_resource_name
    campaign.maximize_conversions = client.get_type("MaximizeConversions")
    campaign.contains_eu_political_advertising = (
        client.enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
    )
    # Nota: la fecha de inicio no se fija por API — la campaña queda en PAUSADO y arranca a correr
    # recién cuando la actives en Google Ads.
    campaign_response = campaign_service.mutate_campaigns(customer_id=customer_id_clean, operations=[campaign_operation])
    campaign_resource_name = campaign_response.results[0].resource_name

    # 3. Segmentación geográfica e idioma
    criterion_service = client.get_service("CampaignCriterionService")
    criterion_ops = []
    for loc_id in location_ids:
        op = client.get_type("CampaignCriterionOperation")
        crit = op.create
        crit.campaign = campaign_resource_name
        crit.location.geo_target_constant = f"geoTargetConstants/{loc_id}"
        criterion_ops.append(op)
    lang_op = client.get_type("CampaignCriterionOperation")
    lang_crit = lang_op.create
    lang_crit.campaign = campaign_resource_name
    lang_crit.language.language_constant = f"languageConstants/{language_id}"
    criterion_ops.append(lang_op)
    criterion_service.mutate_campaign_criteria(customer_id=customer_id_clean, operations=criterion_ops)

    # 4. Grupo de recursos (Asset Group)
    asset_group_service = client.get_service("AssetGroupService")
    ag_operation = client.get_type("AssetGroupOperation")
    ag = ag_operation.create
    ag.name = f"{campaign_name}_AssetGroup"
    ag.campaign = campaign_resource_name
    ag.final_urls.append(final_url)
    ag.status = client.enums.AssetGroupStatusEnum.ENABLED
    ag_response = asset_group_service.mutate_asset_groups(customer_id=customer_id_clean, operations=[ag_operation])
    asset_group_resource_name = ag_response.results[0].resource_name

    # 5. Imágenes como Assets (ajustadas al ratio exacto que exige Google Ads) — se admite más de
    # una por tipo; Google las combina y prueba automáticamente entre sí.
    marketing_image_assets = [
        _gads_upload_image_asset(client, customer_id_clean, _gads_fit_image_to_ratio(b, (1200, 628)), f"{campaign_name}_marketing_{i}_{_ts}")
        for i, b in enumerate(marketing_images_bytes[:20])
    ]
    square_image_assets = [
        _gads_upload_image_asset(client, customer_id_clean, _gads_fit_image_to_ratio(b, (1200, 1200)), f"{campaign_name}_square_{i}_{_ts}")
        for i, b in enumerate(square_images_bytes[:20])
    ]
    logo_image_assets = [
        _gads_upload_image_asset(client, customer_id_clean, _gads_fit_image_to_ratio(b, (1200, 1200)), f"{campaign_name}_logo_{i}_{_ts}")
        for i, b in enumerate((logo_images_bytes or [])[:5])
    ]
    portrait_image_assets = [
        _gads_upload_image_asset(client, customer_id_clean, _gads_fit_image_to_ratio(b, (960, 1200)), f"{campaign_name}_portrait_{i}_{_ts}")
        for i, b in enumerate((portrait_images_bytes or [])[:20])
    ]

    # 6. Textos como Assets (títulos, título largo, descripciones, nombre del negocio)
    headline_assets = [_gads_upload_text_asset(client, customer_id_clean, h, f"{campaign_name}_headline_{i}_{_ts}") for i, h in enumerate(headlines[:15])]
    long_headline_asset = _gads_upload_text_asset(client, customer_id_clean, long_headline, f"{campaign_name}_longheadline_{_ts}")
    description_assets = [_gads_upload_text_asset(client, customer_id_clean, d, f"{campaign_name}_description_{i}_{_ts}") for i, d in enumerate(descriptions[:5])]
    business_name_asset = _gads_upload_text_asset(client, customer_id_clean, business_name, f"{campaign_name}_business_{_ts}")

    # 7. Vincular todos los assets al grupo de recursos
    asset_group_asset_service = client.get_service("AssetGroupAssetService")
    aga_ops = []

    def _link_asset(asset_resource_name, field_type_enum_name):
        op = client.get_type("AssetGroupAssetOperation")
        aga = op.create
        aga.asset_group = asset_group_resource_name
        aga.asset = asset_resource_name
        aga.field_type = getattr(client.enums.AssetFieldTypeEnum, field_type_enum_name)
        aga_ops.append(op)

    for h_asset in headline_assets:
        _link_asset(h_asset, "HEADLINE")
    _link_asset(long_headline_asset, "LONG_HEADLINE")
    for d_asset in description_assets:
        _link_asset(d_asset, "DESCRIPTION")
    _link_asset(business_name_asset, "BUSINESS_NAME")
    for m_asset in marketing_image_assets:
        _link_asset(m_asset, "MARKETING_IMAGE")
    for s_asset in square_image_assets:
        _link_asset(s_asset, "SQUARE_MARKETING_IMAGE")
    for l_asset in logo_image_assets:
        _link_asset(l_asset, "LOGO")
    for p_asset in portrait_image_assets:
        _link_asset(p_asset, "PORTRAIT_MARKETING_IMAGE")
    asset_group_asset_service.mutate_asset_group_assets(customer_id=customer_id_clean, operations=aga_ops)

    # 8. Señales de tema de búsqueda (opcional) — le dicen a Google qué buscan las personas que
    # queremos alcanzar; no reemplazan audiencias, pero son la señal más simple y confiable de Pmax.
    if search_themes:
        signal_service = client.get_service("AssetGroupSignalService")
        signal_ops = []
        for theme in search_themes[:25]:
            op = client.get_type("AssetGroupSignalOperation")
            sig = op.create
            sig.asset_group = asset_group_resource_name
            sig.search_theme.text = theme
            signal_ops.append(op)
        signal_service.mutate_asset_group_signals(customer_id=customer_id_clean, operations=signal_ops)

    return {
        "campaign_resource_name":    campaign_resource_name,
        "asset_group_resource_name": asset_group_resource_name,
    }

def generate_google_display_recommendations(gads_df: pd.DataFrame) -> dict:
    """Genera una recomendación de contenidos para Display basada en el rendimiento real de la campaña
    de marca (branded) de Google Ads — basado en reglas, sin usar una IA de pago."""
    branded_row = None
    if gads_df is not None and not gads_df.empty:
        branded = gads_df[gads_df["Campaña"].str.contains("brand|marca", case=False, na=False)]
        if branded.empty and "Tipo" in gads_df.columns:
            branded = gads_df[gads_df["Tipo"].str.contains("SEARCH", case=False, na=False)].sort_values("CTR", ascending=False)
        if not branded.empty:
            branded_row = branded.iloc[0]

    display_df = pd.DataFrame()
    if gads_df is not None and not gads_df.empty and "Tipo" in gads_df.columns:
        display_df = gads_df[gads_df["Tipo"].str.contains("DISPLAY", case=False, na=False)]

    notes = []
    if branded_row is not None:
        notes.append(
            f"Tu campaña de marca (**{branded_row['Campaña']}**) tiene un CTR de **{branded_row['CTR']:.2f}%** — "
            "úsala como referencia: la gente que ya busca 'Cuy Móvil' conoce la marca, así que en Display "
            "conviene reforzar el mensaje de precio/beneficio para gente que aún no te conoce (frío) o que "
            "visitó tu web pero no completó una compra (remarketing)."
        )
    if not display_df.empty:
        d = display_df.iloc[0]
        notes.append(
            f"Ya tienes una campaña de Display (**{d['Campaña']}**) con CTR {d['CTR']:.2f}%. Si está por debajo "
            "de 0.5% (benchmark típico de Display), prioriza refrescar las imágenes y los títulos antes que subir presupuesto."
        )
    else:
        notes.append("Aún no detecto una campaña de Display activa en esta cuenta — estas piezas te sirven para crear una nueva.")

    audiences = [
        "🔁 Remarketing: visitantes de secure.guinea.pe que llegaron a /cuy/plan o /cuy/personal-data pero no llegaron a /cuy/successful (carrito abandonado del flujo de compra).",
        "🔁 Remarketing: visitantes de cuy.pe y blog.cuy.pe de los últimos 30-60 días.",
        "🎯 Audiencias en el mercado ('In-Market'): 'Planes de telefonía móvil prepago', 'Operadores móviles', 'Smartphones y accesorios'.",
        "🎯 Audiencias afines ('Affinity'): tecnología móvil, compradores conscientes de precio.",
        "👥 Audiencia similar (Similar/Lookalike) a tus clientes actuales o a quienes completaron /cuy/successful.",
    ]

    return {
        "notes": notes,
        "headlines": DISPLAY_HEADLINES_BANK,
        "long_headline": DISPLAY_LONG_HEADLINE,
        "descriptions": DISPLAY_DESCRIPTIONS_BANK,
        "image_specs": DISPLAY_IMAGE_SPECS,
        "ctas": DISPLAY_CTA_OPTIONS,
        "audiences": audiences,
        "branded_row": branded_row,
    }

# ══════════════════════════════════════════════════════════════════════════════
# VENTAS POR CANAL — atribución vía GA4 (conversions), separando Meta Ads FB/IG,
# Google Ads y otras fuentes identificadas
# ══════════════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_ga_sales_by_source(property_id: str, start_date: str, end_date: str, limit: int = 30) -> pd.DataFrame:
    """Trae conversiones (ventas) y sesiones por fuente/medio de sesión (sessionSourceMedium),
    para poder atribuirlas a Meta Ads (FB/IG), Google Ads u otras fuentes."""
    from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Dimension, Metric, OrderBy
    client = init_ga_client()
    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name="sessionSourceMedium")],
        metrics=[Metric(name="conversions"), Metric(name="sessions")],
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="conversions"), desc=True)],
        limit=limit,
    )
    response = client.run_report(request)
    rows = [{
        "Origen":    r.dimension_values[0].value or "(sin asignar)",
        "Ventas":    float(r.metric_values[0].value),
        "Sesiones":  float(r.metric_values[1].value),
    } for r in response.rows]
    return pd.DataFrame(rows)

def _sales_channel_bucket(source_medium: str) -> str:
    """Clasifica un 'fuente / medio' de GA4 en un canal de negocio — separa Meta Ads en Facebook e
    Instagram, identifica Google Ads, y agrupa/etiqueta el resto de fuentes que puede reconocer."""
    s = source_medium.lower()
    is_paid = any(k in s for k in ["cpc", "ppc", "paid", "display", "cpm"])

    if "facebook" in s or s.startswith("fb "):
        return "📘 Meta Ads — Facebook" if is_paid else "📘 Facebook (orgánico)"
    if "instagram" in s or s.startswith("ig "):
        return "📸 Meta Ads — Instagram" if is_paid else "📸 Instagram (orgánico)"
    if "audience network" in s or "messenger" in s:
        return "📣 Meta Ads — Otras (Audience Network/Messenger)"
    if "google" in s:
        if is_paid:
            return "🔍 Google Ads"
        if "organic" in s:
            return "🌱 Google (orgánico/SEO)"
        return "🔍 Google (otro)"
    if "(direct)" in s:
        return "➡️ Directo"
    if "cuy.pe" in s and "blog" not in s:
        return "🐹 cuy.pe (link interno)"
    if "blog.cuy.pe" in s:
        return "📝 blog.cuy.pe (link interno)"
    if "tiktok" in s:
        return "🎵 TikTok" + (" Ads" if is_paid else " (orgánico)")
    if "email" in s or "newsletter" in s:
        return "✉️ Email"
    if "organic" in s:
        return "🌱 Búsqueda orgánica (otro buscador)"
    if "referral" in s:
        origen_ref = source_medium.split("/")[0].strip()
        return f"🔗 Referral: {origen_ref}"
    return f"🌐 Otro: {source_medium}"

def build_sales_by_channel(origin_df: pd.DataFrame) -> pd.DataFrame:
    """Agrupa el detalle de origen (sessionSourceMedium) en canales de negocio con el total de ventas."""
    if origin_df is None or origin_df.empty:
        return pd.DataFrame(columns=["Canal", "Ventas", "Sesiones", "% de ventas"])
    df = origin_df.copy()
    df["Canal"] = df["Origen"].apply(_sales_channel_bucket)
    grouped = df.groupby("Canal", as_index=False)[["Ventas", "Sesiones"]].sum()
    total_ventas = grouped["Ventas"].sum()
    grouped["% de ventas"] = (grouped["Ventas"] / total_ventas * 100) if total_ventas else 0.0
    return grouped.sort_values("Ventas", ascending=False).reset_index(drop=True)

# ══════════════════════════════════════════════════════════════════════════════
# ANÁLISIS UNIFICADO (Resumen) — narrativa automática + preguntas libres
# ══════════════════════════════════════════════════════════════════════════════
def generate_google_ads_conclusions(gads_df) -> str:
    """Genera una conclusión narrativa de Google Ads (basada en reglas, sin costo de API)."""
    if gads_df is None or gads_df.empty:
        return "**Google Ads:** no hay campañas de Cuy Móvil con datos en el período seleccionado."

    total_spend       = gads_df["Gasto"].sum()
    total_impressions = gads_df["Impresiones"].sum()
    total_clicks      = gads_df["Clics"].sum()
    total_conversions = gads_df["Conversiones"].sum()
    avg_ctr           = (total_clicks / total_impressions * 100) if total_impressions else 0
    avg_cpc           = (total_spend / total_clicks) if total_clicks else 0

    lines = [
        f"**Google Ads:** gastaste **${total_spend:,.2f}** en {len(gads_df)} campaña(s) de Cuy Móvil, "
        f"generando {total_clicks:,.0f} clics ({avg_ctr:.2f}% CTR promedio, ${avg_cpc:.3f} CPC promedio) "
        f"y {total_conversions:,.1f} conversiones."
    ]
    if len(gads_df) > 1 and gads_df["CTR"].notna().any():
        best_g  = gads_df.loc[gads_df["CTR"].idxmax()]
        worst_g = gads_df.loc[gads_df["CTR"].idxmin()]
        lines.append(
            f"La campaña de Google Ads con mejor CTR es **{best_g['Campaña']}** ({best_g['CTR']:.2f}%). "
            f"La de menor CTR es **{worst_g['Campaña']}** ({worst_g['CTR']:.2f}%) — vale la pena revisarla."
        )
    if avg_ctr and avg_ctr < 2:
        lines.append("⚠️ El CTR promedio de Google Ads es bajo (<2%) — revisa la relevancia de los anuncios y las palabras clave/segmentación.")
    elif avg_ctr and avg_ctr > 5:
        lines.append("✅ El CTR promedio de Google Ads es alto (>5%), señal de anuncios relevantes para la audiencia.")
    if total_conversions == 0 and total_clicks > 0:
        lines.append("⚠️ Hay clics pero ninguna conversión registrada en Google Ads — revisa el seguimiento de conversiones.")
    return "\n\n".join(lines)

def generate_full_analysis(meta_df, ga_summary, ga_channels, ga_top_pages=None, gads_df=None) -> str:
    """Genera un análisis narrativo combinando Meta Ads y Web Analytics (basado en reglas, sin costo de API)."""
    lines = []

    if meta_df is not None and not meta_df.empty:
        active = meta_df[meta_df["Estado"] == "ACTIVE"]
        if not active.empty:
            total_spend  = active["Gasto"].sum()
            total_clicks = active["Clics"].sum()
            total_impr   = active["Impresiones"].sum()
            avg_ctr      = (total_clicks / total_impr * 100) if total_impr else 0
            best  = active.loc[active["CTR"].idxmax()]
            worst = active.loc[active["CTR"].idxmin()]
            lines.append(
                f"**Meta Ads:** gastaste **${total_spend:,.2f}** en {len(active)} campañas activas, "
                f"generando {total_clicks:,.0f} clics con un CTR promedio de **{avg_ctr:.2f}%**."
            )
            lines.append(
                f"La campaña con mejor rendimiento es **{best['Campaña']}** (CTR {best['CTR']:.2f}%). "
                f"La de menor rendimiento es **{worst['Campaña']}** (CTR {worst['CTR']:.2f}%) — vale la pena revisarla."
            )
            suggestions = get_suggestions(active)
            urgentes = [s for s in suggestions if s.get("urgency") == "ALTA"]
            if urgentes:
                lines.append(f"⚠️ Hay **{len(urgentes)} alerta(s) urgente(s)** — revísalas en la sección Meta Ads.")
            else:
                lines.append("✅ No hay alertas urgentes en tus campañas activas de Meta Ads.")
        else:
            lines.append("**Meta Ads:** no hay campañas activas en el período seleccionado.")
    else:
        lines.append("**Meta Ads:** no se pudo cargar información (verifica el token de acceso en Secrets).")

    if ga_summary:
        lines.append(
            f"**Web Analytics:** tu sitio recibió **{ga_summary['sessions']:,.0f} sesiones** de "
            f"**{ga_summary['users']:,.0f} usuarios**, permaneciendo en promedio **{ga_summary['avg_duration']:.0f} segundos** "
            f"por visita, con tasa de rebote de **{ga_summary['bounce_rate']:.1f}%** y {ga_summary['conversions']:,.0f} conversiones."
        )
        if ga_summary["avg_duration"] < 30:
            lines.append("⚠️ El tiempo promedio en el sitio es bajo (<30s) — revisa si la landing carga rápido y si el contenido responde a lo que promete el anuncio.")
        elif ga_summary["avg_duration"] > 90:
            lines.append("✅ El tiempo promedio en el sitio es alto (>90s), señal de que los visitantes exploran tu contenido.")
        if ga_summary["bounce_rate"] > 60:
            lines.append("⚠️ La tasa de rebote es alta (>60%) — revisa velocidad de carga o relevancia del contenido de aterrizaje.")
        elif ga_summary["bounce_rate"] < 40:
            lines.append("✅ La tasa de rebote es saludable (<40%), señal de que el contenido conecta bien con los visitantes.")

        if ga_channels is not None and not ga_channels.empty:
            top_channel = ga_channels.sort_values("Sesiones", ascending=False).iloc[0]
            lines.append(f"El canal que más tráfico aporta es **{top_channel['Canal']}** con {top_channel['Sesiones']:,.0f} sesiones.")
            total_sesiones = ga_channels["Sesiones"].sum()
            organico = ga_channels[ga_channels["Canal"].str.contains("Organic", case=False, na=False)]["Sesiones"].sum()
            pagado   = ga_channels[ga_channels["Canal"].str.contains("Paid", case=False, na=False)]["Sesiones"].sum()
            directo  = ga_channels[ga_channels["Canal"].str.contains("Direct", case=False, na=False)]["Sesiones"].sum()
            if total_sesiones:
                lines.append(
                    f"Del total de sesiones: **{organico/total_sesiones*100:.0f}% orgánico**, "
                    f"**{pagado/total_sesiones*100:.0f}% pagado (Meta/Google Ads)**, "
                    f"**{directo/total_sesiones*100:.0f}% tráfico directo**. "
                    + ("Dependes mucho de tráfico pagado — conviene invertir en SEO/contenido orgánico para diversificar." if total_sesiones and pagado/total_sesiones > 0.6 else "")
                )

        if ga_top_pages is not None and not ga_top_pages.empty:
            top_page = ga_top_pages.sort_values("Vistas", ascending=False).iloc[0]
            lines.append(f"La página más visitada es **{top_page['Página']}** con {top_page['Vistas']:,.0f} vistas y {top_page['Usuarios']:,.0f} usuarios únicos.")
    else:
        lines.append("**Web Analytics:** no se pudo cargar información (verifica la cuenta de servicio de Google en Secrets).")

    lines.append(generate_google_ads_conclusions(gads_df))

    lines.append("\n_Nota: revisa la sección 'Clarity' para señales de frustración de usuarios._")
    return "\n\n".join(lines)

def answer_question(question: str, meta_df, ga_summary, ga_channels, ga_top_pages=None) -> str:
    """Responde preguntas en lenguaje natural sobre las métricas cargadas (basado en reglas, sin costo de API)."""
    q = question.lower()
    active = meta_df[meta_df["Estado"] == "ACTIVE"] if meta_df is not None and not meta_df.empty else pd.DataFrame()

    # ¿Menciona el nombre de una campaña específica?
    if not active.empty:
        for _, row in active.iterrows():
            nombre = str(row["Campaña"]).lower()
            palabras_clave = [w for w in nombre.split() if len(w) > 4]
            if nombre in q or any(w in q for w in palabras_clave):
                return (f"La campaña **{row['Campaña']}** tiene: Gasto ${row['Gasto']:.2f}, "
                        f"{row['Impresiones']:,.0f} impresiones, {row['Clics']:,.0f} clics, "
                        f"CTR {row['CTR']:.2f}%, CPC ${row['CPC']:.3f}, Frecuencia {row['Frecuencia']:.2f}x.")

    if any(k in q for k in ["ctr", "click through"]):
        if not active.empty and active["Impresiones"].sum():
            avg_ctr = active["Clics"].sum() / active["Impresiones"].sum() * 100
            calif = "excelente" if avg_ctr > 5 else "bueno" if avg_ctr >= 3 else "bajo, por debajo del mínimo recomendado (3%)"
            return f"Tu CTR promedio en campañas activas es **{avg_ctr:.2f}%**, lo cual se considera {calif}."
        return "No tengo datos de Meta Ads cargados para calcular el CTR."

    if any(k in q for k in ["gasto", "presupuesto", "cuanto gaste", "cuánto gasté", "spend"]):
        if not active.empty:
            return f"El gasto total en campañas activas de Meta Ads en el período es **${active['Gasto'].sum():,.2f}**."
        return "No tengo datos de gasto de Meta Ads cargados."

    if any(k in q for k in ["frecuencia"]):
        if not active.empty:
            avg_freq = active["Frecuencia"].mean()
            calif = "alta, con riesgo de saturación" if avg_freq > 4 else "normal"
            return f"La frecuencia promedio de tus campañas activas es **{avg_freq:.2f}x**, considerada {calif}."
        return "No tengo campañas activas cargadas."

    if any(k in q for k in ["mejor campaña", "mejor campana", "top campaign"]):
        if not active.empty:
            best = active.loc[active["CTR"].idxmax()]
            return f"Tu campaña con mejor CTR es **{best['Campaña']}** con {best['CTR']:.2f}%."
        return "No tengo campañas activas cargadas."

    if any(k in q for k in ["peor campaña", "peor campana", "revisar"]):
        if not active.empty:
            worst = active.loc[active["CTR"].idxmin()]
            return f"La campaña con menor CTR es **{worst['Campaña']}** ({worst['CTR']:.2f}%) — podría necesitar revisión."
        return "No tengo campañas activas cargadas."

    if any(k in q for k in ["sesion", "sesión", "sesiones"]):
        if ga_summary:
            return f"Tu sitio tuvo **{ga_summary['sessions']:,.0f} sesiones** en el período seleccionado."
        return "No tengo datos de Google Analytics cargados."

    if any(k in q for k in ["rebote", "bounce"]):
        if ga_summary:
            calif = "alta, conviene revisarla" if ga_summary["bounce_rate"] > 60 else "saludable" if ga_summary["bounce_rate"] < 40 else "normal"
            return f"Tu tasa de rebote es **{ga_summary['bounce_rate']:.1f}%**, lo cual es {calif}."
        return "No tengo datos de Google Analytics cargados."

    if any(k in q for k in ["usuario", "usuarios"]):
        if ga_summary:
            return f"Tu sitio tuvo **{ga_summary['users']:,.0f} usuarios** únicos en el período."
        return "No tengo datos de Google Analytics cargados."

    if any(k in q for k in ["conversion", "conversión", "conversiones"]):
        if ga_summary:
            return f"Se registraron **{ga_summary['conversions']:,.0f} conversiones** en el período."
        return "No tengo datos de Google Analytics cargados."

    if any(k in q for k in ["organico", "orgánico", "pagado", "de donde viene", "de dónde viene", "canal", "channel", "trafico", "tráfico"]):
        if ga_channels is not None and not ga_channels.empty:
            total_sesiones = ga_channels["Sesiones"].sum()
            organico = ga_channels[ga_channels["Canal"].str.contains("Organic", case=False, na=False)]["Sesiones"].sum()
            pagado   = ga_channels[ga_channels["Canal"].str.contains("Paid", case=False, na=False)]["Sesiones"].sum()
            directo  = ga_channels[ga_channels["Canal"].str.contains("Direct", case=False, na=False)]["Sesiones"].sum()
            top3 = ga_channels.sort_values("Sesiones", ascending=False).head(3)
            detalle = "; ".join(f"{r['Canal']}: {r['Sesiones']:,.0f} sesiones" for _, r in top3.iterrows())
            resumen_pct = ""
            if total_sesiones:
                resumen_pct = (f" En términos generales: {organico/total_sesiones*100:.0f}% orgánico, "
                               f"{pagado/total_sesiones*100:.0f}% pagado, {directo/total_sesiones*100:.0f}% directo.")
            return f"Tus principales canales de tráfico son: {detalle}.{resumen_pct}"
        return "No tengo datos de canales de Google Analytics cargados."

    if any(k in q for k in ["pagina", "página", "mas visitada", "más visitada", "url"]):
        if ga_top_pages is not None and not ga_top_pages.empty:
            top_page = ga_top_pages.sort_values("Vistas", ascending=False).iloc[0]
            return (f"Tu página más visitada es **{top_page['Página']}** con {top_page['Vistas']:,.0f} vistas "
                    f"y {top_page['Usuarios']:,.0f} usuarios únicos en el período.")
        return "No tengo datos de páginas de Google Analytics cargados."

    if any(k in q for k in ["tiempo en", "duracion", "duración", "segundos", "cuanto tiempo", "cuánto tiempo"]):
        if ga_summary:
            calif = "bajo — revisa velocidad de carga o relevancia del contenido" if ga_summary["avg_duration"] < 30 else \
                    "alto, buena señal de interés" if ga_summary["avg_duration"] > 90 else "normal"
            return f"Los visitantes pasan en promedio **{ga_summary['avg_duration']:.0f} segundos** en tu sitio, lo cual es {calif}."
        return "No tengo datos de Google Analytics cargados."

    return ("No logré identificar a qué dato te refieres. Intenta preguntar sobre: CTR, gasto, sesiones, "
            "usuarios, rebote, conversiones, canales (orgánico/pagado), página más visitada, tiempo en el sitio, "
            "frecuencia, o el nombre de una campaña específica.")

# ══════════════════════════════════════════════════════════════════════════════
# PARRILLA DE CONTENIDO — recomendación mensual basada en datos reales (sin costo de API)
# ══════════════════════════════════════════════════════════════════════════════
MEDIA_TYPE_ES = {
    "photo": "Imagen estática", "video": "Video", "link": "Enlace/Link",
    "album": "Álbum de fotos", "status": "Texto/Status", "share": "Compartido",
}

AGE_INTEREST_BANDS = [
    ((13, 17),  ["TikTok", "Instagram Reels", "Videojuegos móviles"]),
    ((18, 24),  ["Vida universitaria", "TikTok", "Instagram Reels", "Smartphones"]),
    ((25, 34),  ["Trabajo remoto", "Streaming de video", "Compras en línea", "Instagram"]),
    ((35, 44),  ["Familia", "Planes postpago", "Negocios pequeños", "Educación de hijos"]),
    ((45, 120), ["Noticias", "Salud y bienestar", "Planes postpago"]),
]

CONTENT_PILLARS = [
    {
        "nombre": "Promocional",
        "objetivo": "Ventas / Conversión",
        "concepto": "Planes ilimitados a tu medida",
        "hook": "¿Sabías que puedes tener internet ilimitado desde S/19.90 al mes?",
        "frases": ["Planes desde S/19.90", "Internet ilimitado", "Sin permanencia forzada"],
        "brief": "Pieza estática o carrusel con oferta/precio destacado en grande. Paleta morada (#5543CE) y lima "
                 "(#DCFE6D) de marca, logo Cuy visible, headline corto (máx. 6 palabras).",
    },
    {
        "nombre": "Educativo",
        "objetivo": "Consideración / Educación de producto",
        "concepto": "Aprende a sacarle el máximo provecho a tu plan",
        "hook": "Así activas tu plan Cuy en menos de 2 minutos, sin ir a ninguna tienda.",
        "frases": ["Activación 100% digital", "Internet ilimitado", "Recarga fácil, recarga rápido"],
        "brief": "Carrusel de 3–4 slides explicando un beneficio o cómo usar el servicio. Iconografía simple, "
                 "un mensaje por slide, texto grande legible en mobile.",
    },
    {
        "nombre": "Testimonial / Comunidad",
        "objetivo": "Confianza / Prueba social",
        "concepto": "Historias reales de usuarios Cuy",
        "hook": "Esto es lo que dicen nuestros clientes sobre cambiarse a Cuy Móvil.",
        "frases": ["La red que se adapta a ti", "Miles ya se cambiaron", "Internet ilimitado"],
        "brief": "Formato Reel corto (15–30s) con persona real o estilo UGC. Subtítulos quemados en el video, "
                 "tono cercano y auténtico, sin verse como anuncio tradicional.",
    },
    {
        "nombre": "Entretenimiento / Tendencia",
        "objetivo": "Alcance / Reconocimiento de marca",
        "concepto": "Cuy se sube a la tendencia",
        "hook": "El plan que todos están recargando esta semana.",
        "frases": ["Datos que no se acaban", "Conéctate sin límites", "Planes desde S/19.90"],
        "brief": "Reel con audio o formato de tendencia del momento, edición dinámica, texto en pantalla, "
                 "gancho visual en los primeros 3 segundos.",
    },
]

# Banco de conceptos/ganchos/frases para las campañas de Ads, según objetivo de marketing
AD_CONTENT_BY_OBJECTIVE = {
    "Ventas / Conversiones": {
        "concepto": "Cambia hoy, paga menos",
        "hook": "¿Pagando de más por menos datos? Cámbiate a Cuy Móvil hoy.",
        "frases": ["Planes desde S/19.90", "Internet ilimitado", "Cambio de operador sin costo"],
    },
    "Tráfico al sitio web": {
        "concepto": "Descubre tu plan ideal",
        "hook": "Encuentra en 1 minuto el plan Cuy que se adapta a ti.",
        "frases": ["Elige tu plan online", "Internet ilimitado", "Activación 100% digital"],
    },
    "Interacción / Engagement": {
        "concepto": "Cuéntanos qué necesitas",
        "hook": "¿Qué es lo que más usas de tu celular? Te leemos en los comentarios.",
        "frases": ["Datos que no se acaban", "La red que te escucha"],
    },
    "Captación de leads": {
        "concepto": "Te llamamos con tu plan ideal",
        "hook": "Déjanos tus datos y te armamos el plan perfecto para ti.",
        "frases": ["Planes desde S/19.90", "Asesoría gratuita", "Internet ilimitado"],
    },
    "Reconocimiento de marca": {
        "concepto": "Conoce a Cuy Móvil",
        "hook": "La telefonía móvil que sí te conviene.",
        "frases": ["Internet ilimitado", "Sin letra chica", "Planes desde S/19.90"],
    },
}
DEFAULT_AD_CONTENT = {
    "concepto": "Planes ilimitados a tu medida",
    "hook": "¿Sabías que puedes tener internet ilimitado desde S/19.90 al mes?",
    "frases": ["Planes desde S/19.90", "Internet ilimitado"],
}

DIAS_ES_ORDER = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_age_gender_breakdown(account_id: str, date_preset: str, since: str = "", until: str = "") -> pd.DataFrame:
    """Desglose de rendimiento por edad y género a nivel de cuenta — para saber qué audiencia interactúa mejor."""
    init_api()
    account = AdAccount(account_id)
    if date_preset == "custom" and since and until:
        params = {"time_range": {"since": since, "until": until}, "level": "account", "breakdowns": ["age", "gender"]}
    else:
        params = {"date_preset": date_preset, "level": "account", "breakdowns": ["age", "gender"]}
    try:
        insights = account.get_insights(fields=INSIGHT_FIELDS, params=params)
    except Exception:
        return pd.DataFrame()

    gender_es = {"male": "Hombres", "female": "Mujeres", "unknown": "Sin especificar"}
    rows = []
    for r in insights:
        imp = int(r.get("impressions", 0) or 0)
        if imp == 0:
            continue
        cl = int(r.get("clicks", 0) or 0)
        sp = float(r.get("spend", 0) or 0)
        rows.append({
            "Edad":   r.get("age", "unknown"),
            "Género": gender_es.get(r.get("gender", ""), r.get("gender", "")),
            "Gasto": sp, "Impresiones": imp, "Clics": cl,
            "CTR": (cl / imp * 100) if imp else 0,
        })
    return pd.DataFrame(rows)

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_organic_posts(page_id: str, access_token: str, limit: int = 25) -> pd.DataFrame:
    """Publicaciones orgánicas recientes de la página con su interacción (likes, comentarios, compartidos)."""
    if not page_id or not access_token:
        return pd.DataFrame()
    url = f"https://graph.facebook.com/v21.0/{page_id}/posts"
    params = {
        "fields": ("message,created_time,permalink_url,attachments{media_type},shares,"
                   "likes.summary(true).limit(0),comments.summary(true).limit(0)"),
        "limit": limit,
        "access_token": access_token,
    }
    try:
        resp = requests.get(url, params=params, timeout=20)
        data = resp.json().get("data", [])
    except Exception:
        return pd.DataFrame()

    rows = []
    for post in data:
        likes    = post.get("likes", {}).get("summary", {}).get("total_count", 0) or 0
        comments = post.get("comments", {}).get("summary", {}).get("total_count", 0) or 0
        shares   = post.get("shares", {}).get("count", 0) or 0
        att = post.get("attachments", {}).get("data", [])
        media_type = att[0].get("media_type", "status") if att else "status"
        created = post.get("created_time", "")
        dt = None
        try:
            dt = datetime.strptime(created, "%Y-%m-%dT%H:%M:%S%z").astimezone(PERU_TZ)
        except Exception:
            pass
        score = likes + comments * 2 + shares * 3
        rows.append({
            "Mensaje": (post.get("message") or "(sin texto)")[:160],
            "Tipo": MEDIA_TYPE_ES.get(media_type, media_type),
            "Fecha": dt,
            "Likes": likes, "Comentarios": comments, "Compartidos": shares,
            "Interacción": score,
            "Permalink": post.get("permalink_url", ""),
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        dias_map = dict(zip(
            ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
            DIAS_ES_ORDER,
        ))
        df["Día"]  = df["Fecha"].apply(lambda d: dias_map.get(d.strftime("%A"), "") if d is not None else "")
        df["Hora"] = df["Fecha"].apply(lambda d: d.hour if d is not None else None)
    return df

def _interests_for_age_label(age_label: str) -> list:
    try:
        if "+" in age_label:
            lo, hi = int(age_label.replace("+", "")), 120
        else:
            lo, hi = [int(x) for x in age_label.split("-")]
        mid = (lo + hi) / 2
    except Exception:
        return ["Smartphones", "Telefonía móvil de prepago"]
    for (band_lo, band_hi), interests in AGE_INTEREST_BANDS:
        if band_lo <= mid <= band_hi:
            return interests
    return ["Smartphones", "Telefonía móvil de prepago"]

def generate_meta_campaign_recos(meta_df_wide: pd.DataFrame, age_gender_df: pd.DataFrame,
                                  max_campaigns: int = 4, max_daily_budget: float = 4.0) -> list:
    """Recomienda hasta `max_campaigns` campañas Meta Ads con audiencia y presupuesto sugeridos, según rendimiento real."""
    objective_rank = []
    if meta_df_wide is not None and not meta_df_wide.empty and "Objetivo" in meta_df_wide.columns:
        obj_group = meta_df_wide.groupby("Objetivo").agg(
            Impresiones=("Impresiones_Total", "sum"), Clics=("Clics_Total", "sum")
        )
        obj_group = obj_group[obj_group["Impresiones"] > 0]
        obj_group["CTR"] = obj_group["Clics"] / obj_group["Impresiones"] * 100
        objective_rank = obj_group.sort_values("CTR", ascending=False).index.tolist()

    obj_code_to_label = {v: k for k, v in OBJECTIVES.items()}
    ranked_labels = [obj_code_to_label.get(o, o) for o in objective_rank]
    fallback_order = ["Ventas / Conversiones", "Tráfico al sitio web", "Interacción / Engagement", "Captación de leads"]
    objectives_final = []
    for lbl in ranked_labels + fallback_order:
        if lbl not in objectives_final:
            objectives_final.append(lbl)
    objectives_final = objectives_final[:max_campaigns]

    segments = []
    if age_gender_df is not None and not age_gender_df.empty:
        seg_df = age_gender_df[age_gender_df["Impresiones"] >= 200].copy()
        if seg_df.empty:
            seg_df = age_gender_df.copy()
        seg_df = seg_df.sort_values("CTR", ascending=False)
        for _, row in seg_df.iterrows():
            segments.append({"Edad": row["Edad"], "Género": row["Género"], "CTR": row["CTR"], "Gasto": row["Gasto"]})

    default_segments = [
        {"Edad": "18-24", "Género": "Todos", "CTR": None, "Gasto": None},
        {"Edad": "25-34", "Género": "Todos", "CTR": None, "Gasto": None},
        {"Edad": "35-44", "Género": "Todos", "CTR": None, "Gasto": None},
        {"Edad": "45-54", "Género": "Todos", "CTR": None, "Gasto": None},
    ]
    while len(segments) < max_campaigns:
        segments.append(default_segments[len(segments) % len(default_segments)])
    segments = segments[:max_campaigns]

    budget_tiers = [max_daily_budget, round(max_daily_budget * 0.75, 2),
                    round(max_daily_budget * 0.6, 2), round(max_daily_budget * 0.5, 2)][:max_campaigns]

    recos = []
    for i in range(max_campaigns):
        seg = segments[i]
        obj_label = objectives_final[i] if i < len(objectives_final) else fallback_order[i % len(fallback_order)]
        interests = _interests_for_age_label(str(seg["Edad"]))
        if seg["CTR"] is not None:
            rationale = (f"Este segmento ({seg['Edad']} años, {seg['Género']}) tuvo un CTR real de "
                         f"{seg['CTR']:.2f}% en tus campañas — de los que mejor responden a tus anuncios.")
        else:
            rationale = ("No hay suficiente historial de este segmento en tus campañas; se sugiere como "
                         "banda base de telco para probar y generar datos.")
        if i == 0 and objective_rank:
            rationale += f" El objetivo '{obj_label}' es el que históricamente mejor CTR ha tenido en tu cuenta."
        ad_content = AD_CONTENT_BY_OBJECTIVE.get(obj_label, DEFAULT_AD_CONTENT)
        recos.append({
            "Tipo": "📣 Ads",
            "Campaña": f"Campaña {i+1} · {obj_label}",
            "Concepto": ad_content["concepto"],
            "Objetivo": obj_label,
            "Edad": seg["Edad"], "Género": seg["Género"],
            "Intereses sugeridos": ", ".join(interests),
            "Hook": ad_content["hook"],
            "Frases indispensables": ", ".join(ad_content["frases"]),
            "Presupuesto diario": budget_tiers[i],
            "Justificación": rationale,
        })
    return recos

def generate_organic_calendar(organic_df: pd.DataFrame, weeks: int = 4, posts_per_week: int = 3) -> tuple:
    """Parrilla mensual de contenido orgánico con brief de diseño, según qué formato/día funciona mejor."""
    best_format = None
    best_days = []
    top_posts = pd.DataFrame()

    if organic_df is not None and not organic_df.empty:
        fmt_perf = organic_df.groupby("Tipo")["Interacción"].mean().sort_values(ascending=False)
        if not fmt_perf.empty:
            best_format = fmt_perf.index[0]
        day_df = organic_df[organic_df["Día"] != ""] if "Día" in organic_df.columns else pd.DataFrame()
        if not day_df.empty:
            day_perf = day_df.groupby("Día")["Interacción"].mean().sort_values(ascending=False)
            best_days = [d for d in day_perf.index if d in DIAS_ES_ORDER][:3]
        top_posts = organic_df.sort_values("Interacción", ascending=False).head(3)[
            ["Mensaje", "Tipo", "Interacción", "Permalink"]
        ]
        note = (f"Basado en tus últimas {len(organic_df)} publicaciones: el formato con mejor interacción promedio es "
                f"**{best_format}**" + (f", y los días con mejor respuesta son **{', '.join(best_days)}**." if best_days else "."))
    else:
        note = "No se pudo cargar el historial orgánico (verifica PAGE_ID/permisos) — se usa una parrilla estándar de buenas prácticas."

    if not best_days:
        best_days = ["Martes", "Jueves", "Sábado"]
    while len(best_days) < posts_per_week:
        for d in DIAS_ES_ORDER:
            if d not in best_days:
                best_days.append(d)
            if len(best_days) >= posts_per_week:
                break
    best_days = best_days[:posts_per_week]

    rows = []
    for week in range(1, weeks + 1):
        for i, day in enumerate(best_days):
            pillar = CONTENT_PILLARS[(week - 1 + i) % len(CONTENT_PILLARS)]
            if best_format and i == 0:
                fmt_sugerido = best_format
            elif pillar["nombre"] in ("Testimonial / Comunidad", "Entretenimiento / Tendencia"):
                fmt_sugerido = "Video / Reel"
            else:
                fmt_sugerido = "Imagen estática / Carrusel"
            rows.append({
                "Semana": week,
                "Tipo": "🌱 Orgánico",
                "Día sugerido": day,
                "Concepto": pillar["concepto"],
                "Objetivo": pillar["objetivo"],
                "Pilar de contenido": pillar["nombre"],
                "Formato": fmt_sugerido,
                "Hook": pillar["hook"],
                "Frases indispensables": ", ".join(pillar["frases"]),
                "Brief para diseño": pillar["brief"],
                "CTA sugerido": "Más información" if pillar["nombre"] == "Promocional" else
                                "Conoce más" if pillar["nombre"] == "Educativo" else "Síguenos / Comenta",
            })
    calendar_df = pd.DataFrame(rows)
    return calendar_df, note, top_posts

def generate_unified_grid(calendar_df: pd.DataFrame, ads_recos: list, weeks: int = 4) -> pd.DataFrame:
    """Combina la parrilla orgánica y las campañas de Ads recomendadas en una sola parrilla de contenidos del mes."""
    ad_rows = []
    for week in range(1, weeks + 1):
        if not ads_recos:
            break
        reco = ads_recos[(week - 1) % len(ads_recos)]
        ad_rows.append({
            "Semana": week,
            "Tipo": "📣 Ads",
            "Día sugerido": "Activa toda la semana (mantener presupuesto sugerido)",
            "Concepto": reco["Concepto"],
            "Objetivo": reco["Objetivo"],
            "Pilar de contenido": f"Audiencia: {reco['Edad']} años · {reco['Género']}",
            "Formato": "Imagen o video para Feed/Stories/Reels",
            "Hook": reco["Hook"],
            "Frases indispensables": reco["Frases indispensables"],
            "Brief para diseño": (
                f"Presupuesto diario sugerido: ${reco['Presupuesto diario']:.2f}. Intereses de segmentación: "
                f"{reco['Intereses sugeridos']}. Usar la misma identidad de marca (morado #5543CE / lima #DCFE6D)."
            ),
            "CTA sugerido": "Más información" if "Ventas" in reco["Objetivo"] or "Tráfico" in reco["Objetivo"]
                            else "Contáctanos" if "leads" in reco["Objetivo"] else "Ver más",
        })
    ads_df = pd.DataFrame(ad_rows)
    combined = pd.concat([ads_df, calendar_df], ignore_index=True) if not ads_df.empty else calendar_df.copy()
    combined = combined.sort_values(["Semana", "Tipo"], ascending=[True, False]).reset_index(drop=True)
    cols = ["Semana", "Tipo", "Día sugerido", "Concepto", "Objetivo", "Pilar de contenido",
            "Formato", "Hook", "Frases indispensables", "Brief para diseño", "CTA sugerido"]
    cols = [c for c in cols if c in combined.columns]
    return combined[cols]

# ══════════════════════════════════════════════════════════════════════════════
# LOGIN Y CONTROL DE ACCESO
# ══════════════════════════════════════════════════════════════════════════════
def check_login() -> bool:
    if st.session_state.get("auth_ok"):
        return True

    st.title("🐹 Cuy Móvil · Meta Ads Dashboard")
    st.subheader("🔒 Iniciar sesión")

    if not USERS:
        st.error(
            "No hay usuarios configurados todavía. Agrega la tabla `USERS` en "
            "Streamlit Cloud → Settings → Secrets para habilitar el acceso."
        )
        return False

    with st.form("login_form"):
        email = st.text_input("Correo")
        password = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Ingresar", type="primary")

    if submitted:
        user = USERS.get(email.strip().lower())
        if user and password == user.get("password"):
            st.session_state["auth_ok"] = True
            st.session_state["auth_email"] = email.strip()
            st.session_state["auth_role"] = user.get("role", "viewer")
            st.rerun()
        else:
            st.error("Correo o contraseña incorrectos.")
    return False

if not check_login():
    st.stop()

ROLE = st.session_state.get("auth_role", "viewer")
IS_ADMIN = ROLE == "admin"

# ══════════════════════════════════════════════════════════════════════════════
# UI
# ══════════════════════════════════════════════════════════════════════════════
col_title, col_time = st.columns([4, 1])
with col_title:
    st.title("🐹 Cuy Móvil · Meta Ads Dashboard")
with col_time:
    st.caption(f"📅 {datetime.now(PERU_TZ).strftime('%d %b %Y, %H:%M')} (hora Perú)")

with st.sidebar:
    st.header("🗂️ Accesos")
    _role_label = "🛠️ Administrador" if IS_ADMIN else "👁️ Solo lectura"
    st.caption(f"Sesión: **{st.session_state.get('auth_email', '')}** · {_role_label}")
    if st.button("Cerrar sesión", key="btn_logout", use_container_width=True):
        for _k in ("auth_ok", "auth_email", "auth_role"):
            st.session_state.pop(_k, None)
        st.rerun()
    st.divider()
    nav_section = st.radio(
        "Selecciona una plataforma",
        ["📋 Resumen", "📊 Meta Ads", "🔍 Google Ads", "📈 Web Analytics", "🖱️ Clarity"],
        label_visibility="collapsed",
    )
    st.divider()

    if nav_section == "📋 Resumen":
        st.subheader("Filtros — Resumen")
        resumen_account_label = st.selectbox("Cuenta (Meta Ads)", list(ACCOUNTS.keys()), key="resumen_account_label")
        resumen_account_id    = ACCOUNTS[resumen_account_label]
        resumen_date_label    = st.selectbox("Período", list(DATE_OPTIONS.keys()), index=2, key="resumen_date_label")
        resumen_date_preset   = DATE_OPTIONS[resumen_date_label]

        resumen_since_str, resumen_until_str = "", ""
        if resumen_date_preset == "custom":
            hoy_peru_r = datetime.now(PERU_TZ).date()
            resumen_custom_range = st.date_input(
                "Rango de fechas",
                value=(hoy_peru_r.replace(day=1), hoy_peru_r),
                max_value=hoy_peru_r,
                key="resumen_custom_range",
            )
            if isinstance(resumen_custom_range, tuple) and len(resumen_custom_range) == 2:
                resumen_since_str = resumen_custom_range[0].strftime("%Y-%m-%d")
                resumen_until_str = resumen_custom_range[1].strftime("%Y-%m-%d")
            else:
                st.warning("Selecciona una fecha de inicio y una de fin.")

        if st.button("🔄 Actualizar datos", use_container_width=True, key="refresh_resumen"):
            st.cache_data.clear()
            st.rerun()
        st.caption("Combina Meta Ads + Web Analytics. Revisa la sección 'Clarity' para señales de frustración. Google Ads aún no está conectado.")

    elif nav_section == "📊 Meta Ads":
        st.subheader("Filtros — Meta Ads")
        account_label = st.selectbox("Cuenta", list(ACCOUNTS.keys()))
        account_id    = ACCOUNTS[account_label]
        date_label    = st.selectbox("Período", list(DATE_OPTIONS.keys()), index=2)
        date_preset   = DATE_OPTIONS[date_label]

        since_str, until_str = "", ""
        if date_preset == "custom":
            hoy_peru = datetime.now(PERU_TZ).date()
            custom_range = st.date_input(
                "Rango de fechas",
                value=(hoy_peru.replace(day=1), hoy_peru),
                max_value=hoy_peru,
            )
            if isinstance(custom_range, tuple) and len(custom_range) == 2:
                since_str = custom_range[0].strftime("%Y-%m-%d")
                until_str = custom_range[1].strftime("%Y-%m-%d")
            else:
                st.warning("Selecciona una fecha de inicio y una de fin.")

        platform_filter = st.selectbox("Plataforma (consumo)", ["Todas (FB+IG)", "Solo Facebook", "Solo Instagram"])
        show_paused   = st.toggle("Incluir campañas pausadas", value=False)
        if st.button("🔄 Actualizar datos", use_container_width=True, key="refresh_meta"):
            st.cache_data.clear()
            st.rerun()
        st.caption("Los cambios ejecutados son inmediatos y reales.")

    elif nav_section == "🔍 Google Ads":
        st.subheader("Filtros — Google Ads")
        gads_date_label  = st.selectbox("Período", list(DATE_OPTIONS.keys()), index=2, key="gads_date_label")
        gads_date_preset = DATE_OPTIONS[gads_date_label]

        gads_since_str, gads_until_str = "", ""
        if gads_date_preset == "custom":
            hoy_peru_gads = datetime.now(PERU_TZ).date()
            gads_custom_range = st.date_input(
                "Rango de fechas",
                value=(hoy_peru_gads.replace(day=1), hoy_peru_gads),
                max_value=hoy_peru_gads,
                key="gads_custom_range",
            )
            if isinstance(gads_custom_range, tuple) and len(gads_custom_range) == 2:
                gads_since_str = gads_custom_range[0].strftime("%Y-%m-%d")
                gads_until_str = gads_custom_range[1].strftime("%Y-%m-%d")
            else:
                st.warning("Selecciona una fecha de inicio y una de fin.")

        gads_name_filter = st.text_input(
            "Filtrar por nombre de campaña",
            value="Cuy",
            key="gads_name_filter",
            placeholder="ej. Cuy",
            help="Muestra solo campañas cuyo nombre contenga este texto (la cuenta de Google Ads incluye varias marcas de Guinea Mobile). Déjalo vacío para ver todas.",
        )
        st.caption(f"Cuenta: `{GOOGLE_ADS_CUSTOMER_ID}`")
        if st.button("🔄 Actualizar datos", use_container_width=True, key="refresh_gads"):
            st.cache_data.clear()
            st.rerun()

    elif nav_section == "📈 Web Analytics":
        st.subheader("Filtros — Web Analytics")
        ga_host_label  = st.selectbox("Dominio", list(HOST_OPTIONS.keys()), key="ga_host_label")
        ga_host_filter = HOST_OPTIONS[ga_host_label]
        ga_date_label  = st.selectbox("Período", list(DATE_OPTIONS.keys()), index=2, key="ga_date_label")
        ga_date_preset = DATE_OPTIONS[ga_date_label]

        ga_since_str, ga_until_str = "", ""
        if ga_date_preset == "custom":
            hoy_peru_ga = datetime.now(PERU_TZ).date()
            ga_custom_range = st.date_input(
                "Rango de fechas",
                value=(hoy_peru_ga.replace(day=1), hoy_peru_ga),
                max_value=hoy_peru_ga,
                key="ga_custom_range",
            )
            if isinstance(ga_custom_range, tuple) and len(ga_custom_range) == 2:
                ga_since_str = ga_custom_range[0].strftime("%Y-%m-%d")
                ga_until_str = ga_custom_range[1].strftime("%Y-%m-%d")
            else:
                st.warning("Selecciona una fecha de inicio y una de fin.")

        st.caption(f"Propiedad GA4: `{GA_PROPERTY_ID}`")
        if st.button("🔄 Actualizar datos", use_container_width=True, key="refresh_ga"):
            st.cache_data.clear()
            st.rerun()

    else:
        st.subheader("Filtros — Clarity")
        clarity_days_label = st.selectbox("Días hacia atrás", ["Último día (1)", "Últimos 2 días", "Últimos 3 días"], index=2, key="clarity_days_label")
        clarity_num_days = {"Último día (1)": 1, "Últimos 2 días": 2, "Últimos 3 días": 3}[clarity_days_label]
        clarity_dim1_label = st.selectbox("Desglosar por", list(CLARITY_DIMENSIONS.keys()), index=list(CLARITY_DIMENSIONS.keys()).index("Dispositivo"), key="clarity_dim1_label")
        clarity_dimension1 = CLARITY_DIMENSIONS[clarity_dim1_label]
        clarity_dim2_label = st.selectbox("Y también por", list(CLARITY_DIMENSIONS.keys()), index=list(CLARITY_DIMENSIONS.keys()).index("URL"), key="clarity_dim2_label")
        clarity_dimension2 = CLARITY_DIMENSIONS[clarity_dim2_label]
        st.caption("⚠️ La API de Clarity permite solo **10 llamadas al día** por proyecto. Los datos se cachean 4 horas — evita presionar 'Actualizar' repetidamente.")
        if st.button("🔄 Actualizar datos de Clarity", use_container_width=True, key="refresh_clarity"):
            fetch_clarity_insights.clear()
            st.rerun()

if nav_section == "📋 Resumen":
    st.header("📋 Resumen General")
    st.caption("Vista unificada de todas las plataformas conectadas a este dashboard.")

    meta_df_r     = None
    ga_summary_r  = None
    ga_channels_r = None
    ga_top_pages_r = None
    gads_df_r     = None

    if ACCESS_TOKEN:
        try:
            with st.spinner("Cargando datos de Meta Ads..."):
                meta_df_r = fetch_campaigns(resumen_account_id, resumen_date_preset, resumen_since_str, resumen_until_str)
                if meta_df_r is not None and not meta_df_r.empty:
                    meta_df_r = apply_platform_filter(meta_df_r, "Todas (FB+IG)")
        except Exception as e:
            st.warning(f"No se pudo cargar Meta Ads: {e}")
    else:
        st.info("Meta Ads no está conectado (falta ACCESS_TOKEN en Secrets).")

    if "gcp_service_account" in st.secrets:
        try:
            r_start, r_end = get_ga_date_range(resumen_date_preset, resumen_since_str, resumen_until_str)
            with st.spinner("Cargando datos de Google Analytics..."):
                ga_summary_r   = fetch_ga_summary(GA_PROPERTY_ID, r_start, r_end)
                ga_channels_r  = fetch_ga_channels(GA_PROPERTY_ID, r_start, r_end)
                ga_top_pages_r = fetch_ga_top_pages(GA_PROPERTY_ID, r_start, r_end, limit=5)
        except Exception as e:
            st.warning(f"No se pudo cargar Google Analytics: {e}")
    else:
        st.info("Google Analytics no está conectado (falta la cuenta de servicio en Secrets).")

    if GOOGLE_ADS_READY:
        try:
            gads_start_r, gads_end_r = get_ga_date_range(resumen_date_preset, resumen_since_str, resumen_until_str)
            with st.spinner("Cargando datos de Google Ads..."):
                gads_df_r = fetch_google_ads_campaigns(GOOGLE_ADS_CUSTOMER_ID, gads_start_r, gads_end_r)
                if gads_df_r is not None and not gads_df_r.empty:
                    gads_df_r = gads_df_r[gads_df_r["Campaña"].str.contains("Cuy", case=False, na=False)]
        except Exception as e:
            st.warning(f"No se pudo cargar Google Ads: {e}")
    else:
        st.info("Google Ads no está conectado (falta configurar credenciales en Secrets).")

    st.divider()

    # KPIs combinados de todas las plataformas
    st.subheader("Métricas combinadas")
    active_meta_r = meta_df_r[meta_df_r["Estado"] == "ACTIVE"] if meta_df_r is not None and not meta_df_r.empty else pd.DataFrame()
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("💰 Gasto Meta Ads", f"${active_meta_r['Gasto'].sum():,.2f}" if not active_meta_r.empty else "—")
    if not active_meta_r.empty and active_meta_r["Impresiones"].sum():
        ctr_r = active_meta_r["Clics"].sum() / active_meta_r["Impresiones"].sum() * 100
        k2.metric("📊 CTR Meta Ads", f"{ctr_r:.2f}%")
    else:
        k2.metric("📊 CTR Meta Ads", "—")
    k3.metric("👥 Sesiones Web", f"{ga_summary_r['sessions']:,.0f}" if ga_summary_r else "—")
    k4.metric("🎯 Conversiones Web", f"{ga_summary_r['conversions']:,.0f}" if ga_summary_r else "—")
    k5.metric("⏱️ Tiempo en sitio", f"{ga_summary_r['avg_duration']:.0f} s" if ga_summary_r else "—")
    k6.metric("↩️ Tasa de rebote", f"{ga_summary_r['bounce_rate']:.1f}%" if ga_summary_r else "—")

    st.divider()

    # Comportamiento en la web: de dónde vienen y qué visitan
    st.subheader("🌐 Comportamiento en la web")
    wc1, wc2 = st.columns(2)
    with wc1:
        st.markdown("**¿De dónde viene el tráfico?**")
        if ga_channels_r is not None and not ga_channels_r.empty:
            channels_r_sorted = ga_channels_r.sort_values("Sesiones")
            total_sesiones_r = ga_channels_r["Sesiones"].sum()
            max_sesiones_r = channels_r_sorted["Sesiones"].max()
            fig = px.bar(
                channels_r_sorted, x="Sesiones", y="Canal", orientation="h",
                color="Conversiones", color_continuous_scale=PURPLE_SCALE, text="Sesiones",
            )
            fig.update_traces(texttemplate="%{text:.0f}", textposition="outside", cliponaxis=False)
            fig.update_layout(
                height=320, margin=dict(l=0, r=60, t=0, b=0), yaxis_title="",
                xaxis=dict(range=[0, max_sesiones_r * 1.18]), coloraxis_showscale=False,
            )
            st.plotly_chart(fig, use_container_width=True)
            organico = ga_channels_r[ga_channels_r["Canal"].str.contains("Organic", case=False, na=False)]["Sesiones"].sum()
            pagado = ga_channels_r[ga_channels_r["Canal"].str.contains("Paid", case=False, na=False)]["Sesiones"].sum()
            if total_sesiones_r:
                st.caption(f"Orgánico: {organico/total_sesiones_r*100:.0f}% · Pagado: {pagado/total_sesiones_r*100:.0f}% del total de sesiones.")
        else:
            st.info("Sin datos de canales para este período.")
    with wc2:
        st.markdown("**Páginas más visitadas**")
        if ga_top_pages_r is not None and not ga_top_pages_r.empty:
            st.dataframe(
                ga_top_pages_r.style.format({"Vistas": "{:,.0f}", "Usuarios": "{:,.0f}"}),
                use_container_width=True, hide_index=True, height=320,
            )
        else:
            st.info("Sin datos de páginas para este período.")

    st.divider()

    # Ventas por canal — atribución vía GA4 (conversions), separando Meta Ads FB/IG, Google Ads y otras fuentes
    st.subheader("💰 Ventas por canal")
    st.caption(
        "Ventas (conversiones registradas en GA4) atribuidas por fuente de la sesión — separa Meta Ads en "
        "Facebook e Instagram, Google Ads, y otras fuentes que el sistema identifica automáticamente."
    )
    if "gcp_service_account" in st.secrets:
        try:
            with st.spinner("Calculando ventas por canal..."):
                sales_origin_r = fetch_ga_sales_by_source(GA_PROPERTY_ID, r_start, r_end)
                sales_by_channel_r = build_sales_by_channel(sales_origin_r)
        except Exception as e:
            sales_by_channel_r = pd.DataFrame()
            st.warning(f"No se pudo calcular ventas por canal: {e}")

        if sales_by_channel_r is not None and not sales_by_channel_r.empty and sales_by_channel_r["Ventas"].sum() > 0:
            sc1, sc2 = st.columns([3, 2])
            with sc1:
                chart_sales = sales_by_channel_r[sales_by_channel_r["Ventas"] > 0].sort_values("Ventas")
                max_ventas = chart_sales["Ventas"].max()
                fig = px.bar(
                    chart_sales, x="Ventas", y="Canal", orientation="h",
                    color="Canal", color_discrete_sequence=PURPLE_SCALE + LEMON_SCALE,
                    text="Ventas",
                )
                fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside", cliponaxis=False)
                fig.update_layout(
                    height=max(320, 34 * len(chart_sales)), margin=dict(l=0, r=60, t=0, b=0),
                    yaxis_title="", xaxis=dict(range=[0, max_ventas * 1.2]), showlegend=False,
                )
                st.plotly_chart(fig, use_container_width=True)
            with sc2:
                st.dataframe(
                    sales_by_channel_r[["Canal", "Ventas", "% de ventas"]]
                        .style.format({"Ventas": "{:,.0f}", "% de ventas": "{:.1f}%"}),
                    use_container_width=True, hide_index=True, height=max(320, 34 * len(sales_by_channel_r)),
                )
            top_canal = sales_by_channel_r.iloc[0]
            st.caption(f"El canal que más ventas genera es **{top_canal['Canal']}** con {top_canal['Ventas']:,.0f} ventas ({top_canal['% de ventas']:.1f}% del total).")
        else:
            st.info("No hay conversiones registradas en GA4 para este período — verifica que tengas un evento clave (key event) configurado, como completar la compra en /cuy/successful.")
    else:
        st.info("Google Analytics no está conectado (falta la cuenta de servicio en Secrets).")

    st.divider()

    # Desglose por dominio — cuy.pe vs secure.guinea.pe
    st.subheader("📱 Desglose por dominio")
    if "gcp_service_account" in st.secrets:
        try:
            with st.spinner("Separando métricas por dominio..."):
                ga_by_domain_r = fetch_ga_by_domain(GA_PROPERTY_ID, r_start, r_end, top_limit=5)
        except Exception as e:
            ga_by_domain_r = None
            st.warning(f"No se pudo separar por dominio: {e}")

        if ga_by_domain_r:
            dr1, dr2 = st.columns(2)
            for col, host, label in zip([dr1, dr2], ["cuy.pe", "secure.guinea.pe"], ["🐹 cuy.pe", "🔒 secure.guinea.pe"]):
                with col:
                    st.markdown(f"**{label}**")
                    s = ga_by_domain_r[host]["summary"]
                    tp = ga_by_domain_r[host]["top_pages"]
                    if s and s["sessions"]:
                        m1, m2, m3 = st.columns(3)
                        m1.metric("👥 Sesiones", f"{s['sessions']:,.0f}")
                        m2.metric("⏱️ Tiempo", f"{s['avg_duration']:.0f}s")
                        m3.metric("↩️ Rebote", f"{s['bounce_rate']:.1f}%")
                        if host == "secure.guinea.pe":
                            st.caption("🔻 Funnel de compra (pirámide invertida)")
                        render_domain_top_pages(tp, is_funnel=ga_by_domain_r[host].get("is_funnel", False), height=180)
                    else:
                        st.info(f"Sin datos para **{host}** en este período.")

            if ga_by_domain_r["secure.guinea.pe"].get("summary") and ga_by_domain_r["secure.guinea.pe"]["summary"]["sessions"]:
                st.markdown("**🔒 ¿De dónde llegan las visitas a secure.guinea.pe?**")
                st.caption("Fuente/medio de la sesión: Ads pagados, cuy.pe, blog.cuy.pe, orgánico, directo, etc.")
                render_traffic_origin(ga_by_domain_r["secure.guinea.pe"].get("traffic_origin"))
    else:
        st.info("Google Analytics no está conectado.")

    st.divider()

    # Análisis narrativo automático
    st.subheader("🧠 Análisis completo")
    st.markdown(generate_full_analysis(meta_df_r, ga_summary_r, ga_channels_r, ga_top_pages_r, gads_df_r))

    st.divider()

    # Campo libre de preguntas
    st.subheader("💬 Pregúntale a tus datos")
    st.caption("Escribe una pregunta sobre tus métricas, por ejemplo: '¿cuál es mi página más visitada?', '¿de dónde viene mi tráfico?', '¿cuánto tiempo pasan en mi web?'.")
    user_question = st.text_input("Tu pregunta", key="resumen_question", placeholder="Ej: ¿Cuál es mi página más visitada?")
    if st.button("Preguntar", key="btn_resumen_question", type="primary"):
        if user_question.strip():
            st.info(answer_question(user_question, meta_df_r, ga_summary_r, ga_channels_r, ga_top_pages_r))
        else:
            st.warning("Escribe una pregunta primero.")

elif nav_section == "📊 Meta Ads":
    if not ACCESS_TOKEN:
        st.error("Falta ACCESS_TOKEN. Agrégalo en Streamlit Cloud → Settings → Secrets.")
        st.stop()

    if date_preset == "custom" and not (since_str and until_str):
        st.info("Selecciona un rango de fechas válido en el panel izquierdo para continuar.")
        st.stop()

    # ── Tabs internas de Meta Ads ──────────────────────────────────────────────
    tab_dash, tab_create, tab_grid, tab_ai = st.tabs(
        ["📊 Dashboard", "➕ Crear Anuncio", "🗓️ Parrilla de Contenido", "🧠 Preguntas y Recomendaciones"]
    )

    # ══════════════════════════════════════════════════════════════════════════════
    # TAB 1 — DASHBOARD
    # ══════════════════════════════════════════════════════════════════════════════
    with tab_dash:
        with st.spinner("Cargando datos de Meta Ads..."):
            df = fetch_campaigns(account_id, date_preset, since_str, until_str)

        if df.empty:
            st.info("No hay datos disponibles para este período y cuenta.")
        else:
            raw_view_df = df if show_paused else df[df["Estado"] == "ACTIVE"]

            # Desglose real por plataforma (siempre sobre el total, independiente del filtro)
            total_spend_fb  = raw_view_df["Gasto_FB"].sum()
            total_spend_ig  = raw_view_df["Gasto_IG"].sum()
            total_spend_all = raw_view_df["Gasto_Total"].sum()

            st.caption(f"🔎 Mostrando métricas de: **{platform_filter}**")

            # Aplica el filtro de plataforma a TODAS las métricas (gasto, impresiones, clics, CTR, CPC, alcance, frecuencia)
            view_df = apply_platform_filter(raw_view_df, platform_filter)

            # KPIs
            st.subheader("Resumen del período")

            total_spend       = view_df["Gasto"].sum()
            k1, k2, k3, k4, k5, k6 = st.columns(6)
            total_impressions = view_df["Impresiones"].sum()
            total_clicks      = view_df["Clics"].sum()
            avg_ctr           = (total_clicks / total_impressions * 100) if total_impressions else 0
            avg_cpc           = (total_spend / total_clicks) if total_clicks else 0
            total_reach       = view_df["Alcance"].sum()
            k1.metric("💰 Gasto", f"${total_spend:,.2f}")
            k2.metric("👁️ Impresiones", f"{total_impressions:,.0f}")
            k3.metric("🖱️ Clics",       f"{total_clicks:,.0f}")
            k4.metric("📊 CTR",         f"{avg_ctr:.2f}%")
            k5.metric("💲 CPC",         f"${avg_cpc:.3f}")
            k6.metric("🎯 Alcance",     f"{total_reach:,.0f}")

            # Desglose de consumo por plataforma — siempre visible, sin importar el filtro
            kp1, kp2, kp3 = st.columns(3)
            kp1.metric("📘 Gasto Facebook",  f"${total_spend_fb:,.2f}")
            kp2.metric("📸 Gasto Instagram", f"${total_spend_ig:,.2f}")
            otras_plataformas = max(total_spend_all - total_spend_fb - total_spend_ig, 0)
            kp3.metric("🌐 Otras (Audience Network, etc.)", f"${otras_plataformas:,.2f}")

            st.divider()

            # Gráficos — usa el mismo conjunto de campañas que los KPIs de arriba (respeta el toggle
            # "Incluir campañas pausadas" y el filtro de plataforma), en vez de forzar solo ACTIVE.
            active_df = view_df
            if not active_df.empty:
                g1, g2 = st.columns(2)
                with g1:
                    st.subheader("Gasto por campaña")
                    st.caption(f"Mostrando {len(active_df)} de {len(df)} campañas totales de la cuenta.")
                    max_gasto = active_df["Gasto"].max()
                    fig = px.bar(
                        active_df.sort_values("Gasto"),
                        x="Gasto", y="Campaña", orientation="h",
                        color="CTR", color_continuous_scale="RdYlGn",
                        color_continuous_midpoint=active_df["CTR"].median(),
                        labels={"Gasto": "Gasto (USD)", "CTR": "CTR%"}, text="Gasto",
                    )
                    fig.update_traces(texttemplate="$%{text:.0f}", textposition="outside", cliponaxis=False)
                    fig.update_layout(
                        height=max(380, 32 * len(active_df)), margin=dict(l=0, r=60, t=0, b=0),
                        yaxis_title="", coloraxis_showscale=False,
                        xaxis=dict(range=[0, max_gasto * 1.18]),
                    )
                    st.plotly_chart(fig, use_container_width=True)
                with g2:
                    st.subheader("CTR vs Frecuencia")
                    fig = px.scatter(
                        active_df, x="Frecuencia", y="CTR", size="Gasto",
                        hover_name="Campaña", color="CPC", color_continuous_scale="RdYlGn_r",
                        labels={"CTR": "CTR (%)", "Frecuencia": "Frecuencia (veces)"},
                    )
                    fig.add_vline(x=4, line_dash="dash", line_color="red",
                                  annotation_text="Saturación", annotation_position="top right")
                    fig.update_layout(height=380, margin=dict(l=0, r=0, t=0, b=0))
                    st.plotly_chart(fig, use_container_width=True)

            # Tabla
            st.subheader("Detalle por campaña")
            table_df = view_df[["Campaña", "Estado", "Gasto", "Gasto_FB", "Gasto_IG", "Impresiones",
                                 "Clics", "CTR", "CPC", "Alcance", "Frecuencia"]].copy()
            table_df = table_df.rename(columns={"Gasto_FB": "Gasto FB", "Gasto_IG": "Gasto IG"})
            st.dataframe(
                table_df.style
                    .format({"Gasto": "${:.2f}", "Gasto FB": "${:.2f}", "Gasto IG": "${:.2f}",
                             "CPC": "${:.3f}", "CTR": "{:.2f}%",
                             "Frecuencia": "{:.2f}x", "Impresiones": "{:,.0f}",
                             "Clics": "{:,.0f}", "Alcance": "{:,.0f}"})
                    .map(lambda v: "color: #2ecc71" if isinstance(v, float) and v > 5
                                   else "color: #e74c3c" if isinstance(v, float) and v < 3 else "",
                         subset=["CTR"])
                    .map(lambda v: "color: #e74c3c" if isinstance(v, float) and v > 4 else "",
                         subset=["Frecuencia"]),
                use_container_width=True, hide_index=True,
            )
            st.divider()

            # Sugerencias
            st.subheader("💡 Sugerencias de acción")
            if active_df.empty:
                st.info("No hay campañas activas para analizar.")
            else:
                suggestions = get_suggestions(active_df)
                if not suggestions:
                    st.success("✅ Todas las campañas activas están dentro de los rangos óptimos.")
                else:
                    URGENCY_ICON = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}
                    ACTION_LABEL = {
                        "PAUSE":            "⏸️ Pausar campaña",
                        "INCREASE_BUDGET":  "⬆️ Aumentar presupuesto",
                        "DECREASE_BUDGET":  "⬇️ Reducir presupuesto",
                        "REFRESH_CREATIVE": "🎨 Acción manual requerida",
                    }
                    for i, s in enumerate(suggestions):
                        icon   = URGENCY_ICON.get(s.get("urgency", ""), "⚪")
                        action = s.get("action", "")
                        name   = s.get("campaign_name", "")
                        cid    = s.get("campaign_id", "")
                        reason = s.get("reason", "")
                        budget = s.get("new_budget_usd")
                        with st.expander(f"{icon} **{name}** — {action}", expanded=True):
                            st.write(reason)
                            col_info, col_btn = st.columns([3, 1])
                            with col_info:
                                if budget:
                                    st.caption(f"Presupuesto sugerido: **${budget:.2f}/día**")
                            with col_btn:
                                btn_label = ACTION_LABEL.get(action, "Ejecutar")
                                if action == "REFRESH_CREATIVE":
                                    st.info("Acción manual — ve a Ads Manager para actualizar la creatividad.")
                                elif action == "PAUSE":
                                    if st.button(btn_label, key=f"btn_{i}", type="primary"):
                                        c1, c2 = st.columns(2)
                                        with c1:
                                            if st.button("✅ Sí, pausar", key=f"confirm_{i}"):
                                                with st.spinner("Pausando..."):
                                                    pause_campaign(cid)
                                                st.success("Campaña pausada.")
                                                st.cache_data.clear()
                                        with c2:
                                            if st.button("Cancelar", key=f"cancel_{i}"):
                                                st.rerun()
                                elif action in ("INCREASE_BUDGET", "DECREASE_BUDGET") and budget:
                                    if st.button(btn_label, key=f"btn_{i}", type="primary"):
                                        with st.spinner("Actualizando presupuesto..."):
                                            set_daily_budget(cid, budget)
                                        st.success(f"Presupuesto actualizado a ${budget:.2f}/día")
                                        st.cache_data.clear()

    # ══════════════════════════════════════════════════════════════════════════════
    # TAB 2 — CREAR ANUNCIO
    # ══════════════════════════════════════════════════════════════════════════════
    with tab_create:
        if not IS_ADMIN:
            st.info(
                "🔒 Esta sección es solo para administradores. Tu cuenta tiene acceso de solo "
                "lectura y no puede crear ni publicar anuncios."
            )
        else:
            st.header("➕ Crear nuevo anuncio")
            st.caption("El anuncio se crea en estado **PAUSADO**. Revísalo en Ads Manager antes de activarlo.")
            st.caption(
                "🏷️ El link de destino se etiqueta automáticamente con parámetros UTM "
                "(`utm_source`, `utm_medium`, `utm_campaign`, etc.) para que Google Analytics pueda "
                "distinguir Facebook de Instagram y atribuirte las ventas correctamente."
            )

            # Page ID
            page_id_input = PAGE_ID or ""
            if not page_id_input:
                st.warning("Configura `PAGE_ID` en Streamlit Cloud → Settings → Secrets con el ID de tu página de Facebook.")
                page_id_input = st.text_input(
                    "O ingrésalo aquí temporalmente:",
                    placeholder="ej. 123456789012345",
                    help="Ve a tu página de Facebook → Acerca de → desplázate al fondo → 'ID de la página'"
                )
            else:
                st.success(f"✅ Página configurada: `{page_id_input}`")

            st.divider()

            # ── PASO 1: Campaña ───────────────────────────────────────────────────────
            st.subheader("1️⃣  Campaña")
            p1a, p1b = st.columns(2)
            with p1a:
                camp_name = st.text_input("Nombre de la campaña *", placeholder="ej. JUL26_Ventas_Ilimitados")
            with p1b:
                obj_label = st.selectbox("Objetivo *", list(OBJECTIVES.keys()))
                objective = OBJECTIVES[obj_label]

            st.markdown("**¿Dónde quieres publicar?**")
            PLATFORM_MAP = {"Facebook": "facebook", "Instagram": "instagram"}
            platforms_selected = st.multiselect(
                "Plataformas *", list(PLATFORM_MAP.keys()), default=["Facebook", "Instagram"]
            )

            differentiate_budget = False
            budget_by_platform = {}
            if len(platforms_selected) == 2:
                differentiate_budget = st.checkbox(
                    "Usar presupuestos diferenciados por plataforma",
                    help="Si lo activas, se crea un conjunto de anuncios independiente por cada plataforma, cada uno con su propio presupuesto diario.",
                )

            if differentiate_budget:
                pb1, pb2 = st.columns(2)
                budget_by_platform["facebook"]  = pb1.number_input("Presupuesto diario Facebook (USD) *", min_value=1.0, value=10.0, step=1.0)
                budget_by_platform["instagram"] = pb2.number_input("Presupuesto diario Instagram (USD) *", min_value=1.0, value=10.0, step=1.0)
                daily_budget_total = sum(budget_by_platform.values())
            else:
                daily_budget_total = st.number_input("Presupuesto diario (USD) *", min_value=1.0, value=10.0, step=1.0)

            st.divider()

            # ── PASO 2: Audiencia ─────────────────────────────────────────────────────
            st.subheader("2️⃣  Audiencia")

            with st.expander("🤖 Asistente IA de segmentación", expanded=True):
                st.markdown("Describe con tus palabras a quién quieres mostrarle el anuncio:")
                ai_description = st.text_area(
                    "audience_desc",
                    placeholder='Ej: "Jóvenes peruanos de 18-30 años que usan smartphones y siguen páginas de competidores como Claro y Entel"',
                    height=80,
                    label_visibility="collapsed",
                )
                if st.button("✨ Generar sugerencia de segmentación", type="secondary"):
                    if ai_description.strip():
                        with st.spinner("Analizando tu audiencia y buscando intereses reales en Meta..."):
                            sugg = ai_suggest_segmentation(ai_description)
                            # Resolver cada término sugerido contra intereses REALES de Meta (no genéricos)
                            resolved = []
                            all_terms = sugg["brand_keywords"] + sugg["interest_keywords"]
                            for term in all_terms[:8]:  # límite razonable de llamadas a la API
                                match = resolve_best_interest(term)
                                if match:
                                    resolved.append(match)
                                    st.session_state["selected_interests_map"][match["id"]] = match["name"]
                            sugg["resolved_count"] = len(resolved)
                            sugg["unresolved"] = [t for t in all_terms[:8] if t not in [r["name"] for r in resolved]]
                        st.session_state["ai_sugg"] = sugg
                    else:
                        st.warning("Escribe una descripción primero.")

                if st.session_state.get("ai_sugg"):
                    sugg = st.session_state["ai_sugg"]
                    gender_label = {"all": "Todos", "male": "Hombres", "female": "Mujeres"}.get(sugg["gender"], "Todos")
                    sc1, sc2, sc3 = st.columns(3)
                    sc1.markdown(f"🌍 **Países:** {', '.join(sugg['countries'])}")
                    sc2.markdown(f"👤 **Edad:** {sugg['age_min']}–{sugg['age_max']} (banda angosta, no genérica)")
                    sc3.markdown(f"⚧️ **Género:** {gender_label}")
                    if sugg.get("resolved_count"):
                        st.success(f"✅ Se agregaron {sugg['resolved_count']} intereses **reales** de Meta directamente a tu selección (ver abajo, en '{'Intereses seleccionados'}').")
                    if sugg.get("unresolved"):
                        st.caption(f"No se encontraron en Meta como interés catalogado: {', '.join(sugg['unresolved'])} — puedes buscarlos manualmente abajo.")
                    if sugg.get("narrow_logic"):
                        st.caption("💡 Esta audiencia combina varias señales específicas — es intencionalmente más angosta que una segmentación genérica. Revisa el estimado de audiencia más abajo.")
                    for note in sugg.get("notes", []):
                        st.markdown(note)

            # Campos de audiencia
            ai_sugg = st.session_state.get("ai_sugg", {})
            a1, a2 = st.columns(2)
            with a1:
                default_countries = [k for k, v in COUNTRIES_ES.items() if v in ai_sugg.get("countries", ["PE"])]
                selected_countries_es = st.multiselect(
                    "Países *", list(COUNTRIES_ES.keys()),
                    default=default_countries or ["Perú"],
                )
                selected_countries = [COUNTRIES_ES[c] for c in selected_countries_es]
            with a2:
                gender_default_idx = {"all": 0, "male": 1, "female": 2}.get(ai_sugg.get("gender", "all"), 0)
                gender_choice = st.radio("Género", ["Todos", "Hombres", "Mujeres"],
                                         horizontal=True, index=gender_default_idx)
                genders = {"Todos": [], "Hombres": [1], "Mujeres": [2]}[gender_choice]

            age_min, age_max = st.slider(
                "Rango de edad",
                min_value=13, max_value=65,
                value=(ai_sugg.get("age_min", 18), ai_sugg.get("age_max", 45)),
            )

            # Búsqueda de intereses
            st.markdown("**Intereses** — busca y selecciona")
            bi1, bi2 = st.columns([3, 1])
            with bi1:
                interest_query = st.text_input(
                    "interest_search", label_visibility="collapsed",
                    placeholder="ej. Telefonía móvil, Smartphones, Claro Peru…"
                )
            with bi2:
                do_search = st.button("🔍 Buscar intereses")

            if do_search:
                if interest_query.strip():
                    with st.spinner("Consultando Meta..."):
                        found = search_meta_interests(interest_query)
                    st.session_state["interest_results"] = found
                else:
                    st.warning("Escribe un término primero.")

            # Acumulador persistente de intereses elegidos (sobrevive a nuevas búsquedas)
            if "selected_interests_map" not in st.session_state:
                st.session_state["selected_interests_map"] = {}  # id -> name

            if "interest_results" in st.session_state:
                results = st.session_state["interest_results"]
                if results:
                    for r in results:
                        already = r["id"] in st.session_state["selected_interests_map"]
                        checked = st.checkbox(
                            f"{r['name']}  (~{r['audience']:,.0f} personas)",
                            value=already,
                            key=f"chk_interest_{r['id']}",
                        )
                        if checked:
                            st.session_state["selected_interests_map"][r["id"]] = r["name"]
                        elif already:
                            del st.session_state["selected_interests_map"][r["id"]]
                else:
                    st.info("Sin resultados — prueba otro término.")

            # Mostrar todos los intereses elegidos hasta ahora (de todas las búsquedas)
            if st.session_state["selected_interests_map"]:
                st.markdown("**Intereses seleccionados:**")
                for iid, iname in list(st.session_state["selected_interests_map"].items()):
                    rm_col1, rm_col2 = st.columns([5, 1])
                    rm_col1.write(f"🎯 {iname}")
                    if rm_col2.button("✕ Quitar", key=f"rm_interest_{iid}"):
                        del st.session_state["selected_interests_map"][iid]
                        st.rerun()

            selected_interest_ids = list(st.session_state["selected_interests_map"].keys())

            # Públicos Lookalike
            st.markdown("**Públicos Lookalike** (basados en tus clientes o públicos existentes)")
            lookalikes = fetch_lookalike_audiences(account_id)
            selected_lookalike_ids = []
            if lookalikes:
                lookalike_options = {f"{a['name']}  (~{a['size']:,.0f} personas)": a["id"] for a in lookalikes}
                chosen_lookalikes = st.multiselect("Selecciona públicos Lookalike:", list(lookalike_options.keys()))
                selected_lookalike_ids = [lookalike_options[c] for c in chosen_lookalikes]
            else:
                st.caption("No se encontraron públicos Lookalike en esta cuenta. Puedes crear uno en Ads Manager → Públicos → Crear público → Lookalike, a partir de tu lista de clientes o de tu página.")

            # Estimado real de audiencia — mide qué tan fina quedó la segmentación
            if selected_countries:
                with st.spinner("Calculando tamaño de audiencia..."):
                    audience_est = get_audience_estimate(
                        account_id, selected_countries, age_min, age_max, genders, selected_interest_ids
                    )
                if audience_est is not None:
                    if audience_est < 50_000:
                        st.info(f"👥 **Audiencia estimada: ~{audience_est:,} personas** — muy específica. Bien si buscas precisión, pero vigila que no sea tan chica que limite la entrega.")
                    elif audience_est < 500_000:
                        st.success(f"👥 **Audiencia estimada: ~{audience_est:,} personas** — segmentación fina, buen equilibrio entre precisión y alcance.")
                    else:
                        st.warning(f"👥 **Audiencia estimada: ~{audience_est:,} personas** — todavía amplia. Agrega más intereses o acorta el rango de edad para afinar más.")

            st.divider()

            # ── PASO 3: Creatividad ───────────────────────────────────────────────────
            st.subheader("3️⃣  Creatividad del anuncio")

            is_carousel = st.checkbox(
                "🎠 Publicar como carrusel (2 a 10 imágenes)",
                help="Cada imagen se muestra como una tarjeta deslizable. Puedes darle a cada tarjeta su propio titular y descripción, o dejar el titular/descripción general de abajo.",
            )

            uploaded_image = None
            uploaded_carousel_images = []
            carousel_card_texts = []

            if is_carousel:
                uploaded_carousel_images = st.file_uploader(
                    "Imágenes del carrusel * (JPG o PNG — mín. 1080×1080 px recomendado, 2 a 10 imágenes)",
                    type=["jpg", "jpeg", "png"],
                    accept_multiple_files=True,
                )
                if uploaded_carousel_images:
                    if len(uploaded_carousel_images) > 10:
                        st.warning("Meta permite máximo 10 tarjetas en un carrusel — se usarán solo las primeras 10.")
                        uploaded_carousel_images = uploaded_carousel_images[:10]
                    st.caption(f"{len(uploaded_carousel_images)} imagen(es) cargada(s). Opcionalmente, personaliza cada tarjeta:")
                    for i, img in enumerate(uploaded_carousel_images):
                        cc1, cc2 = st.columns([1, 3])
                        with cc1:
                            st.image(img, width=140)
                        with cc2:
                            card_headline = st.text_input(
                                f"Titular tarjeta {i + 1} (opcional, si vacío usa el titular general)",
                                key=f"carousel_headline_{i}",
                            )
                            card_description = st.text_input(
                                f"Descripción tarjeta {i + 1} (opcional)",
                                key=f"carousel_description_{i}",
                            )
                        carousel_card_texts.append({"headline": card_headline, "description": card_description})
            else:
                uploaded_image = st.file_uploader(
                    "Imagen del anuncio * (JPG o PNG — mín. 1080×1080 px recomendado)",
                    type=["jpg", "jpeg", "png"],
                )
                if uploaded_image:
                    st.image(uploaded_image, caption="Imagen cargada", width=280)

            cr1, cr2 = st.columns(2)
            with cr1:
                primary_text = st.text_area(
                    "Texto principal *",
                    placeholder="Ej: ¡Conéctate sin límites con Cuy Móvil! 🐹 Planes desde S/39.",
                    height=100,
                )
                headline = st.text_input("Titular *", placeholder="Ej: Plan Ilimitado desde S/39")
            with cr2:
                ad_description = st.text_input("Descripción", placeholder="Ej: Sin cortes, sin límites. Pruébalo gratis 7 días.")
                destination_url = st.text_input("URL de destino *", placeholder="https://cuymovil.pe")
                cta_label = st.selectbox("Botón de acción (CTA)", list(CTA_OPTIONS.keys()))
                cta_type  = CTA_OPTIONS[cta_label]

            # Vista previa del anuncio (usa la API de Meta, no publica nada)
            st.markdown("**👁️ Vista previa del anuncio**")
            preview_platform_label = st.radio(
                "Ver como se vería en:",
                ["Facebook (feed móvil)", "Instagram (feed)"],
                horizontal=True,
            )
            preview_ad_format = "MOBILE_FEED_STANDARD" if "Facebook" in preview_platform_label else "INSTAGRAM_STANDARD"

            if st.button("🔍 Generar vista previa"):
                if is_carousel:
                    if len(uploaded_carousel_images) < 2 or not page_id_input or not destination_url:
                        st.warning("Sube al menos 2 imágenes para el carrusel, indica el ID de página y la URL de destino antes de generar la vista previa.")
                    else:
                        with st.spinner("Generando vista previa del carrusel con Meta..."):
                            try:
                                preview_cards = []
                                for img, texts in zip(uploaded_carousel_images, carousel_card_texts):
                                    img_bytes = img.getvalue()
                                    img_ext = img.name.rsplit(".", 1)[-1] if "." in img.name else "jpg"
                                    card_hash = upload_ad_image(account_id, img_bytes, img_ext)
                                    preview_cards.append({
                                        "image_hash": card_hash,
                                        "headline": texts.get("headline") or headline,
                                        "description": texts.get("description") or ad_description,
                                    })
                                preview_html = get_carousel_preview_html(
                                    account_id, page_id_input, preview_cards,
                                    primary_text or " ", destination_url, cta_type, preview_ad_format,
                                )
                                st.session_state["preview_html"] = preview_html
                            except Exception as e:
                                st.error(f"No se pudo generar la vista previa: {e}")
                elif not uploaded_image or not page_id_input or not destination_url:
                    st.warning("Sube una imagen, indica el ID de página y la URL de destino antes de generar la vista previa.")
                else:
                    with st.spinner("Generando vista previa con Meta..."):
                        try:
                            preview_image_bytes = uploaded_image.getvalue()
                            preview_image_ext = uploaded_image.name.rsplit(".", 1)[-1] if "." in uploaded_image.name else "jpg"
                            preview_hash = upload_ad_image(account_id, preview_image_bytes, preview_image_ext)
                            st.session_state["preview_image_hash"] = preview_hash
                            preview_html = get_ad_preview_html(
                                account_id, page_id_input, preview_hash,
                                primary_text or " ", headline or " ", ad_description or "",
                                destination_url, cta_type, preview_ad_format,
                            )
                            st.session_state["preview_html"] = preview_html
                        except Exception as e:
                            st.error(f"No se pudo generar la vista previa: {e}")

            if st.session_state.get("preview_html"):
                st.components.v1.html(st.session_state["preview_html"], height=600, scrolling=True)

            st.divider()

            # ── PASO 4: Detalles finales ──────────────────────────────────────────────
            st.subheader("4️⃣  Detalles finales")
            d1, d2 = st.columns(2)
            with d1:
                start_date = st.date_input("Fecha de inicio", value=date.today())
            with d2:
                if differentiate_budget:
                    resumen_presupuesto = " · ".join(f"{k.capitalize()}: ${v:.2f}/día" for k, v in budget_by_platform.items())
                else:
                    resumen_presupuesto = f"${daily_budget_total:.2f}/día ({', '.join(platforms_selected) or 'sin plataforma'})"
                st.info(f"**Cuenta:** {account_label}\n\n**Presupuesto:** {resumen_presupuesto}")

            st.divider()

            # ── Validación y botón de publicar ────────────────────────────────────────
            missing = []
            if not camp_name:          missing.append("Nombre de campaña")
            if not page_id_input:      missing.append("ID de página de Facebook")
            if not destination_url:    missing.append("URL de destino")
            if not primary_text:       missing.append("Texto principal")
            if not headline:           missing.append("Titular")
            if is_carousel:
                if len(uploaded_carousel_images) < 2:
                    missing.append("Al menos 2 imágenes para el carrusel")
            elif not uploaded_image:
                missing.append("Imagen del anuncio")
            if not selected_countries: missing.append("Al menos un país")
            if not platforms_selected: missing.append("Al menos una plataforma (Facebook o Instagram)")

            if missing:
                st.warning("Faltan campos requeridos: " + "  ·  ".join(missing))
                st.button("🚀 Crear anuncio (pausado)", type="primary", disabled=True)
            else:
                if st.button("🚀 Crear anuncio (pausado)", type="primary"):
                    with st.spinner("Creando campaña → conjunto(s) → imagen(es) → creatividad → anuncio(s)…"):
                        try:
                            image_bytes = None
                            image_ext = None
                            carousel_cards = None

                            if is_carousel:
                                carousel_cards = []
                                for img, texts in zip(uploaded_carousel_images, carousel_card_texts):
                                    carousel_cards.append({
                                        "image_bytes": img.getvalue(),
                                        "image_ext":   img.name.rsplit(".", 1)[-1] if "." in img.name else "jpg",
                                        "headline":    texts.get("headline"),
                                        "description": texts.get("description"),
                                    })
                            else:
                                image_bytes = uploaded_image.read()
                                image_ext   = uploaded_image.name.rsplit(".", 1)[-1] if "." in uploaded_image.name else "jpg"

                            # Armar la configuración de conjuntos de anuncios por plataforma
                            if differentiate_budget:
                                adset_configs = []
                                if "Facebook" in platforms_selected:
                                    adset_configs.append({"platforms": ["facebook"], "budget": budget_by_platform["facebook"], "suffix": "FB"})
                                if "Instagram" in platforms_selected:
                                    adset_configs.append({"platforms": ["instagram"], "budget": budget_by_platform["instagram"], "suffix": "IG"})
                            else:
                                chosen_platform_codes = [PLATFORM_MAP[p] for p in platforms_selected]
                                adset_configs = [{"platforms": chosen_platform_codes, "budget": daily_budget_total, "suffix": ""}]

                            result = create_full_ad(
                                account_id=account_id,
                                page_id=page_id_input,
                                camp_name=camp_name,
                                objective=objective,
                                adset_configs=adset_configs,
                                countries=selected_countries,
                                age_min=age_min,
                                age_max=age_max,
                                genders=genders,
                                interest_ids=selected_interest_ids,
                                custom_audience_ids=selected_lookalike_ids,
                                image_bytes=image_bytes,
                                image_ext=image_ext,
                                primary_text=primary_text,
                                headline=headline,
                                ad_description=ad_description,
                                destination_url=destination_url,
                                cta_type=cta_type,
                                start_date=start_date,
                                carousel_cards=carousel_cards,
                            )

                            st.success("✅ ¡Anuncio creado exitosamente en estado PAUSADO!")
                            r1, r2 = st.columns(2)
                            with r1:
                                adsets_md = "\n".join(
                                    f"- 👥 Conjunto ({', '.join(a['platforms'])}, ${a['budget']:.2f}/día): `{a['adset_id']}` → Anuncio: `{a['ad_id']}`"
                                    for a in result["adsets"]
                                )
                                st.markdown(f"""
        **IDs generados:**
        - 📢 Campaña: `{result['campaign_id']}`
        - 🎨 Creatividad: `{result['creative_id']}`
        {adsets_md}
                                """)
                            with r2:
                                mgr_url = f"https://www.facebook.com/adsmanager/manage/campaigns?act={account_id.replace('act_', '')}"
                                st.markdown(f"### [📋 Ver en Ads Manager]({mgr_url})")
                                st.info("Cuando estés lista, actívalo desde Ads Manager.")
                            st.session_state["preview_html"] = None
                            st.cache_data.clear()

                        except Exception as e:
                            st.error(f"Error al crear el anuncio: {e}")
                            st.caption("Abre los logs en 'Manage app' para ver el detalle.")

        # ══════════════════════════════════════════════════════════════════════════════
        # TAB 3 — PARRILLA DE CONTENIDO (recomendación mensual basada en datos reales)
        # ══════════════════════════════════════════════════════════════════════════════
    with tab_grid:
        st.header("🗓️ Parrilla de Contenido del Mes")
        st.caption(
            "Analiza tus campañas pagadas y tus publicaciones orgánicas para recomendarte hasta 4 campañas "
            "de Meta Ads (audiencia + presupuesto) y una parrilla de contenido orgánico con brief para tu "
            "diseñador — basado en el rendimiento real de tu cuenta, sin usar una IA de pago."
        )

        if not IS_ADMIN:
            st.info(
                "🔒 Tu cuenta tiene acceso de solo lectura y no puede generar la parrilla de contenidos. "
                "Pídele a un administrador que la genere y comparta el CSV contigo."
            )

        if IS_ADMIN and st.button("🎯 Generar recomendación del mes", type="primary", key="btn_generate_grid"):
            st.session_state["grid_generated"] = True

        if IS_ADMIN and st.session_state.get("grid_generated"):
            grid_page_id = PAGE_ID or globals().get("page_id_input", "")
            if not grid_page_id:
                st.warning(
                    "No se detectó `PAGE_ID` en Secrets — la parte de contenido orgánico usará solo buenas "
                    "prácticas estándar (sin analizar tus publicaciones reales)."
                )

            _grid_until = datetime.now(PERU_TZ).date()
            _grid_since = _grid_until - timedelta(days=60)
            _grid_since_str, _grid_until_str = _grid_since.strftime("%Y-%m-%d"), _grid_until.strftime("%Y-%m-%d")

            with st.spinner("Analizando campañas pagadas, audiencias y contenido orgánico (últimos 60 días)..."):
                try:
                    meta_df_wide = fetch_campaigns(account_id, "custom", _grid_since_str, _grid_until_str)
                except Exception as e:
                    meta_df_wide = pd.DataFrame()
                    st.warning(f"No se pudo cargar el historial amplio de Meta Ads: {e}")
                try:
                    age_gender_df = fetch_age_gender_breakdown(account_id, "custom", _grid_since_str, _grid_until_str)
                except Exception as e:
                    age_gender_df = pd.DataFrame()
                    st.warning(f"No se pudo cargar el desglose por edad/género: {e}")
                try:
                    organic_df = fetch_organic_posts(grid_page_id, ACCESS_TOKEN, limit=30)
                except Exception as e:
                    organic_df = pd.DataFrame()
                    st.warning(f"No se pudo cargar el contenido orgánico: {e}")

            st.divider()
            st.subheader("👥 Cómo interactúa tu audiencia (últimos 60 días)")
            if age_gender_df is not None and not age_gender_df.empty:
                seg_view = age_gender_df.sort_values("CTR", ascending=False).head(8).copy()
                seg_view["Segmento"] = seg_view["Edad"].astype(str) + " · " + seg_view["Género"]
                fig = px.bar(
                    seg_view.sort_values("CTR"), x="CTR", y="Segmento", orientation="h",
                    color="Gasto", color_continuous_scale=PURPLE_SCALE,
                    labels={"CTR": "CTR (%)"}, text="CTR",
                )
                fig.update_traces(texttemplate="%{text:.2f}%", textposition="outside", cliponaxis=False)
                fig.update_layout(height=320, margin=dict(l=0, r=60, t=0, b=0), yaxis_title="", coloraxis_showscale=False)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Sin datos suficientes de edad/género en el período — se usarán bandas estándar de telco.")

            st.divider()
            st.subheader("📣 Campañas de Meta Ads recomendadas")
            st.caption("Máximo 4 campañas · presupuesto diario sugerido ≤ $4.00 por campaña.")
            recos = generate_meta_campaign_recos(meta_df_wide, age_gender_df, max_campaigns=4, max_daily_budget=4.0)
            total_budget = sum(r["Presupuesto diario"] for r in recos)
            for r in recos:
                with st.container(border=True):
                    cc1, cc2, cc3 = st.columns([2, 1, 1])
                    cc1.markdown(
                        f"**📣 {r['Campaña']}**\n\n💡 Concepto: **{r['Concepto']}**\n\n"
                        f"👥 {r['Edad']} años · {r['Género']}\n\n"
                        f"🎯 Intereses sugeridos: {r['Intereses sugeridos']}\n\n"
                        f"🪝 Hook: _{r['Hook']}_\n\n"
                        f"✍️ Frases indispensables: {r['Frases indispensables']}"
                    )
                    cc2.metric("💰 Presupuesto/día", f"${r['Presupuesto diario']:.2f}")
                    cc3.metric("🎯 Objetivo", r["Objetivo"])
                    st.caption(r["Justificación"])
            st.info(
                f"💰 Presupuesto diario total sugerido para las {len(recos)} campañas: "
                f"**${total_budget:.2f}/día** (≈ ${total_budget * 30:.0f}/mes)."
            )

            st.divider()
            st.subheader("🗓️ Parrilla de contenidos del mes (Orgánico + Ads)")
            calendar_df, organic_note, top_posts = generate_organic_calendar(organic_df, weeks=4, posts_per_week=3)
            st.markdown(organic_note)
            unified_df = generate_unified_grid(calendar_df, recos, weeks=4)
            st.caption("La columna **Tipo** indica si esa pieza es 🌱 Orgánico o 📣 Ads.")
            st.dataframe(unified_df, use_container_width=True, hide_index=True, height=560)
            csv_bytes = unified_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Descargar parrilla (CSV) para el diseñador", csv_bytes,
                file_name="parrilla_contenido_mensual.csv", mime="text/csv",
            )

            if top_posts is not None and not top_posts.empty:
                st.markdown("**📌 Tus 3 publicaciones orgánicas con mejor interacción (referencia de tono/formato):**")
                st.dataframe(top_posts, use_container_width=True, hide_index=True)
        else:
            st.info("Presiona el botón para generar la recomendación del mes usando tus datos reales.")

    # ══════════════════════════════════════════════════════════════════════════════
    # TAB 4 — PREGUNTAS Y RECOMENDACIONES (IA basada en reglas)
    # ══════════════════════════════════════════════════════════════════════════════
    with tab_ai:
        st.header("🧠 Preguntas y Recomendaciones")
        st.caption(
            "Pregúntale a tus anuncios de Meta Ads — analiza tus campañas y conjuntos de anuncios reales "
            "(incluida la fase de aprendizaje) para darte respuestas y recomendaciones. Basado en reglas, "
            "sin usar una IA de pago."
        )

        with st.spinner("Cargando campañas y fase de aprendizaje..."):
            ai_df_full = fetch_campaigns(account_id, date_preset, since_str, until_str)
            ai_raw_view = ai_df_full if show_paused else ai_df_full[ai_df_full["Estado"] == "ACTIVE"]
            ai_view_df = apply_platform_filter(ai_raw_view, platform_filter) if not ai_raw_view.empty else ai_raw_view

            try:
                ai_learning_df = fetch_learning_status(account_id)
            except Exception as e:
                ai_learning_df = pd.DataFrame()
                st.warning(f"No se pudo cargar la fase de aprendizaje de los conjuntos de anuncios: {e}")

        if ai_view_df is None or ai_view_df.empty:
            st.info("No hay campañas para analizar en este período y cuenta.")
        else:
            if ai_learning_df is not None and not ai_learning_df.empty:
                en_aprendizaje = (ai_learning_df["Fase"] == "LEARNING").sum()
                limitado       = (ai_learning_df["Fase"] == "LEARNING_LIMITED").sum()
                completado     = (ai_learning_df["Fase"] == "SUCCESS").sum()
                c1, c2, c3 = st.columns(3)
                c1.metric("🧪 En aprendizaje", en_aprendizaje)
                c2.metric("⚠️ Aprendizaje limitado", limitado)
                c3.metric("✅ Aprendizaje completado", completado)
                with st.expander("Ver detalle por conjunto de anuncios"):
                    st.dataframe(
                        ai_learning_df[["Conjunto de anuncios", "Campaña", "Estado", "Fase (texto)", "Presupuesto diario"]]
                            .rename(columns={"Fase (texto)": "Fase de aprendizaje"})
                            .style.format({"Presupuesto diario": "${:,.2f}"}),
                        use_container_width=True, hide_index=True,
                    )
                st.divider()

            st.subheader("💬 Pregúntale a tus anuncios")
            st.caption(
                "Ejemplos: '¿qué campañas están en etapa de aprendizaje?', '¿qué debería pausar?', "
                "'¿cómo está mi frecuencia?', '¿cuáles puedo escalar de presupuesto?', o escribe el nombre de una campaña."
            )
            ai_question = st.text_input(
                "Tu pregunta", key="meta_ai_question",
                placeholder="Ej: Tengo una campaña en etapa de aprendizaje, ¿la revisas?",
            )
            if st.button("Preguntar", key="btn_meta_ai_question", type="primary"):
                if ai_question.strip():
                    st.info(generate_meta_ai_answer(ai_question, ai_view_df, ai_learning_df))
                else:
                    st.warning("Escribe una pregunta primero.")

# ══════════════════════════════════════════════════════════════════════════════
# GOOGLE ADS
# ══════════════════════════════════════════════════════════════════════════════
elif nav_section == "🔍 Google Ads":
    st.header("🔍 Google Ads")
    st.caption("Métricas de campañas de Google Ads del período seleccionado.")

    if not GOOGLE_ADS_READY:
        st.error(
            "Falta configurar Google Ads. Agrega `GOOGLE_ADS_CLIENT_ID`, `GOOGLE_ADS_CLIENT_SECRET`, "
            "`GOOGLE_ADS_REFRESH_TOKEN` y `GOOGLE_ADS_DEVELOPER_TOKEN` en Streamlit Cloud → Settings → Secrets."
        )
        st.stop()

    if gads_date_preset == "custom" and not (gads_since_str and gads_until_str):
        st.info("Selecciona un rango de fechas válido en el panel izquierdo para continuar.")
        st.stop()

    gads_start, gads_end = get_ga_date_range(gads_date_preset, gads_since_str, gads_until_str)
    st.caption(f"Período: **{gads_start}** a **{gads_end}** · Cuenta: `{GOOGLE_ADS_CUSTOMER_ID}`")

    try:
        with st.spinner("Cargando datos de Google Ads..."):
            gads_df = fetch_google_ads_campaigns(GOOGLE_ADS_CUSTOMER_ID, gads_start, gads_end)
    except Exception as e:
        st.error(f"No se pudo conectar con Google Ads: {e}")
        st.caption(
            "Verifica que el Customer ID sea correcto, que la cuenta que autorizó el refresh token tenga acceso "
            "a esa cuenta de Google Ads, y que el Developer Token esté aprobado para el nivel de acceso necesario."
        )
        st.stop()

    if gads_df.empty:
        st.info("No hay datos disponibles para este período.")
        st.stop()

    gads_df_unfiltered = gads_df
    if gads_name_filter.strip():
        gads_df = gads_df[gads_df["Campaña"].str.contains(gads_name_filter, case=False, na=False)]
        st.caption(f"🔎 Mostrando solo campañas cuyo nombre contiene: **{gads_name_filter}**")
        if gads_df.empty:
            st.warning(
                f"Ninguna campaña coincide con '{gads_name_filter}'. Estos son los nombres de campaña disponibles "
                "en esta cuenta — ajusta el filtro en el panel izquierdo:"
            )
            st.dataframe(
                gads_df_unfiltered[["Campaña"]].drop_duplicates(),
                use_container_width=True, hide_index=True,
            )
            st.stop()

    st.subheader("Resumen del período")
    total_spend       = gads_df["Gasto"].sum()
    total_impressions = gads_df["Impresiones"].sum()
    total_clicks      = gads_df["Clics"].sum()
    total_conversions = gads_df["Conversiones"].sum()
    avg_ctr           = (total_clicks / total_impressions * 100) if total_impressions else 0
    avg_cpc           = (total_spend / total_clicks) if total_clicks else 0

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("💰 Gasto", f"${total_spend:,.2f}")
    k2.metric("👁️ Impresiones", f"{total_impressions:,.0f}")
    k3.metric("🖱️ Clics", f"{total_clicks:,.0f}")
    k4.metric("📊 CTR", f"{avg_ctr:.2f}%")
    k5.metric("💲 CPC", f"${avg_cpc:.3f}")
    k6.metric("🎯 Conversiones", f"{total_conversions:,.1f}")

    st.divider()

    active_gads_df = gads_df[gads_df["Estado"] == "ENABLED"]
    chart_df = active_gads_df if not active_gads_df.empty else gads_df
    if not chart_df.empty:
        st.subheader("Gasto por campaña")
        max_gasto_gads = chart_df["Gasto"].max()
        fig = px.bar(
            chart_df.sort_values("Gasto"),
            x="Gasto", y="Campaña", orientation="h",
            color="CTR", color_continuous_scale="RdYlGn",
            color_continuous_midpoint=chart_df["CTR"].median(),
            labels={"Gasto": "Gasto (USD)", "CTR": "CTR%"}, text="Gasto",
        )
        fig.update_traces(texttemplate="$%{text:.0f}", textposition="outside", cliponaxis=False)
        fig.update_layout(
            height=max(320, 32 * len(chart_df)), margin=dict(l=0, r=60, t=10, b=0), yaxis_title="",
            xaxis=dict(range=[0, max_gasto_gads * 1.18]), coloraxis_showscale=False,
        )
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    st.subheader("Detalle por campaña")
    st.dataframe(
        gads_df.style.format({
            "Gasto": "${:,.2f}", "Impresiones": "{:,.0f}", "Clics": "{:,.0f}",
            "CTR": "{:.2f}%", "CPC": "${:.3f}", "Conversiones": "{:,.1f}",
        }),
        use_container_width=True, hide_index=True,
    )

    st.divider()

    # ── Recomendaciones de contenido para Display (IA basada en reglas) ────────
    st.subheader("🎨 Recomendaciones de contenido para Display")
    st.caption(
        "Usa el rendimiento de tu campaña de marca (branded) para recomendarte títulos, descripciones, "
        "especificaciones de imagen y audiencias listas para armar y publicar tu campaña de Display — "
        "basado en reglas, sin usar una IA de pago."
    )
    if st.button("🎯 Generar recomendaciones para Display", type="primary", key="btn_gads_display"):
        st.session_state["gads_display_generated"] = True

    if st.session_state.get("gads_display_generated"):
        display_reco = generate_google_display_recommendations(gads_df_unfiltered)

        for note in display_reco["notes"]:
            st.info(note)

        dc1, dc2 = st.columns(2)
        with dc1:
            st.markdown("**📝 Títulos sugeridos** (≤ 30 caracteres c/u)")
            for h in display_reco["headlines"]:
                st.markdown(f"- {h}")
            st.markdown(f"**Título largo** (≤ 90 caracteres): _{display_reco['long_headline']}_")
        with dc2:
            st.markdown("**🧾 Descripciones sugeridas** (≤ 90 caracteres c/u)")
            for d in display_reco["descriptions"]:
                st.markdown(f"- {d}")
            st.markdown(f"**Botones de llamada a la acción sugeridos:** {', '.join(display_reco['ctas'])}")

        st.markdown("**🖼️ Especificaciones de imagen para tu diseñador**")
        specs_df = pd.DataFrame(display_reco["image_specs"], columns=["Elemento", "Tamaño", "Notas"])
        st.dataframe(specs_df, use_container_width=True, hide_index=True)

        st.markdown("**🎯 Audiencias recomendadas**")
        for a in display_reco["audiences"]:
            st.markdown(f"- {a}")

        # Brief descargable para el diseñador
        brief_rows = (
            [{"Tipo": "Título", "Contenido": h} for h in display_reco["headlines"]]
            + [{"Tipo": "Título largo", "Contenido": display_reco["long_headline"]}]
            + [{"Tipo": "Descripción", "Contenido": d} for d in display_reco["descriptions"]]
            + [{"Tipo": "CTA sugerido", "Contenido": c} for c in display_reco["ctas"]]
            + [{"Tipo": "Especificación de imagen", "Contenido": f"{e} — {t} ({n})"} for e, t, n in display_reco["image_specs"]]
            + [{"Tipo": "Audiencia recomendada", "Contenido": a} for a in display_reco["audiences"]]
        )
        brief_csv = pd.DataFrame(brief_rows).to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Descargar brief de Display (CSV) para el diseñador", brief_csv,
            file_name="brief_display_google_ads.csv", mime="text/csv",
        )
    else:
        st.info("Presiona el botón para generar la recomendación de contenidos para Display.")

    st.divider()

    if not IS_ADMIN:
        st.divider()
        st.info(
            "🔒 Crear campañas de Display es solo para administradores. Tu cuenta tiene acceso "
            "de solo lectura y no puede publicar campañas."
        )
    else:
        # ── Crear campaña de Display (Google Ads) ──────────────────────────────────
        st.subheader("🚀 Crear campaña de Display")
        st.caption(
            "Crea una campaña de Display con un anuncio responsivo (varios títulos, descripciones e "
            "imágenes que Google combina automáticamente). Se crea en estado **PAUSADO** — revísala en "
            "Google Ads antes de activarla."
        )

        with st.expander("🎯 Audiencias (opcional)", expanded=False):
            st.markdown("**Demografía**")
            gd_age_keys = st.multiselect("Edad", list(GOOGLE_AGE_RANGE_OPTIONS.keys()), key="gd_age_keys")
            gd_gender_keys = st.multiselect("Género", list(GOOGLE_GENDER_OPTIONS.keys()), key="gd_gender_keys")

            st.divider()
            st.markdown("**🔄 Listas de remarketing**")
            st.caption("Trae las audiencias/listas de remarketing que ya tienes creadas en tu cuenta de Google Ads.")
            if st.button("Cargar mis listas de remarketing", key="btn_load_gads_userlists"):
                with st.spinner("Buscando listas de remarketing en tu cuenta..."):
                    try:
                        st.session_state["gads_user_lists"] = fetch_google_user_lists(GOOGLE_ADS_CUSTOMER_ID)
                    except Exception as e:
                        st.warning(f"No se pudieron cargar las listas: {e}")
                        st.session_state["gads_user_lists"] = pd.DataFrame()

            user_lists_df = st.session_state.get("gads_user_lists")
            gd_selected_user_lists = []
            if user_lists_df is not None and not user_lists_df.empty:
                gd_selected_user_list_names = st.multiselect(
                    "Selecciona listas de remarketing", user_lists_df["Nombre"].tolist(), key="gd_userlist_select",
                )
                gd_selected_user_lists = user_lists_df[
                    user_lists_df["Nombre"].isin(gd_selected_user_list_names)
                ]["resource_name"].tolist()
            elif user_lists_df is not None and user_lists_df.empty:
                st.caption("No se encontraron listas de remarketing abiertas en esta cuenta.")

            st.divider()
            st.markdown("**🎯 Audiencias de afinidad / in-market**")
            st.caption("Busca categorías de audiencia de Google (ej. 'planes móviles', 'telecomunicaciones', 'smartphones').")
            gd_interest_query = st.text_input("Buscar audiencia", key="gd_interest_query")
            if st.button("🔍 Buscar audiencias de Google", key="btn_search_gads_interests"):
                if gd_interest_query.strip():
                    with st.spinner("Buscando en la taxonomía de audiencias de Google..."):
                        try:
                            st.session_state["gads_interest_results"] = search_google_user_interests(gd_interest_query.strip())
                        except Exception as e:
                            st.warning(f"No se pudo buscar: {e}")
                            st.session_state["gads_interest_results"] = pd.DataFrame()
                else:
                    st.warning("Escribe un término de búsqueda primero.")

            interest_results_df = st.session_state.get("gads_interest_results")
            gd_selected_interests = []
            if interest_results_df is not None and not interest_results_df.empty:
                interest_labels = [f"{row['Nombre']} ({row['Tipo']})" for _, row in interest_results_df.iterrows()]
                gd_selected_interest_labels = st.multiselect("Selecciona audiencias", interest_labels, key="gd_interest_select")
                idxs = [interest_labels.index(l) for l in gd_selected_interest_labels]
                gd_selected_interests = interest_results_df.iloc[idxs]["resource_name"].tolist()
            elif interest_results_df is not None and interest_results_df.empty:
                st.caption("No se encontraron audiencias que coincidan con esa búsqueda.")

        with st.form("gads_display_form"):
            gd1, gd2 = st.columns(2)
            with gd1:
                gd_camp_name = st.text_input("Nombre de la campaña *", placeholder="ej. JUL26_Display_Remarketing")
                gd_budget    = st.number_input("Presupuesto diario (USD) *", min_value=1.0, value=5.0, step=1.0)
                gd_final_url = st.text_input("URL de destino *", placeholder="https://cuy.pe")
                gd_business  = st.text_input("Nombre del negocio *", value="Cuy Móvil")
            with gd2:
                gd_locations_es = st.multiselect(
                    "Países *", list(GOOGLE_LOCATION_IDS.keys()), default=["Perú"],
                )
                gd_language_label = st.selectbox("Idioma *", list(GOOGLE_LANGUAGE_IDS.keys()))
                st.caption("La campaña se crea **PAUSADA** — define la fecha de inicio directamente en Google Ads al activarla.")

            st.markdown("**📝 Títulos** (mínimo 3, máximo 5 — hasta 30 caracteres c/u)")
            gd_headline_defaults = (DISPLAY_HEADLINES_BANK + [""] * 5)[:5]
            gd_headlines = [
                st.text_input(f"Título {i + 1}", value=gd_headline_defaults[i], key=f"gd_headline_{i}")
                for i in range(5)
            ]
            gd_long_headline = st.text_input("Título largo (hasta 90 caracteres)", value=DISPLAY_LONG_HEADLINE)

            st.markdown("**🧾 Descripciones** (mínimo 2, máximo 5 — hasta 90 caracteres c/u)")
            gd_description_defaults = (DISPLAY_DESCRIPTIONS_BANK + [""] * 5)[:5]
            gd_descriptions = [
                st.text_input(f"Descripción {i + 1}", value=gd_description_defaults[i], key=f"gd_description_{i}")
                for i in range(4)
            ]

            st.markdown("**🖼️ Imágenes**")
            gi1, gi2, gi3 = st.columns(3)
            with gi1:
                gd_marketing_image = st.file_uploader("Imagen horizontal * (1200×628, relación 1.91:1)", type=["jpg", "jpeg", "png"], key="gd_marketing_img")
                if gd_marketing_image:
                    st.image(gd_marketing_image, width=180)
            with gi2:
                gd_square_image = st.file_uploader("Imagen cuadrada * (1200×1200, relación 1:1)", type=["jpg", "jpeg", "png"], key="gd_square_img")
                if gd_square_image:
                    st.image(gd_square_image, width=140)
            with gi3:
                gd_logo_image = st.file_uploader("Logo (opcional, 1200×1200)", type=["jpg", "jpeg", "png"], key="gd_logo_img")
                if gd_logo_image:
                    st.image(gd_logo_image, width=140)

            gd_submitted = st.form_submit_button("🚀 Crear campaña de Display (pausada)", type="primary")

        if gd_submitted:
            gd_headlines_clean    = [h.strip() for h in gd_headlines if h.strip()]
            gd_descriptions_clean = [d.strip() for d in gd_descriptions if d.strip()]
            gd_missing = []
            if not gd_camp_name:                     gd_missing.append("Nombre de campaña")
            if not gd_final_url:                     gd_missing.append("URL de destino")
            if not gd_business:                      gd_missing.append("Nombre del negocio")
            if not gd_locations_es:                  gd_missing.append("Al menos un país")
            if len(gd_headlines_clean) < 3:           gd_missing.append("Al menos 3 títulos")
            if not gd_long_headline.strip():          gd_missing.append("Título largo")
            if len(gd_descriptions_clean) < 2:        gd_missing.append("Al menos 2 descripciones")
            if not gd_marketing_image:                gd_missing.append("Imagen horizontal")
            if not gd_square_image:                   gd_missing.append("Imagen cuadrada")

            if gd_missing:
                st.warning("Faltan campos requeridos: " + "  ·  ".join(gd_missing))
            else:
                with st.spinner("Creando presupuesto → campaña → segmentación → grupo de anuncios → imágenes → anuncio…"):
                    try:
                        gd_result = create_display_campaign(
                            customer_id=GOOGLE_ADS_CUSTOMER_ID,
                            campaign_name=gd_camp_name,
                            daily_budget_usd=gd_budget,
                            final_url=gd_final_url,
                            headlines=gd_headlines_clean,
                            long_headline=gd_long_headline.strip(),
                            descriptions=gd_descriptions_clean,
                            business_name=gd_business,
                            marketing_image_bytes=gd_marketing_image.getvalue(),
                            square_image_bytes=gd_square_image.getvalue(),
                            logo_image_bytes=gd_logo_image.getvalue() if gd_logo_image else None,
                            location_ids=[GOOGLE_LOCATION_IDS[c] for c in gd_locations_es],
                            language_id=GOOGLE_LANGUAGE_IDS[gd_language_label],
                            age_range_keys=gd_age_keys,
                            gender_keys=gd_gender_keys,
                            user_list_resource_names=gd_selected_user_lists,
                            user_interest_resource_names=gd_selected_interests,
                        )
                        st.success("✅ ¡Campaña de Display creada exitosamente en estado PAUSADO!")
                        st.markdown(f"""
    - 📢 Campaña: `{gd_result['campaign_resource_name']}`
    - 👥 Grupo de anuncios: `{gd_result['ad_group_resource_name']}`
    - 🎨 Anuncio: `{gd_result['ad_resource_name']}`
                        """)
                        mgr_url_gads = f"https://ads.google.com/aw/campaigns?ocid=&__u={GOOGLE_ADS_CUSTOMER_ID}"
                        st.markdown(f"[🔗 Ir a Google Ads]({mgr_url_gads}) para revisarla y activarla cuando quieras.")
                        st.cache_data.clear()
                    except Exception as e:
                        st.error(f"No se pudo crear la campaña de Display: {e}")
                        st.caption(
                            "Verifica que la cuenta autorizada tenga permisos de edición sobre esta cuenta de Google Ads, "
                            "y que el Developer Token tenga el nivel de acceso necesario para crear campañas."
                        )

        st.divider()

        # ── Crear campaña de Performance Max (Google Ads) ───────────────────────────
        st.subheader("🚀 Crear campaña de Performance Max")
        st.caption(
            "Crea una campaña de Performance Max con un solo grupo de recursos (títulos, descripciones "
            "e imágenes que Google combina y distribuye en Búsqueda, Display, YouTube, Gmail y Maps). "
            "Se crea en estado **PAUSADO** — revísala en Google Ads antes de activarla. "
            "Nota: por ahora no incluye señales de audiencia (listas de remarketing / afinidad) como sí "
            "tiene Display — solo temas de búsqueda, que son la señal más simple y confiable en Pmax."
        )

        with st.form("gads_pmax_form"):
            pm1, pm2 = st.columns(2)
            with pm1:
                pm_camp_name = st.text_input("Nombre de la campaña *", placeholder="ej. SEP26_Pmax_Cambiatesindramas")
                pm_budget    = st.number_input("Presupuesto diario (USD) *", min_value=1.0, value=5.0, step=1.0, key="pm_budget")
                pm_final_url = st.text_input("URL de destino *", placeholder="https://cuy.pe", key="pm_final_url")
                pm_business  = st.text_input("Nombre del negocio *", value="Cuy Móvil", key="pm_business")
            with pm2:
                pm_locations_es = st.multiselect(
                    "Países *", list(GOOGLE_LOCATION_IDS.keys()), default=["Perú"], key="pm_locations",
                )
                pm_language_label = st.selectbox("Idioma *", list(GOOGLE_LANGUAGE_IDS.keys()), key="pm_language")
                st.caption("La campaña se crea **PAUSADA** — define la fecha de inicio directamente en Google Ads al activarla.")

            st.markdown("**📝 Títulos** (mínimo 3, máximo 15 — hasta 30 caracteres c/u)")
            pm_headline_defaults = (DISPLAY_HEADLINES_BANK + [""] * 5)[:5]
            pm_headlines = [
                st.text_input(f"Título {i + 1}", value=pm_headline_defaults[i], key=f"pm_headline_{i}")
                for i in range(5)
            ]
            pm_long_headline = st.text_input("Título largo (hasta 90 caracteres)", value=DISPLAY_LONG_HEADLINE, key="pm_long_headline")

            st.markdown("**🧾 Descripciones** (mínimo 2, máximo 5 — hasta 90 caracteres c/u)")
            pm_description_defaults = (DISPLAY_DESCRIPTIONS_BANK + [""] * 5)[:5]
            pm_descriptions = [
                st.text_input(f"Descripción {i + 1}", value=pm_description_defaults[i], key=f"pm_description_{i}")
                for i in range(4)
            ]

            st.markdown("**🔎 Temas de búsqueda** (opcional, hasta 25 — uno por línea)")
            pm_search_themes_raw = st.text_area(
                "Temas de búsqueda", placeholder="planes móviles Perú\nchip liberado\nportabilidad Claro\nllamadas ilimitadas",
                key="pm_search_themes", label_visibility="collapsed",
            )

            st.markdown("**🖼️ Imágenes** — puedes subir varias piezas de arte por tipo; Google las combina y prueba entre sí automáticamente.")
            pi1, pi2 = st.columns(2)
            with pi1:
                pm_marketing_images = st.file_uploader(
                    "Imágenes horizontales * (1200×628, relación 1.91:1 — hasta 20)",
                    type=["jpg", "jpeg", "png"], key="pm_marketing_imgs", accept_multiple_files=True,
                )
                if pm_marketing_images:
                    st.image([f for f in pm_marketing_images], width=140)
            with pi2:
                pm_square_images = st.file_uploader(
                    "Imágenes cuadradas * (1200×1200, relación 1:1 — hasta 20)",
                    type=["jpg", "jpeg", "png"], key="pm_square_imgs", accept_multiple_files=True,
                )
                if pm_square_images:
                    st.image([f for f in pm_square_images], width=120)

            pi3, pi4 = st.columns(2)
            with pi3:
                pm_logo_images = st.file_uploader(
                    "Logos (opcional, 1200×1200 — hasta 5)",
                    type=["jpg", "jpeg", "png"], key="pm_logo_imgs", accept_multiple_files=True,
                )
                if pm_logo_images:
                    st.image([f for f in pm_logo_images], width=100)
            with pi4:
                pm_portrait_images = st.file_uploader(
                    "Imágenes verticales (opcional, relación 4:5 — hasta 20)",
                    type=["jpg", "jpeg", "png"], key="pm_portrait_imgs", accept_multiple_files=True,
                )
                if pm_portrait_images:
                    st.image([f for f in pm_portrait_images], width=100)

            pm_submitted = st.form_submit_button("🚀 Crear campaña de Performance Max (pausada)", type="primary")

        if pm_submitted:
            pm_headlines_clean    = [h.strip() for h in pm_headlines if h.strip()]
            pm_descriptions_clean = [d.strip() for d in pm_descriptions if d.strip()]
            pm_search_themes_clean = [t.strip() for t in pm_search_themes_raw.splitlines() if t.strip()]
            pm_missing = []
            if not pm_camp_name:                     pm_missing.append("Nombre de campaña")
            if not pm_final_url:                     pm_missing.append("URL de destino")
            if not pm_business:                      pm_missing.append("Nombre del negocio")
            if not pm_locations_es:                  pm_missing.append("Al menos un país")
            if len(pm_headlines_clean) < 3:          pm_missing.append("Al menos 3 títulos")
            if not pm_long_headline.strip():         pm_missing.append("Título largo")
            if len(pm_descriptions_clean) < 2:       pm_missing.append("Al menos 2 descripciones")
            if not pm_marketing_images:              pm_missing.append("Al menos 1 imagen horizontal")
            if not pm_square_images:                 pm_missing.append("Al menos 1 imagen cuadrada")

            if pm_missing:
                st.warning("Faltan campos requeridos: " + "  ·  ".join(pm_missing))
            else:
                with st.spinner("Creando presupuesto → campaña → segmentación → grupo de recursos → textos → imágenes → señales…"):
                    try:
                        pm_result = create_performance_max_campaign(
                            customer_id=GOOGLE_ADS_CUSTOMER_ID,
                            campaign_name=pm_camp_name,
                            daily_budget_usd=pm_budget,
                            final_url=pm_final_url,
                            headlines=pm_headlines_clean,
                            long_headline=pm_long_headline.strip(),
                            descriptions=pm_descriptions_clean,
                            business_name=pm_business,
                            marketing_images_bytes=[f.getvalue() for f in pm_marketing_images],
                            square_images_bytes=[f.getvalue() for f in pm_square_images],
                            logo_images_bytes=[f.getvalue() for f in pm_logo_images] if pm_logo_images else None,
                            portrait_images_bytes=[f.getvalue() for f in pm_portrait_images] if pm_portrait_images else None,
                            location_ids=[GOOGLE_LOCATION_IDS[c] for c in pm_locations_es],
                            language_id=GOOGLE_LANGUAGE_IDS[pm_language_label],
                            search_themes=pm_search_themes_clean,
                        )
                        st.success("✅ ¡Campaña de Performance Max creada exitosamente en estado PAUSADO!")
                        st.markdown(f"""
    - 📢 Campaña: `{pm_result['campaign_resource_name']}`
    - 📦 Grupo de recursos: `{pm_result['asset_group_resource_name']}`
                        """)
                        mgr_url_pmax = f"https://ads.google.com/aw/campaigns?ocid=&__u={GOOGLE_ADS_CUSTOMER_ID}"
                        st.markdown(f"[🔗 Ir a Google Ads]({mgr_url_pmax}) para revisarla y activarla cuando quieras.")
                        st.cache_data.clear()
                    except Exception as e:
                        st.error(f"No se pudo crear la campaña de Performance Max: {e}")
                        st.caption(
                            "Verifica que la cuenta autorizada tenga permisos de edición sobre esta cuenta de Google Ads, "
                            "y que el Developer Token tenga el nivel de acceso necesario para crear campañas."
                        )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — WEB ANALYTICS (Google Analytics 4)
# ══════════════════════════════════════════════════════════════════════════════
elif nav_section == "📈 Web Analytics":
    st.header("📈 Web Analytics")

    if "gcp_service_account" not in st.secrets:
        st.error("Falta configurar la cuenta de servicio de Google. Agrega el bloque `[gcp_service_account]` en Streamlit Cloud → Settings → Secrets.")
        st.stop()

    if ga_date_preset == "custom" and not (ga_since_str and ga_until_str):
        st.info("Selecciona un rango de fechas válido en el panel izquierdo para continuar.")
        st.stop()

    ga_start, ga_end = get_ga_date_range(ga_date_preset, ga_since_str, ga_until_str)
    st.caption(f"Período: **{ga_start}** a **{ga_end}** · Dominio: **{ga_host_label}** · Propiedad GA4: `{GA_PROPERTY_ID}`")

    try:
        with st.spinner("Cargando datos de Google Analytics..."):
            ga_summary = fetch_ga_summary(GA_PROPERTY_ID, ga_start, ga_end, host_filter=ga_host_filter)
            ga_timeseries = fetch_ga_timeseries(GA_PROPERTY_ID, ga_start, ga_end)
            ga_channels = fetch_ga_channels(GA_PROPERTY_ID, ga_start, ga_end, host_filter=ga_host_filter)
            ga_top_pages = fetch_ga_top_pages(GA_PROPERTY_ID, ga_start, ga_end, host_filter=ga_host_filter)
    except Exception as e:
        st.error(f"No se pudo conectar con Google Analytics: {e}")
        st.caption("Verifica que la cuenta de servicio tenga acceso de 'Viewer' en la propiedad GA4 y que el Property ID sea correcto.")
        st.stop()

    # KPIs
    st.subheader("Resumen del período")
    a1, a2, a3, a4, a5, a6 = st.columns(6)
    a1.metric("👥 Sesiones",       f"{ga_summary['sessions']:,.0f}")
    a2.metric("🙋 Usuarios",       f"{ga_summary['users']:,.0f}")
    a3.metric("📄 Vistas de página", f"{ga_summary['pageviews']:,.0f}")
    a4.metric("🎯 Conversiones",   f"{ga_summary['conversions']:,.0f}")
    a5.metric("↩️ Tasa de rebote", f"{ga_summary['bounce_rate']:.1f}%")
    a6.metric("⏱️ Duración prom.", f"{ga_summary['avg_duration']:.0f} s")

    st.divider()

    # Gráfico de tendencia + canales
    g1, g2 = st.columns(2)
    with g1:
        st.subheader("Sesiones por día")
        if not ga_timeseries.empty:
            fig = px.line(
                ga_timeseries, x="Fecha", y=["Sesiones", "Usuarios"], markers=True,
                color_discrete_sequence=[BRAND["purple"], BRAND["lemon_dark"]],
            )
            fig.update_layout(height=380, margin=dict(l=0, r=0, t=0, b=0), legend_title="")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sin datos para este período.")
    with g2:
        st.subheader("Sesiones por canal")
        if not ga_channels.empty:
            channels_sorted = ga_channels.sort_values("Sesiones")
            max_sesiones = channels_sorted["Sesiones"].max()
            fig = px.bar(
                channels_sorted,
                x="Sesiones", y="Canal", orientation="h",
                color="Conversiones", color_continuous_scale=PURPLE_SCALE,
                text="Sesiones",
            )
            fig.update_traces(texttemplate="%{text:.0f}", textposition="outside", cliponaxis=False)
            fig.update_layout(
                height=380, margin=dict(l=0, r=60, t=0, b=0), yaxis_title="",
                xaxis=dict(range=[0, max_sesiones * 1.18]),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sin datos de canales para este período.")

    st.divider()

    # Tráfico proveniente de redes sociales pagadas
    st.subheader("🔵 Tráfico vía Paid Social")
    paid_social_row = ga_channels[ga_channels["Canal"].str.contains("Paid Social", case=False, na=False)]
    sessions_paid_social = paid_social_row["Sesiones"].sum() if not paid_social_row.empty else 0
    st.metric("Sesiones vía Paid Social", f"{sessions_paid_social:,.0f}")
    st.caption("Para comparar contra el gasto de Meta Ads del mismo período, revisa la sección '📊 Meta Ads' en el panel izquierdo.")

    st.divider()

    # Top páginas
    st.subheader("Páginas más visitadas")
    if not ga_top_pages.empty:
        st.dataframe(
            ga_top_pages.style.format({"Vistas": "{:,.0f}", "Usuarios": "{:,.0f}"}),
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("Sin datos de páginas para este período.")

    st.divider()

    # Desglose por dominio — cuy.pe vs secure.guinea.pe (siempre lado a lado, sin importar el filtro de dominio)
    st.subheader("📱 Desglose por dominio")
    st.caption("Sesiones, usuarios, tiempo en sitio, rebote y páginas top separados por cada dominio.")
    try:
        with st.spinner("Separando métricas por dominio..."):
            ga_by_domain = fetch_ga_by_domain(GA_PROPERTY_ID, ga_start, ga_end, top_limit=5)
    except Exception as e:
        ga_by_domain = None
        st.warning(f"No se pudo separar por dominio: {e}")

    if ga_by_domain:
        d1, d2 = st.columns(2)
        for col, host, label in zip([d1, d2], ["cuy.pe", "secure.guinea.pe"], ["🐹 cuy.pe", "🔒 secure.guinea.pe"]):
            with col:
                st.markdown(f"**{label}**")
                s = ga_by_domain[host]["summary"]
                tp = ga_by_domain[host]["top_pages"]
                if s and s["sessions"]:
                    m1, m2 = st.columns(2)
                    m1.metric("👥 Sesiones", f"{s['sessions']:,.0f}")
                    m2.metric("🙋 Usuarios", f"{s['users']:,.0f}")
                    m3, m4 = st.columns(2)
                    m3.metric("⏱️ Tiempo en sitio", f"{s['avg_duration']:.0f} s")
                    m4.metric("↩️ Rebote", f"{s['bounce_rate']:.1f}%")
                    if host == "secure.guinea.pe":
                        st.caption("🔻 Funnel de compra (pirámide invertida)")
                    else:
                        st.caption("Páginas más visitadas")
                    render_domain_top_pages(tp, is_funnel=ga_by_domain[host].get("is_funnel", False), height=200)
                else:
                    st.info(f"Sin datos para **{host}** en este período.")

        if ga_by_domain["secure.guinea.pe"].get("summary") and ga_by_domain["secure.guinea.pe"]["summary"]["sessions"]:
            st.markdown("**🔒 ¿De dónde llegan las visitas a secure.guinea.pe?**")
            st.caption("Fuente/medio de la sesión: Ads pagados, cuy.pe, blog.cuy.pe, orgánico, directo, etc.")
            render_traffic_origin(ga_by_domain["secure.guinea.pe"].get("traffic_origin"))

else:  # 🖱️ Clarity
    st.header("🖱️ Microsoft Clarity")
    st.caption("Señales de comportamiento e interacción por página y por dispositivo (rage clicks, dead clicks, etc).")

    if not CLARITY_API_TOKEN:
        st.error("Falta configurar el token de Clarity. Agrega `CLARITY_API_TOKEN` en Streamlit Cloud → Settings → Secrets.")
        st.stop()

    hc1, hc2 = st.columns([3, 1])
    with hc1:
        st.info(
            "La API de Clarity no expone el mapa de calor visual (posición exacta de clics sobre la página) — "
            "eso solo vive en el dashboard nativo de Clarity. Aquí abajo tienes gráficos interactivos con los "
            "números reales (pasa el cursor sobre las barras para ver el detalle), filtrables por dispositivo y página. "
            "Para el heatmap visual real, usa el botón de la derecha."
        )
    with hc2:
        st.link_button("🔥 Ver heatmap visual en Clarity", CLARITY_PROJECT_URL, use_container_width=True)

    st.caption(f"Ventana: **{clarity_days_label}** · Desglose: **{clarity_dim1_label}** + **{clarity_dim2_label}** · Límite: 10 llamadas/día por proyecto.")

    try:
        with st.spinner("Cargando datos de Clarity..."):
            clarity_data = fetch_clarity_insights(clarity_num_days, clarity_dimension1, clarity_dimension2)
    except Exception as e:
        st.error(f"No se pudo conectar con Clarity: {e}")
        st.stop()

    if not clarity_data:
        st.info("Sin datos disponibles para este período.")
        st.stop()

    metric_names_found = [str(block.get("metricName", "(sin nombre)")) for block in clarity_data]

    def _find_col_name(df, *candidates):
        lower_map = {str(c).lower(): c for c in df.columns}
        for cand in candidates:
            if cand.lower() in lower_map:
                return lower_map[cand.lower()]
        return None

    def _numeric_cols(df, exclude=()):
        cols = []
        for c in df.columns:
            if c in exclude:
                continue
            coerced = pd.to_numeric(df[c], errors="coerce")
            if coerced.notna().sum() > 0:
                cols.append(c)
        return cols

    def _classify_domain(url) -> str:
        u = str(url).lower()
        if "cuy.pe" in u:
            return "cuy.pe"
        if "secure.guinea.pe" in u:
            return "secure.guinea.pe"
        return "Otro"

    # Detecta si hay desglose por dispositivo y/o URL en la respuesta, para armar los filtros
    device_values = set()
    domain_available = False
    for block in clarity_data:
        df_tmp = pd.DataFrame(block.get("information", []))
        dcol = _find_col_name(df_tmp, "Device")
        if dcol:
            device_values.update(df_tmp[dcol].dropna().astype(str).unique().tolist())
        ucol = _find_col_name(df_tmp, "URL", "Url", "PageUrl", "Page")
        if ucol:
            domain_available = True

    # KPIs generales de tráfico
    st.subheader("Resumen de tráfico")
    traffic_summary = clarity_traffic_summary(clarity_data)
    if traffic_summary:
        c1, c2, c3 = st.columns(3)
        c1.metric("👥 Sesiones totales", f"{traffic_summary['sessions']:,.0f}")
        c2.metric("🤖 Sesiones de bots", f"{traffic_summary['bot_sessions']:,.0f}")
        c3.metric("🙋 Usuarios únicos", f"{traffic_summary['users']:,.0f}")
    else:
        st.info("Sin métricas de tráfico para este período (el bloque 'Traffic' no vino en la respuesta).")

    st.divider()

    # Filtros interactivos de dispositivo y dominio
    if device_values:
        chosen_device = st.radio(
            "📱 Ver interacciones de:", ["Todos"] + sorted(device_values),
            horizontal=True, key="clarity_device_filter",
        )
    else:
        chosen_device = "Todos"
        st.caption("💡 Elige 'Dispositivo' en el filtro 'Desglosar por' del panel izquierdo para poder comparar Desktop vs Mobile aquí.")

    if domain_available:
        chosen_domain = st.radio(
            "🌐 Ver dominio:", ["Todos", "cuy.pe", "secure.guinea.pe", "Otro"],
            horizontal=True, key="clarity_domain_filter",
        )
    else:
        chosen_domain = "Todos"
        st.caption("💡 Elige 'URL' en alguno de los desgloses del panel izquierdo para poder separar cuy.pe vs secure.guinea.pe aquí.")

    st.divider()

    # Todas las métricas, mostradas como gráficos interactivos (hover = detalle de interacciones)
    st.subheader("📊 Métricas interactivas")
    st.caption(f"Métricas recibidas en esta respuesta: {', '.join(metric_names_found) if metric_names_found else '(ninguna)'}")

    for i, block in enumerate(clarity_data):
        metric_name = str(block.get("metricName", "(sin nombre)"))
        df = pd.DataFrame(block.get("information", []))
        label = CLARITY_METRIC_LABELS.get(metric_name, f"📌 {metric_name}")
        chart_key = f"clarity_chart_{i}_{metric_name}".replace(" ", "_")
        st.markdown(f"**{label}**")

        if df.empty:
            st.caption("Sin filas para esta métrica en el período/desglose seleccionado.")
            continue

        # Filtra por el dispositivo elegido arriba, si esta métrica trae esa columna
        device_col = _find_col_name(df, "Device")
        if device_col and chosen_device != "Todos":
            df = df[df[device_col].astype(str) == chosen_device]

        # Filtra por dominio (cuy.pe / secure.guinea.pe), si esta métrica trae columna de URL
        url_col = _find_col_name(df, "URL", "Url", "PageUrl", "Page")
        if url_col and chosen_domain != "Todos":
            df = df[df[url_col].apply(_classify_domain) == chosen_domain]

        if df.empty:
            st.caption(f"Sin datos para **{chosen_device}** / **{chosen_domain}** en esta métrica.")
            continue

        dim_col = url_col or device_col or (df.columns[0] if len(df.columns) else None)
        num_cols = _numeric_cols(df, exclude={dim_col} if dim_col else set())

        if dim_col and num_cols:
            value_col = num_cols[0]
            plot_df = df.copy()
            plot_df[value_col] = pd.to_numeric(plot_df[value_col], errors="coerce").fillna(0)
            plot_df[dim_col] = plot_df[dim_col].astype(str)
            plot_df = plot_df.sort_values(value_col, ascending=True).tail(15)
            hover_cols = [c for c in df.columns if c != dim_col]
            fig = px.bar(
                plot_df, x=value_col, y=dim_col, orientation="h",
                color=value_col, color_continuous_scale=PURPLE_SCALE,
                hover_data=hover_cols,
            )
            fig.update_layout(
                height=max(280, 30 * len(plot_df)), margin=dict(l=0, r=20, t=10, b=0),
                yaxis_title="", xaxis_title=value_col, coloraxis_showscale=False,
            )
            st.plotly_chart(fig, use_container_width=True, key=chart_key)
            st.caption("Pasa el cursor sobre cada barra para ver el detalle completo de esa fila.")

        with st.expander(f"Ver tabla completa — {label} #{i}"):
            st.dataframe(df, use_container_width=True, hide_index=True)

    st.caption("Nota: los nombres de columnas provienen tal cual de la API de Clarity — cada métrica puede traer campos distintos.")

    with st.expander("🔧 Ver respuesta cruda de la API (debug)"):
        st.json(clarity_data)
