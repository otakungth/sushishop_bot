import os
from flask import Flask, jsonify

# Create Flask app
app = Flask(__main__)

# Health check route (Render needs this to keep service alive)
@app.route("/")
def home():
    return "Service is running!", 200

# Optional status route
@app.route("/health")
def health():
    return jsonify({
        "status": "healthy"
    }), 200


def run():
    """
    Starts the Flask server.
    Uses Render's assigned PORT automatically.
    Falls back to 10000 for local development.
    """
    port = int(os.environ.get("PORT", 10000))
    print(f"🚀 Starting Flask server on port {port}")

    app.run(
        host="0.0.0.0",   # Required for Render
        port=port,
        debug=False      # Never use debug=True on Render
    )
