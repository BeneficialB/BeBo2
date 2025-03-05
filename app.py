from flask import Flask, request, jsonify, render_template, redirect, url_for, session, Response
import anthropic
import os
import random
import string
import json
import requests
from datetime import datetime
from functools import wraps
from dotenv import load_dotenv

# Lade die Umgebungsvariablen aus .env
load_dotenv()

# API-Schlüssel
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
ELEVEN_LABS_API_KEY = os.getenv("ELEVEN_LABS_API_KEY")

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

# Datenbank-Simulation für Diktate und Ergebnisse (im Produktiveinsatz durch eine echte DB ersetzen)
dictations = {}
results = []  # Hier werden die Schülerergebnisse gespeichert

# Deutsche Stimme für die TTS - Otto
GERMAN_VOICE_ID = "FTNCalFNG5bRnkkaP5Ug"  # Otto (deutsche Stimme)

# Hilfsfunktion für Diktat-ID-Generierung
def generate_dictation_id(length=6):
    """Generiert eine zufällige Diktat-ID aus Buchstaben und Zahlen."""
    characters = string.ascii_uppercase + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

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

@app.route("/env_check")
def env_check():
    """Einfacher Endpunkt zur Überprüfung der Umgebungsvariablen"""
    env_vars = {
        "ELEVEN_LABS_API_KEY": ELEVEN_LABS_API_KEY is not None,
        "ELEVEN_LABS_KEY_LENGTH": len(ELEVEN_LABS_API_KEY) if ELEVEN_LABS_API_KEY else 0,
        "ELEVEN_LABS_KEY_START": ELEVEN_LABS_API_KEY[:5] + "..." if ELEVEN_LABS_API_KEY else "None",
        "CLAUDE_API_KEY": CLAUDE_API_KEY is not None,
        "GERMAN_VOICE_ID": GERMAN_VOICE_ID,
        "VOICE_NAME": "Otto"
    }
    return jsonify(env_vars)

@app.route("/elevenlabs_test")
def elevenlabs_test():
    """Einfacher Test für die Eleven Labs API mit Otto-Stimme"""
    if not ELEVEN_LABS_API_KEY:
        return jsonify({
            "success": False,
            "error": "Eleven Labs API-Schlüssel nicht gefunden!"
        })
    
    test_text = "Hallo, ich bin Otto. Ich helfe dir bei deinem Diktat."
    
    try:
        # Eleven Labs API aufrufen
        api_url = f"https://api.elevenlabs.io/v1/text-to-speech/{GERMAN_VOICE_ID}"
        
        response = requests.post(
            api_url,
            headers={
                "Content-Type": "application/json",
                "xi-api-key": ELEVEN_LABS_API_KEY
            },
            json={
                "text": test_text,
                "model_id": "eleven_multilingual_v2"
            }
        )
        
        if response.ok:
            return Response(
                response.content,
                mimetype="audio/mpeg",
                headers={"Cache-Control": "no-cache"}
            )
        else:
            return jsonify({
                "success": False,
                "status_code": response.status_code,
                "error": response.text
            })
    
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })

@app.route("/validate_eleven_key")
def validate_eleven_key():
    """Überprüft, ob der Eleven Labs API-Schlüssel korrekt funktioniert"""
    print("=== ELEVEN LABS TOKEN CHECK ===")
    
    if not ELEVEN_LABS_API_KEY:
        return jsonify({
            "valid": False,
            "error": "API-Schlüssel nicht konfiguriert"
        })
    
    try:
        # Einfachen API-Aufruf machen, um die Gültigkeit zu prüfen
        response = requests.get(
            "https://api.elevenlabs.io/v1/user/subscription",
            headers={"xi-api-key": ELEVEN_LABS_API_KEY}
        )
        
        print(f"Subscription API Status Code: {response.status_code}")
        
        if response.ok:
            subscription_data = response.json()
            print(f"Subscription Daten: {json.dumps(subscription_data)}")
            
            # Stimmen abrufen
            voices_response = requests.get(
                "https://api.elevenlabs.io/v1/voices",
                headers={"xi-api-key": ELEVEN_LABS_API_KEY}
            )
            
            if voices_response.ok:
                voices_data = voices_response.json()
                voices = [{"voice_id": v["voice_id"], "name": v["name"]} 
                         for v in voices_data.get("voices", [])]
                
                # Prüfen, ob unsere Otto-Stimme verfügbar ist
                otto_available = any(v["voice_id"] == GERMAN_VOICE_ID for v in voices)
                
                # Detaillierte API-Informationen zurückgeben
                return jsonify({
                    "valid": True,
                    "subscription": subscription_data,
                    "voices_count": len(voices),
                    "voices": voices,
                    "otto_available": otto_available,
                    "key_starts_with": ELEVEN_LABS_API_KEY[:5] + "..."
                })
            else:
                print(f"Fehler beim Abrufen der Stimmen: {voices_response.status_code}")
                print(f"Antwort: {voices_response.text}")
                return jsonify({
                    "valid": False, 
                    "error": f"Stimmen-API-Fehler: {voices_response.status_code}",
                    "key_starts_with": ELEVEN_LABS_API_KEY[:5] + "..."
                })
        else:
            print(f"Fehlerantwort: {response.text}")
            return jsonify({
                "valid": False,
                "error": f"API-Schlüssel ungültig oder abgelaufen: {response.status_code}",
                "details": response.text,
                "key_starts_with": ELEVEN_LABS_API_KEY[:5] + "..."
            })
    
    except Exception as e:
        print(f"Ausnahme bei der API-Validierung: {str(e)}")
        return jsonify({
            "valid": False,
            "error": str(e),
            "key_starts_with": ELEVEN_LABS_API_KEY[:5] + "..."
        })

@app.route("/create_dictation", methods=["POST"])
@teacher_login_required
def create_dictation():
    """Erstellt ein neues Diktat."""
    # Daten aus dem Formular holen
    title = request.form.get("title", "Unbenanntes Diktat")
    text = request.form.get("text")
    speed = float(request.form.get("speed", "1.0"))
    
    if not text:
        return jsonify({"error": "Kein Text angegeben."}), 400

    try:
        # Eindeutige ID für das Diktat generieren
        dictation_id = generate_dictation_id()
        
        # Diktat speichern
        dictation_info = {
            "id": dictation_id,
            "title": title,
            "text": text,
            "speed": speed,
            "created_at": datetime.now().isoformat(),
            "word_count": len(text.split())  # Wortanzahl für die spätere Prozentberechnung
        }
        
        dictations[dictation_id] = dictation_info
        
        return jsonify({
            "success": True,
            "dictation_id": dictation_id,
            "title": title
        })
        
    except Exception as e:
        return jsonify({"error": f"Fehler beim Erstellen des Diktats: {str(e)}"}), 500

@app.route("/delete_dictation/<dictation_id>", methods=["POST"])
@teacher_login_required
def delete_dictation(dictation_id):
    """Löscht ein Diktat."""
    print(f"Delete request for dictation_id: {dictation_id}")
    
    if dictation_id not in dictations:
        return jsonify({"error": "Diktat nicht gefunden."}), 404
    
    try:
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
    # Log the received ID (helpful for debugging)
    print(f"Received dictation_id: {dictation_id}")
    
    if dictation_id not in dictations:
        return jsonify({"error": "Diktat nicht gefunden."}), 404
    
    # Die Schüleransicht erhält NICHT den Original-Text
    dictation = dictations[dictation_id].copy()
    dictation.pop("text", None)  # Originaltext entfernen
    
    return jsonify(dictation)

@app.route("/get_dictation_audio/<dictation_id>")
def get_dictation_audio(dictation_id):
    """Gibt den Diktattext für die Sprachausgabe zurück (keine visuelle Anzeige für Schüler)."""
    print(f"Audio request for dictation_id: {dictation_id}")
    
    if dictation_id not in dictations:
        return jsonify({"error": "Diktat nicht gefunden."}), 404
    
    # Nur Text und Geschwindigkeit zurückgeben, für die Sprachausgabe
    return jsonify({
        "text": dictations[dictation_id]["text"],
        "speed": dictations[dictation_id]["speed"]
    })

@app.route("/elevenlabs_tts", methods=["POST"])
def elevenlabs_tts():
    """Proxy für die Eleven Labs API, um den API-Schlüssel zu schützen."""
    # API-Schlüssel aus Umgebungsvariablen laden
    if not ELEVEN_LABS_API_KEY:
        print("❌ Eleven Labs API-Schlüssel fehlt!")
        return jsonify({"error": "Eleven Labs API-Schlüssel nicht konfiguriert."}), 500

    # Daten aus der Anfrage holen
    try:
        data = request.json
        print(f"Received request for TTS")
    except Exception as e:
        print(f"Error parsing request data: {e}")
        return jsonify({"error": "Ungültige JSON-Daten"}), 400
    
    text = data.get("text")
    # Standardmäßig die Otto-Stimme verwenden
    voice_id = data.get("voice_id", GERMAN_VOICE_ID)
    
    if not text:
        return jsonify({"error": "Kein Text angegeben."}), 400

    # Textlänge begrenzen, um Probleme mit der API zu vermeiden
    if len(text) > 300:
        text = text[:300] + "..."
        print("Text was truncated to 300 characters due to length restrictions")

    try:
        # Eleven Labs API aufrufen
        api_url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        
        # Einfache Payload mit minimalen Parametern
        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2"
        }
        
        print(f"Sende Anfrage an Eleven Labs API mit Stimme: {voice_id}")
        print(f"API-Schlüssel (erste 5 Zeichen): {ELEVEN_LABS_API_KEY[:5]}...")
        
        response = requests.post(
            api_url,
            headers={
                "Content-Type": "application/json",
                "xi-api-key": ELEVEN_LABS_API_KEY
            },
            json=payload
        )
        
        # Response-Status protokollieren
        print(f"Eleven Labs API Status Code: {response.status_code}")
        
        # Antwort überprüfen
        if not response.ok:
            error_msg = f"Eleven Labs API-Fehler: {response.status_code}"
            try:
                error_json = response.json()
                error_msg += f" - {json.dumps(error_json)}"
            except:
                error_msg += f" - {response.text}"
            
            print(error_msg)
            return jsonify({"error": error_msg}), response.status_code
        
        print("✅ Eleven Labs API erfolgreiche Antwort!")
        # Audio-Daten zurückgeben
        return Response(
            response.content,
            mimetype="audio/mpeg",
            headers={"Cache-Control": "no-cache"}
        )
        
    except Exception as e:
        error_msg = f"Fehler bei der Eleven Labs API: {str(e)}"
        print(error_msg)
        return jsonify({"error": error_msg}), 500

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
    # Log the received ID (helpful for debugging)
    print(f"Received full dictation_id: {dictation_id}")
    
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
    
    print(f"Checking dictation: {dictation_id}, student: {student_name}")
    
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
