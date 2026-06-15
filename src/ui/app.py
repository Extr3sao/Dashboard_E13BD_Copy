import streamlit as st
import pandas as pd
import plotly.express as px
import os
import sys

# Afegir el directori d'arrel al path per permetre importacions de 'src'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from src.core.config_loader import ConfigLoader
from src.core.oracle_client import ensure_oracle_thick_mode
from src.core.db_manager import OracleDBManager
from src.core.ai_assistant import AIAssistant
from src.analytics.queries_oracle import OracleQueries
from src.analytics.scoring_engine import ScoringEngine

# --- INICIALITZACIÓ ORACLE THICK MODE ---
def init_oracle():
    if "oracle_initialized" not in st.session_state:
        config_loader = ConfigLoader()
        try:
            ensure_oracle_thick_mode(
                {"ORACLE_CLIENT_LIB_DIR": config_loader.get_env_var("ORACLE_CLIENT_LIB_DIR")}
            )
            st.session_state["oracle_initialized"] = True
        except RuntimeError as e:
            st.error(str(e))
            st.stop()

init_oracle()
# ----------------------------------------

from src.core.internal_db import InternalDBManager

# Configuració de la pàgina
st.set_page_config(page_title="Oracle Audit & Multi-Agent IA", layout="wide", initial_sidebar_state="expanded")

# --- INICIALITZACIÓ COMPONENTS ---
@st.cache_resource
def get_ai_assistant(model):
    return AIAssistant(model_name=model)

@st.cache_resource
def get_internal_db():
    return InternalDBManager()

db_info = get_internal_db()

# --- GESTIÓ D'ESTAT (SESSION STATE) ---
if "active_schemas" not in st.session_state:
    st.session_state["active_schemas"] = []
if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []

# --- INICIALITZACIÓ ORACLE THICK MODE ---
init_oracle()

# --- BARRA LATERAL (ORQUESTRADOR) ---
with st.sidebar:
    st.title("🧠 Assistent IA")
    
    ia_model = st.selectbox("Model IA (OpenRouter)", 
                            st.session_state.get("available_models", ["google/gemini-2.0-flash-exp:free"]))
    
    st.subheader("🛠️ Context d'Auditoria")
    schemas_input = st.text_input("ActiveSchemas (comes)", value=",".join(st.session_state["active_schemas"]))
    if st.button("Actualitzar Context"):
        st.session_state["active_schemas"] = [s.strip().upper() for s in schemas_input.split(",") if s.strip()]
        st.success("Context actualitzat!")

    st.markdown("---")
    st.subheader("💬 Xat d'Assistència")
    for msg in st.session_state["chat_history"][-3:]:
        role = "user" if msg["role"] == "user" else "assistant"
        st.chat_message(role).write(msg["content"])
    
    user_query = st.chat_input("Pregunta a l'Assistent...")
    if user_query:
        st.session_state["chat_history"].append({"role": "user", "content": user_query})
        assistant = get_ai_assistant(ia_model)
        with st.spinner("L'Assistent IA esta generant resposta..."):
            response = assistant.generate_response(
                user_query,
                context_data={"active_schemas": st.session_state["active_schemas"]}
            )
            st.session_state["chat_history"].append({"role": "assistant", "content": response})
            st.rerun()

# --- COS PRINCIPAL ---
st.title("🛡️ Oracle DB Audit & Governance")

tab_a, tab_b, tab_c, tab_d, tab_cfg = st.tabs([
    "📊 Plana A: Anàlisi", 
    "⌨️ Plana B: Consultes", 
    "📉 Plana C: Optimització", 
    "♻️ Plana D: Repositori d'Obsolets",
    "⚙️ Configuració"
])

# --- PLANA A: ANÀLISI (AUDITORIA TRANSPARENT) ---
with tab_a:
    st.header("Insights d'Auditoria & Riscos")
    col_left, col_right = st.columns([1, 2])
    
    with col_left:
        st.subheader("Criteris d'Anàlisi")
        st.info("""
        1. **Fase 1:** Dependències externes (BLOQUEJANT)
        2. **Fase 2:** Activitat < 30 dies o Jobs actius
        3. **Fase 3:** Aplicacions APEX vinculades
        4. **Fase 4/5:** Inactivitat confirmada
        """)
        if st.button("🔍 Iniciar Auditoria Transparent"):
            with st.spinner("L'Agent DBA està executant l'auditoria..."):
                cl = ConfigLoader()
                profiles = cl.load_connections()
                default_prof = cl.get_env_var("DEFAULT_PROFILE")
                
                if default_prof in profiles:
                    dbm = OracleDBManager(profiles[default_prof])
                    # Obtenim la query de resum de neteja_obsolets.txt (via BBDD interna o queries_oracle)
                    query = OracleQueries.get_summary_query(st.session_state["active_schemas"])
                    data, cols = dbm.execute_query(query)
                    
                    if data:
                        df_audit = pd.DataFrame(data, columns=cols)
                        st.session_state["audit_results"] = df_audit
                        st.session_state["audit_running"] = True
                    dbm.close()
                else:
                    st.error("Perfil de connexió no trobat.")

    with col_right:
        if st.session_state.get("audit_running") and "audit_results" in st.session_state:
            df_res = st.session_state["audit_results"]
            st.success(f"Detecció finalitzada: {len(df_res)} objectes analitzats.")
            
            # Scoring Engine visual
            scoring = ScoringEngine()
            scored_data = []
            for _, row in df_res.iterrows():
                scored_data.append(row.to_dict() | scoring.classify_schema(row))
            
            df_final = pd.DataFrame(scored_data)
            
            # Gràfic d'impacte
            fig = px.bar(df_final, x="USERNAME", y="SIZE_GB", color="risc", 
                         title="Impacte per Esquema i Nivell de Risc",
                         color_discrete_map={"SEGUR": "green", "PRECAUCIÓ": "orange", "CRÍTIC": "red"})
            st.plotly_chart(fig, use_container_width=True)
            
            st.write("### Candidats recomanats per l'Agent DBA")
            st.dataframe(df_final[df_final['risc'].isin(['PRECAUCIÓ', 'CRÍTIC'])][['USERNAME', 'fase', 'risc', 'motiu']])

# --- PLANA B: GESTIÓ DE CONSULTES ---
with tab_b:
    st.header("Flux de Treball SQL")
    
    col_editor, col_results = st.columns([1, 1])
    
    with col_editor:
        st.subheader("📝 Editor i Càrrega")
        uploaded_file = st.file_uploader("Carrega consulta (.txt, .sql)", type=['txt', 'sql'])
        
        default_query = ""
        if uploaded_file is not None:
            default_query = uploaded_file.getvalue().decode("utf-8")
        
        query_to_run = st.text_area("Codi SQL", value=default_query, height=300, placeholder="Escriu o carrega la teva consulta aquí...")
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("🚀 Executar Consulta"):
                if not query_to_run:
                    st.warning("Escriu una consulta per executar.")
                else:
                    cl = ConfigLoader()
                    profiles = cl.load_connections()
                    default_prof = cl.get_env_var("DEFAULT_PROFILE")
                    
                    if default_prof in profiles:
                        with st.spinner("Executant..."):
                            dbm = OracleDBManager(profiles[default_prof])
                            data, cols = dbm.execute_query(query_to_run)
                            if data is not None:
                                st.session_state["query_results"] = pd.DataFrame(data, columns=cols)
                                st.success("Consulta executada!")
                            else:
                                st.error("Error en l'execució. Revisa la sintaxi o la connexió.")
                            dbm.close()
                    else:
                        st.error("No hi ha cap perfil de connexió configurat.")
        
        with col_btn2:
            if st.button("🪄 Analitzar amb IA"):
                if query_to_run:
                    assistant = get_ai_assistant(ia_model)
                    with st.spinner("L'Assistent IA esta analitzant..."):
                        analysis = assistant.analyze_query(query_to_run)
                        st.session_state["query_analysis"] = analysis
                else:
                    st.warning("Escriu una consulta per analitzar.")

    with col_results:
        st.subheader("📊 Resultats")
        if "query_results" in st.session_state:
            df_res = st.session_state["query_results"]
            st.dataframe(df_res, use_container_width=True)
            
            # Botó de descàrrega Excel
            import io
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_res.to_excel(writer, index=False, sheet_name='Resultats')
            
            st.download_button(
                label="📥 Descarregar Excel",
                data=buffer.getvalue(),
                file_name="resultats_consulta.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.info("Els resultats de l'execució apareixeran aquí.")
            
        if "query_analysis" in st.session_state:
            with st.expander("🔍 Anàlisi de la IA", expanded=True):
                st.markdown(st.session_state["query_analysis"])

    st.markdown("---")
    with st.expander("📂 Repositori de Consultes (Cercador)"):
        # Taula de resultats del repositori
        all_queries = db_info.get_queries()
        if all_queries:
            df_q = pd.DataFrame(all_queries, columns=["ID", "SQL", "Explicació", "Origen", "Data"])
            st.dataframe(df_q[['ID', 'Origen', 'Explicació', 'SQL']], use_container_width=True)
            
            sel_id = st.number_input("Selecciona ID per carregar a l'editor", min_value=1, step=1)
            if st.button("📥 Carregar a l'Editor"):
                q_detail = [q for q in all_queries if q[0] == sel_id]
                if q_detail:
                    st.session_state["editor_sql"] = q_detail[0][1]
                    st.success(f"Consulta {sel_id} carregada! Prem el botó 'Executar' quan vulguis.")
                    st.rerun()


# --- PLANA C: OPTIMITZACIÓ ---
with tab_c:
    st.header("Optimització de Rendiment")
    st.markdown("""
    L'**Agent DBA** analitza patrons de consultes pesades i proposa millores basades en el manual de neteja.
    """)
    # Lògica per analitzar consultes amb l'Agent DBA

# --- PLANA D: REPOSITORI D'OBSOLETS ---
with tab_d:
    st.header("♻️ Elements Obsolets")
    st.write("Candidats a eliminació o refactorització detectats pels Agents.")
    obsolets = db_info.get_obsolet_registry()
    if obsolets:
        df_obs = pd.DataFrame(obsolets, columns=["ID", "Esquema", "Objecte", "Tipus", "Desc", "Obsolet", "Motiu", "Risc", "Recomanació", "Origen"])
        st.dataframe(df_obs[['Esquema', 'Objecte', 'Tipus', 'Risc', 'Motiu', 'Recomanació']], use_container_width=True)
    else:
        st.info("No s'han trobat elements al repositori encara.")

# --- PESTANYA CONFIGURACIÓ ---
with tab_cfg:
    st.header("Configuració de Perfils i Metadades")
    cl = ConfigLoader()
    profiles = cl.load_connections()

    col_prof, col_meta = st.columns([1, 1])
    
    with col_prof:
        st.subheader("Gestió de Connexions")
        if profiles:
            selected_p = st.selectbox("Perfil actiu", list(profiles.keys()))
            if st.button("🔌 Provar Connexió"):
                dbm = OracleDBManager(profiles[selected_p])
                if dbm.connect():
                    st.success("✅ Connexió OK!")
                    dbm.close()
                else:
                    st.error(f"❌ Error: {dbm.last_error}")
        
        with st.form("add_new_prof"):
            p_name = st.text_input("Nom Perfil")
            p_user = st.text_input("Usuari")
            p_pass = st.text_input("Pass", type="password")
            p_dsn = st.text_input("DSN (host:port/service)")
            if st.form_submit_button("💾 Desar Nou Perfil"):
                if cl.save_connection(p_name, p_user, p_pass, p_dsn):
                    st.success("Desat!")
                    st.rerun()

    with col_meta:
        st.subheader("Configuració d'Intel·ligència Artificial")
        or_key = cl.get_env_var("OPENROUTER_API_KEY", "")
        new_or_key = st.text_input("OpenRouter API Key", value=or_key, type="password")
        if st.button("💾 Desar Clau OpenRouter"):
            if cl.save_env_var("OPENROUTER_API_KEY", new_or_key):
                st.success("Clau d'OpenRouter desada correctament!")
                st.rerun()
            else:
                st.error("Error en desar la clau.")
        
        st.markdown("---")
        st.subheader("Arbre de Metadades (Esquemes)")
        if st.session_state["active_schemas"]:
            st.write(f"Esquemes monitoritzats: {', '.join(st.session_state['active_schemas'])}")
            # Aquí es podria cridar a una query de DBA_TABLES per llistar objectes
            st.caption("Usa Plana B per cercar objectes específics.")

# --- FINALITZACIÓ ---
st.markdown("---")
st.caption("v3.0 - Auditoria Oracle + Assistencia IA | Internal DB: Activa")


