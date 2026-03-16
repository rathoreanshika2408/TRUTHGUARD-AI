from flask import Flask, request, jsonify
from flask_cors import CORS
from groq import Groq
from PIL import Image
import pytesseract
import os
import json
import platform
from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
twilio_client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))

if platform.system() == "Windows":
    pytesseract.pytesseract.tesseract_cmd = os.getenv("TESSERACT_PATH")

SYSTEM_PROMPT = """You are TruthGuard AI, an expert misinformation detection system for India.

Analyze the given text and respond ONLY with a valid JSON object, no extra text, no markdown, no backticks. Just raw JSON.

Use this exact format:
{
  "credibility_score": 15,
  "verdict": "LIKELY FALSE",
  "verdict_color": "red",
  "manipulation_techniques": ["Urgency trigger", "Financial scam"],
  "red_flags": ["suspicious phrase 1", "suspicious phrase 2"],
  "explanation": "2-3 sentence explanation in English.",
  "explanation_hindi": "same explanation in simple Hindi.",
  "recommended_action": "One short sentence on what the user should do.",
  "fact_check_sources": ["boomlive.in", "altnews.in"]
}

Manipulation techniques to detect: Fear-based messaging, Urgency trigger, Emotional manipulation, Propaganda, Financial scam, Health misinformation, Government scheme scam, Fake statistics, Communal messaging.

Be especially alert to: fake government schemes, WhatsApp health cure forwards, financial scams promising free money, messages asking to share urgently."""

@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.json
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "No text provided"}), 400
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Analyze this for misinformation. Reply with JSON only:\n\n{text}"}
            ],
            temperature=0.2,
            max_tokens=500,
        )
        raw = response.choices[0].message.content.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()
        parsed = json.loads(raw)
        return jsonify(parsed)
    except json.JSONDecodeError:
        return jsonify({"error": "AI response was not valid JSON. Try again."}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/ocr", methods=["POST"])
def ocr():
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400
    file = request.files["image"]
    image = Image.open(file.stream)
    try:
        text = pytesseract.image_to_string(image, lang="eng+hin")
    except:
        text = pytesseract.image_to_string(image, lang="eng")
    text = text.strip()
    if not text:
        return jsonify({"error": "Could not extract text from image"}), 400
    return jsonify({"extracted_text": text})

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    message = data.get("message", "").strip()
    history = data.get("history", [])
    if not message:
        return jsonify({"error": "No message"}), 400
    messages = [{"role": "system", "content": """You are TruthGuard AI assistant.
Help users fact-check claims and understand misinformation in India.
Keep responses under 3 sentences. Be direct and practical.
When unsure, direct users to boomlive.in or altnews.in."""}]
    for h in history[-6:]:
        messages.append(h)
    messages.append({"role": "user", "content": message})
    response = groq_client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=messages,
        temperature=0.5,
        max_tokens=300
    )
    reply = response.choices[0].message.content
    if not reply:
        reply = "I'm not sure. Please check boomlive.in or altnews.in."
    return jsonify({"reply": reply})

@app.route("/trends", methods=["GET"])
def trends():
    return jsonify({
        "trending": [
            {"category": "Health Misinformation",  "count": 2847, "change": "+12%", "color": "#E63946"},
            {"category": "Financial Scams",         "count": 2103, "change": "+28%", "color": "#F59E0B"},
            {"category": "Political Propaganda",    "count": 1876, "change": "+5%",  "color": "#6B7280"},
            {"category": "Govt Scheme Scams",       "count": 1654, "change": "+41%", "color": "#F59E0B"},
            {"category": "Communal Messages",       "count": 1203, "change": "+8%",  "color": "#9CA3AF"},
        ],
        "top_keywords": ["free recharge", "PM Yojana", "cancer cure", "OTP scam", "आयुष्मान", "free laptop", "WhatsApp forward"],
        "total_analyzed_today": 14823
    })

@app.route("/send-whatsapp", methods=["POST"])
def send_whatsapp():
    data = request.json
    result = data.get("result", {})
    phone = data.get("phone", os.getenv("USER_WHATSAPP_NUMBER"))
    score = result.get("credibility_score", "?")
    verdict = result.get("verdict", "UNKNOWN")
    explanation = result.get("explanation", "")
    techniques = ", ".join(result.get("manipulation_techniques", []))
    action = result.get("recommended_action", "")
    message = f"""🛡️ *TruthGuard AI Analysis*

📊 *Credibility Score:* {score}/100
⚠️ *Verdict:* {verdict}

🔍 *Manipulation Techniques:*
{techniques if techniques else "None detected"}

💡 *Explanation:*
{explanation}

✅ *What to do:*
{action}

_Verified by TruthGuard AI — Fighting misinformation in India_"""
    try:
        twilio_client.messages.create(
            from_=f"whatsapp:{os.getenv('TWILIO_WHATSAPP_NUMBER')}",
            to=f"whatsapp:{phone}",
            body=message
        )
        return jsonify({"success": True, "message": "Sent to WhatsApp!"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/login", methods=["POST"])
def login():
    data = request.json
    email = data.get("email", "")
    password = data.get("password", "")
    # Demo login — in production use a real database
    if email and password:
        return jsonify({
            "success": True,
            "user": {
                "name": email.split("@")[0].title(),
                "email": email,
                "whatsapp": os.getenv("USER_WHATSAPP_NUMBER")
            }
        })
    return jsonify({"success": False, "error": "Invalid credentials"}), 401

@app.route("/signup", methods=["POST"])
def signup():
    data = request.json
    email = data.get("email", "")
    password = data.get("password", "")
    phone = data.get("phone", "")
    name = data.get("name", "")
    if email and password and phone:
        return jsonify({
            "success": True,
            "user": {
                "name": name,
                "email": email,
                "whatsapp": phone
            }
        })
    return jsonify({"success": False, "error": "All fields required"}), 400

@app.route("/whatsapp-webhook", methods=["GET", "POST"])
def whatsapp_webhook():
    incoming_msg = request.form.get("Body", "").strip()
    sender = request.form.get("From", "")
    
    if not incoming_msg:
        return "OK", 200

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Analyze this for misinformation. Reply with JSON only:\n\n{incoming_msg}"}
            ],
            temperature=0.2,
            max_tokens=500,
        )
        raw = response.choices[0].message.content.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())

        score = result.get("credibility_score", "?")
        verdict = result.get("verdict", "UNKNOWN")
        explanation = result.get("explanation", "")
        techniques = "\n".join([f"• {t}" for t in result.get("manipulation_techniques", [])])
        action = result.get("recommended_action", "")
        hindi = result.get("explanation_hindi", "")

        if score <= 25:
            emoji = "🔴"
        elif score <= 50:
            emoji = "🟠"
        elif score <= 75:
            emoji = "🟡"
        else:
            emoji = "🟢"

        reply = f"""{emoji} *TruthGuard AI Analysis*

📊 *Credibility Score:* {score}/100
⚠️ *Verdict:* {verdict}

🔍 *Manipulation Techniques:*
{techniques if techniques else "• None detected"}

💡 *Why suspicious:*
{explanation}

🇮🇳 *Hindi:*
{hindi}

✅ *What to do:*
{action}

_TruthGuard AI · Fighting misinformation in India_"""

        twilio_client.messages.create(
            from_=f"whatsapp:{os.getenv('TWILIO_WHATSAPP_NUMBER')}",
            to=sender,
            body=reply
        )

    except Exception as e:
        twilio_client.messages.create(
            from_=f"whatsapp:{os.getenv('TWILIO_WHATSAPP_NUMBER')}",
            to=sender,
            body="⚠️ TruthGuard AI could not analyze this message. Please try again."
        )

    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)))