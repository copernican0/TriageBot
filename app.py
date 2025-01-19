import streamlit as st
import requests
import json
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import DictCursor
import os
from urllib.parse import urlparse

# Database configuration
DATABASE_URL = "postgresql://triagebot_owner:dwN5ALJ7MXWi@ep-weathered-tooth-a5aoa4uf.us-east-2.aws.neon.tech/triagebot?sslmode=require"

def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        st.error(f"Errore di connessione al database: {str(e)}")
        return None

def init_database():
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                # Crea tabella feedback se non esiste
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS feedback (
                        id SERIAL PRIMARY KEY,
                        timestamp TIMESTAMP NOT NULL,
                        rating INTEGER CHECK (rating >= 1 AND rating <= 5),
                        comment TEXT,
                        conversation_length INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
        except Exception as e:
            st.error(f"Errore nell'inizializzazione del database: {str(e)}")
        finally:
            conn.close()

# Chiama init_database all'avvio dell'app
init_database()

# Configurazione iniziale
url = "https://api.groq.com/openai/v1/chat/completions"
headers = {
    "Authorization": f"Bearer {st.secrets['GROQ_API_KEY']}", # Usa la variabile d'ambiente
    "Content-Type": "application/json"
}
model = "llama-3.3-70b-versatile"
SESSION_TIMEOUT = 15  # timeout in minuti

# Caricamento del prompt di sistema
def load_system_prompt():
    try:
        with open("prompt.txt", "r", encoding='utf-8') as file:
            return file.read().strip()
    except FileNotFoundError:
        return """Sei un assistente sperimentale che studia le interazioni AI-umano in contesto di supporto emotivo. 
        Non sei uno psicologo e non fornisci terapia. Mostra empatia mantenendo distanza professionale."""

# Funzione per salvare il feedback nel database
def save_feedback(rating, comment, conversation_length):
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO feedback (timestamp, rating, comment, conversation_length)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                """, (datetime.now(), rating, comment, conversation_length))
                feedback_id = cur.fetchone()[0]
                conn.commit()
                return feedback_id
        except Exception as e:
            st.error(f"Errore nel salvare il feedback: {str(e)}")
            return None
        finally:
            conn.close()
    return None

# Funzione per inviare messaggi a Groq
def send_message(messages):
    body = {
        "messages": messages,
        "model": model
    }
    
    try:
        response = requests.post(url, verify=False, headers=headers, data=json.dumps(body))
        
        if response.status_code == 200:
            response_data = response.json()
            if 'choices' in response_data and len(response_data['choices']) > 0:
                return response_data['choices'][0]['message']['content']
        
        return f"Error: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Error: {str(e)}"

# Funzione per verificare il timeout della sessione
def is_session_expired():
    if 'start_time' not in st.session_state:
        st.session_state.start_time = datetime.now()
        return False
    
    time_elapsed = datetime.now() - st.session_state.start_time
    return time_elapsed > timedelta(minutes=SESSION_TIMEOUT)

# Funzione per resettare la chat
def reset_chat():
    system_prompt = st.session_state.messages[0] if 'messages' in st.session_state else {"role": "system", "content": load_system_prompt()}
    st.session_state.messages = [system_prompt]
    st.session_state.start_time = datetime.now()

# Inizializzazione dello stato della chat
if 'messages' not in st.session_state:
    st.session_state.messages = []
    system_prompt = load_system_prompt()
    st.session_state.messages.append({
        "role": "system",
        "content": system_prompt
    })
    st.session_state.start_time = datetime.now()

# Interfaccia utente
st.title("Chat di Supporto Psicologico")

# Disclaimer
st.warning("""
    Questo è un esperimento di ricerca.
    Non è un servizio di supporto psicologico professionale.
    In caso di necessità, contattare un professionista.
    La sessione ha una durata massima di {} minuti.
""".format(SESSION_TIMEOUT))

# Verifica timeout
if is_session_expired():
    st.warning("La sessione è scaduta. Inizia una nuova chat.")
    reset_chat()
    st.experimental_rerun()
else:
    # Visualizzazione messaggi
    for message in st.session_state.messages[1:]:  # Skip system message
        with st.chat_message(message["role"]):
            st.write(message["content"])

    # Input utente
    if prompt := st.chat_input("Scrivi qui il tuo messaggio..."):
        # Aggiungi messaggio utente
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)
        
        # Ottieni risposta
        response = send_message(st.session_state.messages)
        
        # Aggiungi risposta bot
        st.session_state.messages.append({"role": "assistant", "content": response})
        with st.chat_message("assistant"):
            st.write(response)

# Feedback form
if len(st.session_state.messages) > 2:
    with st.expander("Lascia un feedback"):
        with st.form("feedback"):
            rating = st.slider("Valuta la risposta", 1, 5, 3)
            comment = st.text_area("Commenti")
            submitted = st.form_submit_button("Invia")
            
            if submitted:
                feedback_id = save_feedback(rating, comment, len(st.session_state.messages))
                if feedback_id:
                    st.success("Grazie per il feedback!")
                else:
                    st.error("Si è verificato un errore nel salvare il feedback.")

# Reset chat button
if st.sidebar.button("Nuova Chat"):
    reset_chat()
    st.experimental_rerun()
