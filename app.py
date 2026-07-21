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

# ── Creación completa de anuncio (soporta 1 o varios conjuntos por plataforma) ─
def create_full_ad(
    account_id, page_id, camp_name, objective,
    adset_configs,  # lista: [{"platforms": ["facebook","instagram"], "budget": 10.0, "suffix": ""}]
    countries, age_min, age_max, genders, interest_ids, custom_audience_ids,
    image_bytes, image_ext, primary_text, headline, ad_description,
    destination_url, cta_type, start_date,
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

    # 2. Imagen y creatividad (una sola, compartida por todos los conjuntos)
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

def fetch_ga_by_domain(property_id: str, start_date: str, end_date: str, top_limit: int = 5) -> dict:
    """Trae el desglose de métricas de Web Analytics separado por dominio (cuy.pe / secure.guinea.pe)."""
    result = {}
    for host in ["cuy.pe", "secure.guinea.pe"]:
        result[host] = {
            "summary":   fetch_ga_summary(property_id, start_date, end_date, host_filter=host),
            "top_pages": fetch_ga_top_pages(property_id, start_date, end_date, limit=top_limit, host_filter=host),
        }
    return result

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
# ANÁLISIS UNIFICADO (Resumen) — narrativa automática + preguntas libres
# ══════════════════════════════════════════════════════════════════════════════
def generate_full_analysis(meta_df, ga_summary, ga_channels, ga_top_pages=None) -> str:
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

    lines.append("\n_Nota: Google Ads aún no está conectado a este dashboard. Revisa la sección 'Clarity' para señales de frustración de usuarios._")
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
# UI
# ══════════════════════════════════════════════════════════════════════════════
col_title, col_time = st.columns([4, 1])
with col_title:
    st.title("🐹 Cuy Móvil · Meta Ads Dashboard")
with col_time:
    st.caption(f"📅 {datetime.now(PERU_TZ).strftime('%d %b %Y, %H:%M')} (hora Perú)")

with st.sidebar:
    st.header("🗂️ Accesos")
    nav_section = st.radio(
        "Selecciona una plataforma",
        ["📋 Resumen", "📊 Meta Ads", "📈 Web Analytics", "🖱️ Clarity"],
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
                        if tp is not None and not tp.empty:
                            st.dataframe(
                                tp.style.format({"Vistas": "{:,.0f}", "Usuarios": "{:,.0f}"}),
                                use_container_width=True, hide_index=True, height=180,
                            )
                    else:
                        st.info(f"Sin datos para **{host}** en este período.")
    else:
        st.info("Google Analytics no está conectado.")

    st.divider()

    # Análisis narrativo automático
    st.subheader("🧠 Análisis completo")
    st.markdown(generate_full_analysis(meta_df_r, ga_summary_r, ga_channels_r, ga_top_pages_r))

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
    tab_dash, tab_create = st.tabs(["📊 Dashboard", "➕ Crear Anuncio"])

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

            # Gráficos
            active_df = apply_platform_filter(df[df["Estado"] == "ACTIVE"], platform_filter)
            if not active_df.empty:
                g1, g2 = st.columns(2)
                with g1:
                    st.subheader("Gasto por campaña")
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
                        height=380, margin=dict(l=0, r=60, t=0, b=0),
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
        st.header("➕ Crear nuevo anuncio")
        st.caption("El anuncio se crea en estado **PAUSADO**. Revísalo en Ads Manager antes de activarlo.")

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
            if not uploaded_image or not page_id_input or not destination_url:
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
        if not uploaded_image:     missing.append("Imagen del anuncio")
        if not selected_countries: missing.append("Al menos un país")
        if not platforms_selected: missing.append("Al menos una plataforma (Facebook o Instagram)")

        if missing:
            st.warning("Faltan campos requeridos: " + "  ·  ".join(missing))
            st.button("🚀 Crear anuncio (pausado)", type="primary", disabled=True)
        else:
            if st.button("🚀 Crear anuncio (pausado)", type="primary"):
                with st.spinner("Creando campaña → conjunto(s) → imagen → creatividad → anuncio(s)…"):
                    try:
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
                    if tp is not None and not tp.empty:
                        st.caption("Páginas más visitadas")
                        st.dataframe(
                            tp.style.format({"Vistas": "{:,.0f}", "Usuarios": "{:,.0f}"}),
                            use_container_width=True, hide_index=True, height=200,
                        )
                    else:
                        st.caption("Sin páginas registradas para este dominio en el período.")
                else:
                    st.info(f"Sin datos para **{host}** en este período.")

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
