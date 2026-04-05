import streamlit as st
import base64
import json
import hashlib
from anthropic import Anthropic
import os
from datetime import datetime, date, timedelta
from supabase import create_client
import pandas as pd
import plotly.express as px

client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
supabase = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

st.set_page_config(page_title="Coach Spese", page_icon="💸", layout="centered")

st.markdown("""
<style>
    .main > div { padding-top: 1rem; }
    .stButton button { border-radius: 10px; border: 0.5px solid #e0e0e0; background: white; color: #333; }
    .stButton button:hover { background: #f5f5f5; }
    h1 { font-size: 22px !important; font-weight: 500 !important; }
    h2 { font-size: 18px !important; font-weight: 500 !important; }
    h3 { font-size: 16px !important; font-weight: 500 !important; }
    footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# Login
if 'user_id' not in st.session_state:
    st.title("Coach Spese")
    st.caption("Tieni traccia delle tue spese con l'AI")
    st.divider()
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Accedi", use_container_width=True):
        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        result = supabase.table("users").select("*").eq("username", username).eq("password_hash", pw_hash).execute()
        if result.data:
            user = result.data[0]
            st.session_state.user_id = user["id"]
            st.session_state.is_premium = user["is_premium"]
            st.session_state.username = username
            st.rerun()
        else:
            st.error("Credenziali non valide")
    st.caption("Test: username `test` · password `1234`")
    st.stop()

if 'page' not in st.session_state:
    st.session_state.page = "home"
if 'selected_spesa' not in st.session_state:
    st.session_state.selected_spesa = None

def nav(page):
    st.session_state.page = page
    st.session_state.selected_spesa = None
    st.rerun()

# Navigazione
col1, col2, col3, col4 = st.columns(4)
with col1:
    if st.button("Home", use_container_width=True): nav("home")
with col2:
    if st.button("Categorie", use_container_width=True): nav("categorie")
with col3:
    if st.button("Grafici", use_container_width=True): nav("grafici")
with col4:
    if st.button("Profilo", use_container_width=True): nav("profilo")

st.divider()

def get_spese():
    result = supabase.table("spese").select("*").eq("user_id", st.session_state.user_id).order("data", desc=True).execute()
    return result.data or []

def filtra_per_periodo(spese, periodo):
    oggi = date.today()
    if periodo == "Ultimi 7 giorni":
        cutoff = oggi - timedelta(days=7)
    elif periodo == "Mese attuale":
        cutoff = oggi.replace(day=1)
    elif periodo == "3 mesi":
        cutoff = oggi - timedelta(days=90)
    elif periodo == "Semestre":
        cutoff = oggi - timedelta(days=180)
    elif periodo == "Anno":
        cutoff = oggi.replace(month=1, day=1)
    else:
        return spese
    return [s for s in spese if s["data"] and s["data"] >= cutoff.strftime("%Y-%m-%d")]

SYSTEM_PROMPT = """Analizza la foto di uno scontrino e restituisci SOLO un JSON valido con questi campi:
{"importo": numero, "data": "YYYY-MM-DD", "negozio": "nome", "categoria": "Cibo|Trasporti|Casa|Svago|Altro", "consiglio": "testo breve"}"""

def analizza_foto(image_bytes):
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")
    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=700,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_base64}}]}]
        )
        text = message.content[0].text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].strip()
        return json.loads(text)
    except Exception as e:
        st.error(f"Errore analisi: {e}")
        return None

periodi = ["Mese attuale", "Ultimi 7 giorni", "3 mesi", "Semestre", "Anno", "Totale"]

# DETTAGLIO SPESA
if st.session_state.selected_spesa:
    s = st.session_state.selected_spesa
    if st.button("← Indietro"):
        st.session_state.selected_spesa = None
        st.rerun()

    st.title(s["negozio"])
    st.caption(f"{s['categoria']} · {s['data']}")
    st.metric("Importo", f"€{s['importo']:.2f}")

    if s.get("nota"):
        st.divider()
        st.subheader("Consiglio AI")
        st.info(s["nota"])

    st.divider()
    st.subheader("Modifica")
    nuovo_nome = st.text_input("Nome negozio", value=s["negozio"])
    nuova_categoria = st.selectbox("Categoria", ["Cibo", "Trasporti", "Casa", "Svago", "Altro"],
                                   index=["Cibo", "Trasporti", "Casa", "Svago", "Altro"].index(s["categoria"]) if s["categoria"] in ["Cibo", "Trasporti", "Casa", "Svago", "Altro"] else 4)
    nuovo_importo = st.number_input("Importo (€)", value=float(s["importo"]), min_value=0.0, step=0.5)
    nuova_data = st.date_input("Data", value=datetime.strptime(s["data"], "%Y-%m-%d").date() if s["data"] else date.today())

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Salva modifiche", use_container_width=True):
            supabase.table("spese").update({
                "negozio": nuovo_nome,
                "categoria": nuova_categoria,
                "importo": nuovo_importo,
                "data": nuova_data.strftime("%Y-%m-%d")
            }).eq("id", s["id"]).execute()
            st.success("Modifiche salvate!")
            st.session_state.selected_spesa = None
            st.rerun()
    with c2:
        if st.button("Elimina spesa", use_container_width=True):
            supabase.table("spese").delete().eq("id", s["id"]).execute()
            st.session_state.selected_spesa = None
            st.rerun()

    st.stop()

# HOME
if st.session_state.page == "home":
    now = datetime.now()
    st.title(f"Buongiorno, {st.session_state.username.capitalize()}")

    periodo = st.segmented_control("Periodo", periodi, default="Mese attuale")
    spese = get_spese()
    spese_filtrate = filtra_per_periodo(spese, periodo)
    totale = sum(s["importo"] for s in spese_filtrate)

    c1, c2 = st.columns(2)
    with c1:
        st.metric("Totale speso", f"€{totale:.0f}")
    with c2:
        st.metric("Scontrini", len(spese_filtrate))

    st.divider()
    st.subheader("Aggiungi scontrino")
    uploaded_file = st.file_uploader("Carica foto scontrino", type=["jpg", "jpeg", "png"], label_visibility="collapsed")
    if uploaded_file and st.button("Analizza e salva", use_container_width=True):
        with st.spinner("Analisi in corso..."):
            parsed = analizza_foto(uploaded_file.getvalue())
            if parsed and parsed.get("importo"):
                supabase.table("spese").insert({
                    "user_id": st.session_state.user_id,
                    "data": date.today().strftime("%Y-%m-%d"),
                    "importo": parsed.get("importo"),
                    "negozio": parsed.get("negozio", "Sconosciuto"),
                    "categoria": parsed.get("categoria", "Altro"),
                    "motivo": "",
                    "nota": parsed.get("consiglio", "")
                }).execute()
                st.success(f"Salvata: €{parsed.get('importo')} da {parsed.get('negozio')}")
                if parsed.get("consiglio"):
                    st.info(parsed.get("consiglio"))
                st.rerun()

    if spese_filtrate:
        st.divider()
        st.subheader("Spese")
        for s in spese_filtrate:
            c1, c2, c3 = st.columns([4, 1, 1])
            with c1:
                st.write(f"**{s['negozio']}**")
                st.caption(f"{s['categoria']} · {s['data']}")
            with c2:
                st.write(f"€{s['importo']:.0f}")
            with c3:
                if st.button("→", key=f"det_{s['id']}"):
                    st.session_state.selected_spesa = s
                    st.rerun()
    else:
        st.info("Nessuna spesa nel periodo selezionato.")

# CATEGORIE
elif st.session_state.page == "categorie":
    st.title("Categorie")
    spese = get_spese()
    periodo = st.segmented_control("Periodo", periodi, default="Mese attuale")
    spese = filtra_per_periodo(spese, periodo)

    if not spese:
        st.info("Nessuna spesa nel periodo selezionato.")
    else:
        df = pd.DataFrame(spese)
        categorie = df.groupby("categoria")["importo"].sum().reset_index()
        categorie.columns = ["Categoria", "Totale"]
        categorie = categorie.sort_values("Totale", ascending=False)
        totale_gen = categorie["Totale"].sum()

        for _, row in categorie.iterrows():
            c1, c2 = st.columns([3, 1])
            with c1:
                st.write(f"**{row['Categoria']}**")
                pct = int(row['Totale'] / totale_gen * 100)
                st.progress(pct, text=f"{pct}%")
            with c2:
                st.write(f"€{row['Totale']:.0f}")

        st.divider()
        categoria_sel = st.selectbox("Filtra", ["Tutte"] + list(categorie["Categoria"]))
        spese_cat = spese if categoria_sel == "Tutte" else [s for s in spese if s["categoria"] == categoria_sel]
        for s in spese_cat:
            c1, c2 = st.columns([4, 1])
            with c1:
                st.write(f"**{s['negozio']}** · {s['data']}")
            with c2:
                st.write(f"€{s['importo']:.0f}")
            if s.get("nota"):
                st.caption(s["nota"])

# GRAFICI
elif st.session_state.page == "grafici":
    st.title("Grafici")
    spese = get_spese()
    periodo = st.segmented_control("Periodo", periodi, default="Mese attuale")
    spese = filtra_per_periodo(spese, periodo)

    if not spese:
        st.info("Nessuna spesa nel periodo selezionato.")
    else:
        df = pd.DataFrame(spese)
        df["data"] = pd.to_datetime(df["data"])
        df["mese"] = df["data"].dt.to_period("M").astype(str)

        st.subheader("Spese per categoria")
        cat_data = df.groupby("categoria")["importo"].sum().reset_index()
        fig1 = px.pie(cat_data, values="importo", names="categoria", hole=0.4,
                      color_discrete_sequence=["#534AB7", "#9FE1CB", "#F5C4B3", "#FAC775", "#B5D4F4"])
        fig1.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=280)
        st.plotly_chart(fig1, use_container_width=True)

        st.subheader("Andamento mensile")
        mese_data = df.groupby("mese")["importo"].sum().reset_index()
        fig2 = px.bar(mese_data, x="mese", y="importo",
                      color_discrete_sequence=["#534AB7"])
        fig2.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=250, xaxis_title="", yaxis_title="€")
        st.plotly_chart(fig2, use_container_width=True)

        if st.session_state.is_premium:
            st.subheader("Spese nel tempo")
            fig3 = px.line(df.sort_values("data"), x="data", y="importo",
                           color_discrete_sequence=["#534AB7"])
            fig3.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=250, xaxis_title="", yaxis_title="€")
            st.plotly_chart(fig3, use_container_width=True)

            st.subheader("Distribuzione importi")
            fig4 = px.histogram(df, x="importo", nbins=10,
                                color_discrete_sequence=["#534AB7"])
            fig4.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=250, xaxis_title="€", yaxis_title="")
            st.plotly_chart(fig4, use_container_width=True)
        else:
            st.divider()
            st.caption("Passa a Premium per grafici illimitati.")

# PROFILO
elif st.session_state.page == "profilo":
    st.title("Profilo")
    st.write(f"**Username:** {st.session_state.username}")
    st.write(f"**Piano:** {'Premium' if st.session_state.is_premium else 'Gratuito'}")
    if not st.session_state.is_premium:
        st.divider()
        st.subheader("Passa a Premium")
        st.write("Grafici illimitati e molto altro.")
        st.button("Scopri Premium", use_container_width=True)
    st.divider()
    if st.button("Esci", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

st.caption("Coach Spese · Made with AI")
