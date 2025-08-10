import json
from datetime import datetime
from dateutil import tz
import pandas as pd
import plotly.express as px
import streamlit as st

from scheduler import generate_orders, lpt_schedule, metrics, plan_to_dataframe

st.set_page_config(page_title="APS Scheduling — Plotly", layout="wide")
st.title("APS Scheduling — Plotly/Streamlit MVP")

with st.sidebar:
    st.header("Problem Setup")

    # Start date/time: Aug 9, 2025 at 08:00, Asia/Makassar
    tz_makassar = tz.gettz("Asia/Makassar")
    default_start = datetime(2025, 8, 9, 8, 0, 0, tzinfo=tz_makassar)
  

    # Split into date + time for compatibility with older Streamlit versions
    d = st.date_input("Calendar date", value=default_start.date())
    t = st.time_input("Start time", value=default_start.time(), step=60)

    # Combine back into a timezone-aware datetime
    start_dt = datetime.combine(d, t).replace(tzinfo=tz_makassar)

    machines_n = st.number_input("Machines", min_value=1, max_value=20, value=5, step=1)
    machines = [f"M{i+1}" for i in range(machines_n)]

    st.markdown("---")
    st.subheader("Orders")
    c1, c2, c3 = st.columns(3)
    with c1:
        cnt_A = st.number_input("Count A", min_value=0, max_value=1000, value=33)
        dur_A = st.number_input("Duration A (h)", min_value=0.0, value=2.0, step=0.5)
    with c2:
        cnt_B = st.number_input("Count B", min_value=0, max_value=1000, value=33)
        dur_B = st.number_input("Duration B (h)", min_value=0.0, value=5.0, step=0.5)
    with c3:
        cnt_C = st.number_input("Count C", min_value=0, max_value=1000, value=34)
        dur_C = st.number_input("Duration C (h)", min_value=0.0, value=6.0, step=0.5)

    if st.button("Generate + Optimize (LPT)", type="primary", use_container_width=True):
        orders = generate_orders({"A": cnt_A, "B": cnt_B, "C": cnt_C},
                                 {"A": dur_A, "B": dur_B, "C": dur_C})
        plan = lpt_schedule(orders, machines, start_dt)
        st.session_state["plan"] = plan

    st.markdown("---")
    st.subheader("Import / Export")
    uploaded = st.file_uploader("Import plan JSON", type=["json"], label_visibility="visible")
    if uploaded:
        try:
            payload = json.load(uploaded)
            plan = payload.get("plan")
            if plan:
                st.session_state["plan"] = plan
                st.success("Plan imported.")
            else:
                st.error("JSON missing 'plan' field.")
        except Exception as e:
            st.error(f"Failed to parse JSON: {e}")

    if st.button("Clear plan", use_container_width=True):
        st.session_state.pop("plan", None)

# Initialize default plan
if "plan" not in st.session_state:
    orders = generate_orders({"A": 33, "B": 33, "C": 34},
                             {"A": 2.0, "B": 5.0, "C": 6.0})
    st.session_state["plan"] = lpt_schedule(orders, [f"M{i+1}" for i in range(5)], default_start)

plan = st.session_state["plan"]
df = plan_to_dataframe(plan)

# ---- Metrics ----
m = metrics(plan)
col1, col2 = st.columns([1, 2])
with col1:
    st.metric("Makespan (h)", m["makespan_hours"])
with col2:
    st.json(m, expanded=False)

# ---- Plotly Timeline ----
st.subheader("Schedule Timeline")
if df.empty:
    st.info("No items to display. Use the sidebar to generate a plan.")
else:
    color_discrete_map = {"A": "#10b981", "B": "#f59e0b", "C": "#ef4444"}
    fig = px.timeline(
        df.sort_values(by=["machine", "start"]),
        x_start="start", x_end="end",
        y="machine", color="product",
        hover_data=["id", "product", "duration_hours", "machine", "start", "end"],
        color_discrete_map=color_discrete_map
    )
    fig.update_yaxes(autorange="reversed")  # Gantt-like
    fig.update_layout(
        height=600,
        legend_title_text="Product",
        margin=dict(l=20, r=20, t=40, b=20),
        xaxis_title=None, yaxis_title=None,
        bargap=0.2,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)

# ---- Data + Downloads ----
st.subheader("Data")
st.dataframe(df, use_container_width=True, hide_index=True)

colA, colB = st.columns(2)
with colA:
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("Download CSV", csv, file_name="aps_plan.csv",
                       mime="text/csv", use_container_width=True)
with colB:
    export_payload = json.dumps({"plan": plan}, default=str, indent=2).encode("utf-8")
    st.download_button("Download JSON", export_payload, file_name="aps_plan.json",
                       mime="application/json", use_container_width=True)
