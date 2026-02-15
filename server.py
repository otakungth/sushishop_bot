from flask import Flask
import threading

app = Flask(__name__)

@app.route('/')
def home():
    return "Sushi Shop Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def server_on():
    t = threading.Thread(target=run)
    t.daemon = True
    t.start()
    print("✅ Server started on port 8080")
