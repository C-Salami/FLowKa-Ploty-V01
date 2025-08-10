import json
from datetime import datetime, date, time, timedelta
from dateutil import tz
import pandas as pd
import plotly.express as px
import streamlit as st

from scheduler import (
    generate_orders_with_D,
    schedule_orders,
    metrics,
    plan_to_dataframe,
    dataframe_to_plan,
)

st.set_page_config(page_title="APS Scheduling — Plotly", layout="wide")

# ---------------- THEME: purple + light ----------------
# (we keep dark option in .streamlit/config.toml; this is a light accent pass)
PURPLE = "#7C3AED"  # purple-600
LIGHT_BG = "#ffffff"
MUTED = "#6b7280"

st.markdown(
    f"""
    <style>
      .block-container {{ padding-top: 0.8rem; }}
      h1, h2, h3 {{ color: #111827; }}
      .stButton>button, .stDownloadButton>button {{
        border-radius: 8px;
        border: 1px solid #e5e7eb;
      }}
      .stButton>button:hover {{ border-color: #c7d2fe; }}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("APS Scheduling — Plotly/Streamlit")

# ---------------- TOP: Calendar (date + time) ----------------
tz_makassar = tz.gettz("Asia/Makassar")
default_start = datetime(2025, 8, 9, 8, 0, 0, tzinfo=tz_makassar)

c1, c2, c3 = st.columns([1,1,2])
with c1:
    cal_date = st.date_input("Calendar date", value=default_start.date())
with c2:
    cal_time = st.time_input("Start time", value=default_start.time(), step=60)
start_dt = datetime.combine(cal_date, cal_time).replace(tzinfo=tz_makassar)

st.markdown("---")

# ---------------- SIDEBAR: Controls ----------------
with st.sidebar:
    st.subheader("Setup")

    # Machines with full names
    machines_n = st.number_input("Number of machines", 1, 20, 5, step=1)
    machines = [f"Machine {i+1}" for i in range(machines_n)]

    st.markdown("**Counts / Durations**")
    cA, cB, cC = st.columns(3)
    with cA:
        cnt_A = st.number_input("A count", 0, 2000, 33, 1)
        dur_A = st.number_input("A duration (h)", 0.0, 100.0, 2.0, 0.5)
    with cB:
        cnt_B = st.number_input("B count", 0, 2000, 33, 1)
        dur_B = st.number_input("B duration (h)", 0.0, 100.0, 5.0, 0.5)
    with cC:
        cnt_C = st.number_input("C count", 0, 2000, 34, 1)
        dur_C = st.number_input("C duration (h)", 0.0, 100.0, 6.0, 0.5)

    st.markdown("**Product D (3 ops with dependency)**")
    cnt_D = st.number_input("D count", 0, 2000, 0, 1)
    lag_D_min_h = st.number_input("Min lag between D ops (h)", 0.0, 24.0, 0.0, 0.5)

    st.markdown("---")
    st.markdown("**Scheduling rule**")
    rule = st.selectbox("Heuristic", ["LPT", "EDD", "WSPT"], index=0)

    st.markdown("**Auto due dates (optional)**")
    col_dd1, col_dd2 = st.columns(2)
    with col_dd1:
        use_dd = st.checkbox("Assign due dates", value=False)
    with col_dd2:
        dd_slack = st.number_input("Slack (h)", 0.0, 240.0, 24.0, 1.0, disabled=not use_dd)
    dd_jitter = st.number_input("Jitter (±h)", 0.0, 48.0, 4.0, 1.0, disabled=not use_dd)

    st.markdown("---")
    st.markdown("**Machine downtime**  \nFormat per line: `Machine 1, 2025-08-09 12:00, 2025-08-09 14:00`")
    dt_text = st.text_area("Downtime windows", height=120, placeholder="Machine 1, 2025-08-09 12:00, 2025-08-09 14:00\nMachine 3, 2025-08-10 09:00, 2025-08-10 10:30")

    st.markdown("---")
    st.markdown("**Colors**")
    colA, colB = st.columns(2)
    with colA:
        color_A = st.color_picker("A color", "#8B5CF6")  # purple-500
        color_B = st.color_picker("B color", "#F59E0B")
    with colB:
        color_C = st.color_picker("C color", "#EF4444")
        color_D = st.color_picker("D color", "#10B981")
    per_order_colors = st.checkbox("Random color per order id", value=False)

    st.markdown("---")
    if st.button("Generate + Schedule", type="primary", use_container_width=True):
        st.session_state["_trigger"] = (st.session_state.get("_trigger", 0) + 1)

# ---------------- Parse downtime text ----------------
def parse_downtime(text: str):
    """
    Expected lines: Machine 1, 2025-08-09 12:00, 2025-08-09 14:00
    """
    from datetime import datetime as dt
    out = {}
    if not text:
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            mname, s, e = [x.strip() for x in line.split(",")]
            sdt = dt.fromisoformat(s).replace(tzinfo=tz_makassar)
            edt = dt.fromisoformat(e).replace(tzinfo=tz_makassar)
            out.setdefault(mname, []).append((sdt, edt))
        except Exception:
            st.warning(f"Could not parse downtime line: {line}")
    return out

downtime = parse_downtime(dt_text)

# ---------------- Build orders & schedule ----------------
if "plan" not in st.session_state or st.session_state.get("_trigger"):
    orders = generate_orders_with_D(
        counts={"A": cnt_A, "B": cnt_B, "C": cnt_C},
        durations_ABC={"A": dur_A, "B": dur_B, "C": dur_C},
        count_D=cnt_D,
        lag_D_min_h=lag_D_min_h,
        start=start_dt,
        auto_due_slack_hours=(dd_slack if use_dd else None),
        jitter_hours=(dd_jitter if use_dd else 0.0),
    )
    plan = schedule_orders(
        orders=orders,
        machines=machines,
        start=start_dt,
        rule=rule,
        lag_D_min_h=lag_D_min_h,
        downtime=downtime,
    )
    st.session_state["plan"] = plan

plan = st.session_state["plan"]
df = plan_to_dataframe(plan)

# ---------------- Metrics ----------------
m = metrics(plan)
mt1, mt2 = st.columns([1,2])
with mt1:
    st.metric("Makespan (h)", m["makespan_hours"])
with mt2:
    st.write("Utilization by machine:", m["by_machine"])
if m.get("lateness"):
    st.caption(f"Lateness: {m['lateness']}")

# ---------------- Colors & labels ----------------
# Map colors per product (optionally randomized by order)
base_map = {"A": color_A, "B": color_B, "C": color_C, "D": color_D}
if per_order_colors and not df.empty:
    # generate a color per id, tinting the product color
    import random
    def tint(hex_color, factor):
        # naive lighten/darken
        hc = hex_color.lstrip("#")
        r = int(hc[0:2], 16); g = int(hc[2:4], 16); b = int(hc[4:6], 16)
        r = max(0, min(255, int(r + (255-r)*factor)))
        g = max(0, min(255, int(g + (255-g)*factor)))
        b = max(0, min(255, int(b + (255-b)*factor)))
        return f"#{r:02x}{g:02x}{b:02x}"
    id_to_color = {}
    for oid, grp in df.groupby("id"):
        f = random.uniform(0.15, 0.45)
        id_to_color[oid] = tint(base_map.get(grp.iloc[0]["product"], "#888888"), f)
    df["_color"] = [id_to_color[i] for i in df["id"]]
else:
    df["_color"] = [base_map.get(p, "#888888") for p in df["product"]]

# Label inside each bar: "WO123 D2" or "WO5 A"
if not df.empty:
    df["_label"] = [
        f"{row['id']} {row.get('operation') or row['product']}"
        for _, row in df.iterrows()
    ]

# ---------------- Plotly Timeline ----------------
st.subheader("Schedule Timeline")
if df.empty:
    st.info("No items to display. Adjust inputs, then click Generate + Schedule.")
else:
    fig = px.timeline(
        df.sort_values(by=["machine","start"]),
        x_start="start", x_end="end",
        y="machine",
        color_discrete_sequence=None,
        color="_color",
        text="_label",
        hover_data=["id","product","operation","duration_hours","machine","start","end","due_date"]
    )
    fig.update_traces(textposition="inside", insidetextanchor="middle", cliponaxis=False)
    fig.update_yaxes(autorange="reversed", title=None)
    fig.update_layout(
        height=620,
        margin=dict(l=20,r=20,t=40,b=20),
        xaxis_title=None,
        paper_bgcolor=LIGHT_BG,
        plot_bgcolor=LIGHT_BG,
        font=dict(color="#111827"),
        legend_title_text=None,
        showlegend=False,
    )
    # a subtle purple axis line
    fig.update_xaxes(showline=True, linewidth=1, linecolor=PURPLE, mirror=False)

    st.plotly_chart(fig, use_container_width=True)

# ---------------- Data table + Edit & Save ----------------
st.subheader("Plan Data (editable via table)")
edited_df = st.data_editor(
    df[["id","product","operation","machine","start","end","duration_hours","due_date"]],
    hide_index=True,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "start": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm"),
        "end": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm"),
        "due_date": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm"),
    }
)

c_save1, c_save2, c_save3 = st.columns(3)
with c_save1:
    if st.button("Apply Edits (recompute metrics)"):
        try:
            new_plan = dataframe_to_plan(edited_df)
            st.session_state["plan"] = new_plan
            st.success("Applied edits.")
        except Exception as e:
            st.error(f"Invalid edits: {e}")
with c_save2:
    buf_json = json.dumps({"plan": st.session_state["plan"]}, default=str, indent=2).encode("utf-8")
    st.download_button("Download JSON", data=buf_json, file_name="aps_plan.json", mime="application/json")
with c_save3:
    if not df.empty:
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("Download CSV", data=csv, file_name="aps_plan.csv", mime="text/csv")

st.markdown("**Load Plan**")
uploaded = st.file_uploader("Upload JSON (export format)", type=["json"])
if uploaded:
    try:
        payload = json.load(uploaded)
        plan_loaded = payload.get("plan")
        if plan_loaded:
            st.session_state["plan"] = plan_loaded
            st.success("Plan loaded.")
        else:
            st.error("JSON missing 'plan' field.")
    except Exception as e:
        st.error(f"Failed to parse JSON: {e}")
