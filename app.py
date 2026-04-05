import streamlit as st
import base64
import json
import hashlib
from anthropic import Anthropic
import os
from datetime import datetime
from supabase import create_client

client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
supabase = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

st.set_page_config(page_title="Coach Spese AI", page_icon="💸")
st.title("💸 Coach Spese AI")
st.caption("Versione test con login")

if 'user_id' not in st.session_state:
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Accedi"):
        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        result = supabase.table("users").select("*").eq("username", username).eq("password_hash", pw_hash).execute()
        if result.data:
            user = result.data[0]
            st.session_state.user_id = user["id"]
            st.session_state.is_premium = user["is_premium"]
            st.session_state.username = username
            st.rerun()
        else:
            st.error("Credenziali sbagliate. Prova: test / 1234")
    st.stop()

st.sidebar.success(f"👤 {st.session_state.username} — {'Premium ✅' if st.session_state.is_premium else 'Free'}")

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
        st.error(f"Errore: {e}")
        return None

st.subheader("📸 Carica foto scontrino")
uploaded_file = st.file_uploader("Seleziona foto dello scontrino", type=["jpg", "jpeg", "png"])

if uploaded_file and st.button("🔍 Analizza e salva spesa"):
    with st.spinner("Sto analizzando lo scontrino..."):
        parsed = analizza_foto(uploaded_file.getvalue())
        if parsed and parsed.get("importo"):
            supabase.table("spese").insert({
                "user_id": st.session_state.user_id,
                "data": parsed.get("data", datetime.now().strftime("%Y-%m-%d")),
                "importo": parsed.get("importo"),
                "negozio": parsed.get("negozio", "Sconosciuto"),
                "categoria": parsed.get("categoria", "Altro"),
                "motivo": "",
                "nota": parsed.get("consiglio", "")
            }).execute()
            st.success(f"✅ Salvata: €{parsed.get('importo')} da {parsed.get('negozio')}")
            st.write("**Consiglio:**", parsed.get("consiglio", "Continua così!"))

st.info("**Test rapido**: username = `test`    password = `1234`")
st.caption("Coach Spese AI • Creato da Terminale")
