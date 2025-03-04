from flask import Flask, request, jsonify, render_template, redirect, url_for, session
import anthropic
import os
import random
import string
import json
from datetime import datetime
from dotenv import load_dotenv

# Lade die Umgebungsvariablen aus .env
load_dotenv()

# API-Schlüssel
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")

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

# Hilfsfunktion für Diktat-ID-Generierung
def generate_dictation_id(length=6):
    """Generiert eine zufällige Diktat-ID aus Buchstaben und Zahlen."""
    characters = string.ascii_uppercase + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

@app.route("/")
def index():
    """Render die Startseite mit Auswahlmöglichkeit."""
    return render_template("index.html")

@app.route("/lehrer")
def teacher_view():
    """Render die Lehreransicht."""
    return render_template("lehrer.html")

@app.route("/schueler")
def student_view():
    """Render die Schüleransicht."""
    return render_template("schueler.html")

@app.route("/create_dictation", methods=["POST"])
def create_dictation():
    """Erstellt ein neues Diktat."""
    # Daten aus dem Formular holen
    title = request.form.get("title", "Unbenanntes Diktat")
    text = request.form.get("text")
    language = request.form.get("language", "Deutsch")
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
            "language": language,
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
def get_dictations():
    """Gibt eine Liste aller verfügbaren Diktate zurück (nur für Lehreransicht)."""
    # Vereinfachte Liste ohne Originaltexte
    dictation_list = []
    for d_id, dictation in dictations.items():
        dictation_list.append({
            "id": d_id,
            "title": dictation.get("title", "Unbenanntes Diktat"),
            "created_at": dictation.get("created_at", ""),
            "language": dictation.get("language", "Deutsch")
        })
    
    return jsonify(dictation_list)

@app.route("/get_full_dictation/<dictation_id>")
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
    language = dictations[dictation_id]["language"]
    dictation_title = dictations[dictation_id]["title"]
    
    try:
        # Claude API-Aufruf für die Korrektur
        # Claude API-Aufruf für die Korrektur
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
def get_results():
    """Gibt eine Liste aller Ergebnisse zurück (nur für Lehreransicht)."""
    return jsonify(results)

if __name__ == "__main__":
    app.run(debug=True)