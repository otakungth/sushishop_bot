from flask import Flask, jsonify
import threading
import time
import os
import datetime

app = Flask(__name__)

# เก็บสถานะ
start_time = time.time()
bot_status = {
    "online": False,
    "guilds": 0,
    "users": 0,
    "last_heartbeat": None
}

@app.route('/')
def home():
    """หน้าหลักแสดงสถานะบอท"""
    uptime = time.time() - start_time
    hours, remainder = divmod(uptime, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    return f"""
    <html>
        <head>
            <title>Sushi Shop Bot Status</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; background: #1a1a1a; color: #fff; }}
                .status {{ padding: 20px; border-radius: 10px; margin: 20px 0; }}
                .online {{ background: #00ff0022; border: 1px solid #00ff00; }}
                .offline {{ background: #ff000022; border: 1px solid #ff0000; }}
                .info {{ background: #333; padding: 10px; border-radius: 5px; margin: 5px 0; }}
                h1 {{ color: #ffa500; }}
            </style>
        </head>
        <body>
            <h1>🍣 Sushi Shop Discord Bot</h1>
            <div class="status {'online' if bot_status['online'] else 'offline'}">
                <h2>สถานะ: {'🟢 ออนไลน์' if bot_status['online'] else '🔴 ออฟไลน์'}</h2>
            </div>
            <div class="info">
                <p><strong>🤖 เวลาทำงาน:</strong> {int(hours)}h {int(minutes)}m {int(seconds)}s</p>
                <p><strong>📊 เซิร์ฟเวอร์:</strong> {bot_status['guilds']}</p>
                <p><strong>👥 ผู้ใช้:</strong> {bot_status['users']}</p>
                <p><strong>💓 หัวใจดวงสุดท้าย:</strong> {bot_status['last_heartbeat'] or 'ไม่ทราบ'}</p>
                <p><strong>📅 วันที่:</strong> {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</p>
            </div>
            <p><a href="/health" style="color: #ffa500;">ตรวจสอบสุขภาพ</a> | <a href="/metrics" style="color: #ffa500;">ดูเมตริก</a></p>
        </body>
    </html>
    """

@app.route('/health')
def health():
    """Health check endpoint สำหรับ Render"""
    return jsonify({
        "status": "healthy" if bot_status['online'] else "degraded",
        "timestamp": datetime.datetime.now().isoformat(),
        "uptime": time.time() - start_time,
        "bot_online": bot_status['online']
    }), 200 if bot_status['online'] else 503

@app.route('/metrics')
def metrics():
    """Prometheus-style metrics"""
    return f"""
    # HELP bot_uptime_seconds Bot uptime in seconds
    # TYPE bot_uptime_seconds gauge
    bot_uptime_seconds {time.time() - start_time}
    
    # HELP bot_online Bot online status
    # TYPE bot_online gauge
    bot_online {1 if bot_status['online'] else 0}
    
    # HELP bot_guilds Number of guilds
    # TYPE bot_guilds gauge
    bot_guilds {bot_status['guilds']}
    
    # HELP bot_users Number of users
    # TYPE bot_users gauge
    bot_users {bot_status['users']}
    """

def update_bot_status(online, guilds=0, users=0):
    """อัพเดทสถานะบอท (เรียกจาก main bot)"""
    bot_status['online'] = online
    bot_status['guilds'] = guilds
    bot_status['users'] = users
    bot_status['last_heartbeat'] = datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')

def run():
    """รัน Flask server"""
    port = int(os.getenv("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def server_on():
    """เริ่ม server ใน thread แยก"""
    t = threading.Thread(target=run)
    t.daemon = True
    t.start()
    print(f"✅ Web server started on port {os.getenv('PORT', 8080)}")
    return t
