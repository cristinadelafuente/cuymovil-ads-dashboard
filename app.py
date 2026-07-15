import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.campaign import Campaign
import anthropic
import json
import os
from datetime import datetime

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

ACCESS_TOKEN  = get_secret("ACCESS_TOKEN")
APP_ID        = get_secret("APP_ID") or "1605641477375351"
APP_SECRET    = get_secret("APP_SECRET")
CLAUDE_KEY    = get_secret("CLAUDE_API_KEY")

# ── Constantes ───────────────────────────────────────────────────────────────
ACCOUNTS = {
    "Norte Digital [NDPE] — Cuy Móvil": "act_4207138246212675",
    "Cuy Móvil (histórico)":            "act_10159339378105150",
}

DATE_OPTIONS = {
    "Últimos 7 días":   "last_7d",
    "Últimos 14 días":  "last_14d",
    "Últimos 30 días":  "last_30d",
    "Últimos 90 días":  "last_90d",
    "Este mes":         "this_month",
    "Mes anterior":     "last_month",
}

INSIGHT_FIELDS = ["spend", "impressions", "clicks", "ctr", "cpc", "reach", "frequency"]

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
        status = c.get(Campaign.Field.effective_status, "")
        insights = c.get_insights(
            fields=INSIGHT_FIELDS,
            params={"date_preset": date_preset},
        )
        if not insights:
            continue
        ins = insights[0]
        rows.append({
            "id":           c[Campaign.Field.id],
            "Campaña":      c[Campaign.Field.name],
            "Estado":       status,
            "Objetivo":     c.get(Campaign.Field.objective, ""),
            "Presupuesto":  int(c.get(Campaign.Field.daily_budget, 0)) / 100,
            "Gasto":        float(ins.get("spend", 0)),
            "Impresiones":  int(ins.get("impressions", 0)),
            "Clics":        int(ins.get("clicks", 0)),
            "CTR":          float(ins.get("ctr", 0)),
            "CPC":          float(ins.get("cpc", 0)),
            "Alcance":      int(ins.get("reach", 0)),
            "Frecuencia":   float(ins.get("frequency", 0)),
        })

    return pd.DataFrame(rows)

# ── Acciones sobre campañas ───────────────────────────────────────────────────
def pause_campaign(campaign_id: str):
    init_api()
    Campaign(campaign_id).api_update(
        fields=[], params={"status": Campaign.Status.paused}
    )

def set_daily_budget(campaign_id: str, budget_usd: float):
    init_api()
    Campaign(campaign_id).api_update(
        fields=[], params={"daily_budget": str(int(budget_usd * 100))}
    )

# ── Análisis con Claude ───────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def get_suggestions(data_json: str) -> list:
    if not CLAUDE_KEY:
        return []
    client = anthropic.Anthropic(api_key=CLAUDE_KEY)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": f"""Eres un experto en Meta Ads analizando campañas de Cuy Móvil,
operador móvil peruano. Analiza estos datos y devuelve exactamente 3 sugerencias
de acción priorizadas.

Reglas de análisis:
- CTR > 5% es excelente, < 3% es bajo
- CPC < $0.03 es muy bueno para Perú
- Frecuencia > 4x indica posible saturación de audiencia
- Campañas con > 3 meses activas merecen revisión

Datos de campañas activas:
{data_json}

Responde SOLO con JSON válido, sin texto adicional:
[
  {{
    "campaign_id": "id exacto del campo id",
    "campaign_name": "nombre de la campaña",
    "action": "PAUSE | INCREASE_BUDGET | DECREASE_BUDGET | REFRESH_CREATIVE",
    "reason": "explicación en una línea",
    "urgency": "ALTA | MEDIA | BAJA",
    "new_budget_usd": null_o_numero_con_nuevo_presupuesto_diario
  }}
]"""
        }]
    )
    try:
        text = msg.content[0].text.strip()
        # Extraer JSON si viene con texto extra
        start = text.find("[")
        end   = text.rfind("]") + 1
        return json.loads(text[start:end])
    except Exception:
        return []

# ── UI ────────────────────────────────────────────────────────────────────────
# Header
col_title, col_time = st.columns([4, 1])
with col_title:
    st.title("🦔 Cuy Móvil · Meta Ads Dashboard")
with col_time:
    st.caption(f"📅 {datetime.now().strftime('%d %b %Y, %H:%M')}")

# Sidebar
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

# Validación de token
if not ACCESS_TOKEN:
    st.error("Falta ACCESS_TOKEN. Agrégalo en Streamlit Cloud → Settings → Secrets.")
    st.stop()

# Carga de datos
with st.spinner("Cargando datos de Meta Ads..."):
    df = fetch_campaigns(account_id, date_preset)

if df.empty:
    st.info("No hay datos disponibles para este período y cuenta.")
    st.stop()

view_df = df if show_paused else df[df["Estado"] == "ACTIVE"]

# ── KPIs ──────────────────────────────────────────────────────────────────────
st.subheader("Resumen del período")
k1, k2, k3, k4, k5, k6 = st.columns(6)

total_spend       = view_df["Gasto"].sum()
total_impressions = view_df["Impresiones"].sum()
total_clicks      = view_df["Clics"].sum()
avg_ctr           = (total_clicks / total_impressions * 100) if total_impressions else 0
avg_cpc           = (total_spend / total_clicks) if total_clicks else 0
total_reach       = view_df["Alcance"].sum()

k1.metric("💰 Gasto",        f"${total_spend:,.2f}")
k2.metric("👁️ Impresiones",  f"{total_impressions:,.0f}")
k3.metric("🖱️ Clics",        f"{total_clicks:,.0f}")
k4.metric("📊 CTR",          f"{avg_ctr:.2f}%")
k5.metric("💲 CPC",          f"${avg_cpc:.3f}")
k6.metric("🎯 Alcance",      f"{total_reach:,.0f}")

st.divider()

# ── Gráficos ──────────────────────────────────────────────────────────────────
active_df = df[df["Estado"] == "ACTIVE"]

if not active_df.empty:
    g1, g2 = st.columns(2)

    with g1:
        st.subheader("Gasto por campaña")
        fig = px.bar(
            active_df.sort_values("Gasto"),
            x="Gasto", y="Campaña",
            orientation="h",
            color="CTR",
            color_continuous_scale="RdYlGn",
            color_continuous_midpoint=active_df["CTR"].median(),
            labels={"Gasto": "Gasto (USD)", "CTR": "CTR%"},
            text="Gasto",
        )
        fig.update_traces(texttemplate="$%{text:.0f}", textposition="outside")
        fig.update_layout(height=380, margin=dict(l=0, r=20, t=0, b=0),
                          yaxis_title="", coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

    with g2:
        st.subheader("CTR vs Frecuencia")
        fig = px.scatter(
            active_df,
            x="Frecuencia", y="CTR",
            size="Gasto",
            hover_name="Campaña",
            color="CPC",
            color_continuous_scale="RdYlGn_r",
            labels={"CTR": "CTR (%)", "Frecuencia": "Frecuencia (veces)"},
        )
        fig.add_vline(x=4, line_dash="dash", line_color="red",
                      annotation_text="Saturación", annotation_position="top right")
        fig.update_layout(height=380, margin=dict(l=0, r=0, t=0, b=0))
        st.plotly_chart(fig, use_container_width=True)

# ── Tabla ─────────────────────────────────────────────────────────────────────
st.subheader("Detalle por campaña")

table_df = view_df[[
    "Campaña", "Estado", "Gasto", "Impresiones", "Clics", "CTR", "CPC", "Alcance", "Frecuencia"
]].copy()

st.dataframe(
    table_df.style
        .format({
            "Gasto":       "${:.2f}",
            "CPC":         "${:.3f}",
            "CTR":         "{:.2f}%",
            "Frecuencia":  "{:.2f}x",
            "Impresiones": "{:,.0f}",
            "Clics":       "{:,.0f}",
            "Alcance":     "{:,.0f}",
        })
        .applymap(lambda v: "color: #2ecc71" if isinstance(v, float) and v > 5 else
                            "color: #e74c3c" if isinstance(v, float) and v < 3 else "",
                  subset=["CTR"])
        .applymap(lambda v: "color: #e74c3c" if isinstance(v, float) and v > 4 else "",
                  subset=["Frecuencia"]),
    use_container_width=True,
    hide_index=True,
)

st.divider()

# ── Sugerencias de Claude ──────────────────────────────────────────────────────
st.subheader("🤖 Sugerencias de Claude")

if not CLAUDE_KEY:
    st.info("Agrega `CLAUDE_API_KEY` en Secrets para activar el análisis con IA.")
elif active_df.empty:
    st.info("No hay campañas activas para analizar.")
else:
    analysis_data = active_df[[
        "id", "Campaña", "Gasto", "CTR", "CPC", "Frecuencia", "Impresiones", "Clics", "Alcance"
    ]].to_json(orient="records")

    with st.spinner("Claude está analizando las campañas..."):
        suggestions = get_suggestions(analysis_data)

    if not suggestions:
        st.warning("No se pudieron generar sugerencias. Verifica tu CLAUDE_API_KEY.")
    else:
        URGENCY_ICON = {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}
        ACTION_LABEL = {
            "PAUSE":            "⏸️ Pausar campaña",
            "INCREASE_BUDGET":  "⬆️ Aumentar presupuesto",
            "DECREASE_BUDGET":  "⬇️ Reducir presupuesto",
            "REFRESH_CREATIVE": "🎨 Acción manual requerida",
        }

        for i, s in enumerate(suggestions):
            icon    = URGENCY_ICON.get(s.get("urgency", ""), "⚪")
            action  = s.get("action", "")
            name    = s.get("campaign_name", "")
            cid     = s.get("campaign_id", "")
            reason  = s.get("reason", "")
            budget  = s.get("new_budget_usd")

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
                            confirm = st.warning(
                                f"¿Confirmas pausar **{name}**?", icon="⚠️"
                            )
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
