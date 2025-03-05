from flask import Flask, request, jsonify, render_template, redirect, url_for, session, send_file
import anthropic
import os
import random
import string
import json
import requests
from datetime import datetime
from functools import wraps
from dotenv import load_dotenv
import io
import uuid

# Lade die Umgebungsvariablen aus .env
load_dotenv()

# API-Schlüssel
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

# Prüfe, ob der Elevenlabs API-Key gesetzt ist
if not ELEVENLABS_API_KEY:
    raise ValueError("❌ FEHLER: Elevenlabs API-Key nicht gefunden! Stelle sicher, dass die .env-Datei existiert.")

# Passwort für den Lehrerbereich
TEACHER_PASSWORD = "Hamburg1!"

# Überprüfe, ob der Claude API-Key geladen wurde
if not CLAUDE_API_KEY:
    raise ValueError("❌ FEHLER: Claude API-Key nicht gefunden! Stelle sicher, dass die .env-Datei existiert.")

# Anthropic API-Client
client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

# Flask-App erstellen
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "diktate-sind-cool-aber-geheim")

# Pfad für gespeicherte Audiodateien
AUDIO_DIR = os.path.join(app.static_folder or 'static', 'audio')
os.makedirs(AUDIO_DIR, exist_ok=True)

# Datenbank-Simulation für Diktate und Ergebnisse (im Produktiveinsatz durch eine echte DB ersetzen)
dictations = {}
results = []  # Hier werden die Schülerergebnisse gespeichert

# Hilfsfunktion für Diktat-ID-Generierung
def generate_dictation_id(length=6):
    """Generiert eine zufällige Diktat-ID aus Buchstaben und Zahlen."""
    characters = string.ascii_uppercase + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

# Funktion zum Ersetzen der Satzzeichen durch gesprochene Wörter
def replace_punctuation_with_words(text):
    """Ersetzt Satzzeichen durch gesprochene Wörter für die Diktat-Ausgabe."""
    return text.replace(".", " Punkt ") \
               .replace(",", " Komma ") \
               .replace(";", " Semikolon ") \
               .replace(":", " Doppelpunkt ") \
               .replace("?", " Fragezeichen ") \
               .replace("!", " Ausrufezeichen ") \
               .replace("(", " Klammer auf ") \
               .replace(")", " Klammer zu ") \
               .replace("\"", " Anführungszeichen ") \
               .replace("'", " Apostroph ") \
               .replace("-", " Bindestrich ") \
               .replace("/", " Schrägstrich ")

# Funktion zur Generierung von Audio mit Elevenlabs
def generate_audio_with_elevenlabs(text, speed=1.0):
    """Generiert eine Audiodatei mit Elevenlabs TTS."""
    url = "https://api.elevenlabs.io/v1/text-to-speech/ThT5KcBeYPX3keUQqHPh"  # Voice ID für "Daniel" (deutsche Stimme)
    
    # Text mit ausgesprochenen Satzzeichen
    text_with_spoken_punctuation = replace_punctuation_with_words(text)
    
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": ELEVENLABS_API_KEY
    }
    
    # Geschwindigkeitsanpassung über die stability_settings
    # Elevenlabs verwendet andere Parameter als ResponsiveVoice, daher Anpassung nötig
    stability = 0.5  # Standardstabilität
    
    # Die Geschwindigkeit wird durch die Anpassung der stability_settings simuliert
    # Höhere speed = niedrigere stability für schnelleres Sprechen
    if speed > 1.0:
        stability = max(0.1, 0.5 - ((speed - 1.0) * 0.2))
    # Niedrigere speed = höhere stability für langsameres Sprechen
    elif speed < 1.0:
        stability = min(0.9, 0.5 + ((1.0 - speed) * 0.2))
    
    data = {
        "text": text_with_spoken_punctuation,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": stability,
            "similarity_boost": 0.75
        }
    }
    
    try:
        response = requests.post(url, json=data, headers=headers)
        if response.status_code == 200:
            return response.content
        else:
            print(f"Fehler bei der Elevenlabs API: {response.status_code}, {response.text}")
            return None
    except Exception as e:
        print(f"Fehler bei der Elevenlabs API: {str(e)}")
        return None

# Funktion zum Teilen eines Textes in gleichmäßige Abschnitte
def split_text_into_sections(text, num_sections=3):
    """Teilt den Text in die angegebene Anzahl an Abschnitten."""
    words = text.split()
    section_size = len(words) // num_sections
    sections = []
    
    for i in range(num_sections):
        start = i * section_size
        end = (i + 1) * section_size if i < num_sections - 1 else len(words)
        sections.append(' '.join(words[start:end]))
    
    return sections

# Dekorator für passwortgeschützte Routen
def teacher_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('teacher_logged_in'):
            return redirect(url_for('teacher_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/")
def index():
    """Render die Startseite mit Auswahlmöglichkeit."""
    return render_template("index.html")

@app.route("/lehrer/login", methods=["GET", "POST"])
def teacher_login():
    """Anmeldeseite für den Lehrerbereich."""
    error = None
    if request.method == "POST":
        password = request.form.get("password")
        if password == TEACHER_PASSWORD:
            session['teacher_logged_in'] = True
            return redirect(url_for('teacher_view'))
        else:
            error = "Falsches Passwort. Bitte versuche es erneut."
    
    return render_template("login.html", error=error)

@app.route("/lehrer/logout")
def teacher_logout():
    """Abmelden vom Lehrerbereich."""
    session.pop('teacher_logged_in', None)
    return redirect(url_for('index'))

@app.route("/lehrer")
@teacher_login_required
def teacher_view():
    """Render die Lehreransicht."""
    return render_template("lehrer.html")

@app.route("/schueler")
def student_view():
    """Render die Schüleransicht."""
    return render_template("schueler.html")

@app.route("/create_dictation", methods=["POST"])
@teacher_login_required
def create_dictation():
    """Erstellt ein neues Diktat und generiert die Audiodateien."""
    # Daten aus dem Formular holen
    title = request.form.get("title", "Unbenanntes Diktat")
    text = request.form.get("text")
    speed = float(request.form.get("speed", "1.0"))
    
    if not text:
        return jsonify({"error": "Kein Text angegeben."}), 400

    try:
        # Eindeutige ID für das Diktat generieren
        dictation_id = generate_dictation_id()
        
        # Generiere Audio für das gesamte Diktat
        full_audio = generate_audio_with_elevenlabs(text, speed)
        if not full_audio:
            return jsonify({"error": "Fehler bei der Audio-Generierung."}), 500
        
        # Speichere die Audio-Datei
        full_audio_filename = f"{dictation_id}_full.mp3"
        full_audio_path = os.path.join(AUDIO_DIR, full_audio_filename)
        with open(full_audio_path, 'wb') as f:
            f.write(full_audio)
        
        # Teile das Diktat in Abschnitte
        sections = split_text_into_sections(text)
        section_audio_files = []
        
        # Generiere und speichere Audio für jeden Abschnitt
        for i, section_text in enumerate(sections):
            section_audio = generate_audio_with_elevenlabs(section_text, speed)
            if section_audio:
                section_filename = f"{dictation_id}_section{i+1}.mp3"
                section_path = os.path.join(AUDIO_DIR, section_filename)
                with open(section_path, 'wb') as f:
                    f.write(section_audio)
                section_audio_files.append(section_filename)
        
        # Diktat speichern
        dictation_info = {
            "id": dictation_id,
            "title": title,
            "text": text,
            "speed": speed,
            "created_at": datetime.now().isoformat(),
            "word_count": len(text.split()),  # Wortanzahl für die spätere Prozentberechnung
            "audio_file": full_audio_filename,
            "section_audio_files": section_audio_files
        }
        
        dictations[dictation_id] = dictation_info
        
        return jsonify({
            "success": True,
            "dictation_id": dictation_id,
            "title": title
        })
        
    except Exception as e:
        return jsonify({"error": f"Fehler beim Erstellen des Diktats: {str(e)}"}), 500

@app.route("/audio/<filename>")
def get_audio(filename):
    """Gibt eine Audiodatei zurück."""
    try:
        return send_file(os.path.join(AUDIO_DIR, filename), mimetype="audio/mpeg")
    except Exception as e:
        return jsonify({"error": f"Fehler beim Laden der Audiodatei: {str(e)}"}), 404

@app.route("/delete_dictation/<dictation_id>", methods=["POST"])
@teacher_login_required
def delete_dictation(dictation_id):
    """Löscht ein Diktat und die zugehörigen Audiodateien."""
    if dictation_id not in dictations:
        return jsonify({"error": "Diktat nicht gefunden."}), 404
    
    try:
        # Audiodateien löschen
        dictation = dictations[dictation_id]
        audio_file = dictation.get("audio_file")
        if audio_file:
            audio_path = os.path.join(AUDIO_DIR, audio_file)
            if os.path.exists(audio_path):
                os.remove(audio_path)
        
        # Abschnitts-Audiodateien löschen
        section_files = dictation.get("section_audio_files", [])
        for section_file in section_files:
            section_path = os.path.join(AUDIO_DIR, section_file)
            if os.path.exists(section_path):
                os.remove(section_path)
        
        # Diktat löschen
        del dictations[dictation_id]
        
        # Zugehörige Ergebnisse löschen
        global results
        results = [r for r in results if r["dictation_id"] != dictation_id]
        
        return jsonify({"success": True})
        
    except Exception as e:
        return jsonify({"error": f"Fehler beim Löschen des Diktats: {str(e)}"}), 500

@app.route("/get_dictation/<dictation_id>")
def get_dictation(dictation_id):
    """Gibt Informationen zu einem Diktat zurück, ohne den Originaltext."""
    if dictation_id not in dictations:
        return jsonify({"error": "Diktat nicht gefunden."}), 404
    
    # Die Schüleransicht erhält NICHT den Original-Text
    dictation = dictations[dictation_id].copy()
    dictation.pop("text", None)  # Originaltext entfernen
    
    return jsonify(dictation)

@app.route("/get_dictations")
@teacher_login_required
def get_dictations():
    """Gibt eine Liste aller verfügbaren Diktate zurück (nur für Lehreransicht)."""
    # Vereinfachte Liste ohne Originaltexte
    dictation_list = []
    for d_id, dictation in dictations.items():
        dictation_list.append({
            "id": d_id,
            "title": dictation.get("title", "Unbenanntes Diktat"),
            "created_at": dictation.get("created_at", "")
        })
    
    return jsonify(dictation_list)

@app.route("/get_full_dictation/<dictation_id>")
@teacher_login_required
def get_full_dictation(dictation_id):
    """Gibt vollständige Informationen zu einem Diktat zurück, einschließlich Text (nur für Lehreransicht)."""
    if dictation_id not in dictations:
        return jsonify({"error": "Diktat nicht gefunden."}), 404
    
    # Die Lehreransicht erhält den vollständigen Eintrag
    return jsonify(dictations[dictation_id])

@app.route("/check_dictation", methods=["POST"])
def check_dictation():
    """Überprüft das vom Benutzer eingegebene Diktat und gibt Feedback."""
    dictation_id = request.form.get("dictation_id")
    user_text = request.form.get("user_text")
    student_name = request.form.get("student_name", "Unbekannt")
    
    if not dictation_id or not user_text:
        return jsonify({"error": "Fehlende Eingaben."}), 400
    
    if dictation_id not in dictations:
        return jsonify({"error": "Diktat nicht gefunden."}), 404
    
    original_text = dictations[dictation_id]["text"]
    dictation_title = dictations[dictation_id]["title"]
    
    try:
        # Claude API-Aufruf für die Korrektur
        message = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=1000,
            messages=[
                {"role": "user", "content": f"""
                    Du bist ein Sprachlehrer für Deutsch.
                    
                    🔹 **Deine Aufgabe:**  
                    1️⃣ **Vergleiche den vom Schüler geschriebenen Text mit dem Originaltext.**  
                    2️⃣ **Liste NUR die falsch geschriebenen Wörter und ihre korrekte Schreibweise auf.**
                    3️⃣ **Gib eine Bewertung (0-10 Punkte) und berechne die Prozentzahl der richtig geschriebenen Wörter.**
                    
                    📌 **Originaltext (Lehrerversion):**
                    "{original_text}"
                    
                    📝 **Vom Schüler geschriebener Text:**
                    "{user_text}"
                    
                    Deine Antwort soll folgendes Format haben:
                    
                    **Korrektur:**
                    falsch: [falsches Wort 1] → richtig: [richtiges Wort 1]
                    falsch: [falsches Wort 2] → richtig: [richtiges Wort 2]
                    ...
                    
                    **Bewertung:**
                    [X/10 Punkte]
                    
                    **Prozent korrekt:**
                    [Y%]
                    
                    Außerdem gib am Ende deiner Antwort eine einfache Zeile mit nur der Punktzahl und dem Prozentsatz aus, 
                    die ich programmatisch extrahieren kann. Zum Beispiel: "SCORE:7.5|PERCENT:85"
                """}
            ]
        )
        
        result_text = message.content[0].text if isinstance(message.content, list) else message.content
        
        # Punktzahl und Prozentsatz aus der Antwort extrahieren
        score = 0
        percent = 0
        
        # Nach dem Score-Format suchen
        import re
        score_match = re.search(r"SCORE:(\d+\.?\d*)\|PERCENT:(\d+\.?\d*)", result_text)
        if score_match:
            score = float(score_match.group(1))
            percent = float(score_match.group(2))
            
            # Diese Zeile aus dem Ergebnis entfernen
            result_text = re.sub(r"SCORE:\d+\.?\d*\|PERCENT:\d+\.?\d*", "", result_text).strip()
        
        # Ergebnis in der "Datenbank" speichern
        result_entry = {
            "student_name": student_name,
            "dictation_id": dictation_id,
            "dictation_title": dictation_title,
            "score": score,
            "percent": percent,
            "created_at": datetime.now().isoformat()
        }
        results.append(result_entry)
        
        return jsonify({
            "result": result_text,
            "score": score,
            "percent": percent
        })
        
    except Exception as e:
        result = f"❌ Fehler bei der Claude API: {str(e)}"
        return jsonify({"result": result, "score": 0, "percent": 0})

@app.route("/get_results")
@teacher_login_required
def get_results():
    """Gibt eine Liste aller Ergebnisse zurück (nur für Lehreransicht)."""
    return jsonify(results)

if __name__ == "__main__":
    app.run(debug=True)
