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
from datetime import datetime, timezone, date

# ── Configuración de página ──────────────────────────────────────────────────
st.set_page_config(
    page_title="Cuy Móvil · Meta Ads",
    page_icon="🦔",
    layout="wide",
    initial_sidebar_state="expanded",
)

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
def fetch_campaigns(account_id: str, date_preset: str) -> pd.DataFrame:
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
    rows = []
    for c in campaigns:
        status   = c.get(Campaign.Field.effective_status, "")
        insights = c.get_insights(fields=INSIGHT_FIELDS, params={"date_preset": date_preset})
        if not insights:
            continue
        ins       = insights[0]
        start_raw = c.get(Campaign.Field.start_time, "")
        try:
            start_dt    = datetime.fromisoformat(start_raw)
            dias_activa = (datetime.now(tz=start_dt.tzinfo) - start_dt).days
        except Exception:
            dias_activa = 0
        rows.append({
            "id":          c[Campaign.Field.id],
            "Campaña":     c[Campaign.Field.name],
            "Estado":      status,
            "Objetivo":    c.get(Campaign.Field.objective, ""),
            "Presupuesto": int(c.get(Campaign.Field.daily_budget, 0)) / 100,
            "Días activa": dias_activa,
            "Gasto":       float(ins.get("spend", 0)),
            "Impresiones": int(ins.get("impressions", 0)),
            "Clics":       int(ins.get("clicks", 0)),
            "CTR":         float(ins.get("ctr", 0)),
            "CPC":         float(ins.get("cpc", 0)),
            "Alcance":     int(ins.get("reach", 0)),
            "Frecuencia":  float(ins.get("frequency", 0)),
        })
    return pd.DataFrame(rows)

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

# ── IA de segmentación (basada en reglas) ─────────────────────────────────────
def ai_suggest_segmentation(description: str) -> dict:
    desc = description.lower()
    result = {
        "countries": ["PE"],
        "age_min": 18,
        "age_max": 45,
        "gender": "all",
        "interest_keywords": [],
        "notes": [],
    }

    # Competencia / páginas de terceros
    if any(kw in desc for kw in ["competencia", "competidor", "otras marcas", "páginas similares",
                                  "paginas similares", "claro", "entel", "bitel", "movistar",
                                  "interactuan", "interactúan"]):
        result["notes"].append("⚠️ **Meta no permite apuntar directamente a seguidores de páginas de competidores** (restricción de privacidad). Alternativas:")
        result["notes"].append("→ **Intereses por marca**: busca 'Claro', 'Entel', 'Bitel', 'Movistar' abajo — si aparecen como intereses, úsalos.")
        result["notes"].append("→ **Lookalike audience**: sube tu lista de clientes en Meta y encontrará perfiles similares a los de la competencia.")
        result["notes"].append("→ **Intereses por industria**: 'Telefonía móvil', 'Smartphones', 'Telecomunicaciones'.")
        result["interest_keywords"].extend(["Telefonía móvil", "Smartphones", "Telecomunicaciones", "4G LTE"])

    # Telco / datos / planes
    if any(kw in desc for kw in ["celular", "móvil", "movil", "teléfono", "telefono", "smartphone",
                                  "plan", "ilimitado", "datos", "internet", "prepago", "postpago", "chip"]):
        result["interest_keywords"].extend(["Smartphones", "Telefonía móvil", "Internet móvil", "Aplicaciones móviles"])

    # Jóvenes / Gen Z
    if any(kw in desc for kw in ["jóvenes", "jovenes", "millennials", "gen z", "generación z",
                                  "universitarios", "estudiantes", "chicos"]):
        result["age_min"], result["age_max"] = 16, 28
        result["interest_keywords"].extend(["TikTok", "Instagram", "Videojuegos", "Música", "Streaming"])

    # Adultos / profesionales
    if any(kw in desc for kw in ["adultos", "profesionales", "trabajadores", "ejecutivos",
                                  "empresarios", "padres", "madres"]):
        result["age_min"], result["age_max"] = 28, 55
        result["interest_keywords"].extend(["Negocios", "Productividad", "Finanzas personales"])

    # Género
    if any(kw in desc for kw in ["mujeres", "femenino", "mamás", "madre"]):
        result["gender"] = "female"
    if any(kw in desc for kw in ["hombres", "masculino", "hombre"]):
        result["gender"] = "male"

    # Gamers
    if any(kw in desc for kw in ["gamers", "gaming", "videojuegos", "esports"]):
        result["age_min"], result["age_max"] = 15, 35
        result["interest_keywords"].extend(["Videojuegos", "eSports", "Mobile gaming"])

    # Redes sociales
    if any(kw in desc for kw in ["redes sociales", "instagram", "tiktok", "youtube"]):
        result["interest_keywords"].extend(["Instagram", "TikTok", "YouTube", "Creadores de contenido"])

    # Precio / ahorro
    if any(kw in desc for kw in ["precio", "barato", "económico", "economico",
                                  "oferta", "descuento", "ahorro", "promo"]):
        result["interest_keywords"].extend(["Cupones y descuentos", "Compras online"])

    # Deportes
    if any(kw in desc for kw in ["deportes", "fútbol", "futbol", "gym", "fitness", "running"]):
        result["interest_keywords"].extend(["Deportes", "Fútbol", "Fitness y bienestar"])

    # LATAM
    if any(kw in desc for kw in ["latinoamérica", "latinoamerica", "latam",
                                  "sudamérica", "toda la región"]):
        result["countries"] = ["PE", "MX", "CO", "AR", "CL", "EC"]
        result["notes"].append("→ Se sugiere apuntar a múltiples países de LATAM.")

    # Deduplicar y fallback
    result["interest_keywords"] = list(dict.fromkeys(result["interest_keywords"]))
    if not result["interest_keywords"]:
        result["interest_keywords"] = ["Telefonía móvil", "Smartphones", "Tecnología"]

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

# ── Creación completa de anuncio ──────────────────────────────────────────────
def create_full_ad(
    account_id, page_id, camp_name, objective, daily_budget_usd,
    adset_name, countries, age_min, age_max, genders, interest_ids,
    image_bytes, image_ext, primary_text, headline, ad_description,
    destination_url, cta_type, start_date,
):
    init_api()

    # 1. Campaña
    camp = AdAccount(account_id).create_campaign(
        fields=[Campaign.Field.id],
        params={
            Campaign.Field.name:                 camp_name,
            Campaign.Field.objective:             objective,
            Campaign.Field.status:                "PAUSED",
            Campaign.Field.special_ad_categories: [],
        }
    )
    camp_id = camp[Campaign.Field.id]

    # 2. Conjunto de anuncios
    targeting = {
        "geo_locations": {"countries": countries},
        "age_min": age_min,
        "age_max": age_max,
    }
    if genders:
        targeting["genders"] = genders
    if interest_ids:
        targeting["flexible_spec"] = [{"interests": [{"id": str(iid)} for iid in interest_ids]}]

    start_ts = int(datetime.combine(start_date, datetime.min.time()).timestamp())

    adset = AdAccount(account_id).create_ad_set(
        fields=[AdSet.Field.id],
        params={
            AdSet.Field.name:              adset_name,
            AdSet.Field.campaign_id:       camp_id,
            AdSet.Field.daily_budget:      int(daily_budget_usd * 100),
            AdSet.Field.billing_event:     "IMPRESSIONS",
            AdSet.Field.optimization_goal: "LINK_CLICKS",
            AdSet.Field.targeting:         targeting,
            AdSet.Field.status:            "PAUSED",
            AdSet.Field.start_time:        start_ts,
        }
    )
    adset_id = adset[AdSet.Field.id]

    # 3. Subir imagen
    ext = ("." + image_ext.lower().replace("jpeg", "jpg")) if image_ext else ".jpg"
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(image_bytes)
        tmp_path = tmp.name
    try:
        img_obj = AdImage(parent_id=account_id)
        img_obj[AdImage.Field.filename] = tmp_path
        img_obj.remote_create()
        image_hash = img_obj[AdImage.Field.hash]
    finally:
        os.unlink(tmp_path)

    # 4. Creatividad
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

    # 5. Anuncio
    ad = AdAccount(account_id).create_ad(
        fields=[Ad.Field.id],
        params={
            Ad.Field.name:     camp_name,
            Ad.Field.adset_id: adset_id,
            Ad.Field.creative: {"creative_id": creative_id},
            Ad.Field.status:   "PAUSED",
        }
    )
    return {
        "campaign_id": camp_id,
        "adset_id":    adset_id,
        "creative_id": creative_id,
        "ad_id":       ad[Ad.Field.id],
    }

# ══════════════════════════════════════════════════════════════════════════════
# UI
# ══════════════════════════════════════════════════════════════════════════════
col_title, col_time = st.columns([4, 1])
with col_title:
    st.title("🦔 Cuy Móvil · Meta Ads Dashboard")
with col_time:
    st.caption(f"📅 {datetime.now().strftime('%d %b %Y, %H:%M')}")

with st.sidebar:
    st.header("Filtros")
    account_label = st.selectbox("Cuenta", list(ACCOUNTS.keys()))
    account_id    = ACCOUNTS[account_label]
    date_label    = st.selectbox("Período", list(DATE_OPTIONS.keys()), index=2)
    date_preset   = DATE_OPTIONS[date_label]
    show_paused   = st.toggle("Incluir campañas pausadas", value=False)
    if st.button("🔄 Actualizar datos", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    st.caption("Los cambios ejecutados son inmediatos y reales.")

if not ACCESS_TOKEN:
    st.error("Falta ACCESS_TOKEN. Agrégalo en Streamlit Cloud → Settings → Secrets.")
    st.stop()

# ── Tabs principales ──────────────────────────────────────────────────────────
tab_dash, tab_create = st.tabs(["📊 Dashboard", "➕ Crear Anuncio"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
with tab_dash:
    with st.spinner("Cargando datos de Meta Ads..."):
        df = fetch_campaigns(account_id, date_preset)

    if df.empty:
        st.info("No hay datos disponibles para este período y cuenta.")
    else:
        view_df = df if show_paused else df[df["Estado"] == "ACTIVE"]

        # KPIs
        st.subheader("Resumen del período")
        k1, k2, k3, k4, k5, k6 = st.columns(6)
        total_spend       = view_df["Gasto"].sum()
        total_impressions = view_df["Impresiones"].sum()
        total_clicks      = view_df["Clics"].sum()
        avg_ctr           = (total_clicks / total_impressions * 100) if total_impressions else 0
        avg_cpc           = (total_spend / total_clicks) if total_clicks else 0
        total_reach       = view_df["Alcance"].sum()
        k1.metric("💰 Gasto",       f"${total_spend:,.2f}")
        k2.metric("👁️ Impresiones", f"{total_impressions:,.0f}")
        k3.metric("🖱️ Clics",       f"{total_clicks:,.0f}")
        k4.metric("📊 CTR",         f"{avg_ctr:.2f}%")
        k5.metric("💲 CPC",         f"${avg_cpc:.3f}")
        k6.metric("🎯 Alcance",     f"{total_reach:,.0f}")
        st.divider()

        # Gráficos
        active_df = df[df["Estado"] == "ACTIVE"]
        if not active_df.empty:
            g1, g2 = st.columns(2)
            with g1:
                st.subheader("Gasto por campaña")
                fig = px.bar(
                    active_df.sort_values("Gasto"),
                    x="Gasto", y="Campaña", orientation="h",
                    color="CTR", color_continuous_scale="RdYlGn",
                    color_continuous_midpoint=active_df["CTR"].median(),
                    labels={"Gasto": "Gasto (USD)", "CTR": "CTR%"}, text="Gasto",
                )
                fig.update_traces(texttemplate="$%{text:.0f}", textposition="outside")
                fig.update_layout(height=380, margin=dict(l=0, r=20, t=0, b=0),
                                  yaxis_title="", coloraxis_showscale=False)
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
        table_df = view_df[["Campaña", "Estado", "Días activa", "Gasto", "Impresiones",
                             "Clics", "CTR", "CPC", "Alcance", "Frecuencia"]].copy()
        st.dataframe(
            table_df.style
                .format({"Gasto": "${:.2f}", "CPC": "${:.3f}", "CTR": "{:.2f}%",
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
    p1a, p1b, p1c = st.columns(3)
    with p1a:
        camp_name = st.text_input("Nombre de la campaña *", placeholder="ej. JUL26_Ventas_Ilimitados")
    with p1b:
        obj_label = st.selectbox("Objetivo *", list(OBJECTIVES.keys()))
        objective = OBJECTIVES[obj_label]
    with p1c:
        daily_budget = st.number_input("Presupuesto diario (USD) *", min_value=1.0, value=10.0, step=1.0)

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
                with st.spinner("Analizando tu audiencia..."):
                    sugg = ai_suggest_segmentation(ai_description)
                st.session_state["ai_sugg"] = sugg
            else:
                st.warning("Escribe una descripción primero.")

        if st.session_state.get("ai_sugg"):
            sugg = st.session_state["ai_sugg"]
            gender_label = {"all": "Todos", "male": "Hombres", "female": "Mujeres"}.get(sugg["gender"], "Todos")
            sc1, sc2, sc3 = st.columns(3)
            sc1.markdown(f"🌍 **Países:** {', '.join(sugg['countries'])}")
            sc2.markdown(f"👤 **Edad:** {sugg['age_min']}–{sugg['age_max']}")
            sc3.markdown(f"⚧️ **Género:** {gender_label}")
            if sugg["interest_keywords"]:
                st.markdown(f"🎯 **Intereses sugeridos:** {', '.join(sugg['interest_keywords'])}")
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

    selected_interest_ids = []
    if "interest_results" in st.session_state:
        results = st.session_state["interest_results"]
        if results:
            options_map = {
                f"{r['name']}  (~{r['audience']:,.0f} personas)": r["id"] for r in results
            }
            chosen = st.multiselect("Selecciona intereses:", list(options_map.keys()),
                                    key="chosen_interests")
            selected_interest_ids = [options_map[c] for c in chosen]
        else:
            st.info("Sin resultados — prueba otro término.")

    st.divider()

    # ── PASO 3: Creatividad ───────────────────────────────────────────────────
    st.subheader("3️⃣  Creatividad del anuncio")

    uploaded_image = st.file_uploader(
        "Imagen del anuncio * (JPG o PNG — mín. 1080×1080 px recomendado)",
        type=["jpg", "jpeg", "png"],
    )
    if uploaded_image:
        st.image(uploaded_image, caption="Vista previa", width=280)

    cr1, cr2 = st.columns(2)
    with cr1:
        primary_text = st.text_area(
            "Texto principal *",
            placeholder="Ej: ¡Conéctate sin límites con Cuy Móvil! 🦔 Planes desde S/39.",
            height=100,
        )
        headline = st.text_input("Titular *", placeholder="Ej: Plan Ilimitado desde S/39")
    with cr2:
        ad_description = st.text_input("Descripción", placeholder="Ej: Sin cortes, sin límites. Pruébalo gratis 7 días.")
        destination_url = st.text_input("URL de destino *", placeholder="https://cuymovil.pe")
        cta_label = st.selectbox("Botón de acción (CTA)", list(CTA_OPTIONS.keys()))
        cta_type  = CTA_OPTIONS[cta_label]

    st.divider()

    # ── PASO 4: Detalles finales ──────────────────────────────────────────────
    st.subheader("4️⃣  Detalles finales")
    d1, d2 = st.columns(2)
    with d1:
        adset_name = st.text_input("Nombre del conjunto de anuncios",
                                   value=(camp_name + "_Conjunto") if camp_name else "")
        start_date = st.date_input("Fecha de inicio", value=date.today())
    with d2:
        st.info(f"**Cuenta:** {account_label}\n\n**Presupuesto:** ${daily_budget:.2f}/día")

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

    if missing:
        st.warning("Faltan campos requeridos: " + "  ·  ".join(missing))
        st.button("🚀 Crear anuncio (pausado)", type="primary", disabled=True)
    else:
        if st.button("🚀 Crear anuncio (pausado)", type="primary"):
            with st.spinner("Creando campaña → conjunto → imagen → creatividad → anuncio…"):
                try:
                    image_bytes = uploaded_image.read()
                    image_ext   = uploaded_image.name.rsplit(".", 1)[-1] if "." in uploaded_image.name else "jpg"

                    result = create_full_ad(
                        account_id=account_id,
                        page_id=page_id_input,
                        camp_name=camp_name,
                        objective=objective,
                        daily_budget_usd=daily_budget,
                        adset_name=adset_name or camp_name + "_Conjunto",
                        countries=selected_countries,
                        age_min=age_min,
                        age_max=age_max,
                        genders=genders,
                        interest_ids=selected_interest_ids,
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
                        st.markdown(f"""
**IDs generados:**
- 📢 Campaña: `{result['campaign_id']}`
- 👥 Conjunto: `{result['adset_id']}`
- 🎨 Creatividad: `{result['creative_id']}`
- 📌 Anuncio: `{result['ad_id']}`
                        """)
                    with r2:
                        mgr_url = f"https://www.facebook.com/adsmanager/manage/campaigns?act={account_id.replace('act_', '')}"
                        st.markdown(f"### [📋 Ver en Ads Manager]({mgr_url})")
                        st.info("Cuando estés lista, actívalo desde Ads Manager.")
                    st.cache_data.clear()

                except Exception as e:
                    st.error(f"Error al crear el anuncio: {e}")
                    st.caption("Abre los logs en 'Manage app' para ver el detalle.")
