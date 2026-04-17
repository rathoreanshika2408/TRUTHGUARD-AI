from flask import Flask, request, jsonify
from flask_cors import CORS
from groq import Groq
from PIL import Image
import pytesseract
import os
import json
import platform
import subprocess
import tempfile
import requests as http_requests
from urllib.parse import urlparse
from datetime import datetime
from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# ── Tesseract path (works on both Windows and Render/Linux) ──
if platform.system() == "Windows":
    pytesseract.pytesseract.tesseract_cmd = os.getenv(
        "TESSERACT_PATH", r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    )
else:
    pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

# ── Clients ──
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
twilio_sid   = os.getenv("TWILIO_ACCOUNT_SID")
twilio_token = os.getenv("TWILIO_AUTH_TOKEN")
twilio_client = Client(twilio_sid, twilio_token) if twilio_sid and twilio_token else None

# ── CORS preflight ──
@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        response = jsonify({'status': 'ok'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
        return response

# ── AI System Prompt ──
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

# ── Trusted domains & scam URL patterns ──
TRUSTED_DOMAINS = [
    "gov.in", "nic.in", "india.gov.in", "pib.gov.in",
    "google.com", "youtube.com", "wikipedia.org",
    "ndtv.com", "thehindu.com", "hindustantimes.com",
    "timesofindia.com", "indianexpress.com", "bbc.com",
    "reuters.com", "boomlive.in", "altnews.in", "vishvasnews.com"
]

SCAM_KEYWORDS = [
    "free-recharge", "win-prize", "lucky-draw", "get-rich",
    "click-here-now", "limited-offer", "pm-yojana-free",
    "whatsapp-lottery", "bit.ly", "tinyurl", "cutt.ly"
]

# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

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
        parsed = json.loads(raw.strip())
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
    try:
        image = Image.open(file.stream).convert("RGB")
        try:
            text = pytesseract.image_to_string(image, lang="eng+hin")
        except Exception:
            text = pytesseract.image_to_string(image, lang="eng")
        text = text.strip()
        if not text:
            return jsonify({"error": "No text found in image. Try a clearer photo."}), 400
        return jsonify({"extracted_text": text})
    except Exception as e:
        return jsonify({"error": f"OCR failed: {str(e)}"}), 500


@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    message = data.get("message", "").strip()
    history = data.get("history", [])
    if not message:
        return jsonify({"error": "No message"}), 400
    messages = [{"role": "system", "content": (
        "You are TruthGuard AI assistant. "
        "Help users fact-check claims and understand misinformation in India. "
        "Keep responses under 3 sentences. Be direct and practical. "
        "When unsure, direct users to boomlive.in or altnews.in."
    )}]
    for h in history[-6:]:
        messages.append(h)
    messages.append({"role": "user", "content": message})
    response = groq_client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=messages,
        temperature=0.5,
        max_tokens=300
    )
    reply = response.choices[0].message.content or "I'm not sure. Please check boomlive.in or altnews.in."
    return jsonify({"reply": reply})


@app.route("/trends", methods=["GET"])
def trends():
    month = datetime.now().strftime("%B")
    year  = datetime.now().year
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "You are a misinformation trends analyst for India. Reply ONLY with valid JSON, no markdown."},
                {"role": "user", "content": f"""Generate current trending scams in India for {month} {year}.
Return JSON in this exact format:
{{
  "trending": [
    {{
      "title": "Scam name",
      "category": "Financial Scam",
      "description": "2 sentence description of this scam",
      "why_now": "Why this scam is happening in {month}",
      "count": 2847,
      "change": "+28%",
      "color": "#E63946",
      "blog_url": "https://boomlive.in",
      "blog_source": "boomlive.in"
    }}
  ],
  "top_keywords": ["keyword1", "keyword2"],
  "total_analyzed_today": 14823,
  "month": "{month} {year}"
}}
Generate 5 realistic trending scams relevant to {month} in India (tax season, festivals, elections, weather etc).
"""}
            ],
            temperature=0.7,
            max_tokens=800,
        )
        raw = response.choices[0].message.content.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return jsonify(json.loads(raw.strip()))
    except Exception:
        return jsonify({
            "trending": [
                {"title": "ITR Refund Scam", "category": "Financial Scam", "count": 3102, "change": "+41%", "color": "#E63946",
                 "description": "Fake SMS claiming income tax refund, asking to click a link.", "why_now": "Tax filing season in April",
                 "blog_url": "https://boomlive.in", "blog_source": "boomlive.in"},
                {"title": "IPL Betting Fraud", "category": "Financial Scam", "count": 2847, "change": "+63%", "color": "#F59E0B",
                 "description": "WhatsApp groups promising guaranteed IPL match betting wins.", "why_now": "IPL season running in April",
                 "blog_url": "https://altnews.in", "blog_source": "altnews.in"},
            ],
            "top_keywords": ["ITR refund", "IPL betting", "OTP scam"],
            "total_analyzed_today": 14823,
            "month": f"{month} {year}"
        })


@app.route('/verify-url', methods=['POST'])
def verify_url():
    data = request.get_json()
    url  = data.get('url', '').strip()
    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    parsed = urlparse(url)
    domain = parsed.netloc.lower().replace("www.", "")

    is_trusted = any(domain == td or domain.endswith("." + td) for td in TRUSTED_DOMAINS)
    scam_flag  = any(kw in url.lower() for kw in SCAM_KEYWORDS)

    try:
        r = http_requests.get(url, timeout=5, allow_redirects=True)
        is_reachable = r.status_code == 200
        final_url    = r.url
        redirected   = final_url != url
    except Exception:
        is_reachable = False
        final_url    = url
        redirected   = False

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Analyze this URL for misinformation, scam, or phishing. Domain: {domain}. Full URL: {url}. Reply with JSON only."}
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
    except Exception as e:
        result = {"error": str(e)}

    result["is_trusted_domain"] = is_trusted
    result["scam_url_pattern"]  = scam_flag
    result["is_reachable"]      = is_reachable
    result["redirected"]        = redirected
    result["final_url"]         = final_url
    result["domain"]            = domain
    return jsonify(result)

import yt_dlp
import tempfile

@app.route('/analyze-youtube', methods=['POST'])
def analyze_youtube():
    data = request.get_json()
    url = data.get('url', '').strip()
    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = os.path.join(tmpdir, "audio.mp3")

            ydl_opts = {
                'format': 'worstaudio/worst',
                'outtmpl': audio_path,
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}],
                'quiet': True,
                'max_filesize': 10 * 1024 * 1024,  # 10MB max
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            # Use Groq's Whisper API — fast, no local model
            with open(audio_path, 'rb') as f:
                transcription = groq_client.audio.transcriptions.create(
                    model="whisper-large-v3-turbo",
                    file=f,
                    response_format="text"
                )
            transcript = transcription.strip()

        # Analyze with AI
        ai_response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Analyze this YouTube video transcript for misinformation. Reply with JSON only:\n\n{transcript[:3000]}"}
            ],
            temperature=0.2,
            max_tokens=500,
        )
        raw = ai_response.choices[0].message.content.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw.strip())
        parsed["transcript_preview"] = transcript[:400]
        return jsonify(parsed)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route("/send-whatsapp", methods=["POST"])
def send_whatsapp():
    data        = request.json
    result      = data.get("result", {})
    phone       = data.get("phone", os.getenv("USER_WHATSAPP_NUMBER"))
    score       = result.get("credibility_score", "?")
    verdict     = result.get("verdict", "UNKNOWN")
    explanation = result.get("explanation", "")
    techniques  = ", ".join(result.get("manipulation_techniques", []))
    action      = result.get("recommended_action", "")
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
    data     = request.json
    email    = data.get("email", "")
    password = data.get("password", "")
    if email and password:
        return jsonify({"success": True, "user": {
            "name": email.split("@")[0].title(),
            "email": email,
            "whatsapp": os.getenv("USER_WHATSAPP_NUMBER")
        }})
    return jsonify({"success": False, "error": "Invalid credentials"}), 401


@app.route("/signup", methods=["POST"])
def signup():
    data     = request.json
    email    = data.get("email", "")
    password = data.get("password", "")
    phone    = data.get("phone", "")
    name     = data.get("name", "")
    if email and password and phone:
        return jsonify({"success": True, "user": {
            "name": name, "email": email, "whatsapp": phone
        }})
    return jsonify({"success": False, "error": "All fields required"}), 400


@app.route("/whatsapp-webhook", methods=["GET", "POST"])
def whatsapp_webhook():
    incoming_msg = request.form.get("Body", "").strip()
    sender       = request.form.get("From", "")
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
        result     = json.loads(raw.strip())
        score      = result.get("credibility_score", "?")
        verdict    = result.get("verdict", "UNKNOWN")
        explanation= result.get("explanation", "")
        techniques = "\n".join([f"• {t}" for t in result.get("manipulation_techniques", [])])
        action     = result.get("recommended_action", "")
        hindi      = result.get("explanation_hindi", "")
        emoji = "🔴" if score <= 25 else "🟠" if score <= 50 else "🟡" if score <= 75 else "🟢"
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
            to=sender, body=reply
        )
    except Exception:
        twilio_client.messages.create(
            from_=f"whatsapp:{os.getenv('TWILIO_WHATSAPP_NUMBER')}",
            to=sender,
            body="⚠️ TruthGuard AI could not analyze this message. Please try again."
        )
    return "OK", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)))