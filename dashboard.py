import streamlit as st
import pandas as pd
import os
import glob
import plotly.express as px
import yaml

# 1. Config & Load Data
st.set_page_config(page_title="DB Cleaning Dashboard", layout="wide")

with open("config/config.yaml", "r") as f:
    config = yaml.safe_load(f)

def load_latest_snapshot():
    list_of_files = glob.glob(os.path.join(config['paths']['snapshots'], '*.parquet'))
    if not list_of_files:
        return None
    latest_file = max(list_of_files, key=os.path.getctime)
    return pd.read_parquet(latest_file)

df = load_latest_snapshot()

st.title("📊 DB Cleaning & Obsolescence Dashboard")

if df is None:
    st.warning("No s'han trobat snapshots. Executa `python main.py` per generar-ne un.")
else:
    # --- Sidebar Filters ---
    st.sidebar.header("Filtres")
    schema_filter = st.sidebar.multiselect("Esquema", options=df['schema'].unique(), default=df['schema'].unique())
    rec_filter = st.sidebar.multiselect("Recomanació", options=df['recommendation'].unique(), default=df['recommendation'].unique())
    min_score = st.sidebar.slider("Score Mínim", 0, 100, 0)

    filtered_df = df[
        (df['schema'].isin(schema_filter)) & 
        (df['recommendation'].isin(rec_filter)) &
        (df['score'] >= min_score)
    ]

    # --- Metrics Top Cards ---
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Objectes", len(filtered_df))
    col2.metric("Mida Total (GB)", f"{filtered_df['size_gb'].sum():.2f}")
    col3.metric("Candidats DROP", len(filtered_df[filtered_df['recommendation'] == 'DROP']))
    col4.metric("Avg Score", f"{filtered_df['score'].mean():.1f}")

    # --- Tabs ---
    tab1, tab2, tab3 = st.tabs(["📋 Backlog de Neteja", "📈 Anàlisi de Mida", "🔍 Detall per Esquema"])

    with tab1:
        st.subheader("Backlog Prioritzat")
        st.dataframe(filtered_df.sort_values(by='score', ascending=False), use_container_width=True)
        
        csv = filtered_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Exportar Backlog a CSV", data=csv, file_name="cleaning_backlog.csv", mime="text/csv")

    with tab2:
        st.subheader("Distribució de Mida per Esquema")
        fig_size = px.pie(filtered_df, values='size_gb', names='schema', hole=0.4, title="Pes GB per Esquema")
        st.plotly_chart(fig_size, use_container_width=True)

        st.subheader("Top 10 Objectes més Pesats")
        top_10 = filtered_df.nlargest(10, 'size_gb')
        fig_bar = px.bar(top_10, x='table_name', y='size_gb', color='recommendation', text_auto='.2s', title="Mida per Taula")
        st.plotly_chart(fig_bar, use_container_width=True)

    with tab3:
        st.subheader("Score vs Mida")
        fig_scatter = px.scatter(
            filtered_df, x="size_gb", y="score", 
            color="recommendation", hover_name="table_name",
            size="size_gb", log_x=True, size_max=60
        )
        st.plotly_chart(fig_scatter, use_container_width=True)

st.sidebar.markdown("---")
st.sidebar.info("Eina d'auditoria de BBDD v1.0")
