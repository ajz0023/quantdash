import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import requests
import io
from datetime import datetime

# ══════════════════════════════════════════
# PAGE CONFIG
# ══════════════════════════════════════════
st.set_page_config(
    page_title="QuantDash",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ══════════════════════════════════════════
# STYLING
# ══════════════════════════════════════════
st.markdown("""
<style>
    /* Dark theme overrides */
    .stApp { background-color: #0d1117; }
    .main .block-container { padding-top: 1rem; padding-bottom: 1rem; max-width: 1400px; }

    /* KPI cards */
    .kpi-card {
        background: #161b22; border: 1px solid rgba(255,255,255,0.08);
        border-radius: 10px; padding: 16px; margin-bottom: 12px;
    }
    .kpi-title { font-size: 11px; color: #7d8590; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }
    .kpi-row { display: flex; justify-content: space-between; margin-bottom: 4px; }
    .kpi-label { font-size: 11px; color: #7d8590; }
    .kpi-val-pos { font-size: 15px; font-weight: 600; color: #3fb950; font-family: monospace; }
    .kpi-val-neg { font-size: 15px; font-weight: 600; color: #f85149; font-family: monospace; }
    .kpi-val-neu { font-size: 15px; font-weight: 600; color: #7d8590; font-family: monospace; }

    /* Metric overrides */
    [data-testid="stMetricValue"] { font-size: 18px !important; }
    [data-testid="stMetricDelta"] { font-size: 12px !important; }

    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] { gap: 8px; background-color: #161b22; border-radius: 10px; padding: 4px; }
    .stTabs [data-baseweb="tab"] { border-radius: 6px; color: #7d8590; font-size: 13px; padding: 6px 16px; }
    .stTabs [aria-selected="true"] { background-color: #21262d !important; color: #e6edf3 !important; }

    /* Dataframe */
    [data-testid="stDataFrame"] { border-radius: 10px; }

    /* Selectbox */
    [data-testid="stSelectbox"] label { font-size: 12px; color: #7d8590; text-transform: uppercase; letter-spacing: 0.5px; }

    /* Headers */
    h1, h2, h3 { color: #e6edf3 !important; }
    p { color: #7d8590; }

    /* Hide streamlit branding */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    header { visibility: hidden; }

    /* Section headers */
    .section-hdr {
        font-size: 13px; font-weight: 500; color: #e6edf3;
        margin-bottom: 12px; padding-bottom: 6px;
        border-bottom: 1px solid rgba(255,255,255,0.08);
    }

    /* Badge */
    .badge-mine { background: rgba(79,142,247,0.15); color: #4f8ef7; border-radius: 4px; padding: 1px 6px; font-size: 10px; font-weight: 600; }
    .badge-bm { background: rgba(214,153,34,0.15); color: #d29922; border-radius: 4px; padding: 1px 6px; font-size: 10px; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════
SHEET_ID_KEY = "sheet_id"

def get_sheet_url(sheet_id, tab):
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={tab}"

@st.cache_data(ttl=300, show_spinner=False)
def load_tab(sheet_id, tab):
    url = get_sheet_url(sheet_id, tab)
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        return df
    except Exception as e:
        st.error(f"Error loading tab '{tab}': {e}")
        return pd.DataFrame()

def load_all_data(sheet_id):
    with st.spinner("Loading data from Google Sheet…"):
        tabs = {}
        for tab in ["Config", "Returns", "Backtest_Returns", "Benchmarks", "Backtest", "FX", "Overall_portfolio"]:
            tabs[tab] = load_tab(sheet_id, tab)
    return tabs

def parse_config(cfg_df, ret_df):
    """Parse config — derive strategies from Returns tab (IsMine=TRUE) for reliability."""
    cfg = {}
    if not cfg_df.empty:
        for _, row in cfg_df.iterrows():
            p = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
            v = str(row.iloc[1]).strip() if len(row) > 1 and pd.notna(row.iloc[1]) else ""
            if p and v and " " not in p:  # only single-word keys are reliable
                cfg[p] = v

    # Derive strategies from Returns tab
    strategies = []
    # Handle column name variations (IsMine, Is Mine, ismine, empty header etc.)
    if not ret_df.empty:
        # Find IsMine column regardless of case/spacing
        ismine_col = next((c for c in ret_df.columns if str(c).strip().replace(" ","").lower() == "ismine"), None)
        if ismine_col and ismine_col != "IsMine":
            ret_df = ret_df.rename(columns={ismine_col: "IsMine"})
        # If still not found, check if column C (index 2) contains TRUE/FALSE — use it
        if "IsMine" not in ret_df.columns and len(ret_df.columns) > 2:
            col_c = ret_df.iloc[:, 2].astype(str).str.strip().str.upper()
            if col_c.isin(["TRUE","FALSE","1","0","YES","NO"]).any():
                ret_df = ret_df.rename(columns={ret_df.columns[2]: "IsMine"})
    if not ret_df.empty and "IsMine" in ret_df.columns:
        # Accept TRUE, true, True, 1, Yes, yes, YES
        mine = ret_df[ret_df["IsMine"].astype(str).str.strip().str.upper().isin(["TRUE","1","YES"])].copy()
        for _, row in mine.iterrows():
            strategies.append({
                "name": str(row.get("Strategy", "")).strip(),
                "benchmark": str(row.get("Benchmark", "")).strip(),
                "currency": str(row.get("Currency", "USD")).strip(),
            })

    cfg["strategies"] = strategies
    def safe_float(val, default):
        try:
            return float(val or default)
        except (ValueError, TypeError):
            return default

    cfg["weights"] = {
        "cagr":   safe_float(cfg.get("Weight_CAGR"),   0.40),
        "sharpe": safe_float(cfg.get("Weight_Sharpe"), 0.30),
        "maxdd":  safe_float(cfg.get("Weight_MaxDD"),  0.20),
        "vol":    safe_float(cfg.get("Weight_Vol"),    0.10),
    }
    # Normalise weights
    w_sum = sum(cfg["weights"].values())
    if w_sum > 0:
        cfg["weights"] = {k: v/w_sum for k, v in cfg["weights"].items()}
    try:
        cfg["heatmap_start"] = int(float(cfg.get("HeatmapStartYear", 2018) or 2018))
    except (ValueError, TypeError):
        cfg["heatmap_start"] = 2018
    try:
        cfg["rf_rate"] = float(cfg.get("RiskFreeRate", 0.04) or 0.04)
    except (ValueError, TypeError):
        cfg["rf_rate"] = 0.04
    return cfg

def get_month_cols(df):
    """Return columns that match Mon-YYYY format."""
    return [c for c in df.columns if pd.to_datetime(c, format="%b-%Y", errors="coerce") is not pd.NaT
            and pd.to_datetime(c, format="%b-%Y", errors="coerce") != pd.NaT]

def parse_returns_row(row, month_cols):
    """Parse a returns row into a Series indexed by month."""
    vals = {}
    for m in month_cols:
        v = row.get(m, "")
        try:
            vals[m] = float(str(v).replace("%","").strip()) if str(v).strip() not in ["","nan"] else np.nan
        except:
            vals[m] = np.nan
    return pd.Series(vals)

def to_usd(series, currency, fx_df):
    """Convert a return series to USD using FX rates."""
    if currency == "USD" or fx_df.empty:
        return series
    result = series.copy()
    for month in series.index:
        if pd.isna(series[month]):
            continue
        fx_row = fx_df[fx_df["Month"] == month] if "Month" in fx_df.columns else pd.DataFrame()
        if fx_row.empty:
            continue
        if currency == "AUD" and "AUDUSD" in fx_row.columns:
            rate = float(fx_row["AUDUSD"].iloc[0])
            result[month] = series[month] * rate
        elif currency == "INR" and "INRUSD" in fx_row.columns:
            rate = float(fx_row["INRUSD"].iloc[0])
            result[month] = series[month] * rate
    return result

# ══════════════════════════════════════════
# CALCULATIONS
# ══════════════════════════════════════════
def slice_period(series, period):
    """Slice a return series to the given period."""
    s = series.dropna()
    if s.empty:
        return s
    now = datetime.now()
    if period == "YTD":
        n = now.month
    elif period == "1Y":
        n = 12
    elif period == "2Y":
        n = 24
    elif period == "3Y":
        n = 36
    elif period == "5Y":
        n = 60
    else:
        return s
    return s.iloc[-n:] if len(s) >= n else s

def calc_metrics(rets, rf=0.04):
    """Calculate performance metrics from a return series."""
    s = rets.dropna()
    if s.empty:
        return {}
    n = len(s)
    total = (1 + s).prod() - 1
    cagr = (1 + s).prod() ** (12/n) - 1
    vol = s.std() * np.sqrt(12)
    sharpe = (cagr - rf) / vol if vol > 0 else 0
    # Max drawdown
    eq = (1 + s).cumprod()
    peak = eq.cummax()
    dd = (eq - peak) / peak
    maxdd = dd.min()
    # Current drawdown
    cur_dd = dd.iloc[-1] if not dd.empty else 0
    wins = (s > 0).sum()
    return {
        "total": total, "cagr": cagr, "vol": vol, "sharpe": sharpe,
        "maxdd": maxdd, "cur_dd": cur_dd, "wins": wins,
        "win_rate": wins/n, "n": n
    }

def equity_curve(rets):
    s = rets.dropna()
    return (1 + s).cumprod() * 100

def drawdown_series(rets):
    s = rets.dropna()
    eq = (1 + s).cumprod()
    peak = eq.cummax()
    return ((eq - peak) / peak * 100)

def rolling_12m(rets):
    s = rets.dropna()
    return s.rolling(12).apply(lambda x: (1+x).prod()-1, raw=True) * 100

def fmt_pct(v, dec=1, sign=True):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    prefix = "+" if sign and v > 0 else ""
    return f"{prefix}{v*100:.{dec}f}%"

def color_val(v, invert=False):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    good = v > 0 if not invert else v < 0
    color = "#3fb950" if good else "#f85149"
    prefix = "+" if v > 0 else ""
    return f'<span style="color:{color};font-weight:600;font-family:monospace">{prefix}{v*100:.1f}%</span>'

# ══════════════════════════════════════════
# CHART HELPERS
# ══════════════════════════════════════════
DARK = dict(
    plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
    font=dict(color="#7d8590", size=11),
    xaxis=dict(gridcolor="rgba(255,255,255,0.04)", showgrid=True, zeroline=False),
    yaxis=dict(gridcolor="rgba(255,255,255,0.04)", showgrid=True, zeroline=False, side="right"),
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
    margin=dict(l=10, r=50, t=30, b=30),
    hovermode="x unified",
)

def line_chart(traces, title="", height=280):
    fig = go.Figure()
    for t in traces:
        fig.add_trace(t)
    fig.update_layout(**DARK, height=height, title=dict(text=title, font=dict(size=13, color="#e6edf3"), x=0))
    return fig

def bar_chart(x, y, colors, title="", height=240):
    fig = go.Figure(go.Bar(x=x, y=y, marker_color=colors, name="", hovertemplate="%{y:.2f}%"))
    fig.update_layout(**DARK, height=height, title=dict(text=title, font=dict(size=13, color="#e6edf3"), x=0))
    return fig

# ══════════════════════════════════════════
# MAIN APP
# ══════════════════════════════════════════
def main():
    # ── Header ──
    col_logo, col_title, col_time = st.columns([1, 6, 2])
    with col_logo:
        st.markdown("### ⬡ **Quant**Dash")
    with col_time:
        st.markdown(f"<p style='text-align:right;margin-top:12px;font-size:12px'>{datetime.now().strftime('%d %b %Y %H:%M')}</p>", unsafe_allow_html=True)

    # ── Sheet ID ──
    if SHEET_ID_KEY not in st.session_state:
        st.session_state[SHEET_ID_KEY] = "1qD8I4KDGheqbMXg8_Fia3Qjch5repf383s9DpJCvwTE"

    # ── Tabs ──
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📈 Strategy overview", "🌡 Heatmap", "🏆 Ranking", "💼 Portfolio", "⚙ Setup"])

    # ── Load data ──
    sheet_id = st.session_state[SHEET_ID_KEY]
    if not sheet_id:
        for tab in [tab1, tab2, tab3, tab4]:
            with tab:
                st.info("Enter your Google Sheet ID in the Setup tab to get started.")
        with tab5:
            render_setup()
        return

    tabs_data = load_all_data(sheet_id)
    if tabs_data["Returns"].empty:
        st.error("Could not load data. Check your Sheet ID and that the sheet is published to web.")
        return

    cfg = parse_config(tabs_data["Config"], tabs_data["Returns"])
    month_cols = get_month_cols(tabs_data["Returns"])

    with tab1:
        render_overview(cfg, tabs_data, month_cols)
    with tab2:
        render_heatmap(cfg, tabs_data, month_cols)
    with tab3:
        render_ranking(cfg, tabs_data, month_cols)
    with tab4:
        render_portfolio(tabs_data)
    with tab5:
        render_setup()

# ══════════════════════════════════════════
# TAB 1 — STRATEGY OVERVIEW
# ══════════════════════════════════════════
def render_overview(cfg, tabs_data, month_cols):
    ret_df = tabs_data["Returns"]
    bt_ret_df = tabs_data["Backtest_Returns"]
    bm_df = tabs_data["Benchmarks"]
    bt_df = tabs_data["Backtest"]
    strategies = cfg["strategies"]

    if not strategies:
        st.error("No strategies found with IsMine=TRUE in your Returns tab.")
        return

    # ── Selectors ──
    c1, c2, c3, c4, c5 = st.columns([3, 2, 1, 1, 1])
    with c1:
        strat_names = [s["name"] for s in strategies]
        selected_name = st.selectbox("Strategy", strat_names, key="ov_strat")
    with c2:
        period = st.selectbox("Period", ["YTD","1Y","2Y","3Y","5Y","All"], index=1, key="ov_period")

    selected = next((s for s in strategies if s["name"] == selected_name), strategies[0])
    bm_name = selected["benchmark"]
    currency = selected["currency"]

    # Get live returns
    strat_row = ret_df[ret_df["Strategy"] == selected_name]
    live_rets = pd.Series(dtype=float)
    if not strat_row.empty:
        live_rets = parse_returns_row(strat_row.iloc[0], month_cols).dropna()

    # Get benchmark returns
    bm_rets = pd.Series(dtype=float)
    bm_month_cols = get_month_cols(bm_df)
    if not bm_df.empty and bm_name:
        bm_row = bm_df[bm_df["Benchmark"] == bm_name]
        if not bm_row.empty:
            bm_rets = parse_returns_row(bm_row.iloc[0], bm_month_cols).dropna()

    # Get backtest returns
    bt_rets = pd.Series(dtype=float)
    bt_month_cols = get_month_cols(bt_ret_df) if not bt_ret_df.empty else []
    if not bt_ret_df.empty and "Strategy" in bt_ret_df.columns:
        bt_row = bt_ret_df[bt_ret_df["Strategy"] == selected_name]
        if not bt_row.empty:
            bt_rets = parse_returns_row(bt_row.iloc[0], bt_month_cols).dropna()

    # Get backtest summary metrics
    bt_summary = {}
    if not bt_df.empty and "Strategy" in bt_df.columns:
        bt_row2 = bt_df[bt_df["Strategy"] == selected_name]
        if not bt_row2.empty:
            r = bt_row2.iloc[0]
            bt_summary = {
                "cagr":   float(r.get("CAGR",   np.nan)) / 100 if pd.notna(r.get("CAGR")) else np.nan,
                "sharpe": float(r.get("Sharpe", np.nan)) if pd.notna(r.get("Sharpe")) else np.nan,
                "maxdd":  float(r.get("MaxDD",  np.nan)) / 100 if pd.notna(r.get("MaxDD")) else np.nan,
                "annvol": float(r.get("AnnVol", np.nan)) / 100 if pd.notna(r.get("AnnVol")) else np.nan,
                "inception": str(r.get("InceptionDate","—")),
            }

    # Slice by period
    live_sliced = slice_period(live_rets, period)
    bm_sliced = bm_rets.reindex(live_sliced.index).fillna(0)

    live_m = calc_metrics(live_sliced, cfg["rf_rate"])
    bm_m = calc_metrics(bm_sliced, cfg["rf_rate"])

    # Metadata row
    st.markdown(f"""
    <div style='display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap'>
        <div style='background:#161b22;border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:6px 12px;font-size:12px;color:#7d8590'>
            Benchmark: <strong style='color:#e6edf3'>{bm_name}</strong></div>
        <div style='background:#161b22;border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:6px 12px;font-size:12px;color:#7d8590'>
            Currency: <strong style='color:#e6edf3'>{currency}</strong></div>
        <div style='background:#161b22;border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:6px 12px;font-size:12px;color:#7d8590'>
            Inception: <strong style='color:#e6edf3'>{live_rets.index[0] if not live_rets.empty else "—"}</strong></div>
        <div style='background:#161b22;border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:6px 12px;font-size:12px;color:#7d8590'>
            Live months: <strong style='color:#e6edf3'>{len(live_rets)}</strong></div>
    </div>
    """, unsafe_allow_html=True)

    # ── KPI Cards ──
    def kpi_card(title, live_val, bt_val, bm_val, fmt_fn=fmt_pct, invert=False):
        def fmt_colored(v):
            if v is None or (isinstance(v, float) and np.isnan(v)):
                return '<span class="kpi-val-neu">—</span>'
            good = (v > 0) if not invert else (v < 0)
            cls = "kpi-val-pos" if good else "kpi-val-neg"
            return f'<span class="{cls}">{fmt_fn(v)}</span>'
        return f"""
        <div class='kpi-card'>
            <div class='kpi-title'>{title}</div>
            <div class='kpi-row'><span class='kpi-label'>Live</span>{fmt_colored(live_val)}</div>
            <div class='kpi-row'><span class='kpi-label'>Backtest</span>{fmt_colored(bt_val)}</div>
            <div class='kpi-row'><span class='kpi-label'>Benchmark</span>{fmt_colored(bm_val)}</div>
        </div>"""

    k1, k2, k3 = st.columns(3)
    with k1:
        st.markdown(kpi_card("CAGR",
            live_m.get("cagr"), bt_summary.get("cagr"), bm_m.get("cagr")), unsafe_allow_html=True)
    with k2:
        st.markdown(kpi_card("Max drawdown",
            live_m.get("maxdd"), bt_summary.get("maxdd"), bm_m.get("maxdd"),
            lambda v: fmt_pct(v, sign=False), invert=True), unsafe_allow_html=True)
    with k3:
        st.markdown(kpi_card("Current drawdown",
            live_m.get("cur_dd"), None, bm_m.get("cur_dd"),
            lambda v: fmt_pct(v, sign=False), invert=True), unsafe_allow_html=True)

    # ── Charts ──
    # Equity curve
    eq_period = st.selectbox("Equity curve zoom", ["YTD","1Y","2Y","3Y","5Y","All"], index=1, key="eq_zoom")
    eq_live_sliced = slice_period(live_rets, eq_period)
    eq_bm_sliced = bm_rets.reindex(eq_live_sliced.index).fillna(0)
    eq_live = equity_curve(eq_live_sliced)
    eq_bm = equity_curve(eq_bm_sliced)

    fig_eq = line_chart([
        go.Scatter(x=eq_live.index, y=eq_live.values, name=selected_name,
                   line=dict(color="#4f8ef7", width=2), fill="tozeroy",
                   fillcolor="rgba(79,142,247,0.06)"),
        go.Scatter(x=eq_bm.index, y=eq_bm.values, name=bm_name,
                   line=dict(color="#7c3aed", width=1.5, dash="dot"),
                   fill="tozeroy", fillcolor="rgba(124,58,237,0.03)"),
    ], title="Equity curve — growth of $100", height=300)
    fig_eq.update_layout(yaxis=dict(ticksuffix=""))
    st.plotly_chart(fig_eq, use_container_width=True)

    # Monthly returns + Drawdown side by side
    cc1, cc2 = st.columns(2)
    with cc1:
        colors = ["#3fb950" if v >= 0 else "#f85149" for v in live_sliced.values]
        fig_m = go.Figure()
        fig_m.add_trace(go.Bar(x=live_sliced.index, y=(live_sliced*100).values,
                               marker_color=colors, name=selected_name,
                               hovertemplate="%{x}: %{y:.2f}%"))
        fig_m.add_trace(go.Scatter(x=bm_sliced.index, y=(bm_sliced*100).values,
                                   name=bm_name, line=dict(color="#7c3aed", width=1.5, dash="dot")))
        fig_m.update_layout(**DARK, height=260,
                            title=dict(text="Monthly returns", font=dict(size=13, color="#e6edf3"), x=0))
        st.plotly_chart(fig_m, use_container_width=True)
    with cc2:
        dd_live = drawdown_series(live_sliced)
        dd_bm = drawdown_series(bm_sliced)
        fig_dd = line_chart([
            go.Scatter(x=dd_live.index, y=dd_live.values, name=selected_name,
                       line=dict(color="#f85149", width=1.5), fill="tozeroy",
                       fillcolor="rgba(248,81,73,0.1)"),
            go.Scatter(x=dd_bm.index, y=dd_bm.values, name=bm_name,
                       line=dict(color="#7c3aed", width=1.5, dash="dot")),
        ], title="Drawdown", height=260)
        fig_dd.update_layout(yaxis=dict(ticksuffix="%"))
        st.plotly_chart(fig_dd, use_container_width=True)

    # Rolling 12m
    roll_live = rolling_12m(live_sliced)
    roll_bm = rolling_12m(bm_sliced)
    fig_roll = line_chart([
        go.Scatter(x=roll_live.index, y=roll_live.values, name=selected_name,
                   line=dict(color="#4f8ef7", width=2), fill="tozeroy",
                   fillcolor="rgba(79,142,247,0.06)"),
        go.Scatter(x=roll_bm.index, y=roll_bm.values, name=bm_name,
                   line=dict(color="#7c3aed", width=1.5, dash="dot")),
    ], title="Rolling 12-month return", height=240)
    fig_roll.update_layout(yaxis=dict(ticksuffix="%"))
    st.plotly_chart(fig_roll, use_container_width=True)

    # ── Actual vs Backtest Table ──
    st.markdown("<div class='section-hdr'>Actual vs backtest — monthly returns</div>", unsafe_allow_html=True)
    if not bt_rets.empty and not live_sliced.empty:
        common_idx = live_sliced.index
        bt_aligned = bt_rets.reindex(common_idx)
        ab_rows = []
        for m in reversed(common_idx):
            act = live_sliced.get(m, np.nan)
            bt = bt_aligned.get(m, np.nan)
            diff = act - bt if not np.isnan(act) and not np.isnan(bt) else np.nan
            ab_rows.append({
                "Month": m,
                "Actual": fmt_pct(act) if not np.isnan(act) else "—",
                "Backtest": fmt_pct(bt) if not np.isnan(bt) else "—",
                "Difference": fmt_pct(diff) if not np.isnan(diff) else "—",
                "_diff": diff if not np.isnan(diff) else 0,
                "_act": act,
            })
        ab_df = pd.DataFrame(ab_rows)

        # Summary row
        total_act = (1 + live_sliced).prod() - 1
        total_bt = (1 + bt_aligned.dropna()).prod() - 1
        total_diff = total_act - total_bt

        # Style dataframe
        display_df = ab_df[["Month","Actual","Backtest","Difference"]].copy()
        # Add summary
        summary = pd.DataFrame([{"Month":"Total (compounded)",
                                   "Actual": fmt_pct(total_act),
                                   "Backtest": fmt_pct(total_bt),
                                   "Difference": fmt_pct(total_diff)}])
        display_df = pd.concat([display_df, summary], ignore_index=True)
        st.dataframe(display_df, use_container_width=True, hide_index=True, height=400)
    else:
        st.info("No backtest monthly returns available for this strategy. Add data to the Backtest_Returns tab.")

    # ── Monthly Heatmap ──
    st.markdown("<div class='section-hdr'>Monthly returns heatmap — full history</div>", unsafe_allow_html=True)
    if not live_rets.empty:
        hm_data = []
        months_order = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        for m in live_rets.index:
            try:
                d = pd.to_datetime(m, format="%b-%Y")
                hm_data.append({"Year": d.year, "Month": d.strftime("%b"), "Return": live_rets[m], "MonthN": d.month})
            except:
                pass
        if hm_data:
            hm_df = pd.DataFrame(hm_data)
            pivot = hm_df.pivot_table(index="Year", columns="MonthN", values="Return", aggfunc="first")
            pivot.columns = [months_order[c-1] for c in pivot.columns]
            # Add full year
            pivot["Full year"] = pivot.apply(lambda row: (1+row.dropna()).prod()-1, axis=1)
            # Sort years descending
            pivot = pivot.sort_index(ascending=False)
            # Format as percentages for display
            fmt_pivot = pivot.map(lambda v: f"{v*100:+.1f}%" if pd.notna(v) else "—")

            # Color the cells using plotly heatmap
            # Column-relative colouring for monthly heatmap
            hm_colorscale = [
                [0.0,  "#c0392b"],[0.25, "#e74c3c"],
                [0.45, "#f39c12"],[0.50, "#f1c40f"],
                [0.55, "#2ecc71"],[0.75, "#27ae60"],
                [1.0,  "#1a5e38"],
            ]
            zvals_raw = pivot.values * 100
            # Normalise each column relative to its own min/max
            zvals_norm = np.zeros_like(zvals_raw, dtype=float)
            for ci in range(zvals_raw.shape[1]):
                col = zvals_raw[:, ci]
                valid = col[~np.isnan(col)]
                if len(valid) < 2:
                    zvals_norm[:, ci] = 0.5
                    continue
                cmin, cmax = valid.min(), valid.max()
                rng = cmax - cmin
                zvals_norm[:, ci] = (col - cmin) / rng if rng > 0 else 0.5
            fig_hm = go.Figure(go.Heatmap(
                z=zvals_norm,
                x=list(pivot.columns),
                y=[str(y) for y in pivot.index],
                text=fmt_pivot.values,
                texttemplate="%{text}",
                textfont=dict(size=11, color="white"),
                colorscale=hm_colorscale,
                zmin=0, zmax=1,
                showscale=False,
                hoverongaps=False,
                xgap=2, ygap=2,
            ))
            fig_hm.update_layout(
                plot_bgcolor="#0d1117", paper_bgcolor="#161b22",
                font=dict(color="#e6edf3", size=11),
                margin=dict(l=50,r=20,t=50,b=10),
                height=max(200, len(pivot)*34+80),
                xaxis=dict(side="top", tickfont=dict(size=11, color="#e6edf3")),
                yaxis=dict(tickfont=dict(size=11, color="#e6edf3")),
            )
            st.plotly_chart(fig_hm, use_container_width=True)

# ══════════════════════════════════════════
# TAB 2 — HEATMAP
# ══════════════════════════════════════════
def render_heatmap(cfg, tabs_data, month_cols):
    ret_df = tabs_data["Returns"]
    bm_df = tabs_data["Benchmarks"]
    fx_df = tabs_data["FX"]
    bm_month_cols = get_month_cols(bm_df)

    # Controls
    c1, c2, c3 = st.columns([2, 2, 2])
    start_year = cfg["heatmap_start"]
    cur_year = datetime.now().year
    year_options = ["All years"] + [str(y) for y in range(start_year, cur_year+1)]
    with c1:
        selected_year = st.selectbox("Year", year_options, key="hm_year")
    with c2:
        investors = ["All investors"] + sorted(ret_df["Investor"].dropna().unique().tolist()) if "Investor" in ret_df.columns else ["All investors"]
        inv_filter = st.selectbox("Investor", investors, key="hm_inv")
    with c3:
        mine_only = st.checkbox("My strategies only", key="hm_mine")

    # Build combined data
    all_rows = []

    # Add benchmarks
    if not bm_df.empty and "Benchmark" in bm_df.columns:
        for _, row in bm_df.iterrows():
            bm_name = str(row.get("Benchmark","")).strip()
            rets = parse_returns_row(row, bm_month_cols)
            all_rows.append({
                "Investor": "—", "Name": bm_name, "Type": "Benchmark",
                "Currency": "USD", "IsMine": False, "rets": rets
            })

    # Add strategies
    if not ret_df.empty:
        for _, row in ret_df.iterrows():
            is_mine = str(row.get("IsMine","")).strip().upper() in ["TRUE","1","YES"]
            if mine_only and not is_mine:
                continue
            if inv_filter != "All investors" and str(row.get("Investor","")) != inv_filter and not (is_mine and inv_filter == "All investors"):
                if inv_filter != "All investors" and str(row.get("Investor","")) != inv_filter:
                    pass
            ccy = str(row.get("Currency","USD"))
            rets = parse_returns_row(row, month_cols)
            rets_usd = to_usd(rets, ccy, fx_df)
            all_rows.append({
                "Investor": str(row.get("Investor","—")),
                "Name": str(row.get("Strategy","")),
                "Type": "Strategy",
                "Currency": ccy,
                "IsMine": is_mine,
                "rets": rets_usd
            })

    if not all_rows:
        st.info("No data to display.")
        return

    # Build display table
    months_order = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

    if selected_year == "All years":
        years = list(range(start_year, cur_year+1))
        col_labels = [str(y) for y in years]
        def get_val(r, col):
            yr = int(col)
            yr_rets = r["rets"][[m for m in r["rets"].index if m.endswith(f"-{yr}")]].dropna()
            return (1+yr_rets).prod()-1 if not yr_rets.empty else np.nan
    else:
        col_labels = months_order
        def get_val(r, col):
            key = f"{col}-{selected_year}"
            v = r["rets"].get(key, np.nan)
            return v

    def get_full_year(r):
        if selected_year == "All years":
            valid = r["rets"].dropna()
            return (1+valid).prod()-1 if not valid.empty else np.nan
        else:
            yr_rets = r["rets"][[m for m in r["rets"].index if m.endswith(f"-{selected_year}")]].dropna()
            return (1+yr_rets).prod()-1 if not yr_rets.empty else np.nan

    # Build matrix for heatmap
    row_labels = []
    matrix = []
    text_matrix = []
    is_mine_list = []
    type_list = []

    for r in all_rows:
        row_labels.append(f"{r['Investor']} | {r['Name']}")
        is_mine_list.append(r["IsMine"])
        type_list.append(r["Type"])
        vals = [get_val(r, c) for c in col_labels] + [get_full_year(r)]
        def safe_val(v):
            if v is None: return np.nan
            try: return float(v)
            except: return np.nan
        vals = [safe_val(v) for v in vals]
        matrix.append([v*100 if not np.isnan(v) else np.nan for v in vals])
        text_matrix.append([f"{v*100:+.1f}%" if not np.isnan(v) else "—" for v in vals])

    all_cols = col_labels + ["Full year"]

    # Column-relative normalisation: rank within each column 0-1
    # So best in each year = 1 (green), worst = 0 (red), middle = 0.5 (yellow)
    matrix_arr = np.array([[v if v is not None and not np.isnan(v) else np.nan
                            for v in row] for row in matrix], dtype=float)

    norm_matrix = np.full_like(matrix_arr, np.nan)
    for col_idx in range(matrix_arr.shape[1]):
        col = matrix_arr[:, col_idx]
        valid = col[~np.isnan(col)]
        if len(valid) < 2:
            norm_matrix[:, col_idx] = 0.5
            continue
        col_min, col_max = valid.min(), valid.max()
        rng = col_max - col_min
        if rng == 0:
            norm_matrix[:, col_idx] = 0.5
        else:
            norm_matrix[:, col_idx] = (col - col_min) / rng

    # Colorscale: red → yellow → green (0 → 0.5 → 1)
    colorscale = [
        [0.0,  "#c0392b"],  # deep red (lowest in column)
        [0.25, "#e74c3c"],  # red
        [0.45, "#f39c12"],  # orange
        [0.5,  "#f1c40f"],  # yellow (middle)
        [0.55, "#2ecc71"],  # light green
        [0.75, "#27ae60"],  # green
        [1.0,  "#1a5e38"],  # deep green (highest in column)
    ]

    fig = go.Figure(go.Heatmap(
        z=norm_matrix.tolist(),
        x=all_cols,
        y=row_labels,
        text=text_matrix,
        texttemplate="%{text}",
        textfont=dict(size=10, color="white"),
        colorscale=colorscale,
        zmin=0, zmax=1,
        showscale=False,
        hoverongaps=False,
        xgap=2, ygap=2,
    ))
    fig.update_layout(
        plot_bgcolor="#0d1117", paper_bgcolor="#161b22",
        font=dict(color="#e6edf3", size=10),
        margin=dict(l=220, r=40, t=60, b=20),
        height=max(350, len(all_rows)*30+100),
        xaxis=dict(side="top", tickfont=dict(size=11, color="#e6edf3"),
                   gridcolor="rgba(255,255,255,0.05)"),
        yaxis=dict(tickfont=dict(size=10, color="#e6edf3"),
                   autorange="reversed",
                   gridcolor="rgba(255,255,255,0.05)"),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Sortable summary table
    st.markdown("<div class='section-hdr'>Summary table — click column headers to sort</div>", unsafe_allow_html=True)
    tbl_rows = []
    for i, r in enumerate(all_rows):
        fy = get_full_year(r)
        mine_tag = " ★" if r["IsMine"] else ""
        tbl_rows.append({
            "Investor": r["Investor"],
            "Strategy / Benchmark": r["Name"] + mine_tag,
            "Type": r["Type"],
            "Currency": r["Currency"],
            "Full year": fmt_pct(fy) if pd.notna(fy) and not np.isnan(fy) else "—",
            "_fy_sort": fy if pd.notna(fy) and not np.isnan(fy) else -999,
        })
    tbl_df = pd.DataFrame(tbl_rows).sort_values("_fy_sort", ascending=False)
    st.dataframe(
        tbl_df[["Investor","Strategy / Benchmark","Type","Currency","Full year"]],
        use_container_width=True, hide_index=True
    )

# ══════════════════════════════════════════
# TAB 3 — RANKING
# ══════════════════════════════════════════
def render_ranking(cfg, tabs_data, month_cols):
    ret_df = tabs_data["Returns"]
    bt_df = tabs_data["Backtest"]
    fx_df = tabs_data["FX"]

    c1, c2 = st.columns([3, 2])
    with c1:
        period = st.selectbox("Period", ["YTD","1Y","3Y","5Y","All"], key="rank_period")
    with c2:
        mine_only = st.checkbox("My strategies only", key="rank_mine")

    # Build scored rows
    scored = []
    for _, row in ret_df.iterrows():
        is_mine = str(row.get("IsMine","")).strip().upper() in ["TRUE","1","YES"]
        if mine_only and not is_mine:
            continue
        ccy = str(row.get("Currency","USD"))
        name = str(row.get("Strategy",""))
        rets = parse_returns_row(row, month_cols)
        rets_usd = to_usd(rets, ccy, fx_df)
        sliced = slice_period(rets_usd.dropna(), period)
        m = calc_metrics(sliced, cfg["rf_rate"])

        # Backtest summary
        bt_row = bt_df[bt_df["Strategy"]==name] if not bt_df.empty and "Strategy" in bt_df.columns else pd.DataFrame()
        bt_cagr = float(bt_row.iloc[0].get("CAGR",np.nan))/100 if not bt_row.empty and pd.notna(bt_row.iloc[0].get("CAGR")) else np.nan
        bt_sharpe = float(bt_row.iloc[0].get("Sharpe",np.nan)) if not bt_row.empty and pd.notna(bt_row.iloc[0].get("Sharpe")) else np.nan
        bt_maxdd = float(bt_row.iloc[0].get("MaxDD",np.nan))/100 if not bt_row.empty and pd.notna(bt_row.iloc[0].get("MaxDD")) else np.nan
        bt_vol = float(bt_row.iloc[0].get("AnnVol",np.nan))/100 if not bt_row.empty and pd.notna(bt_row.iloc[0].get("AnnVol")) else np.nan

        scored.append({
            "Strategy": name,
            "Investor": str(row.get("Investor","—")),
            "IsMine": is_mine,
            "Return": m.get("total", np.nan),
            "CAGR": m.get("cagr", np.nan),
            "Sharpe": m.get("sharpe", np.nan),
            "Max DD": m.get("maxdd", np.nan),
            "Ann. Vol": m.get("vol", np.nan),
            "Months": m.get("n", 0),
            "_cagr": m.get("cagr", np.nan),
            "_sharpe": m.get("sharpe", np.nan),
            "_maxdd": m.get("maxdd", np.nan),
            "_vol": m.get("vol", np.nan),
        })

    if not scored:
        st.info("No data to display.")
        return

    scored_df = pd.DataFrame(scored)

    # Calculate Score (normalised 0-100)
    def norm_col(col, invert=False):
        vals = scored_df[col].replace([np.inf,-np.inf], np.nan).dropna()
        if vals.empty or vals.max() == vals.min():
            return pd.Series([50.0]*len(scored_df), index=scored_df.index)
        mn, mx = vals.min(), vals.max()
        normed = (scored_df[col] - mn) / (mx - mn) * 100
        return 100 - normed if invert else normed

    w = cfg["weights"]
    scored_df["Score"] = (
        norm_col("_cagr") * w["cagr"] +
        norm_col("_sharpe") * w["sharpe"] +
        norm_col("_maxdd") * w["maxdd"] +
        norm_col("_vol", invert=True) * w["vol"]
    ).round(1)

    # Sort by Score by default
    scored_df = scored_df.sort_values("Score", ascending=False).reset_index(drop=True)
    scored_df.index += 1  # 1-based ranking

    # Format display
    display = pd.DataFrame({
        "#": scored_df.index,
        "Strategy": scored_df.apply(lambda r: f"{r['Strategy']} ★" if r["IsMine"] else r["Strategy"], axis=1),
        "Investor": scored_df["Investor"],
        "Return": scored_df["Return"].apply(lambda v: fmt_pct(v) if pd.notna(v) else "—"),
        "CAGR": scored_df["CAGR"].apply(lambda v: fmt_pct(v) if pd.notna(v) else "—"),
        "Sharpe": scored_df["Sharpe"].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "—"),
        "Max DD": scored_df["Max DD"].apply(lambda v: fmt_pct(v, sign=False) if pd.notna(v) else "—"),
        "Ann. Vol": scored_df["Ann. Vol"].apply(lambda v: fmt_pct(v, sign=False) if pd.notna(v) else "—"),
        "Months": scored_df["Months"],
        "Score": scored_df["Score"].apply(lambda v: f"{v:.1f}" if pd.notna(v) else "—"),
    })

    st.dataframe(display, use_container_width=True, hide_index=True,
                 column_config={"#": st.column_config.NumberColumn(width="small"),
                                "Score": st.column_config.TextColumn(width="small")})
    st.caption("★ = My strategy  |  Score = weighted composite (CAGR 40%, Sharpe 30%, Max DD 20%, Vol 10%)  |  Click column headers to sort")


# ══════════════════════════════════════════
# TAB 4 — PORTFOLIO OVERVIEW
# ══════════════════════════════════════════
def render_portfolio(tabs_data):
    port_df = tabs_data.get("Overall_portfolio", pd.DataFrame())
    bm_df   = tabs_data.get("Benchmarks", pd.DataFrame())

    if port_df.empty:
        st.error("Could not load Overall_portfolio tab. Check the tab name matches exactly.")
        return

    # Detect value columns (Mon-YYYY format) - use same logic as get_month_cols
    val_cols = get_month_cols(port_df)

    if not val_cols:
        # Debug: show what columns were found
        st.error(f"No monthly columns found in Overall_portfolio tab. Found columns: {list(port_df.columns)[:10]}")
        return

    # Find Portfolio column (first non-month column)
    port_col = port_df.columns[0]
    bm_col   = port_df.columns[1] if len(port_df.columns) > 1 else None

    # Get SP500 benchmark returns
    bm_month_cols = get_month_cols(bm_df) if not bm_df.empty else []
    sp500_rets = pd.Series(dtype=float)
    if not bm_df.empty and "Benchmark" in bm_df.columns:
        sp_row = bm_df[bm_df["Benchmark"] == "SP500"]
        if not sp_row.empty:
            sp500_rets = parse_returns_row(sp_row.iloc[0], bm_month_cols)

    # Parse portfolio values
    portfolios = {}
    for _, row in port_df.iterrows():
        name = str(row[port_col]).strip()
        vals = {}
        for c in val_cols:
            try:
                v = str(row[c]).replace(",","").replace("$","").strip()
                vals[c] = float(v) if v and v != "nan" else np.nan
            except:
                vals[c] = np.nan
        portfolios[name] = pd.Series(vals)

    if not portfolios:
        st.error("No portfolio rows found.")
        return

    # Sort columns chronologically
    val_cols_sorted = sorted(val_cols,
        key=lambda x: pd.to_datetime(x, format="%b-%Y", errors="coerce"))

    # ── Period selector ──
    period = st.radio("Period", ["YTD", "All"], horizontal=True, key="port_period")

    if period == "YTD":
        now = datetime.now()
        display_cols = [c for c in val_cols_sorted
                       if pd.to_datetime(c, format="%b-%Y", errors="coerce").year == now.year]
    else:
        display_cols = val_cols_sorted

    if not display_cols:
        st.warning("No data for selected period.")
        return

    start_col = display_cols[0]
    end_col   = display_cols[-1]

    # ── KPI Cards ──
    def calc_portfolio_kpis(series, start_col, end_col):
        start_val = series.get(start_col, np.nan)
        end_val   = series.get(end_col,   np.nan)
        if pd.isna(start_val) or pd.isna(end_val) or start_val == 0:
            return {}
        ytd_pct   = (end_val - start_val) / start_val
        ytd_dollar = end_val - start_val
        return {
            "latest":     end_val,
            "ytd_pct":    ytd_pct,
            "ytd_dollar": ytd_dollar,
            "start":      start_val,
        }

    # SP500 YTD for alpha calculation
    sp500_ytd = np.nan
    if not sp500_rets.empty:
        sp_cols = [c for c in display_cols if c in sp500_rets.index]
        if sp_cols:
            sp_slice = sp500_rets[sp_cols].dropna()
            sp500_ytd = (1 + sp_slice).prod() - 1 if not sp_slice.empty else np.nan

    def kpi_card_portfolio(name, kpis, sp500_ytd):
        if not kpis:
            return f"<div class='kpi-card'><div class='kpi-title'>{name}</div><div style='color:#7d8590'>No data</div></div>"
        latest     = kpis["latest"]
        ytd_pct    = kpis["ytd_pct"]
        ytd_dollar = kpis["ytd_dollar"]
        alpha      = ytd_pct - sp500_ytd if not np.isnan(sp500_ytd) else np.nan

        def col(v, invert=False):
            if np.isnan(v): return "#7d8590"
            return "#3fb950" if (v > 0) != invert else "#f85149"

        alpha_str = f"{alpha*100:+.1f}% vs SP500" if not np.isnan(alpha) else "—"
        return f"""
        <div class='kpi-card' style='border-top:3px solid {"#4f8ef7" if "AA" in name else "#7c3aed" if "NJ" in name else "#3fb950"}'>
            <div class='kpi-title'>{name}</div>
            <div class='kpi-row'>
                <span class='kpi-label'>Latest value</span>
                <span style='font-size:18px;font-weight:700;color:#e6edf3;font-family:monospace'>
                    ${latest:,.0f}
                </span>
            </div>
            <div class='kpi-row' style='margin-top:8px'>
                <span class='kpi-label'>YTD return</span>
                <span style='font-size:15px;font-weight:600;color:{col(ytd_pct)};font-family:monospace'>
                    {ytd_pct*100:+.1f}%
                </span>
            </div>
            <div class='kpi-row'>
                <span class='kpi-label'>YTD $ gain</span>
                <span style='font-size:14px;font-weight:600;color:{col(ytd_dollar)};font-family:monospace'>
                    ${ytd_dollar:+,.0f}
                </span>
            </div>
            <div class='kpi-row'>
                <span class='kpi-label'>Alpha</span>
                <span style='font-size:13px;font-weight:500;color:{col(alpha) if not np.isnan(alpha) else "#7d8590"}'>
                    {alpha_str}
                </span>
            </div>
        </div>"""

    port_names = list(portfolios.keys())
    kpi_cols = st.columns(len(port_names))
    for i, name in enumerate(port_names):
        kpis = calc_portfolio_kpis(portfolios[name], start_col, end_col)
        with kpi_cols[i]:
            st.markdown(kpi_card_portfolio(name, kpis, sp500_ytd), unsafe_allow_html=True)

    # ── Growth Chart ──
    st.markdown("<div class='section-hdr' style='margin-top:16px'>Portfolio value over time</div>",
                unsafe_allow_html=True)

    colors = {"AA": "#4f8ef7", "NJ": "#7c3aed", "Total": "#3fb950"}
    fig = go.Figure()
    for name, series in portfolios.items():
        y_vals = [series.get(c, np.nan) for c in display_cols]
        color  = colors.get(name, "#e6edf3")
        fig.add_trace(go.Scatter(
            x=display_cols, y=y_vals,
            name=name,
            line=dict(color=color, width=2.5),
            fill="tozeroy" if name == "Total" else None,
            fillcolor="rgba(63,185,80,0.05)" if name == "Total" else None,
            hovertemplate=f"<b>{name}</b><br>%{{x}}: $%{{y:,.0f}}<extra></extra>",
            mode="lines+markers",
            marker=dict(size=5, color=color),
        ))

    fig.update_layout(
        **DARK, height=320,
        yaxis=dict(
            tickprefix="$", tickformat=",.0f",
            gridcolor="rgba(255,255,255,0.04)",
            side="right"
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Monthly Returns Table ──
    st.markdown("<div class='section-hdr'>Monthly breakdown</div>", unsafe_allow_html=True)

    tbl_rows = []
    for i in range(len(display_cols) - 1, -1, -1):
        c = display_cols[i]
        prev_c = display_cols[i - 1] if i > 0 else None
        row = {"Month": c}
        for name, series in portfolios.items():
            curr_val = series.get(c, np.nan)
            prev_val = series.get(prev_c, np.nan) if prev_c else np.nan
            pct = (curr_val - prev_val) / prev_val if not (np.isnan(curr_val) or np.isnan(prev_val) or prev_val == 0) else np.nan
            row[f"{name} value"]  = f"${curr_val:,.0f}" if not np.isnan(curr_val) else "—"
            row[f"{name} %"]      = f"{pct*100:+.1f}%" if not np.isnan(pct) else "—"
        # SP500 for that month
        sp_ret = sp500_rets.get(c, np.nan) if not sp500_rets.empty else np.nan
        row["SP500 %"] = f"{sp_ret*100:+.1f}%" if not np.isnan(sp_ret) else "—"
        # Alpha for each portfolio
        for name, series in portfolios.items():
            curr_val = series.get(c, np.nan)
            prev_val = series.get(prev_c, np.nan) if prev_c else np.nan
            pct = (curr_val - prev_val) / prev_val if not (np.isnan(curr_val) or np.isnan(prev_val) or prev_val == 0) else np.nan
            alpha = pct - sp_ret if not (np.isnan(pct) or np.isnan(sp_ret)) else np.nan
            row[f"{name} alpha"] = f"{alpha*100:+.1f}%" if not np.isnan(alpha) else "—"
        tbl_rows.append(row)

    if tbl_rows:
        tbl_df = pd.DataFrame(tbl_rows)
        st.dataframe(tbl_df, use_container_width=True, hide_index=True)

# ══════════════════════════════════════════
# TAB 5 — SETUP
# ══════════════════════════════════════════
def render_setup():
    st.markdown("### Connect your Google Sheet")
    st.markdown("""
    **Step 1** — Find your Sheet ID in the URL:
    `docs.google.com/spreadsheets/d/**SHEET_ID**/edit`

    **Step 2** — Publish the sheet:
    `File → Share and export → Publish to web → Entire document → Publish`

    **Step 3** — Also share publicly:
    `Share → Anyone with the link → Viewer`
    """)

    sheet_id = st.text_input("Sheet ID", value=st.session_state.get(SHEET_ID_KEY,""), key="setup_id")
    if st.button("Connect", type="primary"):
        st.session_state[SHEET_ID_KEY] = sheet_id
        st.cache_data.clear()
        st.success("✓ Sheet ID saved. Reload the page to connect.")
        st.rerun()

    st.divider()
    st.markdown("### Required sheet structure — 6 tabs")
    tabs_info = {
        "Config": "Parameter | Value — settings, weights, heatmap start year",
        "Returns": "Strategy | Investor | IsMine | Currency | Benchmark | Jan-2018 | … (decimals)",
        "Backtest_Returns": "Strategy | Currency | Benchmark | Jan-2010 | … (your strategies only)",
        "Benchmarks": "Benchmark | Jan-2010 | … (decimals)",
        "Backtest": "Strategy | Investor | IsMine | Currency | Benchmark | InceptionDate | CAGR | Sharpe | MaxDD | AnnVol",
        "FX": "Month | AUDUSD | INRUSD",
    }
    for tab, desc in tabs_info.items():
        st.markdown(f"**{tab}** — `{desc}`")

if __name__ == "__main__":
    main()
