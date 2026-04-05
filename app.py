import streamlit as st
import base64
import json
import hashlib
from anthropic import Anthropic
import os
from datetime import datetime, date
from supabase import create_client
import pandas as pd
import plotly.express as px

client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
supabase = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

st.set_page_config(page_title="Coach Spese", page_icon="💸", layout="centered")

st.markdown("""
<style>
    .main > div { padding-top: 1rem; }
    .metric-card { background: #f8f8f8; border-radius: 12px; padding: 16px; margin-bottom: 8px; }
    .expense-item { border: 0.5px solid #e0e0e0; border-radius: 10px; padding: 12px 16px; margin-bottom: 8px; }
    div[data-testid="stHorizontalBlock"] { gap: 8px; }
    .stButton button { border-radius: 10px; border: 0.5px solid #e0e0e0; background: white; color: #333; }
    .stButton button:hover { background: #f5f5f5; border-color: #ccc; }
    h1 { font-size: 22px !important; font-weight: 500 !important; }
    h2 { font-size: 18px !important; font-weight: 500 !important; }
    h3 { font-size: 16px !important; font-weight: 500 !important; }
    .premium-badge { background: #EEEDFE; color: #534AB7; font-size: 11px; padding: 2px 8px; border-radius: 4px; }
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

# Navigazione
if 'page' not in st.session_state:
    st.session_state.page = "home"

def nav(page):
    st.session_state.page = page
    st.rerun()

col1, col2, col3, col4 = st.columns(4)
with col1:
    if st.button("Home", use_container_width=True):
        nav("home")
with col2:
    if st.button("Categorie", use_container_width=True):
        nav("categorie")
with col3:
    if st.button("Grafici", use_container_width=True):
        nav("grafici")
with col4:
    if st.button("Profilo", use_container_width=True):
        nav("profilo")

st.divider()

# Carica spese
def get_spese():
    result = supabase.table("spese").select("*").eq("user_id", st.session_state.user_id).order("data", desc=True).execute()
    return result.data or []

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

# HOME
if st.session_state.page == "home":
    now = datetime.now()
    st.title(f"Buongiorno, {st.session_state.username.capitalize()}")
    st.caption(f"{now.strftime('%B %Y').capitalize()}")

    spese = get_spese()
    mese_corrente = now.strftime("%Y-%m")
    spese_mese = [s for s in spese if s["data"] and s["data"].startswith(mese_corrente)]
    totale_mese = sum(s["importo"] for s in spese_mese)

    c1, c2 = st.columns(2)
    with c1:
        st.metric("Speso questo mese", f"€{totale_mese:.0f}")
    with c2:
        st.metric("Scontrini salvati", len(spese))

    st.divider()
    st.subheader("Aggiungi scontrino")
    uploaded_file = st.file_uploader("Carica foto scontrino", type=["jpg", "jpeg", "png"], label_visibility="collapsed")
    if uploaded_file and st.button("Analizza e salva", use_container_width=True):
        with st.spinner("Analisi in corso..."):
            parsed = analizza_foto(uploaded_file.getvalue())
            if parsed and parsed.get("importo"):
                supabase.table("spese").insert({
                    "user_id": st.session_state.user_id,
                    "data": parsed.get("data", now.strftime("%Y-%m-%d")),
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

    if spese:
        st.divider()
        st.subheader("Ultime spese")
        for s in spese[:5]:
            c1, c2, c3 = st.columns([3, 1, 1])
            with c1:
                st.write(f"**{s['negozio']}**")
                st.caption(f"{s['categoria']} · {s['data']}")
            with c2:
                st.write(f"€{s['importo']:.0f}")
            with c3:
                if st.button("X", key=f"del_{s['id']}"):
                    supabase.table("spese").delete().eq("id", s["id"]).execute()
                    st.rerun()

# CATEGORIE
elif st.session_state.page == "categorie":
    st.title("Categorie")
    spese = get_spese()
    if not spese:
        st.info("Nessuna spesa ancora. Aggiungi il tuo primo scontrino!")
    else:
        df = pd.DataFrame(spese)
        categorie = df.groupby("categoria")["importo"].sum().reset_index()
        categorie.columns = ["Categoria", "Totale"]
        categorie = categorie.sort_values("Totale", ascending=False)

        for _, row in categorie.iterrows():
            c1, c2 = st.columns([3, 1])
            with c1:
                st.write(f"**{row['Categoria']}**")
                pct = row['Totale'] / categorie['Totale'].sum() * 100
                st.progress(int(pct))
            with c2:
                st.write(f"€{row['Totale']:.0f}")

        st.divider()
        categoria_sel = st.selectbox("Filtra per categoria", ["Tutte"] + list(categorie["Categoria"]))
        spese_filtrate = spese if categoria_sel == "Tutte" else [s for s in spese if s["categoria"] == categoria_sel]
        for s in spese_filtrate:
            st.write(f"**{s['negozio']}** — €{s['importo']:.0f} · {s['data']}")
            if s.get("nota"):
                st.caption(s["nota"])

# GRAFICI
elif st.session_state.page == "grafici":
    st.title("Grafici")
    spese = get_spese()

    if not spese:
        st.info("Nessuna spesa ancora.")
    else:
        df = pd.DataFrame(spese)
        df["data"] = pd.to_datetime(df["data"])
        df["mese"] = df["data"].dt.to_period("M").astype(str)

        # Grafico 1 — sempre disponibile
        st.subheader("Spese per categoria")
        cat_data = df.groupby("categoria")["importo"].sum().reset_index()
        fig1 = px.pie(cat_data, values="importo", names="categoria", hole=0.4,
                      color_discrete_sequence=["#534AB7", "#9FE1CB", "#F5C4B3", "#FAC775", "#B5D4F4"])
        fig1.update_layout(margin=dict(t=0, b=0, l=0, r=0), showlegend=True, height=280)
        st.plotly_chart(fig1, use_container_width=True)

        # Grafico 2 — sempre disponibile
        st.subheader("Andamento mensile")
        mese_data = df.groupby("mese")["importo"].sum().reset_index()
        fig2 = px.bar(mese_data, x="mese", y="importo",
                      color_discrete_sequence=["#534AB7"])
        fig2.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=250,
                           xaxis_title="", yaxis_title="€")
        st.plotly_chart(fig2, use_container_width=True)

        # Grafici premium
        if st.session_state.is_premium:
            st.subheader("Spese nel tempo")
            fig3 = px.line(df.sort_values("data"), x="data", y="importo",
                           color_discrete_sequence=["#534AB7"])
            fig3.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=250,
                               xaxis_title="", yaxis_title="€")
            st.plotly_chart(fig3, use_container_width=True)

            st.subheader("Distribuzione importi")
            fig4 = px.histogram(df, x="importo", nbins=10,
                                color_discrete_sequence=["#534AB7"])
            fig4.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=250,
                               xaxis_title="€", yaxis_title="")
            st.plotly_chart(fig4, use_container_width=True)
        else:
            st.divider()
            st.markdown('<span class="premium-badge">Premium</span>', unsafe_allow_html=True)
            st.caption("Passa a Premium per accedere a grafici illimitati.")

# PROFILO
elif st.session_state.page == "profilo":
    st.title("Profilo")
    st.write(f"**Username:** {st.session_state.username}")
    st.write(f"**Piano:** {'Premium' if st.session_state.is_premium else 'Gratuito'}")

    if not st.session_state.is_premium:
        st.divider()
        st.subheader("Passa a Premium")
        st.write("Grafici illimitati, esportazione dati e molto altro.")
        st.button("Scopri Premium", use_container_width=True)

    st.divider()
    if st.button("Esci", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

st.caption("Coach Spese · Made with AI")
