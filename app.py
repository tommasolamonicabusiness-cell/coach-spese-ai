import streamlit as st
import base64
import json
import hashlib
from anthropic import Anthropic
import os
import sqlite3
import tempfile, pathlib
from datetime import datetime

client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

DB_PATH = pathlib.Path(tempfile.gettempdir()) / "coach_spese.db"
conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)

conn.execute('''CREATE TABLE IF NOT EXISTS spese 
                (id INTEGER PRIMARY KEY, user_id INTEGER, data TEXT, importo REAL, 
                 negozio TEXT, categoria TEXT, motivo TEXT, nota TEXT)''')

conn.execute('''CREATE TABLE IF NOT EXISTS users 
                (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT, 
                 is_premium INTEGER DEFAULT 0)''')

test_hash = hashlib.sha256("1234".encode()).hexdigest()
conn.execute("INSERT OR IGNORE INTO users (username, password_hash, is_premium) VALUES ('test', ?, 1)", (test_hash,))
conn.commit()

st.set_page_config(page_title="Coach Spese AI", page_icon="💸")
st.title("💸 Coach Spese AI")
st.caption("Versione test con login")

if 'user_id' not in st.session_state:
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Accedi"):
        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        user = conn.execute("SELECT id, is_premium FROM users WHERE username=? AND password_hash=?", 
                           (username, pw_hash)).fetchone()
        if user:
            st.session_state.user_id = user[0]
            st.session_state.is_premium = bool(user[1])
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
    except:
        return None

st.subheader("📸 Carica foto scontrino")
uploaded_file = st.file_uploader("Seleziona foto dello scontrino", type=["jpg", "jpeg", "png"])

if uploaded_file and st.button("🔍 Analizza e salva spesa"):
    with st.spinner("Claude sta analizzando lo scontrino..."):
        parsed = analizza_foto(uploaded_file.getvalue())
        if parsed and parsed.get("importo"):
            conn.execute("""INSERT INTO spese (user_id, data, importo, negozio, categoria, motivo, nota)
                            VALUES (?, ?, ?, ?, ?, ?, ?)""",
                         (st.session_state.user_id, parsed.get("data", datetime.now().strftime("%Y-%m-%d")), 
                          parsed.get("importo"), parsed.get("negozio", "Sconosciuto"), 
                          parsed.get("categoria", "Altro"), "", parsed.get("consiglio", "")))
            conn.commit()
            st.success(f"✅ Salvata: €{parsed.get('importo')} da {parsed.get('negozio')}")
            st.write("**Consiglio:**", parsed.get("consiglio", "Continua così!"))
        else:
            st.error("Non ho capito bene la foto. Prova con una più chiara o luminosa.")

st.info("**Test rapido**: username = `test`    password = `1234`")
st.caption("Coach Spese AI • Creato da Terminale")
