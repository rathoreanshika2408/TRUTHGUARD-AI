from flask import Flask, request, jsonify
from flask_cors import CORS
from groq import Groq
from PIL import Image
import pytesseract
import os
import json
import platform
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

if platform.system() == "Windows":
    pytesseract.pytesseract.tesseract_cmd = os.getenv("TESSERACT_PATH")

SYSTEM_PROMPT = """You are TruthGuard AI, an expert misinformation detection system for India.
Analyze the given text and respond ONLY with a valid JSON object, no extra text, no markdown, no backticks.

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
}"""

@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.json
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "No text provided"}), 400
    try:
        response = client.chat.completions.create(
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
        return jsonify(json.loads(raw.strip()))
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
        return jsonify({"error": "Could not extract text"}), 400
    return jsonify({"extracted_text": text})

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    message = data.get("message", "").strip()
    history = data.get("history", [])
    if not message:
        return jsonify({"error": "No message"}), 400
    messages = [{"role": "system", "content": "You are TruthGuard AI assistant. Help users fact-check claims in India. Keep responses under 3 sentences. Direct users to boomlive.in or altnews.in when unsure."}]
    for h in history[-6:]:
        messages.append(h)
    messages.append({"role": "user", "content": message})
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=messages,
        temperature=0.5,
        max_tokens=300
    )
    return jsonify({"reply": response.choices[0].message.content})

@app.route("/trends", methods=["GET"])
def trends():
    return jsonify({
        "trending": [
            {"category": "Health Misinformation", "count": 2847, "change": "+12%", "color": "#FF6B6B"},
            {"category": "Financial Scams", "count": 2103, "change": "+28%", "color": "#FFD166"},
            {"category": "Political Propaganda", "count": 1876, "change": "+5%", "color": "#00C2CB"},
            {"category": "Govt Scheme Scams", "count": 1654, "change": "+41%", "color": "#F4A261"},
            {"category": "Communal Messages", "count": 1203, "change": "+8%", "color": "#A8DADC"},
        ],
        "top_keywords": ["free recharge", "PM Yojana", "cancer cure", "OTP scam", "आयुष्मान", "free laptop"],
        "total_analyzed_today": 14823
    })

if __name__ == "__main__":
    app.run(debug=True, port=5000)
    
if platform.system() == "Windows":
    pytesseract.pytesseract.tesseract_cmd = os.getenv("TESSERACT_PATH")