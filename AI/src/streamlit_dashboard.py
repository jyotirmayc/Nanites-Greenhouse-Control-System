import streamlit as st, pandas as pd
st.set_page_config(layout="wide")
st.title("Greenhouse Dashboard (Demo)")

df = pd.read_csv("../data/synthetic_greenhouse_7days_10min.csv", parse_dates=['ts'])
st.write("Static sample (last 200 rows):")
st.line_chart(df.set_index('ts')[['soil_theta','T','RH','PPFD']].tail(200))
st.write("Run the demo publisher and inference service to see live MQTT topics (use separate terminal).")
