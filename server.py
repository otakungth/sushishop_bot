from flask import Flask
import threading
import time

app = Flask(__name__)

@app.route('/')
def home():
    return "Sushi Shop Bot is running!"

@app.route('/health')
def health():
    return {"status": "alive", "time": time.time()}, 200

def run():
    # ใช้ port ที่ Render กำหนด หรือ 8080
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def server_on():
    t = threading.Thread(target=run)
    t.daemon = True
    t.start()
    print(f"✅ Server started on port {os.environ.get('PORT', 8080)}")
