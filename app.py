import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import requests
import io
import time
import os
from dotenv import load_dotenv

load_dotenv(override=True)  # local .env for development

def get_secret(key: str, default=None):
    """Read from st.secrets (Streamlit Cloud) or .env (local)."""
    try:
        return st.secrets[key]
    except (KeyError, FileNotFoundError):
        return os.getenv(key, default)

st.set_page_config(
    page_title="Rwanda LFS Dashboard",
    page_icon="🇷🇼",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Brand colours (Rwanda flag palette) ──────────────────────────────────────
BLUE     = "#00A1DE"
YELLOW   = "#FAD201"
GREEN    = "#20603D"
DARK     = "#1a3a2a"
LIGHT_BG = "#f4f6f9"
GREY     = "#6c757d"
PALETTE  = [BLUE, GREEN, YELLOW, "#e74c3c", "#9b59b6", "#e67e22", "#1abc9c", "#34495e"]

CHART_LAYOUT = dict(
    plot_bgcolor="white", paper_bgcolor="white",
    margin=dict(t=34, b=10, l=10, r=10),
    font=dict(family="sans-serif", size=12),
)

st.markdown(f"""
<style>
  body, .main {{ background:{LIGHT_BG}; }}
  .card {{
    background:white; border-radius:12px; padding:18px 20px 14px;
    box-shadow:0 1px 6px rgba(0,0,0,0.07); border-top:4px solid {BLUE};
  }}
  .card-green  {{ border-top-color:{GREEN}; }}
  .card-yellow {{ border-top-color:{YELLOW}; }}
  .card-red    {{ border-top-color:#e74c3c; }}
  .kpi-val {{ font-size:2.1rem; font-weight:800; color:{DARK}; line-height:1.1; }}
  .kpi-lbl {{ font-size:0.78rem; color:{GREY}; text-transform:uppercase; letter-spacing:.05em; margin-bottom:4px; }}
  .kpi-sub {{ font-size:0.78rem; color:{GREY}; margin-top:3px; }}
  .sec-hdr {{
    font-size:0.9rem; font-weight:700; color:{DARK};
    text-transform:uppercase; letter-spacing:.06em;
    border-left:3px solid {BLUE}; padding-left:8px; margin:22px 0 10px;
  }}
  hr.div {{ border:none; border-top:1px solid #e2e8f0; margin:6px 0 14px; }}
</style>
""", unsafe_allow_html=True)

# ── Data loading (source hidden from UI) ──────────────────────────────────────
def onedrive_to_download_url(url: str) -> str:
    """Convert a SharePoint/OneDrive sharing URL to a direct download URL."""
    url = url.strip()
    # Already a direct download link
    if "download=1" in url or url.endswith((".xlsx", ".xls", ".csv")):
        return url
    # SharePoint/OneDrive for Business sharing links
    if "sharepoint.com" in url or "onedrive.live.com" in url:
        sep = "&" if "?" in url else "?"
        return url + sep + "download=1"
    # Short OneDrive links (1drv.ms) — follow redirect then append download param
    return url

REFRESH_MINUTES = int(get_secret("REFRESH_MINUTES", 15))

@st.cache_data(ttl=60 * REFRESH_MINUTES, show_spinner="Refreshing survey data…")
def load_data() -> pd.DataFrame:
    raw_url = get_secret("DATA_URL", "")
    if not raw_url:
        raise ValueError("DATA_URL is not set.")
    url = onedrive_to_download_url(raw_url)

    resp = requests.get(url, timeout=30)
    resp.raise_for_status()

    content_type = resp.headers.get("Content-Type", "")
    if "spreadsheetml" in content_type or url.lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(resp.content))
    else:
        df = pd.read_csv(io.StringIO(resp.text))

    df["interview_date"] = pd.to_datetime(df["interview_date"], errors="coerce")
    return df

# ── Sidebar (filters only — no data source shown) ─────────────────────────────
with st.sidebar:
    st.image(
        "https://upload.wikimedia.org/wikipedia/commons/thumb/1/17/Flag_of_Rwanda.svg/320px-Flag_of_Rwanda.svg.png",
        width=110,
    )
    st.markdown("### 🇷🇼 Rwanda LFS")
    st.caption("Labour Force Survey · 2024")
    st.divider()

    if st.button("🔄 Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    try:
        df_raw = load_data()
        last_refresh = datetime.now().strftime("%d %b %Y, %H:%M")
        st.caption(f"Last loaded: {last_refresh}")
    except Exception as e:
        st.error(f"Could not load data: {e}")
        st.info("Set DATA_URL in Streamlit Cloud Secrets (deployed) or in your local `.env` file.")
        st.stop()

    st.divider()
    st.markdown("**🔍 Filters**")

    provinces = sorted(df_raw["province"].dropna().unique())
    sel_prov = st.multiselect("Province", provinces, default=[])

    areas = sorted(df_raw["area_type"].dropna().unique())
    sel_area = st.multiselect("Area type", areas, default=[])

    sexes = sorted(df_raw["sex"].dropna().unique())
    sel_sex = st.multiselect("Sex", sexes, default=[])

    emp_statuses = sorted(df_raw["employment_status"].dropna().unique())
    sel_emp = st.multiselect("Employment status", emp_statuses, default=[])

    min_d = df_raw["interview_date"].min().date()
    max_d = df_raw["interview_date"].max().date()
    sel_dates = st.date_input("Interview date range", value=(min_d, max_d),
                              min_value=min_d, max_value=max_d)

# ── Apply filters ─────────────────────────────────────────────────────────────
df = df_raw.copy()
if sel_prov:  df = df[df["province"].isin(sel_prov)]
if sel_area:  df = df[df["area_type"].isin(sel_area)]
if sel_sex:   df = df[df["sex"].isin(sel_sex)]
if sel_emp:   df = df[df["employment_status"].isin(sel_emp)]
if len(sel_dates) == 2:
    df = df[(df["interview_date"].dt.date >= sel_dates[0]) &
            (df["interview_date"].dt.date <= sel_dates[1])]

employed   = df[df["employment_status"] == "Employed"]
unemployed = df[df["employment_status"] == "Unemployed"]

# ── Auto-refresh note ─────────────────────────────────────────────────────────
if REFRESH_MINUTES > 0:
    with st.sidebar:
        st.caption(f"Auto-refresh every {REFRESH_MINUTES} min")

# ── Page header ───────────────────────────────────────────────────────────────
st.markdown(
    f"<h2 style='color:{DARK};margin-bottom:0'>Rwanda Labour Force Survey Dashboard</h2>"
    f"<p style='color:{GREY};margin-top:4px'>Survey year 2024 &nbsp;·&nbsp; "
    f"<b>{len(df):,}</b> respondents shown &nbsp;·&nbsp; "
    f"Updated {datetime.now().strftime('%d %b %Y, %H:%M')}</p>",
    unsafe_allow_html=True,
)
st.markdown("<hr class='div'>", unsafe_allow_html=True)

# ── KPI cards ─────────────────────────────────────────────────────────────────
n          = len(df)
emp_rate   = (df["employment_status"] == "Employed").mean() * 100
unemp_rate = (df["employment_status"] == "Unemployed").sum() / (
    max((df["employment_status"] != "Inactive").sum(), 1)) * 100
female_pct = (df["sex"] == "Female").mean() * 100
hi_pct     = (df["health_insurance"] == "Yes").mean() * 100
sp_pct     = (df["social_protection_coverage"] == "Yes").mean() * 100
urban_pct  = (df["area_type"] == "Urban").mean() * 100

kpis = [
    ("card",        "Total Respondents",  f"{n:,}",              f"{df['interview_date'].dt.date.nunique()} survey days"),
    ("card-green",  "Employment Rate",    f"{emp_rate:.1f}%",    f"Unemployment: {unemp_rate:.1f}%"),
    ("card",        "Female Share",       f"{female_pct:.1f}%",  f"Male: {100-female_pct:.1f}%"),
    ("card-yellow", "Health Insurance",   f"{hi_pct:.1f}%",      f"Social protection: {sp_pct:.1f}%"),
    ("card-green",  "Urban Respondents",  f"{urban_pct:.1f}%",   f"Rural: {100-urban_pct:.1f}%"),
]
cols = st.columns(5)
for col, (css, lbl, val, sub) in zip(cols, kpis):
    with col:
        st.markdown(f"""
        <div class="card {css}">
          <div class="kpi-lbl">{lbl}</div>
          <div class="kpi-val">{val}</div>
          <div class="kpi-sub">{sub}</div>
        </div>""", unsafe_allow_html=True)

# ── Section 1 : Survey progress ───────────────────────────────────────────────
st.markdown("<div class='sec-hdr'>📅 Survey Progress</div>", unsafe_allow_html=True)
col_prog, col_prov = st.columns([3, 2])

with col_prog:
    daily = (df.groupby(df["interview_date"].dt.date)
               .size().reset_index(name="Daily")
               .rename(columns={"interview_date": "Date"}))
    daily["Cumulative"] = daily["Daily"].cumsum()
    fig = go.Figure()
    fig.add_bar(x=daily["Date"], y=daily["Daily"],
                name="Daily", marker_color=BLUE, opacity=0.85)
    fig.add_scatter(x=daily["Date"], y=daily["Cumulative"],
                    name="Cumulative", mode="lines",
                    line=dict(color=GREEN, width=2.5), yaxis="y2")
    fig.update_layout(
        **CHART_LAYOUT, title="Daily Interview Count & Cumulative Total", height=320,
        yaxis=dict(title="Daily count", gridcolor="#f0f0f0"),
        yaxis2=dict(title="Cumulative", overlaying="y", side="right", showgrid=False),
        xaxis=dict(showgrid=False),
        legend=dict(orientation="h", y=1.1), bargap=0.25,
    )
    st.plotly_chart(fig, use_container_width=True)

with col_prov:
    prov = df["province"].value_counts().reset_index()
    prov.columns = ["Province", "Count"]
    prov["Pct"] = (prov["Count"] / prov["Count"].sum() * 100).round(1)
    fig2 = px.bar(prov, x="Count", y="Province", orientation="h",
                  text=prov["Pct"].astype(str) + "%",
                  color="Province", color_discrete_sequence=PALETTE,
                  title="Respondents by Province")
    fig2.update_layout(**CHART_LAYOUT, height=320, showlegend=False,
                       yaxis=dict(categoryorder="total ascending"))
    fig2.update_traces(textposition="outside")
    st.plotly_chart(fig2, use_container_width=True)

# ── Section 2 : Demographics ──────────────────────────────────────────────────
st.markdown("<div class='sec-hdr'>👤 Demographics</div>", unsafe_allow_html=True)
d1, d2, d3 = st.columns(3)

with d1:
    sex_c = df["sex"].value_counts().reset_index()
    sex_c.columns = ["Sex", "Count"]
    fig = px.pie(sex_c, names="Sex", values="Count", hole=0.5,
                 color_discrete_map={"Male": BLUE, "Female": "#e74c3c"},
                 title="Gender Distribution")
    fig.update_layout(**CHART_LAYOUT, height=300,
                      legend=dict(orientation="h", y=-0.05))
    fig.update_traces(textinfo="percent+label", textposition="outside")
    st.plotly_chart(fig, use_container_width=True)

with d2:
    bins = [14, 24, 34, 44, 54, 64, 75]
    lbls = ["15-24", "25-34", "35-44", "45-54", "55-64", "65+"]
    df["age_grp"] = pd.cut(df["age"], bins=bins, labels=lbls, right=True)
    age_sex = df.groupby(["age_grp", "sex"], observed=True).size().reset_index(name="Count")
    fig = px.bar(age_sex, x="age_grp", y="Count", color="sex", barmode="group",
                 color_discrete_map={"Male": BLUE, "Female": "#e74c3c"},
                 title="Age Distribution by Sex",
                 labels={"age_grp": "Age group", "Count": "Respondents"})
    fig.update_layout(**CHART_LAYOUT, height=300,
                      xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#f0f0f0"),
                      legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig, use_container_width=True)

with d3:
    mar = df["marital_status"].value_counts().reset_index()
    mar.columns = ["Status", "Count"]
    fig = px.bar(mar, x="Count", y="Status", orientation="h",
                 color="Status", color_discrete_sequence=PALETTE,
                 title="Marital Status")
    fig.update_layout(**CHART_LAYOUT, height=300, showlegend=False,
                      yaxis=dict(categoryorder="total ascending"),
                      xaxis=dict(gridcolor="#f0f0f0"))
    st.plotly_chart(fig, use_container_width=True)

# ── Section 3 : Employment overview ──────────────────────────────────────────
st.markdown("<div class='sec-hdr'>💼 Employment Overview</div>", unsafe_allow_html=True)
e1, e2, e3 = st.columns(3)

with e1:
    emp_c = df["employment_status"].value_counts().reset_index()
    emp_c.columns = ["Status", "Count"]
    color_map = {"Employed": GREEN, "Unemployed": "#e74c3c", "Inactive": GREY}
    fig = px.pie(emp_c, names="Status", values="Count", hole=0.5,
                 color="Status", color_discrete_map=color_map,
                 title="Employment Status")
    fig.update_layout(**CHART_LAYOUT, height=300,
                      legend=dict(orientation="h", y=-0.05))
    fig.update_traces(textinfo="percent+label", textposition="outside")
    st.plotly_chart(fig, use_container_width=True)

with e2:
    sec = employed["sector_of_employment"].value_counts().reset_index()
    sec.columns = ["Sector", "Count"]
    fig = px.bar(sec, x="Count", y="Sector", orientation="h",
                 color="Sector", color_discrete_sequence=PALETTE,
                 title="Sector of Employment (Employed only)")
    fig.update_layout(**CHART_LAYOUT, height=300, showlegend=False,
                      yaxis=dict(categoryorder="total ascending"),
                      xaxis=dict(gridcolor="#f0f0f0"))
    st.plotly_chart(fig, use_container_width=True)

with e3:
    etype = employed["employment_type"].value_counts().reset_index()
    etype.columns = ["Type", "Count"]
    fig = px.pie(etype, names="Type", values="Count", hole=0.5,
                 color_discrete_sequence=PALETTE,
                 title="Employment Type (Employed only)")
    fig.update_layout(**CHART_LAYOUT, height=300,
                      legend=dict(orientation="h", y=-0.05))
    fig.update_traces(textinfo="percent+label", textposition="outside")
    st.plotly_chart(fig, use_container_width=True)

# ── Section 4 : Labour market quality ────────────────────────────────────────
st.markdown("<div class='sec-hdr'>📊 Labour Market Quality</div>", unsafe_allow_html=True)
l1, l2, l3 = st.columns(3)

with l1:
    income = employed[employed["monthly_income_rwf"] > 0]["monthly_income_rwf"]
    fig = px.histogram(income, nbins=25, color_discrete_sequence=[GREEN],
                       title="Monthly Income Distribution (RWF)",
                       labels={"value": "RWF", "count": "Respondents"})
    med = income.median()
    fig.add_vline(x=med, line_dash="dash", line_color="#e74c3c",
                  annotation_text=f"Median: {med:,.0f} RWF",
                  annotation_position="top right")
    fig.update_layout(**CHART_LAYOUT, height=300, showlegend=False,
                      xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#f0f0f0"))
    st.plotly_chart(fig, use_container_width=True)

with l2:
    hrs = employed[employed["usual_weekly_hours"] > 0]["usual_weekly_hours"]
    fig = px.histogram(hrs, nbins=20, color_discrete_sequence=[BLUE],
                       title="Usual Weekly Hours (Employed)",
                       labels={"value": "Hours/week", "count": "Respondents"})
    fig.add_vline(x=40, line_dash="dot", line_color=YELLOW,
                  annotation_text="40 h standard", annotation_position="top left")
    fig.update_layout(**CHART_LAYOUT, height=300, showlegend=False,
                      xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#f0f0f0"))
    st.plotly_chart(fig, use_container_width=True)

with l3:
    under_y = (employed["underemployed"] == "Yes").sum()
    under_n = (employed["underemployed"] == "No").sum()
    inf_y   = (employed["informal_employment"] == "Yes").sum()
    inf_n   = (employed["informal_employment"] == "No").sum()
    fig = go.Figure()
    fig.add_bar(name="Underemployed",   x=["Yes", "No"], y=[under_y, under_n],
                marker_color=[YELLOW, "#c8d6c8"])
    fig.add_bar(name="Informal employ", x=["Yes", "No"], y=[inf_y, inf_n],
                marker_color=["#e74c3c", "#c8d6c8"])
    fig.update_layout(
        **CHART_LAYOUT, barmode="group", height=300,
        title="Underemployment & Informality",
        xaxis=dict(showgrid=False),
        yaxis=dict(gridcolor="#f0f0f0", title="Respondents"),
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig, use_container_width=True)

# ── Section 5 : Education & Social Protection ─────────────────────────────────
st.markdown("<div class='sec-hdr'>📚 Education & Social Protection</div>", unsafe_allow_html=True)
s1, s2, s3 = st.columns(3)

EDU_ORDER = ["No Education","Primary","Lower Secondary",
             "Upper Secondary","TVET","University","Postgraduate"]

with s1:
    edu = df["education_level"].value_counts().reindex(EDU_ORDER).dropna().reset_index()
    edu.columns = ["Level", "Count"]
    fig = px.bar(edu, x="Level", y="Count",
                 color_discrete_sequence=[BLUE], title="Education Level")
    fig.update_layout(**CHART_LAYOUT, height=300,
                      xaxis=dict(showgrid=False, tickangle=-30),
                      yaxis=dict(gridcolor="#f0f0f0"))
    st.plotly_chart(fig, use_container_width=True)

with s2:
    hi = df["health_insurance"].value_counts().reset_index()
    hi.columns = ["Coverage", "Count"]
    fig = px.pie(hi, names="Coverage", values="Count", hole=0.5,
                 color_discrete_map={"Yes": GREEN, "No": "#e74c3c"},
                 title="Health Insurance Coverage")
    fig.update_layout(**CHART_LAYOUT, height=300,
                      legend=dict(orientation="h", y=-0.05))
    fig.update_traces(textinfo="percent+label", textposition="outside")
    st.plotly_chart(fig, use_container_width=True)

with s3:
    tr = df["training_last_12months"].value_counts().reset_index()
    tr.columns = ["Trained", "Count"]
    sp_c = df["social_protection_coverage"].value_counts().reset_index()
    sp_c.columns = ["Social Prot.", "Count"]
    fig = go.Figure()
    fig.add_bar(name="Training (12m)",  x=tr["Trained"],      y=tr["Count"],
                marker_color=[GREEN, GREY])
    fig.add_bar(name="Social protection", x=sp_c["Social Prot."], y=sp_c["Count"],
                marker_color=[BLUE, "#aac4d4"])
    fig.update_layout(
        **CHART_LAYOUT, barmode="group", height=300,
        title="Training & Social Protection",
        xaxis=dict(showgrid=False),
        yaxis=dict(gridcolor="#f0f0f0", title="Respondents"),
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig, use_container_width=True)

# ── Section 6 : Inactivity & Unemployment ────────────────────────────────────
st.markdown("<div class='sec-hdr'>🔍 Inactivity & Unemployment Detail</div>", unsafe_allow_html=True)
u1, u2 = st.columns(2)

with u1:
    inactive = df[df["employment_status"] == "Inactive"]
    ir = inactive["inactivity_reason"].value_counts().reset_index()
    ir.columns = ["Reason", "Count"]
    fig = px.bar(ir, x="Count", y="Reason", orientation="h",
                 color="Reason", color_discrete_sequence=PALETTE,
                 title=f"Reasons for Inactivity  (n={len(inactive):,})")
    fig.update_layout(**CHART_LAYOUT, height=280, showlegend=False,
                      yaxis=dict(categoryorder="total ascending"),
                      xaxis=dict(gridcolor="#f0f0f0"))
    st.plotly_chart(fig, use_container_width=True)

with u2:
    ru = unemployed["reason_unemployed"].value_counts().reset_index()
    ru.columns = ["Reason", "Count"]
    fig = px.bar(ru, x="Count", y="Reason", orientation="h",
                 color="Reason", color_discrete_sequence=PALETTE,
                 title=f"Reasons for Unemployment  (n={len(unemployed):,})")
    fig.update_layout(**CHART_LAYOUT, height=280, showlegend=False,
                      yaxis=dict(categoryorder="total ascending"),
                      xaxis=dict(gridcolor="#f0f0f0"))
    st.plotly_chart(fig, use_container_width=True)

# ── Raw data explorer (optional / internal use) ───────────────────────────────
with st.expander("🗂 Data Explorer"):
    search = st.text_input("Search all columns", "")
    disp = df if not search else df[df.apply(
        lambda r: r.astype(str).str.contains(search, case=False).any(), axis=1)]
    st.dataframe(disp, use_container_width=True, height=350)
    st.caption(f"{len(disp):,} of {len(df):,} rows")
