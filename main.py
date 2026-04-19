import os, datetime, discord, re, asyncio, json, traceback, time, aiohttp, logging
import random
import math
import signal
import sys
import shutil
from discord.ext import commands, tasks
from discord.ui import View, Button, Modal, TextInput, Select
from discord import app_commands
from flask import Flask, jsonify
from threading import Thread
from typing import Dict, List, Optional, Tuple
from datetime import datetime as dt

# ============ STARTUP DEBUG ============
print("=" * 60)
print("Starting Sushi Shop Bot...")
print("=" * 60)

# Check Python version
print(f"🐍 Python version: {sys.version}")

# Check for token
token = os.getenv("TOKEN")
if not token:
    print("❌ ERROR: TOKEN not found in environment variables!")
    print("Please set TOKEN environment variable in Render dashboard")
    sys.exit(1)
else:
    print(f"✅ TOKEN found (length: {len(token)})")

# ============ DATA DIRECTORY SETUP WITH PERSISTENT DISK ============
PERSISTENT_DISK = "/app/data"

if os.path.exists(PERSISTENT_DISK) and os.access(PERSISTENT_DISK, os.W_OK):
    DATA_DIR = PERSISTENT_DISK
    print(f"✅ Using Render persistent disk: {DATA_DIR}")
else:
    DATA_DIR = os.getenv("DATA_DIR", ".")
    print(f"⚠️ Persistent disk not found or not writable, using: {DATA_DIR}")

try:
    os.makedirs(DATA_DIR, exist_ok=True)
    test_file = os.path.join(DATA_DIR, ".write_test")
    with open(test_file, 'w') as f:
        f.write("test")
    os.remove(test_file)
    print(f"✅ DATA_DIR: {DATA_DIR} (writable)")
except Exception as e:
    print(f"❌ Cannot use DATA_DIR={DATA_DIR}: {e}")
    DATA_DIR = "."
    os.makedirs(DATA_DIR, exist_ok=True)
    test_file = os.path.join(DATA_DIR, ".write_test")
    with open(test_file, 'w') as f:
        f.write("test")
    os.remove(test_file)
    print(f"✅ Now using DATA_DIR: {DATA_DIR}")

print(f"📁 Data files will be stored in: {DATA_DIR}")

app = Flask(__name__)
start_time = time.time()
bot_status = {"online": False, "guilds": 0, "users": 0}

@app.route('/')
def home():
    uptime = time.time() - start_time
    return f"Bot is alive! Uptime: {int(uptime/3600)}h {int((uptime%3600)/60)}m"

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "bot_online": bot_status['online']}), 200

def keep_alive():
    Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.getenv("PORT", 8080)), debug=False, use_reloader=False), daemon=True).start()
    print(f"✅ Web server started")

logging.getLogger('werkzeug').setLevel(logging.ERROR)

try:
    import pytz
    def get_thailand_time(): return dt.now(pytz.timezone('Asia/Bangkok'))
except:
    def get_thailand_time(): return dt.utcnow() + datetime.timedelta(hours=7)

intents = discord.Intents.all()
intents.message_content = True
intents.members = True

# Global variables
gamepass_rate = 7
gamepass_rate_high = 7
gamepass_threshold = 3999
group_rate_low = 4
group_rate_high = 4.5
shop_open = True
group_ticket_enabled = True
gamepass_stock = 20000
group_stock = 25000

# Daily robux sales tracking
daily_robux_sold = 0
daily_sales_date = get_thailand_time().strftime("%Y%m%d")

# Channel IDs
MAIN_CHANNEL_ID = 1475342278976606229
SALES_LOG_CHANNEL_ID = 1475344141419417612
CREDIT_CHANNEL_ID = 1475343873684406353
DELIVERED_CATEGORY_ID = 1475345768037482662
ARCHIVED_CATEGORY_ID = 1485235427500753059
BUYER_ROLE_ID = 1475346221605588992
WELCOME_CHANNEL_ID = 1475344769679888455
SUSHI_GAMEPASS_CATEGORY_ID = 1475342278976606228
ANONYMOUS_USER_ROLE_ID = 1486352633290821673

# Level roles
LEVEL_ROLES = {
    0: 1475346221605588992,
    5000: 1488073560030445569,
    10000: 1488073523946717356,
    25000: 1488073771662315614,
    50000: 1488073590162329640,
    100000: 1488073619543294153,
    555555: 1488075865337106563
}

# Level names
LEVEL_NAMES = {
    0: "🍣 | Sushi Lover",
    5000: "🐱 | Sushi Silver",
    10000: "😼 | Sushi Pass",
    25000: "🐈 | Sushi Platinum",
    50000: "🐈‍⬛ | Sushi Premium",
    100000: "🥡 | Sushi Otoro",
    555555: "👑 | Sushi Wistom"
}

GAMEPASS_CATEGORY_NAME = "sushi gamepass"
GROUP_CATEGORY_NAME = "robux group"
ROBUX_EMOJI = "<:sushirobux:1486314072701141074>"

WELCOME_MESSAGES = [
    "ยินดีต้อนรับ {} สู่ร้าน Sushi Shop 🍣",
    "สวัสดีค่ะ {} ยินดีต้อนรับนะคะ 🍣",
    "ยินดีต้อนรับนะคะ {} 🍣",
    "สวัสดีค่ะ ยินดีต้อนรับ {} ค่า 🍣"
]

# File paths
user_data_file = os.path.join(DATA_DIR, "user_data.json")
ticket_transcripts_file = os.path.join(DATA_DIR, "ticket_transcripts.json")
ticket_counter_file = os.path.join(DATA_DIR, "ticket_counter.json")
ticket_robux_data_file = os.path.join(DATA_DIR, "ticket_robux_data.json")
ticket_customer_data_file = os.path.join(DATA_DIR, "ticket_customer_data.json")
stock_file = os.path.join(DATA_DIR, "stock_values.json")
ticket_buyer_data_file = os.path.join(DATA_DIR, "ticket_buyer_data.json")
user_levels_file = os.path.join(DATA_DIR, "user_levels.json")
daily_sales_file = os.path.join(DATA_DIR, "daily_sales.json")
user_robux_balance_file = os.path.join(DATA_DIR, "user_robux_balance.json")
timer_pause_file = os.path.join(DATA_DIR, "timer_pause.json")

print(f"📄 Data files will be saved to:")
print(f"   - {user_levels_file}")
print(f"   - {stock_file}")
print(f"   - {ticket_counter_file}")
print(f"   - {daily_sales_file}")
print(f"   - {user_robux_balance_file}")
print(f"   - {timer_pause_file}")

# In-memory data structures
user_data = {}
ticket_transcripts = {}
ticket_robux_data = {}
ticket_customer_data = {}
ticket_buyer_data = {}
user_levels = {}
user_notes = {}
ticket_activity = {}
ticket_removal_tasks = {}
ticket_anonymous_mode = {}
ticket_counter = {"counter": 1, "date": get_thailand_time().strftime("%d%m%y")}
ticket_archived_timers = {}
user_robux_balance = {}
paused_timers = {}

sp_added_tracker = {}

# ============ TIMER PAUSE/RESUME FUNCTIONS ============

def load_paused_timers():
    """Load paused timer data from file"""
    global paused_timers
    try:
        if os.path.exists(timer_pause_file):
            with open(timer_pause_file, 'r', encoding='utf-8') as f:
                paused_timers = json.load(f)
                print(f"✅ Loaded {len(paused_timers)} paused timers")
        else:
            paused_timers = {}
            save_paused_timers()
    except Exception as e:
        print(f"❌ Error loading paused timers: {e}")
        paused_timers = {}

def save_paused_timers():
    """Save paused timer data to file"""
    try:
        with open(timer_pause_file, 'w', encoding='utf-8') as f:
            json.dump(paused_timers, f, ensure_ascii=False, indent=2)
        print(f"✅ Saved {len(paused_timers)} paused timers")
        return True
    except Exception as e:
        print(f"❌ Error saving paused timers: {e}")
        return False

def is_timer_paused(channel_id):
    """Check if timer is paused for a channel"""
    return str(channel_id) in paused_timers

def get_paused_remaining(channel_id):
    """Get remaining time for paused timer"""
    channel_id_str = str(channel_id)
    if channel_id_str in paused_timers:
        return paused_timers[channel_id_str].get("remaining", 0)
    return 0

def pause_timer(channel_id, remaining_seconds):
    """Pause a timer and store remaining time"""
    channel_id_str = str(channel_id)
    paused_timers[channel_id_str] = {
        "remaining": remaining_seconds,
        "paused_at": time.time()
    }
    save_paused_timers()
    print(f"⏸️ Timer paused for channel {channel_id} with {remaining_seconds} seconds remaining")

def resume_timer(channel_id):
    """Resume a timer and return remaining time, removes from paused storage"""
    channel_id_str = str(channel_id)
    if channel_id_str in paused_timers:
        remaining = paused_timers[channel_id_str].get("remaining", 0)
        del paused_timers[channel_id_str]
        save_paused_timers()
        print(f"▶️ Timer resumed for channel {channel_id} with {remaining} seconds remaining")
        return remaining
    return 0

def cancel_paused_timer(channel_id):
    """Remove a paused timer without resuming"""
    channel_id_str = str(channel_id)
    if channel_id_str in paused_timers:
        del paused_timers[channel_id_str]
        save_paused_timers()
        print(f"🗑️ Paused timer cancelled for channel {channel_id}")

# ============ ROBUX BALANCE FUNCTIONS ============

def load_robux_balance():
    """Load user robux balance from file"""
    global user_robux_balance
    try:
        if os.path.exists(user_robux_balance_file):
            with open(user_robux_balance_file, 'r', encoding='utf-8') as f:
                user_robux_balance = json.load(f)
                # Convert string values to float for decimal support
                for key, value in user_robux_balance.items():
                    if isinstance(value, str):
                        user_robux_balance[key] = float(value)
                print(f"✅ Loaded robux balance for {len(user_robux_balance)} users")
        else:
            user_robux_balance = {}
            save_robux_balance()
    except Exception as e:
        print(f"❌ Error loading robux balance: {e}")
        user_robux_balance = {}

def save_robux_balance():
    """Save user robux balance to file"""
    try:
        with open(user_robux_balance_file, 'w', encoding='utf-8') as f:
            json.dump(user_robux_balance, f, ensure_ascii=False, indent=2)
        print(f"✅ Saved robux balance for {len(user_robux_balance)} users")
        return True
    except Exception as e:
        print(f"❌ Error saving robux balance: {e}")
        return False

def get_user_robux_balance(user_id):
    """Get robux balance for a user"""
    user_id_str = str(user_id)
    return user_robux_balance.get(user_id_str, 0)

def set_user_robux_balance(user_id, amount):
    """Set robux balance for a user"""
    user_id_str = str(user_id)
    user_robux_balance[user_id_str] = amount
    save_robux_balance()
    return amount

def deduct_user_robux_balance(user_id, amount):
    """Deduct robux from user balance, returns new balance or None if insufficient"""
    user_id_str = str(user_id)
    current = user_robux_balance.get(user_id_str, 0)
    if current < amount:
        return None
    new_balance = current - amount
    user_robux_balance[user_id_str] = new_balance
    save_robux_balance()
    return new_balance

def add_user_robux_balance(user_id, amount):
    """Add robux to user balance"""
    user_id_str = str(user_id)
    current = user_robux_balance.get(user_id_str, 0)
    new_balance = current + amount
    user_robux_balance[user_id_str] = new_balance
    save_robux_balance()
    return new_balance

# ============ DAILY SALES FUNCTIONS ============
def load_daily_sales():
    global daily_robux_sold, daily_sales_date
    try:
        if os.path.exists(daily_sales_file):
            with open(daily_sales_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                daily_robux_sold = data.get("robux_sold", 0)
                daily_sales_date = data.get("date", get_thailand_time().strftime("%Y%m%d"))
                print(f"✅ Loaded daily sales: {daily_robux_sold} Robux on {daily_sales_date}")
        else:
            daily_robux_sold = 0
            daily_sales_date = get_thailand_time().strftime("%Y%m%d")
            save_daily_sales()
    except Exception as e:
        print(f"❌ Error loading daily sales: {e}")
        daily_robux_sold = 0
        daily_sales_date = get_thailand_time().strftime("%Y%m%d")

def save_daily_sales():
    try:
        data = {
            "robux_sold": daily_robux_sold,
            "date": daily_sales_date
        }
        save_json(daily_sales_file, data)
    except Exception as e:
        print(f"❌ Error saving daily sales: {e}")

async def add_daily_robux(amount):
    global daily_robux_sold, daily_sales_date
    
    daily_robux_sold += amount
    save_daily_sales()
    print(f"✅ Added {amount} Robux to daily sales. Total: {daily_robux_sold}")

def reset_daily_robux():
    """Manually reset daily robux sales to 0"""
    global daily_robux_sold, daily_sales_date
    daily_robux_sold = 0
    daily_sales_date = get_thailand_time().strftime("%Y%m%d")
    save_daily_sales()
    print(f"🔄 Daily sales manually reset to 0 on {daily_sales_date}")

# ============ JSON FUNCTIONS ============
def load_json(file, default):
    try:
        if os.path.exists(file):
            with open(file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return default
    except Exception as e:
        print(f"❌ Error loading {file}: {e}")
        return default

def save_json(file, data):
    try:
        if os.path.exists(file):
            backup_file = f"{file}.backup"
            try:
                shutil.copy2(file, backup_file)
            except:
                pass
        
        with open(file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"❌ Error saving {file}: {e}")
        return False

def backup_user_levels():
    if os.path.exists(user_levels_file):
        backup_file = os.path.join(DATA_DIR, f"user_levels_backup_{dt.now().strftime('%Y%m%d_%H%M%S')}.json")
        try:
            shutil.copy2(user_levels_file, backup_file)
            print(f"✅ Backup created: {backup_file}")
            
            for file in os.listdir(DATA_DIR):
                if file.startswith('user_levels_backup_') and file.endswith('.json'):
                    file_path = os.path.join(DATA_DIR, file)
                    if os.path.getmtime(file_path) < time.time() - 7 * 86400:
                        os.remove(file_path)
                        print(f"🗑️ Removed old backup: {file}")
        except Exception as e:
            print(f"❌ Error creating backup: {e}")

def load_user_levels():
    try:
        if os.path.exists(user_levels_file):
            with open(user_levels_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    repaired = False
                    for user_id, user_data in data.items():
                        if not isinstance(user_data, dict):
                            data[user_id] = {"sp": 0, "total_robux": 0}
                            repaired = True
                        elif "sp" not in user_data:
                            user_data["sp"] = 0
                            repaired = True
                        elif "total_robux" not in user_data:
                            user_data["total_robux"] = user_data.get("sp", 0)
                            repaired = True
                    
                    if repaired:
                        save_json(user_levels_file, data)
                    
                    return data
        return {}
    except Exception as e:
        print(f"❌ Error loading {user_levels_file}: {e}")
        backups = [f for f in os.listdir(DATA_DIR) if f.startswith('user_levels_backup_') and f.endswith('.json')]
        if backups:
            latest_backup = max(backups, key=lambda x: os.path.getmtime(os.path.join(DATA_DIR, x)))
            print(f"⚠️ Attempting to load from backup: {latest_backup}")
            try:
                with open(os.path.join(DATA_DIR, latest_backup), 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    print(f"✅ Successfully loaded from backup: {latest_backup}")
                    return data
            except Exception as backup_error:
                print(f"❌ Failed to load from backup: {backup_error}")
        return {}

def load_stock_values():
    global gamepass_stock, group_stock, gamepass_rate, gamepass_rate_high, gamepass_threshold, group_rate_low, group_rate_high, shop_open, group_ticket_enabled
    stock_data = load_json(stock_file, {})
    if stock_data:
        gamepass_stock = stock_data.get("gamepass_stock", 20000)
        group_stock = stock_data.get("group_stock", 8500)
        gamepass_rate = stock_data.get("gamepass_rate", 6.5)
        gamepass_rate_high = stock_data.get("gamepass_rate_high", 6.7)
        gamepass_threshold = stock_data.get("gamepass_threshold", 4000)
        group_rate_low = stock_data.get("group_rate_low", 4)
        group_rate_high = stock_data.get("group_rate_high", 4.5)
        shop_open = stock_data.get("shop_open", True)
        group_ticket_enabled = stock_data.get("group_ticket_enabled", True)

def save_stock_values():
    stock_data = {
        "gamepass_stock": gamepass_stock,
        "group_stock": group_stock,
        "gamepass_rate": gamepass_rate,
        "gamepass_rate_high": gamepass_rate_high,
        "gamepass_threshold": gamepass_threshold,
        "group_rate_low": group_rate_low,
        "group_rate_high": group_rate_high,
        "shop_open": shop_open,
        "group_ticket_enabled": group_ticket_enabled
    }
    save_json(stock_file, stock_data)
    print(f"✅ Stock values saved")

def save_all_data_sync():
    success = True
    success &= save_json(user_data_file, user_data)
    success &= save_json(ticket_transcripts_file, ticket_transcripts)
    success &= save_json(ticket_robux_data_file, ticket_robux_data)
    success &= save_json(ticket_customer_data_file, ticket_customer_data)
    success &= save_json(ticket_buyer_data_file, ticket_buyer_data)
    success &= save_json(user_levels_file, user_levels)
    success &= save_json(user_robux_balance_file, user_robux_balance)
    save_stock_values()
    save_paused_timers()
    print("✅ All data saved (sync)")
    return success

async def save_all_data():
    success = True
    success &= save_json(user_data_file, user_data)
    success &= save_json(ticket_transcripts_file, ticket_transcripts)
    success &= save_json(ticket_robux_data_file, ticket_robux_data)
    success &= save_json(ticket_customer_data_file, ticket_customer_data)
    success &= save_json(ticket_buyer_data_file, ticket_buyer_data)
    success &= save_json(user_levels_file, user_levels)
    success &= save_json(user_robux_balance_file, user_robux_balance)
    save_stock_values()
    save_paused_timers()
    print(f"✅ All data saved at {get_thailand_time().strftime('%H:%M:%S')}")
    return success

def load_all_data():
    global user_data, ticket_transcripts, ticket_robux_data, ticket_customer_data, ticket_buyer_data, user_levels, ticket_counter, user_robux_balance
    
    user_data = load_json(user_data_file, {})
    ticket_transcripts = load_json(ticket_transcripts_file, {})
    ticket_robux_data = load_json(ticket_robux_data_file, {})
    ticket_customer_data = load_json(ticket_customer_data_file, {})
    ticket_buyer_data = load_json(ticket_buyer_data_file, {})
    user_levels = load_user_levels()
    ticket_counter = load_json(ticket_counter_file, {"counter": 1, "date": get_thailand_time().strftime("%d%m%y")})
    
    load_stock_values()
    load_daily_sales()
    load_robux_balance()
    load_paused_timers()
    
    print(f"✅ Loaded all data from JSON:")
    print(f"   - {len(user_data)} users")
    print(f"   - {len(ticket_transcripts)} tickets")
    print(f"   - {len(ticket_buyer_data)} buyer records")
    print(f"   - {len(user_levels)} users with SP")
    print(f"   - {len(user_robux_balance)} users with robux balance")
    print(f"   - {len(paused_timers)} paused timers")
    print(f"   - Total SP: {sum(data['sp'] for data in user_levels.values())}")
    print(f"   - Stock: GP={gamepass_stock}, Group={group_stock}")
    print(f"   - Daily Sales: {daily_robux_sold} Robux")

# ============ LEVEL SYSTEM FUNCTIONS ============
def get_threshold_from_sp(sp):
    sorted_thresholds = sorted(LEVEL_ROLES.keys(), reverse=True)
    for threshold in sorted_thresholds:
        if sp >= threshold:
            return threshold
    return 0

def get_role_for_sp(sp):
    sorted_thresholds = sorted(LEVEL_ROLES.keys(), reverse=True)
    for threshold in sorted_thresholds:
        if sp >= threshold:
            return LEVEL_ROLES[threshold]
    return LEVEL_ROLES[0]

def get_level_name_from_sp(sp):
    threshold = get_threshold_from_sp(sp)
    return LEVEL_NAMES.get(threshold, "🍣 | Sushi Lover")

def get_level_info(sp):
    sorted_levels = sorted(LEVEL_ROLES.keys())
    
    current_level = 0
    current_level_name = LEVEL_NAMES.get(0, "🍣 | Sushi Lover")
    next_level = None
    next_level_name = None
    sp_needed = 0
    
    for i, threshold in enumerate(sorted_levels):
        if sp >= threshold:
            current_level = threshold
            current_level_name = LEVEL_NAMES.get(threshold, f"Level {i+1}")
            if i + 1 < len(sorted_levels):
                next_level = sorted_levels[i + 1]
                next_level_name = LEVEL_NAMES.get(next_level, f"Level {i+2}")
                sp_needed = next_level - sp
            else:
                sp_needed = 0
                next_level_name = "ระดับสูงสุด"
        else:
            if next_level is None:
                next_level = threshold
                next_level_name = LEVEL_NAMES.get(next_level, f"Level {i+1}")
                sp_needed = next_level - sp
            break
    
    if next_level is None:
        next_level = sorted_levels[-1]
        next_level_name = LEVEL_NAMES.get(next_level, "ระดับสูงสุด")
        sp_needed = 0
    
    return current_level, current_level_name, next_level, next_level_name, sp_needed

def get_next_level_sp(sp):
    sorted_levels = sorted(LEVEL_ROLES.keys())
    for threshold in sorted_levels:
        if sp < threshold:
            return threshold - sp
    return 0

async def send_level_up_dm(member, new_sp, old_sp):
    try:
        old_level_name = get_level_name_from_sp(old_sp)
        new_level_name = get_level_name_from_sp(new_sp)
        
        if old_level_name == new_level_name:
            return
        
        next_sp_needed = get_next_level_sp(new_sp)
        next_level_name = None
        
        sorted_levels = sorted(LEVEL_ROLES.keys())
        for threshold in sorted_levels:
            if new_sp < threshold:
                next_level_name = LEVEL_NAMES.get(threshold, "Unknown Level")
                break
        
        embed = discord.Embed(
            title="🎉 LEVEL UP! 🎉",
            description=f"**ยินดีด้วย {member.display_name}!**\nคุณได้เลื่อนระดับแล้ว!",
            color=0xFFD700
        )
        embed.add_field(name="📈 ระดับเดิม", value=f"{old_level_name}", inline=True)
        embed.add_field(name="➡️ ระดับใหม่", value=f"**{new_level_name}**", inline=True)
        embed.add_field(name="✨ SP ทั้งหมด", value=f"**{format_number(new_sp)}** SP", inline=False)
        
        if next_sp_needed > 0 and next_level_name:
            embed.add_field(
                name="🎯 ระดับถัดไป",
                value=f"{next_level_name}\nต้องการอีก **{format_number(next_sp_needed)}** SP",
                inline=False
            )
        else:
            embed.add_field(name="🏆 สถานะ", value="คุณถึงระดับสูงสุดแล้ว! 🎉", inline=False)
        
        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/717757556889747657/1403684950770847754/noFilter.png")
        embed.set_footer(text="Sushi Shop • ขอบคุณที่ใช้บริการ 💖")
        
        await member.send(embed=embed)
        print(f"✅ Sent level up DM to {member.name} - {old_level_name} → {new_level_name}")
        
    except Exception as e:
        print(f"⚠️ Could not send DM to {member.name}: {e}")

async def update_member_roles(member, new_sp, old_sp=None):
    """Update member roles based on their skill points"""
    if not member:
        print(f"❌ Cannot update roles: member is None")
        return False
    
    guild = member.guild
    bot_member = guild.me
    
    if not bot_member.guild_permissions.manage_roles:
        print(f"❌ Bot doesn't have Manage Roles permission in {guild.name}")
        return False
    
    if old_sp is None:
        user_id_str = str(member.id)
        if user_id_str in user_levels:
            old_sp = user_levels[user_id_str].get("sp", 0)
        else:
            old_sp = 0
    
    old_role_id = get_role_for_sp(old_sp)
    new_role_id = get_role_for_sp(new_sp)
    
    if old_role_id == new_role_id:
        expected_role = guild.get_role(new_role_id)
        if expected_role and expected_role not in member.roles:
            print(f"⚠️ User {member.name} should have role {expected_role.name} but doesn't. Adding it...")
            try:
                await member.add_roles(expected_role, reason=f"Fixing missing role for {new_sp} SP")
                print(f"✅ Added missing role {expected_role.name} to {member.name}")
                return True
            except Exception as e:
                print(f"❌ Failed to add missing role: {e}")
                return False
        return True
    
    old_role = guild.get_role(old_role_id) if old_role_id else None
    new_role = guild.get_role(new_role_id) if new_role_id else None
    
    if not new_role:
        print(f"❌ Cannot find new role with ID {new_role_id}")
        return False
    
    if new_role.position >= bot_member.top_role.position:
        print(f"⚠️ Bot cannot manage role {new_role.name} - role is higher than bot's highest role ({bot_member.top_role.name})")
        return False
    
    try:
        if old_role and old_role in member.roles:
            await member.remove_roles(old_role, reason=f"Level up from {old_sp} to {new_sp} SP")
            print(f"✅ Removed role {old_role.name} from {member.name}")
        
        if new_role not in member.roles:
            await member.add_roles(new_role, reason=f"Reached {new_sp} SP")
            print(f"✅ Added role {new_role.name} to {member.name} (SP: {new_sp})")
            
            if old_role_id != new_role_id:
                await send_level_up_dm(member, new_sp, old_sp)
            return True
        else:
            print(f"ℹ️ {member.name} already has role {new_role.name}")
            return True
            
    except discord.Forbidden:
        print(f"❌ Forbidden: Bot cannot manage role {new_role.name}")
        return False
    except Exception as e:
        print(f"❌ Failed to update roles for {member.name}: {e}")
        return False

async def add_sp(user_id, amount, ticket_id=None):
    """Add SP to a user - ALWAYS 1x rate with duplicate prevention"""
    if not user_id or amount <= 0:
        return 0
    
    # Check if SP was already added for this ticket (prevents double addition)
    if ticket_id and ticket_id in sp_added_tracker:
        print(f"⚠️ SP already added for ticket {ticket_id}, skipping duplicate addition")
        return sp_added_tracker[ticket_id]
    
    user_id_str = str(user_id)
    
    if user_id_str not in user_levels:
        user_levels[user_id_str] = {"sp": 0, "total_robux": 0}
    
    old_sp = user_levels[user_id_str]["sp"]
    user_levels[user_id_str]["sp"] += amount
    user_levels[user_id_str]["total_robux"] += amount
    new_sp = user_levels[user_id_str]["sp"]
    
    if ticket_id:
        sp_added_tracker[ticket_id] = amount
    
    save_json(user_levels_file, user_levels)
    print(f"✅ Added {amount} SP (x1) to user {user_id}: {old_sp} → {new_sp} SP")
    
    guild = None
    for g in bot.guilds:
        guild = g
        break
    
    if guild:
        member = guild.get_member(user_id)
        if member:
            success = await update_member_roles(member, new_sp, old_sp)
            if not success:
                print(f"⚠️ First attempt to update roles failed for {member.name}, retrying...")
                await asyncio.sleep(2)
                await update_member_roles(member, new_sp, old_sp)
        else:
            print(f"⚠️ Could not find member {user_id} in guild")
    else:
        print(f"⚠️ No guild found")
    
    return new_sp

async def remove_sp(user_id, amount):
    if not user_id:
        return False
    
    user_id_str = str(user_id)
    if user_id_str not in user_levels:
        return False
    
    old_sp = user_levels[user_id_str]["sp"]
    if old_sp < amount:
        return False
    
    user_levels[user_id_str]["sp"] -= amount
    user_levels[user_id_str]["total_robux"] -= amount
    new_sp = user_levels[user_id_str]["sp"]
    
    save_json(user_levels_file, user_levels)
    print(f"✅ Removed {amount} SP from {user_id}: {old_sp} → {new_sp} SP")
    
    guild = None
    for g in bot.guilds:
        guild = g
        break
    
    if guild:
        member = guild.get_member(user_id)
        if member:
            await update_member_roles(member, new_sp, old_sp)
    
    return True

# ============ HELPER FUNCTIONS ============
def get_gamepass_rate(robux_amount):
    """Return the appropriate gamepass rate based on robux amount"""
    if robux_amount > gamepass_threshold:
        return gamepass_rate_high
    return gamepass_rate

class RateLimiter:
    def __init__(self, max_calls=1, period=1.0):
        self.max_calls = max_calls
        self.period = period
        self.calls = []
        self._lock = asyncio.Lock()
    
    async def acquire(self):
        async with self._lock:
            now = time.time()
            self.calls = [c for c in self.calls if now - c < self.period]
            if len(self.calls) >= self.max_calls:
                await asyncio.sleep(self.period - (now - self.calls[0]))
                return await self.acquire()
            self.calls.append(now)
            return True

def format_number(num: int) -> str:
    return f"{num:,}"

def round_price(value):
    return int(value + 0.5001)

def is_user_always_anonymous(user):
    if not user or not user.guild:
        return False
    anonymous_role = user.guild.get_role(ANONYMOUS_USER_ROLE_ID)
    return anonymous_role and anonymous_role in user.roles

def get_next_ticket_number():
    global ticket_counter
    current_date = get_thailand_time().strftime("%d%m%y")
    if ticket_counter["date"] != current_date:
        ticket_counter = {"counter": 1, "date": current_date}
    else:
        ticket_counter["counter"] += 1
    save_json(ticket_counter_file, ticket_counter)
    return ticket_counter["counter"]

def admin_only():
    async def predicate(ctx):
        if ctx.author.guild_permissions.administrator:
            return True
        admin_role = ctx.guild.get_role(1361016912259055896)
        if admin_role and admin_role in ctx.author.roles:
            return True
        await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะผู้ดูแลระบบเท่านั้น", delete_after=5)
        return False
    return commands.check(predicate)

# ============ EXPRESSION EVALUATION FUNCTION (with space support) ============
def evaluate_expression(expr: str) -> float:
    try:
        expr = expr.replace(",", "")
        expr = expr.replace(" ", "")
        expr = expr.lower().replace("x", "*")
        expr = expr.replace("÷", "/")
        
        allowed_chars = set("0123456789+-*/().")
        if not all(c in allowed_chars for c in expr):
            raise ValueError("Expression contains invalid characters")
        
        result = eval(expr)
        
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        
        if result < 0:
            raise ValueError("Result cannot be negative")
        
        return result
    except Exception as e:
        raise ValueError(f"Invalid expression: {str(e)}")

# ============ VIEW CLASSES ============
class LevelCheckView(View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id
        
        check_btn = Button(label="เช็คเลเวลของคุณ", style=discord.ButtonStyle.primary, emoji="📊")
        rank_btn = Button(label="อันดับเลเวล", style=discord.ButtonStyle.primary, emoji="🏆")
        
        check_btn.callback = self.check_callback
        rank_btn.callback = self.rank_callback
        
        self.add_item(check_btn)
        self.add_item(rank_btn)
    
    async def check_callback(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        user_id_str = str(user_id)
        
        if user_id_str not in user_levels:
            sp = 0
            total_robux = 0
        else:
            sp = user_levels[user_id_str]["sp"]
            total_robux = user_levels[user_id_str]["total_robux"]
        
        current_level, current_level_name, next_level, next_level_name, sp_needed = get_level_info(sp)
        
        embed = discord.Embed(
            title="🍣 ระดับของคุณ",
            description=f"**{interaction.user.display_name}**",
            color=0x00FF99
        )
        embed.add_field(name="💰 โรบัคที่ซื้อทั้งหมด", value=f"**{format_number(total_robux)}** {ROBUX_EMOJI}", inline=True)
        embed.add_field(name="🏅 ระดับปัจจุบัน", value=f"{current_level_name}", inline=True)
        
        if sp_needed > 0:
            progress = (sp - current_level) / (next_level - current_level) if next_level > current_level else 0
            progress_bar = "🍣" * int(progress * 10) + "⬜" * (10 - int(progress * 10))
            embed.add_field(
                name="⏫ ความคืบหน้า", 
                value=f"`{progress_bar}` {format_number(sp - current_level)}/{format_number(next_level - current_level)} SP\nเหลืออีก **{format_number(sp_needed)}** SP สู่{next_level_name}",
                inline=False
            )
        else:
            embed.add_field(name="🏆 สถานะ", value=f"คุณถึง{current_level_name}สูงสุดแล้ว! 🎉", inline=False)
        
        embed.set_footer(text="Sushi Shop • 1 โรบัคที่ซื้อ = 1 SP")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def rank_callback(self, interaction: discord.Interaction):
        sorted_users = sorted(user_levels.items(), key=lambda x: x[1]["sp"], reverse=True)[:10]
        
        embed = discord.Embed(
            title="🏆 อันดับเลเวลสูงสุด",
            color=0xFFD700
        )
        
        if not sorted_users:
            embed.description = "ยังไม่มีข้อมูล"
        else:
            rank_text = ""
            for i, (user_id_str, data) in enumerate(sorted_users, 1):
                user = interaction.guild.get_member(int(user_id_str))
                if user:
                    name = user.mention
                else:
                    name = f"ผู้ใช้ #{user_id_str}"
                
                sp = data["sp"]
                level_name = get_level_name_from_sp(sp)
                
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "📊"
                rank_text += f"{medal} **#{i}** {name}\n"
                rank_text += f"   ✨ **{format_number(sp)}** SP | {level_name}\n\n"
            
            embed.description = rank_text
        
        embed.set_footer(text="Sushi Shop • 1 โรบัคที่ซื้อ = 1 SP")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

class CalculatorView(View):
    def __init__(self):
        super().__init__(timeout=None)
        
        gamepass_btn = Button(label="คำนวณเกมพาส", style=discord.ButtonStyle.primary, emoji="🎮")
        group_btn = Button(label="คำนวณโรกลุ่ม", style=discord.ButtonStyle.primary, emoji="👥")
        gpb_btn = Button(label="คำนวนเงินบาท (เกมพาส)", style=discord.ButtonStyle.secondary, emoji="💰")
        gb_btn = Button(label="คำนวนเงินบาท (โรกลุ่ม)", style=discord.ButtonStyle.secondary, emoji="💰")
        
        gamepass_btn.callback = self.gamepass_callback
        group_btn.callback = self.group_callback
        gpb_btn.callback = self.gpb_callback
        gb_btn.callback = self.gb_callback
        
        self.add_item(gamepass_btn)
        self.add_item(group_btn)
        self.add_item(gpb_btn)
        self.add_item(gb_btn)
    
    async def gamepass_callback(self, interaction: discord.Interaction):
        modal = GamepassCalculatorModal()
        await interaction.response.send_modal(modal)
    
    async def group_callback(self, interaction: discord.Interaction):
        modal = GroupCalculatorModal()
        await interaction.response.send_modal(modal)
    
    async def gpb_callback(self, interaction: discord.Interaction):
        modal = GamepassBahtCalculatorModal()
        await interaction.response.send_modal(modal)
    
    async def gb_callback(self, interaction: discord.Interaction):
        modal = GroupBahtCalculatorModal()
        await interaction.response.send_modal(modal)

class GamepassCalculatorModal(Modal, title="🍣 คำนวณเกมพาส"):
    robux_amount = TextInput(
        label="จำนวนโรบัค",
        placeholder="พิมพ์ตัวเลขเช่น 500, 100+200, 1000x2",
        required=True,
        max_length=50
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            robux = evaluate_expression(self.robux_amount.value)
            robux = int(robux)
            
            if robux <= 0:
                await interaction.response.send_message("❌ กรุณากรอกจำนวนที่มากกว่า 0", ephemeral=True)
                return
            
            rate = get_gamepass_rate(robux)
            price = robux / rate
            price_int = round_price(price)
            
            if robux > gamepass_threshold:
                rate_text = f"เรท {rate} (มากกว่า {gamepass_threshold} {ROBUX_EMOJI})"
            else:
                rate_text = f"เรท {rate}"
            
            embed = discord.Embed(
                title=f"🎮 Gamepass {format_number(robux)} {ROBUX_EMOJI} = {format_number(price_int)} บาท ({rate_text})",
                color=0xFFA500
            )
            embed.set_footer(text="Sushi Shop 🍣")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except ValueError as e:
            await interaction.response.send_message(f"❌ {str(e)}\nกรุณาพิมพ์ตัวเลขหรือสมการที่ถูกต้อง เช่น 1000 หรือ 500+500", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

class GamepassBahtCalculatorModal(Modal, title="🍣 คำนวณเงินบาท (เกมพาส)"):
    baht_amount = TextInput(
        label="จำนวนเงิน (บาท)",
        placeholder="พิมพ์ตัวเลขเช่น 500, 100+200, 1000x2",
        required=True,
        max_length=50
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            baht = evaluate_expression(self.baht_amount.value)
            baht = float(baht)
            
            if baht <= 0:
                await interaction.response.send_message("❌ กรุณากรอกจำนวนที่มากกว่า 0", ephemeral=True)
                return
            
            robux_normal = int(baht * gamepass_rate)
            robux_high = int(baht * gamepass_rate_high)
            
            embed = discord.Embed(
                title=f"🎮 {format_number(int(baht))} บาท",
                color=0xFFA500
            )
            embed.add_field(name=f"เรท {gamepass_rate} (ปกติ)", value=f"{format_number(robux_normal)} {ROBUX_EMOJI}", inline=True)
            embed.add_field(name=f"เรท {gamepass_rate_high} (> {gamepass_threshold} {ROBUX_EMOJI})", value=f"{format_number(robux_high)} {ROBUX_EMOJI}", inline=True)
            embed.set_footer(text="Sushi Shop 🍣")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except ValueError as e:
            await interaction.response.send_message(f"❌ {str(e)}\nกรุณาพิมพ์ตัวเลขหรือสมการที่ถูกต้อง เช่น 500 หรือ 100+200", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

class GroupCalculatorModal(Modal, title="🍣 คำนวณโรกลุ่ม"):
    robux_amount = TextInput(
        label="จำนวนโรบัค",
        placeholder="พิมพ์ตัวเลขเช่น 500, 100+200, 1000x2",
        required=True,
        max_length=50
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            robux = evaluate_expression(self.robux_amount.value)
            robux = int(robux)
            
            if robux <= 0:
                await interaction.response.send_message("❌ กรุณากรอกจำนวนที่มากกว่า 0", ephemeral=True)
                return
            
            price_baht_low = robux / group_rate_low
            price_baht_high = robux / group_rate_high
            
            if price_baht_high >= 500:
                rate = group_rate_high
                price = price_baht_high
                rate_text = f"เรท {group_rate_high} (500 บาทขึ้นไป)"
            else:
                rate = group_rate_low
                price = price_baht_low
                rate_text = f"เรท {group_rate_low} (ต่ำกว่า 500 บาท)"
            
            price_int = round_price(price)
            
            embed = discord.Embed(
                title=f"👥 Group {format_number(robux)} {ROBUX_EMOJI} = {format_number(price_int)} บาท ({rate_text})",
                color=0xFFA500
            )
            embed.set_footer(text="Sushi Shop 🍣")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except ValueError as e:
            await interaction.response.send_message(f"❌ {str(e)}\nกรุณาพิมพ์ตัวเลขหรือสมการที่ถูกต้อง เช่น 1000 หรือ 500+500", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

class GroupBahtCalculatorModal(Modal, title="🍣 คำนวณเงินบาท (โรกลุ่ม)"):
    baht_amount = TextInput(
        label="จำนวนเงิน (บาท)",
        placeholder="พิมพ์ตัวเลขเช่น 500, 100+200, 1000x2",
        required=True,
        max_length=50
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            baht = evaluate_expression(self.baht_amount.value)
            baht = float(baht)
            
            if baht <= 0:
                await interaction.response.send_message("❌ กรุณากรอกจำนวนที่มากกว่า 0", ephemeral=True)
                return
            
            if baht >= 500:
                rate = group_rate_high
                rate_text = f"เรท {group_rate_high} (500 บาทขึ้นไป)"
            else:
                rate = group_rate_low
                rate_text = f"เรท {group_rate_low} (ต่ำกว่า 500 บาท)"
            
            robux = int(baht * rate)
            
            embed = discord.Embed(
                title=f"👥 {format_number(int(baht))} บาท = {format_number(robux)} {ROBUX_EMOJI} ({rate_text})",
                color=0xFFA500
            )
            embed.set_footer(text="Sushi Shop 🍣")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except ValueError as e:
            await interaction.response.send_message(f"❌ {str(e)}\nกรุณาพิมพ์ตัวเลขหรือสมการที่ถูกต้อง เช่น 500 หรือ 100+200", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

class EmbedShopView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.update_buttons()
    
    def update_buttons(self):
        self.clear_items()
        
        gamepass_btn = Button(
            label="กดเกมพาส", 
            style=discord.ButtonStyle.success if shop_open else discord.ButtonStyle.danger, 
            emoji="🎮", 
            disabled=not shop_open
        )
        group_btn = Button(
            label="เติมโรกลุ่ม", 
            style=discord.ButtonStyle.success if shop_open else discord.ButtonStyle.danger, 
            emoji="👥", 
            disabled=not shop_open
        )
        notes_btn = Button(label="จดวันที่เข้ากลุ่ม", style=discord.ButtonStyle.secondary, emoji="📝")
        
        async def gamepass_cb(i):
            if not shop_open:
                await i.response.send_message("❌ ร้านปิดชั่วคราว กรุณารอเปิดให้บริการ", ephemeral=True)
                return
            await handle_open_ticket(i, "🍣Sushi Gamepass 🍣", "gamepass")
        
        async def group_cb(i):
            if not shop_open:
                await i.response.send_message("❌ ร้านปิดชั่วคราว กรุณารอเปิดให้บริการ", ephemeral=True)
                return
            await handle_open_ticket(i, "💰Robux Group💰", "group")
        
        async def notes_cb(i):
            await i.response.send_modal(PersonalNoteModal())
        
        gamepass_btn.callback = gamepass_cb
        group_btn.callback = group_cb
        notes_btn.callback = notes_cb
        
        self.add_item(gamepass_btn)
        self.add_item(group_btn)
        self.add_item(notes_btn)

class PersonalNoteModal(Modal, title="📝 จดวันที่เข้ากลุ่ม"):
    note = TextInput(
        label="จดวันที่เข้ากลุ่ม ดูจากวันที่ปัจจุบัน", 
        placeholder="เช่น: 20/10 , 20 ต.ค.", 
        style=discord.TextStyle.paragraph, 
        required=False, 
        max_length=1000
    )
    
    async def on_submit(self, i):
        if self.note.value.strip():
            user_notes[str(i.user.id)] = {
                "note": self.note.value, 
                "created_at": dt.now().isoformat(), 
                "updated_at": dt.now().isoformat()
            }
            embed = discord.Embed(title="✅ บันทึกโน้ตเรียบร้อย", color=0x00FF00)
            embed.add_field(name="📝 จดวันที่เข้ากลุ่ม", value=self.note.value)
            await i.response.send_message(embed=embed, ephemeral=True)
        else:
            if str(i.user.id) in user_notes:
                del user_notes[str(i.user.id)]
                await i.response.send_message("🗑️ ลบโน้ตส่วนตัวเรียบร้อยแล้ว", ephemeral=True)
            else:
                await i.response.send_message("❌ คุณยังไม่มีโน้ตที่บันทึกไว้", ephemeral=True)

class GamepassTicketModal(Modal, title="📋 แบบฟอร์มกดเกมพาส"):
    map_name = TextInput(
        label="🗺 ชื่อแมพที่จะกด?", 
        placeholder="ชื่อแมพ เช่น Sushi Fruits", 
        required=True
    )
    gamepass_name = TextInput(
        label="💸 ชื่อเกมพาส?", 
        placeholder="ชื่อเกมพาส เช่น VIP + x2 เงิน", 
        required=True
    )
    robux_amount = TextInput(
        label="🎟 ราคาของเกมพาสเท่าไหร่บ้าง?", 
        placeholder="เช่น 300 / 100+100+100 / 100x3", 
        required=True
    )
    
    async def on_submit(self, i):
        global gamepass_rate, gamepass_rate_high, gamepass_threshold
        
        try:
            if is_user_always_anonymous(i.user):
                ticket_anonymous_mode[str(i.channel.id)] = True
                ticket_customer_data[str(i.channel.id)] = "ไม่ระบุตัวตน"
                save_json(ticket_customer_data_file, ticket_customer_data)
            else:
                ticket_anonymous_mode[str(i.channel.id)] = False
            
            expr = self.robux_amount.value.lower().replace("x", "*").replace("÷", "/").replace(" ", "")
            if not re.match(r"^[\d\s\+\-\*\/\(\)]+$", expr):
                await i.response.send_message(
                    "❌ กรุณาใส่เฉพาะตัวเลข และเครื่องหมาย + - * / x ÷ ()", 
                    ephemeral=True
                )
                return
            
            robux = int(eval(expr))
            rate = get_gamepass_rate(robux)
            price = robux / rate
            price_int = round_price(price)
            
            # Create embed WITHOUT admin mention
            embed = discord.Embed(title="📨 รายละเอียดการสั่งซื้อ", color=0x00FF99)
            # NO admin mention description here
            embed.add_field(name="🗺️ ชื่อแมพ", value=self.map_name.value, inline=False)
            embed.add_field(name="🎟 เกมพาส", value=self.gamepass_name.value, inline=False)
            embed.add_field(name=f"💸 ราคา{ROBUX_EMOJI}", value=f"{format_number(robux)}", inline=True)
            embed.add_field(name="💰 ราคา", value=f"{format_number(price_int)} บาท", inline=True)
            if robux > gamepass_threshold:
                embed.add_field(name="⚡ เรท", value=f"{rate} (มากกว่า {gamepass_threshold} {ROBUX_EMOJI})", inline=True)
            embed.set_footer(text="แอดมินจะตอบกลับเร็วๆนี้")
            
            view = View(timeout=300)
            cancel_btn = Button(label="❌ ยกเลิกสินค้า", style=discord.ButtonStyle.danger)
            
            async def cancel_cb(interaction):
                await interaction.response.send_message("❌ คำสั่งซื้อถูกยกเลิก")
                await interaction.message.delete()
            
            cancel_btn.callback = cancel_cb
            view.add_item(cancel_btn)
            
            await i.response.send_message(embed=embed, view=view)
            
        except Exception as e:
            await i.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)


class GroupTicketModal(Modal, title="📋 แบบฟอร์มสั่งซื้อ Robux Group"):
    user_name = TextInput(
        label="🪪 ชื่อในเกม", 
        placeholder=" ชื่อในเกมเช่น Sushiuser67", 
        required=True
    )
    robux_amount = TextInput(
        label=f"💸 ต้องการกี่โรบัค ?", 
        placeholder="จำนวนโรบัคเช่น 3000", 
        required=True
    )
    
    async def on_submit(self, i):
        global group_rate_low, group_rate_high
        
        try:
            if is_user_always_anonymous(i.user):
                ticket_anonymous_mode[str(i.channel.id)] = True
                ticket_customer_data[str(i.channel.id)] = "ไม่ระบุตัวตน"
                save_json(ticket_customer_data_file, ticket_customer_data)
            else:
                ticket_anonymous_mode[str(i.channel.id)] = False
            
            try:
                robux = int(self.robux_amount.value.replace(",", "").strip())
            except ValueError:
                await i.response.send_message("❌ กรุณากรอกจำนวนโรบัคเป็นตัวเลข", ephemeral=True)
                return
            
            price_baht = robux / group_rate_low
            rate = group_rate_low if price_baht < 500 else group_rate_high
            price = robux / rate
            price_int = round_price(price)
            
            # Create embed WITHOUT admin mention
            embed = discord.Embed(title="📨 รายละเอียดคำสั่งซื้อโรบัคกลุ่ม", color=0x00FF99)
            # NO admin mention description here
            embed.add_field(name="🪪 ชื่อในเกม", value=self.user_name.value, inline=False)
            embed.add_field(name=f"💸 จำนวนโรบัค", value=f"{format_number(robux)}", inline=True)
            embed.add_field(name="💰 ราคา", value=f"{format_number(price_int)} บาท", inline=True)
            embed.set_footer(text="แอดมินจะตอบกลับเร็วๆนี้")
            
            view = View(timeout=300)
            cancel_btn = Button(label="❌ ยกเลิกสินค้า", style=discord.ButtonStyle.danger)
            
            async def cancel_cb(interaction):
                await interaction.response.send_message("❌ คำสั่งซื้อถูกยกเลิก")
                await interaction.message.delete()
            
            cancel_btn.callback = cancel_cb
            view.add_item(cancel_btn)
            
            await i.response.send_message(embed=embed, view=view)
            
        except Exception as e:
            print(f"Error in GroupTicketModal: {e}")
            traceback.print_exc()
            await i.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

class DeliveryView(View):
    def __init__(self, channel, product_type, robux_amount, price, buyer, is_reorder=False):
        super().__init__(timeout=None)
        self.channel = channel
        self.product_type = product_type
        self.robux_amount = robux_amount
        self.price = price
        self.buyer = buyer
        self.delivered = False
        self.is_reorder = is_reorder
        self.receipt_sent = False
        
        deliver_btn = Button(label="ส่งสินค้าแล้ว ✅", style=discord.ButtonStyle.success, emoji="✅")
        cancel_btn = Button(label="ยกเลิก ❌", style=discord.ButtonStyle.danger, emoji="❌")
        
        async def deliver_cb(i):
            if i.channel.id != self.channel.id:
                return
            
            admin_role = i.guild.get_role(1361016912259055896)
            if not i.user.guild_permissions.administrator and (not admin_role or admin_role not in i.user.roles):
                await i.response.send_message("❌ คุณไม่มีสิทธิ์ใช้ปุ่มนี้", ephemeral=True)
                return
            
            if self.delivered:
                await i.response.edit_message(content="✅ สินค้าถูกส่งเรียบร้อยแล้ว", embed=None, view=None)
                return
            
            delivery_image = None
            async for msg in self.channel.history(limit=10):
                if msg.author == i.user and msg.attachments:
                    for att in msg.attachments:
                        if any(att.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif']):
                            delivery_image = att.url
                            break
                    if delivery_image:
                        break
            
            if not delivery_image:
                await i.response.send_message(
                    "❌ ผู้ส่งสินค้าต้องแนบหลักฐานการส่งสินค้าก่อน !", 
                    ephemeral=True
                )
                return
            
            confirm_view = View(timeout=300)
            confirm_btn = Button(label="ยืนยัน", style=discord.ButtonStyle.success, emoji="✅")
            edit_btn = Button(label="แก้ไข", style=discord.ButtonStyle.secondary, emoji="✏️")
            
            async def confirm_cb(interaction):
                try:
                    self.delivered = True
                    
                    if self.buyer:
                        ticket_customer_data[str(self.channel.id)] = self.buyer.name
                        save_json(ticket_customer_data_file, ticket_customer_data)

                        if self.robux_amount:
                            ticket_id = str(self.channel.id)
                            await add_sp(self.buyer.id, self.robux_amount, ticket_id)
                            await add_daily_robux(self.robux_amount)
                            print(f"✅ Added {self.robux_amount} SP (x1) to {self.buyer.name} via DeliveryView")
                    
                    receipt_color = 0xFFA500 if self.product_type == "Gamepass" else 0x00FFFF
                    
                    anonymous_mode = ticket_anonymous_mode.get(str(self.channel.id), False)
                    buyer_display = "ไม่ระบุตัวตน" if anonymous_mode else (self.buyer.mention if self.buyer else "ไม่ทราบ")
                    
                    if not self.receipt_sent:
                        self.receipt_sent = True
                        
                        log_channel = bot.get_channel(SALES_LOG_CHANNEL_ID)
                        if log_channel:
                            log_embed = discord.Embed(
                                title=f"🍣 ใบเสร็จการสั่งซื้อ ({self.product_type}) 🍣", 
                                color=receipt_color
                            )
                            log_embed.add_field(name="😊 ผู้ซื้อ", value=buyer_display, inline=False)
                            log_embed.add_field(name=f"💸 จำนวน{ROBUX_EMOJI}", value=f"{format_number(self.robux_amount)}", inline=True)
                            price_int = round_price(self.price)
                            log_embed.add_field(name="💰 ราคาตามเรท", value=f"{format_number(price_int)} บาท", inline=True)
                            
                            if delivery_image:
                                log_embed.set_image(url=delivery_image)
                            
                            log_embed.set_footer(text=f"จัดส่งสินค้าสำเร็จ 🤗 • {get_thailand_time().strftime('%d/%m/%y, %H:%M')}")
                            
                            await log_channel.send(embed=log_embed)
                            print(f"✅ ส่งใบเสร็จไปยัง sales log channel เรียบร้อย")
                        
                        if self.buyer and not anonymous_mode and not self.is_reorder:
                            try:
                                dm_embed = discord.Embed(
                                    title=f"🧾 ใบเสร็จการซื้อสินค้า ({self.product_type})",
                                    description="ขอบคุณที่ใช้บริการ Sushi Shop นะคะ 🍣",
                                    color=receipt_color
                                )
                                dm_embed.add_field(name="📦 สินค้า", value=self.product_type, inline=True)
                                dm_embed.add_field(name=f"💸 จำนวน{ROBUX_EMOJI}", value=f"{format_number(self.robux_amount)}", inline=True)
                                price_int = round_price(self.price)
                                dm_embed.add_field(name="💰 ราคา", value=f"{format_number(price_int)} บาท", inline=True)
                                
                                if delivery_image:
                                    dm_embed.set_image(url=delivery_image)
                                
                                dm_embed.add_field(name="📝 หมายเหตุ", value="หากมีปัญหากรุณาติดต่อแอดมินในเซิร์ฟ", inline=False)
                                dm_embed.set_footer(text="Sushi Shop • ขอบคุณที่ใช้บริการ💖")
                                
                                await self.buyer.send(embed=dm_embed)
                                print(f"✅ ส่งใบเสร็จไปยัง DM ของ {self.buyer.name} เรียบร้อย")
                            except Exception as e:
                                print(f"⚠️ ไม่สามารถส่ง DM ถึง {self.buyer.name}: {e}")
                    
                    try:
                        await interaction.response.edit_message(content="✅ บันทึกการส่งสินค้าเรียบร้อย", embed=None, view=None)
                    except:
                        pass
                        
                except Exception as e:
                    print(f"Error in confirm_cb: {e}")
                    try:
                        await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)
                    except:
                        pass
            
            async def edit_cb(interaction):
                await interaction.response.send_message(
                    "📝 กรุณาแนบหลักฐานการส่งสินค้า แล้วกดปุ่ม 'ส่งสินค้าแล้ว ✅' อีกครั้ง", 
                    ephemeral=True
                )
            
            confirm_btn.callback = confirm_cb
            edit_btn.callback = edit_cb
            
            confirm_view.add_item(confirm_btn)
            confirm_view.add_item(edit_btn)
            
            embed = discord.Embed(title="📦 ยืนยันการส่งสินค้า", description="ยืนยันหลักฐานการส่งสินค้านี้หรือไม่?", color=0x00FF00)
            embed.set_image(url=delivery_image)
            
            await i.response.send_message(embed=embed, view=confirm_view, ephemeral=True)
        
        async def cancel_cb(i):
            if i.channel.id != self.channel.id:
                return
            await i.response.send_message("❌ คำสั่งซื้อถูกยกเลิก", ephemeral=True)
            await i.message.delete()
        
        deliver_btn.callback = deliver_cb
        cancel_btn.callback = cancel_cb
        
        self.add_item(deliver_btn)
        self.add_item(cancel_btn)

# ============ BOT CLASS ============
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        self.last_update_time = 0
        self.is_reacting_to_credit_channel = False
        self.commands_synced = False
        self.stock_lock = asyncio.Lock()
        self.api_rate_limiter = RateLimiter(1, 1.0)
        self.react_rate_limiter = RateLimiter(1, 0.5)
        self.channel_edit_rate_limiter = RateLimiter(1, 5)
        self.command_rate_limiter = RateLimiter(1, 2)
        self.stock_message = None
        self.main_channel_message = None
        self._shutdown_flag = False
        self._shutdown_event = asyncio.Event()
        
        load_all_data()
        backup_user_levels()
    
    async def setup_hook(self):
        print(f"✅ Setup hook completed")
        # Sync slash commands
        await self.tree.sync()
        print(f"✅ Slash commands synced")
    
    async def close(self):
        print("\n⚠️ กำลังปิดระบบอย่างปลอดภัย...")
        print("💾 กำลังบันทึกข้อมูลทั้งหมด...")
        
        for i in range(3):
            save_all_data_sync()
            await asyncio.sleep(0.5)
        
        backup_user_levels()
        print("✅ บันทึกข้อมูลเรียบร้อย!")
        print("👋 ลาก่อน!")
        
        await super().close()

bot = MyBot()

# ============ TICKET HELPER FUNCTIONS ============
async def schedule_removal(channel, buyer, delay_seconds):
    """Schedule removal of buyer permission after delay_seconds"""
    if is_timer_paused(channel.id):
        print(f"⏸️ Timer is paused for {channel.name}, not scheduling")
        return
    
    if str(channel.id) in ticket_removal_tasks:
        try:
            ticket_removal_tasks[str(channel.id)].cancel()
        except:
            pass
    
    task = asyncio.create_task(remove_buyer_permission_after_delay(channel, buyer, delay_seconds))
    ticket_removal_tasks[str(channel.id)] = task
    
    try:
        await task
    except asyncio.CancelledError:
        print(f"ℹ️ Removal task cancelled for {channel.name}")
    finally:
        if str(channel.id) in ticket_removal_tasks:
            del ticket_removal_tasks[str(channel.id)]

def cancel_removal(channel_id):
    """Cancel the removal timer for a channel"""
    if str(channel_id) in ticket_removal_tasks:
        ticket_removal_tasks[str(channel_id)].cancel()
        del ticket_removal_tasks[str(channel_id)]
        print(f"✅ Cancelled removal timer for channel {channel_id}")
        return True
    return False

async def reset_timer(channel, buyer):
    """Reset the 1-hour timer for a channel (used when customer clicks 'สั่งของต่อ')"""
    print(f"🔄 Resetting timer for channel {channel.name}")
    
    cancel_removal(channel.id)
    
    if is_timer_paused(channel.id):
        cancel_paused_timer(channel.id)
    
    await schedule_removal(channel, buyer, 3600)
    print(f"✅ Timer reset to 1 hour for {channel.name}")

async def schedule_auto_delete_after_delivered(channel, delay_seconds):
    """Schedule ticket to be deleted after being in delivered category for delay_seconds"""
    if str(channel.id) in ticket_archived_timers:
        try:
            ticket_archived_timers[str(channel.id)].cancel()
        except:
            pass
    
    task = asyncio.create_task(auto_delete_ticket_after_delay(channel, delay_seconds))
    ticket_archived_timers[str(channel.id)] = task
    
    try:
        await task
    except asyncio.CancelledError:
        print(f"ℹ️ Auto-delete task cancelled for {channel.name}")
    finally:
        if str(channel.id) in ticket_archived_timers:
            del ticket_archived_timers[str(channel.id)]

async def auto_delete_ticket_after_delay(channel, delay_seconds):
    """Delete ticket after delay_seconds (1 hour = 3600 seconds)"""
    try:
        print(f"⏳ Ticket {channel.name} will be deleted in {delay_seconds/3600} hours")
        await asyncio.sleep(delay_seconds)
        
        if not channel or channel not in channel.guild.channels:
            print(f"❌ Ticket {channel.name} no longer exists")
            return
        
        await save_ticket_transcript(channel, "ระบบอัตโนมัติ (1 ชั่วโมง)")
        await asyncio.sleep(2)
        
        print(f"🗑️ Auto-deleting ticket {channel.name} after {delay_seconds/3600} hours")
        await channel.delete()
        
    except Exception as e:
        print(f"❌ Error in auto_delete_ticket_after_delay: {e}")

async def update_channel_name():
    try:
        channel = bot.get_channel(MAIN_CHANNEL_ID)
        if channel:
            if shop_open:
                new_name = "〔🟢เปิด〕กดสั่งซื้อห้องนี้"
            else:
                new_name = "〔🔴ปิดชั่วคราว〕"
            
            if channel.name != new_name:
                await bot.channel_edit_rate_limiter.acquire()
                await channel.edit(name=new_name)
                print(f"✅ เปลี่ยนชื่อช่องเป็น: {new_name}")
            else:
                print(f"ℹ️ ชื่อช่องคงเดิม: {channel.name}")
    except Exception as e:
        print(f"❌ Error updating channel name: {e}")

async def update_main_channel():
    try:
        channel = bot.get_channel(MAIN_CHANNEL_ID)
        if not channel:
            return
        
        embed = discord.Embed(title="🍣 Sushi Shop 🍣 เปิดให้บริการ" if shop_open else "🍣 Sushi Shop 🍣 ปิดให้บริการ", 
                              color=0xFFA500 if shop_open else 0xFF0000)
        embed.add_field(
            name=f"🎮 กดเกมพาส | 📦 Stock: {format_number(gamepass_stock)} {'🟢' if gamepass_stock > 0 else '🔴'}", 
            value=f"```เรท: {gamepass_rate})```", 
            inline=False
        )
        embed.add_field(
            name=f"👥 โรบัคกลุ่ม | 📦 Stock: {format_number(group_stock)} {'🟢' if group_stock > 0 else '🔴'}", 
            value=f"```เรท: {group_rate_low} | 500 บาท+ เรท {group_rate_high}\n⚠️เข้ากลุ่ม 15 วันก่อนซื้อ⚠️```", 
            inline=False
        )
        embed.set_thumbnail(url="https://media.discordapp.net/attachments/717757556889747657/1403684950770847754/noFilter.png")
        embed.set_image(url="https://media.discordapp.net/attachments/1485285161955360963/1487653032563965962/image-241.png")
        embed.set_footer(
            text=f"Sushi Shop • รับกดเกมพาสและอื่น ๆ |: {get_thailand_time().strftime('%d/%m/%y %H:%M')}", 
            icon_url="https://media.discordapp.net/attachments/717757556889747657/1403684950770847754/noFilter.png"
        )
        
        view = EmbedShopView()
        
        if bot.main_channel_message:
            try:
                await bot.main_channel_message.edit(embed=embed, view=view)
                print("✅ Updated main channel message")
                return
            except:
                bot.main_channel_message = None
        
        async for msg in channel.history(limit=20):
            if msg.author == bot.user and len(msg.embeds) > 0:
                if "Sushi Shop" in msg.embeds[0].title:
                    bot.main_channel_message = msg
                    await msg.edit(embed=embed, view=view)
                    print("✅ Found and updated existing main channel message")
                    return
        
        bot.main_channel_message = await channel.send(embed=embed, view=view)
        print("✅ Sent new main channel message")
        
    except Exception as e:
        print(f"❌ Error updating main channel: {e}")
        traceback.print_exc()

async def handle_open_ticket(interaction, category_name, stock_type):
    global gamepass_stock, group_stock
    
    try:
        if stock_type == "gamepass" and gamepass_stock <= 0:
            await interaction.response.send_message("❌ โรบัคหมดชั่วคราว", ephemeral=True)
            return
        
        if stock_type == "group" and group_stock <= 0:
            await interaction.response.send_message("❌ โรบัคหมดชั่วคราว", ephemeral=True)
            return
        
        if not shop_open:
            await interaction.response.send_message("❌ ปิดชั่วคราว กรุณารอร้านเปิด", ephemeral=True)
            return
        
        existing = discord.utils.get(
            interaction.guild.text_channels, 
            name=f"ticket-{interaction.user.name}-{interaction.user.id}".lower()
        )
        
        if existing:
            view = View()
            view.add_item(discord.ui.Button(
                label="📩 ไปที่ตั๋ว", 
                url=f"https://discord.com/channels/{existing.guild.id}/{existing.id}", 
                style=discord.ButtonStyle.link
            ))
            await interaction.response.send_message(
                "📌 คุณมีตั๋วเปิดอยู่แล้ว กดปุ่มด้านล่างเพื่อไปที่ตั๋ว", 
                view=view, 
                ephemeral=True
            )
            return
        
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        admin_role = interaction.guild.get_role(1361016912259055896)
        if admin_role:
            overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        if stock_type == "gamepass":
            category = discord.utils.get(interaction.guild.categories, id=SUSHI_GAMEPASS_CATEGORY_ID)
            if not category:
                category = discord.utils.get(interaction.guild.categories, name=category_name)
        else:
            category = discord.utils.get(interaction.guild.categories, name=category_name)
        
        if not category:
            await interaction.response.send_message(f"❌ ไม่พบหมวดหมู่ {category_name}", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        channel = await interaction.guild.create_text_channel(
            name=f"ticket-{interaction.user.name}-{interaction.user.id}".lower(),
            overwrites=overwrites,
            category=category
        )
        
        ticket_activity[channel.id] = {
            'last_activity': get_thailand_time(), 
            'ty_used': False,
            'buyer_id': interaction.user.id
        }
        
        ticket_buyer_data[str(channel.id)] = {
            "user_id": interaction.user.id,
            "user_name": interaction.user.name,
            "user_display": interaction.user.display_name,
            "created_at": get_thailand_time().isoformat()
        }
        save_json(ticket_buyer_data_file, ticket_buyer_data)
        
        if is_user_always_anonymous(interaction.user):
            ticket_anonymous_mode[str(channel.id)] = True
            ticket_customer_data[str(channel.id)] = "ไม่ระบุตัวตน"
        else:
            ticket_customer_data[str(channel.id)] = interaction.user.name
        
        save_json(ticket_customer_data_file, ticket_customer_data)
        
        if stock_type == "gamepass":
            async with bot.stock_lock:
                gamepass_stock -= 1
        elif stock_type == "group":
            async with bot.stock_lock:
                group_stock -= 1
        
        save_stock_values()
        
        await update_main_channel()
        
        view = View()
        view.add_item(discord.ui.Button(
            label="📩 ไปที่ตั๋ว", 
            url=f"https://discord.com/channels/{channel.guild.id}/{channel.id}", 
            style=discord.ButtonStyle.link
        ))
        await interaction.followup.send("📩 เปิดตั๋วเรียบร้อย", view=view, ephemeral=True)
        
        # Get the admin role mention for the ticket embed
        admin_mention_role = interaction.guild.get_role(1486330338539077713)
        admin_mention = admin_mention_role.mention if admin_mention_role else "@Admin"
        
        if admin_role:
            await channel.send(content=f"{admin_role.mention} มีตั๋วใหม่! {admin_mention}")
        
        embed = discord.Embed(
            title="🍣 Sushi Shop 🍣", 
            color=0x00FF99
        )
        # ADD ADMIN MENTION AT THE TOP OF THE EMBED
        embed.description = f"{admin_mention}\n\n"
        embed.add_field(name="👤 ผู้ซื้อ", value=interaction.user.mention, inline=False)
        
        if stock_type == "gamepass":
            embed.add_field(
                name="🎮 บริการกดเกมพาส", 
                value=f"📦 โรบัคคงเหลือ: **{format_number(gamepass_stock)}**\n💰 เรท: {gamepass_rate} (ปกติ) | {gamepass_rate_high} (>{gamepass_threshold} {ROBUX_EMOJI})", 
                inline=False
            )
        elif stock_type == "group":
            embed.add_field(
                name="👥 เติมโรบัคกลุ่ม", 
                value=f"📦 โรบัคคงเหลือ: **{format_number(group_stock)}**\n💰 เรท: {group_rate_low} | 500 บาท+ เรท {group_rate_high}", 
                inline=False
            )
        
        embed.set_footer(text="Sushi Shop")
        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/717757556889747657/1403684950770847754/noFilter.png")
        
        ticket_view = View(timeout=None)
        
        if stock_type == "gamepass":
            form_btn = Button(label="📝 กรอกแบบฟอร์มเกมพาส", style=discord.ButtonStyle.primary, emoji="📝")
            
            async def form_callback(i):
                if i.channel.id == channel.id:
                    modal = GamepassTicketModal()
                    await i.response.send_modal(modal)
                else:
                    await i.response.send_message("❌ คุณไม่สามารถใช้ปุ่มนี้ในช่องอื่นได้", ephemeral=True)
            
            form_btn.callback = form_callback
            
        elif stock_type == "group":
            form_btn = Button(label="📝 กรอกชื่อในเกม", style=discord.ButtonStyle.primary, emoji="📝")
            
            async def form_callback(i):
                if i.channel.id == channel.id:
                    modal = GroupTicketModal()
                    await i.response.send_modal(modal)
                else:
                    await i.response.send_message("❌ คุณไม่สามารถใช้ปุ่มนี้ในช่องอื่นได้", ephemeral=True)
            
            form_btn.callback = form_callback
        
        close_btn = Button(label="🔒 ปิดตั๋ว", style=discord.ButtonStyle.danger, emoji="🔒")
        
        async def close_callback(i):
            if i.channel.id == channel.id:
                if i.user == interaction.user or (admin_role and admin_role in i.user.roles):
                    await save_ticket_transcript(channel, i.user)
                    await i.response.send_message("📪 กำลังปิดตั๋ว...")
                    await asyncio.sleep(2)
                    await channel.delete()
                else:
                    await i.response.send_message("❌ คุณไม่มีสิทธิ์ปิดตั๋วนี้", ephemeral=True)
        
        close_btn.callback = close_callback
        
        ticket_view.add_item(form_btn)
        ticket_view.add_item(close_btn)
        
        await channel.send(embed=embed, view=ticket_view)
        print(f"✅ ส่ง embed ต้อนรับในตั๋ว {channel.name} เรียบร้อย")
        
        # Get admin role mention
        admin_mention_role = interaction.guild.get_role(1486330338539077713)
        admin_mention = admin_mention_role.mention if admin_mention_role else "@Admin"

        welcome_msg = await channel.send(f"# สนใจซื้ออะไรแจ้งแอดมินได้เลยค่ะ <:sushiheart:1410484970291466300>\n{admin_mention}")
        print(f"✅ ส่งข้อความต้อนรับในตั๋ว {channel.name}")
        
    except Exception as e:
        print(f"❌ Error opening ticket: {e}")
        traceback.print_exc()
        try:
            await interaction.followup.send(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)
        except:
            pass
            
async def save_ticket_transcript(channel, action_by=None, robux_amount=None, customer_name=None):
    try:
        print(f"📝 กำลังบันทึกประวัติตั๋ว: {channel.name}")
        ticket_number = get_next_ticket_number()
        now = get_thailand_time()
        date_str = now.strftime("%d%m%y")
        time_str = now.strftime("%H%M")
        
        if robux_amount:
            robux_str = str(robux_amount)
        else:
            robux_str = ticket_robux_data.get(str(channel.id), "1099")
        
        if customer_name:
            customer_str = customer_name
        else:
            customer_str = ticket_customer_data.get(
                str(channel.id), 
                channel.name.split('-')[1] if channel.name.startswith("ticket-") else "wforr"
            )
        
        filename = f"{date_str}{time_str}-{robux_str}-{customer_str}"
        
        ticket_transcripts[str(channel.id)] = {
            "filename": filename,
            "channel_name": channel.name,
            "channel_id": channel.id,
            "ticket_number": ticket_number,
            "date": date_str,
            "time": time_str,
            "timestamp": f"{date_str}{time_str}",
            "robux_amount": str(robux_str),
            "customer_name": customer_str,
            "category": channel.category.name if channel.category else "ไม่มีหมวดหมู่",
            "created_at": now.isoformat(),
            "closed_by": str(action_by) if action_by else "ระบบอัตโนมัติ",
            "messages_count": 0
        }
        
        save_json(ticket_transcripts_file, ticket_transcripts)
        print(f"✅ บันทึกประวัติตั๋วเรียบร้อย: {filename}")
        return True, filename
        
    except Exception as e:
        print(f"❌ Error saving transcript: {e}")
        return False, str(e)

async def move_to_delivered_category(channel):
    try:
        if not channel:
            return False
            
        guild = channel.guild
        
        delivered_category = guild.get_channel(DELIVERED_CATEGORY_ID)
        if not delivered_category or not isinstance(delivered_category, discord.CategoryChannel):
            delivered_category = discord.utils.get(guild.categories, id=DELIVERED_CATEGORY_ID)
            if not delivered_category:
                print(f"❌ ไม่พบ category ส่งของแล้ว (ID: {DELIVERED_CATEGORY_ID})")
                return False
        
        if channel.category and channel.category.id == DELIVERED_CATEGORY_ID:
            print(f"ℹ️ ตั๋ว {channel.name} อยู่ใน category ส่งของแล้วแล้ว")
            return True
        
        await channel.edit(category=delivered_category)
        print(f"✅ ย้ายตั๋ว {channel.name} ไปยัง category ส่งของแล้ว")
        
        await schedule_auto_delete_after_delivered(channel, 3600)
        print(f"⏰ Ticket {channel.name} will be auto-deleted in 1 hour")
        
        return True
        
    except Exception as e:
        print(f"❌ Error moving to delivered category: {e}")
        return False

async def move_to_original_category(channel, product_type):
    try:
        if not channel:
            return False
            
        guild = channel.guild
        target_category = None
        
        if product_type == "gamepass":
            target_category = guild.get_channel(SUSHI_GAMEPASS_CATEGORY_ID)
            if not target_category:
                target_category = discord.utils.get(guild.categories, id=SUSHI_GAMEPASS_CATEGORY_ID)
        elif product_type == "group":
            target_category = discord.utils.get(guild.categories, name=GROUP_CATEGORY_NAME)
        
        if not target_category:
            print(f"❌ ไม่พบ category สำหรับ {product_type}")
            return False
        
        await channel.edit(category=target_category)
        print(f"✅ ย้ายตั๋ว {channel.name} กลับไปยัง category {target_category.name}")
        return True
        
    except Exception as e:
        print(f"❌ Error moving to original category: {e}")
        return False

async def reset_channel_name(channel, user_id, product_type):
    try:
        user = None
        for member in channel.guild.members:
            if member.id == user_id:
                user = member
                break
        
        if not user:
            channel_name = channel.name
            if '-' in channel_name:
                parts = channel_name.split('-')
                if len(parts) >= 2:
                    potential_name = parts[-1].lower()
                    for member in channel.guild.members:
                        if member.name.lower() == potential_name or member.display_name.lower() == potential_name:
                            user = member
                            break
        
        if user:
            new_name = f"ticket-{user.name}-{user.id}".lower()
            await channel.edit(name=new_name)
            print(f"✅ เปลี่ยนชื่อตั๋วเป็น: {new_name}")
            return True
        else:
            print(f"❌ ไม่พบผู้ใช้สำหรับ channel {channel.name}")
            return False
            
    except Exception as e:
        print(f"❌ Error resetting channel name: {e}")
        return False

async def remove_buyer_permission_after_delay(channel, buyer, delay_seconds):
    try:
        print(f"⏳ กำลังรอ {delay_seconds} วินาทีก่อนลบสิทธิ์การดูของ {channel.name}")
        
        remaining = delay_seconds
        while is_timer_paused(channel.id):
            paused_data = paused_timers.get(str(channel.id), {})
            remaining = paused_data.get("remaining", remaining)
            print(f"⏸️ Timer paused for {channel.name}, waiting for resume... ({remaining} seconds remaining)")
            await asyncio.sleep(5)
        
        await asyncio.sleep(remaining)
        
        if not channel or channel not in channel.guild.channels:
            print(f"❌ ตั๋ว {channel.name} ไม่มีอยู่แล้ว")
            return
        
        if buyer:
            try:
                overwrites = channel.overwrites
                if buyer in overwrites:
                    overwrites[buyer].update(read_messages=False)
                    await bot.channel_edit_rate_limiter.acquire()
                    await channel.edit(overwrites=overwrites)
                    print(f"✅ ลบสิทธิ์การดูของผู้ซื้อ {buyer.name} เรียบร้อย")
            except Exception as e:
                print(f"⚠️ ไม่สามารถลบสิทธิ์ view ของผู้ซื้อ: {e}")
        
    except asyncio.CancelledError:
        print(f"ℹ️ Removal task cancelled for {channel.name}")
        raise
    except Exception as e:
        print(f"❌ Error in remove_buyer_permission_after_delay: {e}")

async def add_buyer_role(buyer, guild):
    try:
        if not buyer:
            return False
        
        buyer_role = guild.get_role(BUYER_ROLE_ID)
        if not buyer_role:
            print(f"❌ ไม่พบ role ID: {BUYER_ROLE_ID}")
            return False
        
        if buyer_role not in buyer.roles:
            await buyer.add_roles(buyer_role)
            print(f"✅ เพิ่ม role ให้ {buyer.name} เรียบร้อย")
            return True
        else:
            print(f"ℹ️ {buyer.name} มี role อยู่แล้ว")
            return False
            
    except Exception as e:
        print(f"❌ Error adding buyer role: {e}")
        return False

# ============ CREDIT CHANNEL FUNCTIONS ============

async def update_credit_channel_name():
    """Update credit channel name with current message count"""
    try:
        credit_channel = bot.get_channel(CREDIT_CHANNEL_ID)
        if not credit_channel:
            print(f"❌ Credit channel not found with ID: {CREDIT_CHANNEL_ID}")
            return
        
        message_count = 0
        try:
            async for _ in credit_channel.history(limit=None):
                message_count += 1
                if message_count >= 10000:
                    break
            print(f"📊 Credit channel has {message_count} messages")
        except Exception as e:
            print(f"⚠️ Error counting messages: {e}")
            return
        
        new_name = f"〔✅〕ให้เครดิต--{message_count}"
        
        if credit_channel.name != new_name:
            try:
                await credit_channel.edit(name=new_name)
                print(f"✅ Credit channel name updated to: {new_name}")
                
                with open(os.path.join(DATA_DIR, "credit_message_count.txt"), "w") as f:
                    f.write(str(message_count))
            except discord.Forbidden:
                print(f"❌ Bot lacks permission to edit channel name")
            except discord.HTTPException as e:
                print(f"❌ HTTP error updating channel name: {e}")
            except Exception as e:
                print(f"❌ Error updating channel name: {e}")
        else:
            print(f"ℹ️ Credit channel name already correct: {new_name}")
            
    except Exception as e:
        print(f"❌ Error in update_credit_channel_name: {e}")
        traceback.print_exc()

@tasks.loop(minutes=5)
async def update_credit_channel_task():
    """Update credit channel name every 5 minutes"""
    print("🔄 Running credit channel update task...")
    await update_credit_channel_name()

# Also update when a message is sent in the credit channel
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    # Update credit channel name when a new message is sent
    if message.channel.id == CREDIT_CHANNEL_ID:
        if message.author != bot.user:
            # Add reactions
            await asyncio.sleep(1)
            for emoji in ["❤️", "🍣", "💎"]:
                try:
                    await message.add_reaction(emoji)
                    await asyncio.sleep(0.5)
                except:
                    pass
            
            # Update channel name immediately (don't wait for the 5-minute task)
            await update_credit_channel_name()
    
    await bot.process_commands(message)

@bot.event
async def on_message_delete(message):
    if message.channel.id == CREDIT_CHANNEL_ID:
        # Update channel name when a message is deleted
        await asyncio.sleep(1)
        await update_credit_channel_name()

@bot.event
async def on_bulk_message_delete(messages):
    if messages and messages[0].channel.id == CREDIT_CHANNEL_ID:
        await asyncio.sleep(1)
        await update_credit_channel_name()

# ============ BASIC COMMANDS ============
@bot.command(name="open")
@admin_only()
async def open_cmd(ctx):
    global shop_open
    shop_open = True
    
    try:
        await ctx.message.delete()
    except:
        pass
    
    await bot.command_rate_limiter.acquire()
    save_stock_values()
    await update_channel_name()
    await update_main_channel()
    
    embed = discord.Embed(title="✅ เปิดร้าน", description="ร้าน Sushi Shop เปิดให้บริการ", color=0x00FF00)
    embed.set_footer(text=f"เวลา: {get_thailand_time().strftime('%d/%m/%y %H:%M')}")
    await ctx.send(embed=embed)

@bot.command(name="close")
@admin_only()
async def close_cmd(ctx):
    global shop_open
    shop_open = False
    
    try:
        await ctx.message.delete()
    except:
        pass
    
    await bot.command_rate_limiter.acquire()
    save_stock_values()
    await update_channel_name()
    await update_main_channel()
    
    embed = discord.Embed(title="🔴 ปิดร้าน", description="ร้าน Sushi Shop ปิดให้บริการชั่วคราว", color=0xFF0000)
    embed.set_footer(text=f"เวลา: {get_thailand_time().strftime('%d/%m/%y %H:%M')}")
    await ctx.send(embed=embed)

@bot.command()
async def link(ctx):
    await ctx.send("# 🔗 ลิงก์กลุ่ม\nเข้ากลุ่มนี้ 15 วันก่อนซื้อโรกลุ่ม: https://www.roblox.com/communities/34713179/VALKYs\nSushi Shop 🍣")

@bot.command(name="robuxtoday")
@admin_only()
async def robuxtoday_cmd(ctx):
    """Check how many robux sold today - Admin only"""
    embed = discord.Embed(
        title="📊 ยอดขายโรบัค",
        description=f"**{format_number(daily_robux_sold)}** {ROBUX_EMOJI}",
        color=0x00FF99
    )
    embed.set_footer(text=f"ข้อมูล ณ วันที่ {get_thailand_time().strftime('%d/%m/%Y')}")
    await ctx.send(embed=embed)

@bot.command(name="resetrobuxtoday")
@admin_only()
async def reset_robuxtoday_cmd(ctx):
    """Reset daily robux sales to 0"""
    reset_daily_robux()
    
    embed = discord.Embed(
        title="🔄 รีเซ็ตยอดขายโรบัคเรียบร้อย",
        description=f"ยอดขายโรบัคถูกรีเซ็ตเป็น **0** {ROBUX_EMOJI}",
        color=0x00FF00
    )
    embed.set_footer(text=f"รีเซ็ตโดย {ctx.author.name} • {get_thailand_time().strftime('%d/%m/%Y %H:%M:%S')}")
    await ctx.send(embed=embed)
    print(f"✅ Daily robux sales reset to 0 by {ctx.author.name}")

# ============ TIMER CONTROL COMMANDS ============

@bot.command(name="stop")
@admin_only()
async def stop_timer_cmd(ctx):
    """Stop/Pause the 1-hour countdown for the current ticket channel"""
    channel = ctx.channel
    
    if not channel.name.startswith("ticket-") and not re.match(r'^\d{10}-\d+-[\w\u0E00-\u0E7F]+$', channel.name):
        await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะในตั๋วเท่านั้น", delete_after=5)
        return
    
    if str(channel.id) not in ticket_removal_tasks and not is_timer_paused(channel.id):
        await ctx.send("❌ ไม่มีตัวจับเวลาที่กำลังทำงานอยู่ในตั๋วนี้", delete_after=5)
        return
    
    if is_timer_paused(channel.id):
        await ctx.send("⏸️ ตัวจับเวลาถูกหยุดไว้แล้ว", delete_after=5)
        return
    
    remaining = 3600
    if str(channel.id) in ticket_removal_tasks:
        pass
    
    cancel_removal(channel.id)
    pause_timer(channel.id, remaining)
    
    embed = discord.Embed(
        title="⏸️ หยุดตัวจับเวลา",
        description=f"ตัวจับเวลาสำหรับตั๋วนี้ถูกหยุดชั่วคราว\n⏱️ เวลาที่เหลือ: **{remaining//60} นาที {remaining%60} วินาที**\n\nใช้ `!resume` เพื่อเริ่มต่อ",
        color=0xFFA500
    )
    await ctx.send(embed=embed)

@bot.command(name="resume")
@admin_only()
async def resume_timer_cmd(ctx):
    """Resume the 1-hour countdown for the current ticket channel"""
    channel = ctx.channel
    
    if not channel.name.startswith("ticket-") and not re.match(r'^\d{10}-\d+-[\w\u0E00-\u0E7F]+$', channel.name):
        await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะในตั๋วเท่านั้น", delete_after=5)
        return
    
    if not is_timer_paused(channel.id):
        await ctx.send("❌ ไม่มีตัวจับเวลาที่ถูกหยุดไว้ในตั๋วนี้", delete_after=5)
        return
    
    remaining = get_paused_remaining(channel.id)
    
    buyer = None
    if str(channel.id) in ticket_buyer_data:
        buyer_id = ticket_buyer_data[str(channel.id)].get("user_id")
        if buyer_id:
            buyer = ctx.guild.get_member(buyer_id)
    
    resume_timer(channel.id)
    await schedule_removal(channel, buyer, remaining)
    
    embed = discord.Embed(
        title="▶️ เริ่มตัวจับเวลาต่อ",
        description=f"ตัวจับเวลาถูกเริ่มต่อ\n⏱️ เวลาที่เหลือ: **{remaining//60} นาที {remaining%60} วินาที**",
        color=0x00FF00
    )
    await ctx.send(embed=embed)

@bot.command()
@admin_only()
async def stock(ctx, stock_type=None, amount=None):
    global gamepass_stock, group_stock
    
    try:
        await ctx.message.delete()
    except:
        pass
    
    if not stock_type:
        embed = discord.Embed(title="📊 สต๊อกสินค้า", color=0x00FF99)
        embed.add_field(name="🎮 Gamepass Stock", value=f"**{format_number(gamepass_stock)}**", inline=True)
        embed.add_field(name="👥 Group Stock", value=f"**{format_number(group_stock)}**", inline=True)
        await ctx.send(embed=embed)
        
    elif stock_type.lower() in ["gp", "gamepass", "เกมพาส"]:
        if amount is None:
            embed = discord.Embed(title="🎮 Gamepass Stock", description=f"**{format_number(gamepass_stock)}**", color=0x00FF99)
            await ctx.send(embed=embed)
        else:
            try:
                gamepass_stock = int(amount.replace(",", ""))
                save_stock_values()
                embed = discord.Embed(title="✅ ตั้งค่า Stock เรียบร้อย", description=f"ตั้งค่า สต๊อกเกมพาส เป็น **{format_number(gamepass_stock)}** เรียบร้อยแล้ว", color=0x00FF00)
                await ctx.send(embed=embed)
                await update_main_channel()
            except ValueError:
                await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)
            
    elif stock_type.lower() in ["g", "group", "กรุ๊ป"]:
        if amount is None:
            embed = discord.Embed(title="👥 Group Stock", description=f"**{format_number(group_stock)}**", color=0x00FF99)
            await ctx.send(embed=embed)
        else:
            try:
                group_stock = int(amount.replace(",", ""))
                save_stock_values()
                embed = discord.Embed(title="✅ ตั้งค่า Stock เรียบร้อย", description=f"ตั้งค่า สต๊อกโรบัคกลุ่ม เป็น **{format_number(group_stock)}** เรียบร้อยแล้ว", color=0x00FF00)
                await ctx.send(embed=embed)
                await update_main_channel()
            except ValueError:
                await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)
    else:
        embed = discord.Embed(title="❌ การใช้งานไม่ถูกต้อง", description="**การใช้งาน:**\n`!stock` - เช็ค stock ทั้งหมด\n`!stock gp <จำนวน>` - ตั้งค่า Gamepass stock\n`!stock group <จำนวน>` - ตั้งค่า Group stock", color=0xFF0000)
        await ctx.send(embed=embed)

@bot.command()
@admin_only()
async def group(ctx, status=None):
    global group_ticket_enabled
    
    try:
        await ctx.message.delete()
    except:
        pass
    
    if status is None:
        current_status = "✅ เปิด" if group_ticket_enabled else "❌ ปิด"
        embed = discord.Embed(title="👥 สถานะบริการโรกลุ่ม", description=f"**{current_status}**", color=0x00FF00 if group_ticket_enabled else 0xFF0000)
        await ctx.send(embed=embed)
        
    elif status.lower() in ["on", "enable", "เปิด"]:
        group_ticket_enabled = True
        save_stock_values()
        embed = discord.Embed(title="✅ เปิดโรกลุ่ม", description="เปิดตั๋วโรกลุ่มแล้ว", color=0x00FF00)
        await ctx.send(embed=embed)
        await update_main_channel()
        
    elif status.lower() in ["off", "disable", "ปิด"]:
        group_ticket_enabled = False
        save_stock_values()
        embed = discord.Embed(title="❌ ปิดโรกลุ่ม", description="ปิดตั๋วโรกลุ่มแล้ว", color=0xFF0000)
        await ctx.send(embed=embed)
        await update_main_channel()
    else:
        embed = discord.Embed(title="❌ การใช้งานไม่ถูกต้อง", description="**การใช้งาน:**\n`!group` - เช็คสถานะ\n`!group on` - เปิด Group ticket\n`!group off` - ปิด Group ticket", color=0xFF0000)
        await ctx.send(embed=embed)

@bot.command()
@admin_only()
async def rate(ctx, rate_type=None, low_rate=None, high_rate=None):
    global gamepass_rate, gamepass_rate_high, gamepass_threshold, group_rate_low, group_rate_high
    
    try:
        await ctx.message.delete()
    except:
        pass
    
    if rate_type is None:
        embed = discord.Embed(title="🍣 เรทโรบัคปัจจุบัน", color=0x00FF99)
        embed.add_field(name="🎮 Gamepass Rate", value=f"**{gamepass_rate}** (ปกติ) | **{gamepass_rate_high}** (>{gamepass_threshold} {ROBUX_EMOJI})", inline=True)
        embed.add_field(name="👥 Group Rate", value=f"**{group_rate_low} | 500 บาท+ เรท {group_rate_high}**", inline=True)
        await ctx.send(embed=embed)
        
    elif rate_type.lower() == "group":
        if low_rate is None or high_rate is None:
            embed = discord.Embed(title="❌ การใช้งานไม่ถูกต้อง", description="**การใช้งาน:** `!rate group <low_rate> <high_rate>`", color=0xFF0000)
            await ctx.send(embed=embed)
            return
        
        try:
            group_rate_low = float(low_rate)
            group_rate_high = float(high_rate)
            save_stock_values()
            embed = discord.Embed(title="✅ เปลี่ยนเรทโรกลุ่มเรียบร้อย", description=f"ตั้งค่าเรทโรกลุ่มเป็น **{group_rate_low} | 500 บาท+ เรท {group_rate_high}** เรียบร้อยแล้ว", color=0x00FF00)
            await ctx.send(embed=embed)
            await update_main_channel()
        except ValueError:
            await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)
        
    elif rate_type.lower() == "gamepass":
        if low_rate is None or high_rate is None:
            embed = discord.Embed(title="❌ การใช้งานไม่ถูกต้อง", description="**การใช้งาน:** `!rate gamepass <normal_rate> <high_rate>`", color=0xFF0000)
            await ctx.send(embed=embed)
            return
        
        try:
            gamepass_rate = float(low_rate)
            gamepass_rate_high = float(high_rate)
            save_stock_values()
            embed = discord.Embed(title="✅ เปลี่ยนเรทเกมพาสเรียบร้อย", description=f"ตั้งค่าเรทเกมพาสเป็น **{gamepass_rate}** (ปกติ) | **{gamepass_rate_high}** (>{gamepass_threshold} {ROBUX_EMOJI}) เรียบร้อยแล้ว", color=0x00FF00)
            await ctx.send(embed=embed)
            await update_main_channel()
        except ValueError:
            await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)
    else:
        embed = discord.Embed(title="❌ การใช้งานไม่ถูกต้อง", description="**การใช้งาน:**\n`!rate` - เช็คเรททั้งหมด\n`!rate group <low> <high>` - ตั้งค่าเรทโรกลุ่ม\n`!rate gamepass <normal> <high>` - ตั้งค่าเรทเกมพาส", color=0xFF0000)
        await ctx.send(embed=embed)

# ============ ROBUX BALANCE COMMAND ============

@bot.command(name="baht")
@admin_only()
async def baht_cmd(ctx, user: discord.Member = None, amount: float = None):
    """Set baht balance for a user. Usage: !baht @user <amount>"""
    if user is None or amount is None:
        embed = discord.Embed(
            title="❌ การใช้งานไม่ถูกต้อง",
            description="**การใช้งาน:** `!baht @ผู้ใช้ <จำนวนบาท>`\n\n**ตัวอย่าง:**\n`!baht @user123 1000` - ตั้งค่าเงินคงเหลือ 1000\n`!baht @user123 0.05` - ตั้งค่า 0.05 บาท\n\n**หมายเหตุ:** เมื่อใช้ `!od` จำนวนบาทจะถูกหักอัตโนมัติ",
            color=0xFF0000
        )
        await ctx.send(embed=embed, delete_after=10)
        return
    
    if amount < 0:
        await ctx.send("❌ จำนวนเงินต้องมากกว่าหรือเท่ากับ 0", delete_after=5)
        return
    
    set_user_robux_balance(user.id, amount)
    
    embed = discord.Embed(
        title="✅ ตั้งค่าเงินคงเหลือสำเร็จ",
        description=f"**{user.mention}** มีเงินคงเหลือ **{amount:.2f}** บาท",
        color=0x00FF00
    )
    embed.set_footer(text=f"เมื่อใช้ !od จำนวนบาทจะถูกหักอัตโนมัติ")
    await ctx.send(embed=embed)

@bot.command(name="checkbaht")
async def check_baht_cmd(ctx, user: discord.Member = None):
    """Check baht balance for a user"""
    if user is None:
        user = ctx.author
    
    if user != ctx.author:
        admin_role = ctx.guild.get_role(1361016912259055896)
        if not ctx.author.guild_permissions.administrator and (not admin_role or admin_role not in ctx.author.roles):
            await ctx.send("❌ คุณไม่มีสิทธิ์เช็คบาทคงเหลือของผู้อื่น", delete_after=5)
            return
    
    balance = get_user_robux_balance(user.id)
    
    embed = discord.Embed(
        title="💰 บาทคงเหลือ",
        description=f"**{user.mention}** มีบาทคงเหลือ **{balance:.2f}** บาท",
        color=0x00FF99
    )
    await ctx.send(embed=embed)

@bot.command(name="addbaht")
@admin_only()
async def add_baht_cmd(ctx, user: discord.Member, amount: float):
    """Add baht to user balance"""
    if amount <= 0:
        await ctx.send("❌ จำนวนบาทต้องมากกว่า 0", delete_after=5)
        return
    
    new_balance = add_user_robux_balance(user.id, amount)
    
    embed = discord.Embed(
        title="✅ เพิ่มบาทสำเร็จ",
        description=f"เพิ่ม **{amount:.2f}** บาท ให้ {user.mention}\nปัจจุบันเหลือ **{new_balance:.2f}** บาท",
        color=0x00FF00
    )
    await ctx.send(embed=embed)

@bot.command(name="checkallbaht")
@admin_only()
async def check_all_baht_cmd(ctx):
    """Check all users who have remaining baht balance"""
    if not user_robux_balance:
        await ctx.send("❌ ไม่มีข้อมูลบาทคงเหลือในระบบ", delete_after=5)
        return
    
    users_with_balance = {}
    for user_id_str, balance in user_robux_balance.items():
        if balance > 0:
            users_with_balance[user_id_str] = balance
    
    if not users_with_balance:
        await ctx.send("📊 ไม่มีผู้ใช้ที่มีเงืนคงเหลือในระบบ", delete_after=5)
        return
    
    sorted_users = sorted(users_with_balance.items(), key=lambda x: x[1], reverse=True)
    
    embeds = []
    current_embed = discord.Embed(
        title="💰 รายชื่อผู้ใช้ที่มีเงินคงเหลือ",
        color=0x00FF99
    )
    
    description = ""
    page = 1
    total_pages = (len(sorted_users) + 20) // 20
    
    for i, (user_id_str, balance) in enumerate(sorted_users, 1):
        user = ctx.guild.get_member(int(user_id_str))
        if user:
            user_name = f"{user.mention} ({user.name})"
        else:
            user_name = f"ผู้ใช้ ID: {user_id_str}"
        
        line = f"**{i}.** {user_name} - `{balance:.2f}` บาท\n"
        
        if len(description + line) > 1800:
            current_embed.description = description
            current_embed.set_footer(text=f"หน้า {page}/{total_pages}")
            embeds.append(current_embed)
            
            page += 1
            current_embed = discord.Embed(
                title="💰 รายชื่อผู้ใช้ที่มีเงินคงเหลือ (ต่อ)",
                color=0x00FF99
            )
            description = line
        else:
            description += line
    
    if description:
        current_embed.description = description
        current_embed.set_footer(text=f"หน้า {page}/{total_pages}")
        embeds.append(current_embed)
    
    for embed in embeds:
        await ctx.send(embed=embed)
    
    total_balance = sum(users_with_balance.values())
    summary_embed = discord.Embed(
        title="📊 สรุปเงินคงเหลือ",
        description=f"**จำนวนผู้ใช้ที่มีบาทคงเหลือ:** {len(users_with_balance)} คน\n"
                   f"**บาทคงเหลือรวมทั้งหมด:** {total_balance:.2f} บาท",
        color=0x00FF99
    )
    await ctx.send(embed=summary_embed)

# ============ ORDER COMMANDS ============
@bot.command()
@admin_only()
async def od(ctx, *, expr):
    global gamepass_stock, gamepass_rate, gamepass_rate_high, gamepass_threshold
    
    if not ctx.channel.name.startswith("ticket-") and not re.match(r'^\d{10}-\d+-[\w\u0E00-\u0E7F]+$', ctx.channel.name):
        await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะในตั๋วเท่านั้น", delete_after=5)
        return
    
    try:
        expr_clean = expr.replace(",", "").lower().replace("x", "*").replace("÷", "/").replace(" ", "")
        robux = int(eval(expr_clean))
        
        rate = get_gamepass_rate(robux)
        price = robux / rate
        price_int = round_price(price)
        
        buyer = None
        if str(ctx.channel.id) in ticket_buyer_data:
            buyer_id = ticket_buyer_data[str(ctx.channel.id)].get("user_id")
            if buyer_id:
                buyer = ctx.guild.get_member(buyer_id)
        
        if not buyer:
            parts = ctx.channel.name.split('-')
            if len(parts) >= 3:
                try:
                    buyer = ctx.guild.get_member(int(parts[-1]))
                except:
                    pass
        
        if not buyer:
            async for msg in ctx.channel.history(limit=20):
                if not msg.author.bot and msg.author != ctx.guild.me:
                    buyer = msg.author
                    break
        
        balance_message = None
        if buyer:
            current_balance = get_user_robux_balance(buyer.id)
            if current_balance > 0:
                if current_balance >= price_int:
                    new_balance = deduct_user_robux_balance(buyer.id, price_int)
                    balance_message = f"\n\n💰 **{buyer.mention} เหลือ {new_balance:.2f} บาท**"
                else:
                    balance_message = f"\n\n⚠️ **{buyer.mention} มีเงินบาทเหลือไม่พอ!** (มี {current_balance:.2f} บาท ต้องการ {price_int} บาท)"
            elif current_balance == 0:
                balance_message = f"\n\n💰 **{buyer.mention} ไม่มีเงินคงเหลือในระบบ**"
        
        if buyer:
            await add_buyer_role(buyer, ctx.guild)
        
        async with bot.stock_lock:
            gamepass_stock = max(0, gamepass_stock - robux)
        
        save_stock_values()
        
        ticket_robux_data[str(ctx.channel.id)] = str(robux)
        save_json(ticket_robux_data_file, ticket_robux_data)
        
        embed = discord.Embed(title="🍣คำสั่งซื้อสินค้า🍣", color=0xFFA500)
        embed.add_field(name="📦 ประเภทสินค้า", value="Gamepass", inline=False)
        embed.add_field(name=f"💸 จำนวน{ROBUX_EMOJI}", value=f"{format_number(robux)}", inline=True)
        embed.add_field(name="💰 ราคาตามเรท", value=f"{format_number(price_int)} บาท", inline=True)
        if robux > gamepass_threshold:
            embed.add_field(name="⚡ เรท", value=f"{rate} (มากกว่า {gamepass_threshold} {ROBUX_EMOJI})", inline=True)
        
        if balance_message:
            embed.add_field(name="💵 เงินคงเหลือ", value=balance_message, inline=False)
        
        embed.set_footer(text=f"รับออร์เดอร์แล้ว 🤗 • {get_thailand_time().strftime('%d/%m/%y, %H:%M')}")
        
        await ctx.send(embed=embed, view=DeliveryView(ctx.channel, "Gamepass", robux, price, buyer, is_reorder=False))
        await update_main_channel()
        
    except Exception as e:
        print(f"❌ Error in !od: {e}")
        traceback.print_exc()
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")

@bot.command()
@admin_only()
async def odg(ctx, *, expr):
    global group_stock, group_rate_low, group_rate_high
    
    if not ctx.channel.name.startswith("ticket-") and not re.match(r'^\d{10}-\d+-[\w\u0E00-\u0E7F]+$', ctx.channel.name):
        await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะในตั๋วเท่านั้น", delete_after=5)
        return
    
    try:
        expr_clean = expr.replace(",", "").lower().replace("x", "*").replace("÷", "/").replace(" ", "")
        robux = int(eval(expr_clean))
        price_baht = robux / group_rate_low
        rate = group_rate_low if price_baht < 500 else group_rate_high
        price = robux / rate
        price_int = round_price(price)
        
        buyer = None
        if str(ctx.channel.id) in ticket_buyer_data:
            buyer_id = ticket_buyer_data[str(ctx.channel.id)].get("user_id")
            if buyer_id:
                buyer = ctx.guild.get_member(buyer_id)
        
        if not buyer:
            parts = ctx.channel.name.split('-')
            if len(parts) >= 3:
                try:
                    buyer = ctx.guild.get_member(int(parts[-1]))
                except:
                    pass
        
        if not buyer:
            async for msg in ctx.channel.history(limit=20):
                if not msg.author.bot and msg.author != ctx.guild.me:
                    buyer = msg.author
                    break
        
        balance_message = None
        if buyer:
            current_balance = get_user_robux_balance(buyer.id)
            if current_balance > 0:
                if current_balance >= price_int:
                    new_balance = deduct_user_robux_balance(buyer.id, price_int)
                    balance_message = f"\n\n💰 **{buyer.mention} เหลือ {new_balance:.2f} บาท**"
                else:
                    balance_message = f"\n\n⚠️ **{buyer.mention} มีบาทคงเหลือไม่พอ!** (มี {current_balance:.2f} บาท ต้องการ {price_int} บาท)"
            elif current_balance == 0:
                balance_message = f"\n\n💰 **{buyer.mention} ไม่มีเงินคงเหลือในระบบ"
        
        if buyer:
            await add_buyer_role(buyer, ctx.guild)
        
        async with bot.stock_lock:
            group_stock = max(0, group_stock - robux)
        
        save_stock_values()
        
        ticket_robux_data[str(ctx.channel.id)] = str(robux)
        save_json(ticket_robux_data_file, ticket_robux_data)
        
        embed = discord.Embed(title="🍣คำสั่งซื้อสินค้า🍣", color=0x00FFFF)
        embed.add_field(name="📦 ประเภทสินค้า", value="Group", inline=False)
        embed.add_field(name=f"💸 จำนวน{ROBUX_EMOJI}", value=f"{format_number(robux)}", inline=True)
        embed.add_field(name="💰 ราคาตามเรท", value=f"{format_number(price_int)} บาท", inline=True)
        
        if balance_message:
            embed.add_field(name="💵 เงินคงเหลือ", value=balance_message, inline=False)
        
        embed.set_footer(text=f"รับออร์เดอร์แล้ว 🤗 • {get_thailand_time().strftime('%d/%m/%y, %H:%M')}")
        
        await ctx.send(embed=embed, view=DeliveryView(ctx.channel, "Group", robux, price, buyer, is_reorder=False))
        await update_main_channel()
        
    except Exception as e:
        print(f"❌ Error in !odg: {e}")
        traceback.print_exc()
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")

# ============ DATA COMMANDS ============
@bot.command(name="savedata")
@admin_only()
async def save_data_cmd(ctx):
    print(f"DEBUG: savedata command triggered by {ctx.author.name}")
    
    try:
        await ctx.send("💾 กำลังบันทึกข้อมูล...")
        print("DEBUG: Sent initial message")
        
        success = save_all_data_sync()
        print(f"DEBUG: save_all_data_sync returned: {success}")
        
        backup_user_levels()
        print("DEBUG: Backup created")
        
        if success and os.path.exists(user_levels_file):
            file_size = os.path.getsize(user_levels_file)
            await ctx.send(f"✅ บันทึกข้อมูลเรียบร้อย! (ขนาดไฟล์: {file_size} bytes)")
            print(f"DEBUG: Success message sent, file size: {file_size}")
        else:
            await ctx.send("❌ เกิดข้อผิดพลาดในการบันทึกข้อมูล")
            print("DEBUG: Failed to save")
            
    except Exception as e:
        print(f"ERROR in savedata: {e}")
        traceback.print_exc()
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")

@bot.command(name="checkdata")
@admin_only()
async def check_data_cmd(ctx):
    total_users = len(user_levels)
    total_sp = sum(data["sp"] for data in user_levels.values())
    
    embed = discord.Embed(title="📊 สถานะข้อมูล SP", color=0x00FF99)
    embed.add_field(name="👥 จำนวนผู้ใช้", value=f"{total_users}", inline=True)
    embed.add_field(name="✨ SP รวมทั้งหมด", value=f"{format_number(total_sp)}", inline=True)
    embed.add_field(name="💾 ไฟล์ข้อมูล", value=user_levels_file, inline=True)
    
    if os.path.exists(user_levels_file):
        file_size = os.path.getsize(user_levels_file)
        embed.add_field(name="📁 ขนาดไฟล์", value=f"{file_size} bytes", inline=True)
        embed.add_field(name="🕐 แก้ไขล่าสุด", value=dt.fromtimestamp(os.path.getmtime(user_levels_file)).strftime('%Y-%m-%d %H:%M:%S'), inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name="backupdata")
@admin_only()
async def backup_data_cmd(ctx):
    await ctx.send("🔄 กำลังสร้าง backup...")
    backup_user_levels()
    await ctx.send("✅ สร้าง backup ข้อมูล SP เรียบร้อยแล้ว")

@bot.command(name="checkdir")
@admin_only()
async def check_dir_cmd(ctx):
    embed = discord.Embed(title="📁 Data Directory Check", color=0xFFA500)
    
    embed.add_field(name="DATA_DIR", value=DATA_DIR, inline=False)
    
    exists = os.path.exists(DATA_DIR)
    embed.add_field(name="Directory Exists", value="✅ Yes" if exists else "❌ No", inline=True)
    
    if exists:
        writable = os.access(DATA_DIR, os.W_OK)
        embed.add_field(name="Writable", value="✅ Yes" if writable else "❌ No", inline=True)
    
    files = []
    for file in os.listdir(DATA_DIR):
        if file.endswith('.json'):
            files.append(file)
    
    if files:
        embed.add_field(name="JSON Files", value="\n".join(files[:10]), inline=False)
    else:
        embed.add_field(name="JSON Files", value="No JSON files found", inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name="fixallroles")
@admin_only()
async def fix_all_roles_cmd(ctx):
    """Force update all users' roles based on their SP"""
    await ctx.send("🔄 กำลังตรวจสอบและซ่อมแซมบทบาทให้สมาชิกทั้งหมด...")
    
    fixed_count = 0
    error_count = 0
    no_sp_count = 0
    
    for member in ctx.guild.members:
        if member.bot:
            continue
            
        user_id_str = str(member.id)
        if user_id_str in user_levels:
            sp = user_levels[user_id_str]["sp"]
            expected_role_id = get_role_for_sp(sp)
            expected_role = ctx.guild.get_role(expected_role_id)
            
            if expected_role:
                if expected_role not in member.roles:
                    for threshold, role_id in LEVEL_ROLES.items():
                        role = ctx.guild.get_role(role_id)
                        if role and role in member.roles and role != expected_role:
                            try:
                                await member.remove_roles(role)
                                print(f"Removed wrong role {role.name} from {member.name}")
                            except:
                                pass
                    
                    try:
                        await member.add_roles(expected_role, reason=f"Auto-fix role for {sp} SP")
                        fixed_count += 1
                        print(f"✅ Added {expected_role.name} to {member.name} (SP: {sp})")
                        await asyncio.sleep(0.5)
                    except Exception as e:
                        error_count += 1
                        print(f"❌ Failed to add role to {member.name}: {e}")
            else:
                error_count += 1
                print(f"❌ Role not found for threshold {expected_role_id}")
        else:
            no_sp_count += 1
    
    embed = discord.Embed(
        title="✅ ซ่อมแซมบทบาทเสร็จสมบูรณ์",
        description=f"**ผลลัพธ์:**\n"
                   f"✅ แก้ไขสมาชิก: {fixed_count} คน\n"
                   f"⚠️ สมาชิกไม่มี SP: {no_sp_count} คน\n"
                   f"❌ เกิดข้อผิดพลาด: {error_count} คน",
        color=0x00FF00
    )
    await ctx.send(embed=embed)

@bot.command(name="checklv")
@admin_only()
async def check_lv_cmd(ctx, user: discord.Member = None):
    """Check user level - Admin only now"""
    if user is None:
        user = ctx.author
    
    user_id_str = str(user.id)
    if user_id_str not in user_levels:
        sp = 0
        total_robux = 0
    else:
        sp = user_levels[user_id_str]["sp"]
        total_robux = user_levels[user_id_str]["total_robux"]
    
    level_name = get_level_name_from_sp(sp)
    current_level, current_level_name, next_level, next_level_name, sp_needed = get_level_info(sp)
    
    sorted_users = sorted(user_levels.items(), key=lambda x: x[1]["sp"], reverse=True)
    
    rank = 1
    for i, (user_id_str_temp, data) in enumerate(sorted_users, 1):
        if user_id_str == user_id_str_temp:
            rank = i
            break
    
    embed = discord.Embed(title="🍣 ข้อมูลเลเวลผู้ใช้ 🍣", color=0x00FF99)
    embed.set_author(name=user.display_name, icon_url=user.avatar.url if user.avatar else None)
    
    medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"#{rank}"
    embed.add_field(name="🍣 อันดับ", value=f"{medal}", inline=True)
    embed.add_field(name="🏅 ระดับ", value=f"{level_name}", inline=True)
    embed.add_field(name="✨ SP ทั้งหมด", value=f"**{format_number(sp)}** SP", inline=False)
    embed.add_field(name="💰 โรบัคที่ซื้อทั้งหมด", value=f"**{format_number(total_robux)}** {ROBUX_EMOJI}", inline=True)
    
    if sp_needed > 0:
        progress = (sp - current_level) / (next_level - current_level) if next_level > current_level else 0
        progress_bar = "🍣" * int(progress * 10) + "⬜" * (10 - int(progress * 10))
        embed.add_field(
            name="⏫ ความคืบหน้า", 
            value=f"`{progress_bar}` {format_number(sp - current_level)}/{format_number(next_level - current_level)} SP\nเหลืออีก **{format_number(sp_needed)}** SP สู่{next_level_name}",
            inline=False
        )
    else:
        embed.add_field(name="🏆 สถานะ", value=f"คุณถึง{level_name}สูงสุดแล้ว! 🎉", inline=False)
    
    embed.set_footer(text="Sushi Shop • 1 โรบัคที่ซื้อ = 1 SP")
    embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/717757556889747657/1403684950770847754/noFilter.png")
    
    await ctx.send(embed=embed)

@bot.command(name="level")
@admin_only()
async def level_cmd(ctx):
    """Level system info - Admin only now"""
    view = LevelCheckView(ctx.author.id)
    embed = discord.Embed(
        title="🍣 ระบบเลเวล Sushi Shop",
        description="กดปุ่มด้านล่างเพื่อเช็คเลเวลของคุณหรือดูอันดับ",
        color=0x00FF99
    )
    embed.add_field(
        name="✨ วิธีการได้ Sushi Point",
        value=f"ซื้อ 1 {ROBUX_EMOJI} = 1 SP\n(บันทึกเมื่อแอดมินกดส่งสินค้า)",
        inline=False
    )
    
    level_list = []
    sorted_levels = sorted(LEVEL_ROLES.keys())
    for threshold in sorted_levels:
        role_id = LEVEL_ROLES[threshold]
        role_mention = f"<@&{role_id}>"
        
        if threshold == 0:
            level_list.append(f"1 SP - {role_mention}")
        else:
            level_list.append(f"{format_number(threshold)} SP - {role_mention}")
    
    embed.add_field(name="🏆 ระดับ", value="\n".join(level_list), inline=False)
    embed.set_footer(text="Sushi Shop 🍣")
    
    await ctx.send(embed=embed, view=view)

@bot.command(name="setsp")
@admin_only()
async def set_sp_cmd(ctx, user: discord.Member, amount: int):
    user_id_str = str(user.id)
    
    if user_id_str not in user_levels:
        user_levels[user_id_str] = {"sp": 0, "total_robux": 0}
    
    old_sp = user_levels[user_id_str]["sp"]
    
    user_levels[user_id_str]["sp"] = amount
    user_levels[user_id_str]["total_robux"] = amount
    
    save_json(user_levels_file, user_levels)
    print(f"✅ Saved user {user.name} SP to {amount}")
    
    await update_member_roles(user, amount, old_sp)
    
    embed = discord.Embed(
        title="✅ ตั้งค่า SP สำเร็จ",
        description=f"ตั้งค่า SP ของ {user.mention} จาก **{format_number(old_sp)}** เป็น **{format_number(amount)}**",
        color=0x00FF00
    )
    await ctx.send(embed=embed)

@bot.command(name="delsp")
@admin_only()
async def del_sp_cmd(ctx, user: discord.Member, amount: int):
    success = await remove_sp(user.id, amount)
    
    if success:
        user_id_str = str(user.id)
        new_sp = user_levels[user_id_str]["sp"] if user_id_str in user_levels else 0
        embed = discord.Embed(
            title="✅ ลบ SP สำเร็จ",
            description=f"ลบ **{format_number(amount)}** SP จาก {user.mention}\nเหลือ SP **{format_number(new_sp)}**",
            color=0x00FF00
        )
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"❌ เกิดข้อผิดพลาดในการลบ SP หรือ SP ไม่เพียงพอ", delete_after=5)

@bot.command(name="tkd")
@admin_only()
async def tkd_cmd(ctx):
    channel = ctx.channel
    channel_name = channel.name
    
    valid_formats = False
    
    if channel_name.startswith("ticket-"):
        valid_formats = True
    
    pattern = r'^\d{10}-\d+-[\w\u0E00-\u0E7F]+$'
    if re.match(pattern, channel_name):
        valid_formats = True
    
    if not valid_formats:
        await ctx.send(f"❌ คำสั่งนี้ใช้ได้เฉพาะในช่องตั๋วเท่านั้น\nรูปแบบที่ใช้ได้: ticket-... หรือ [ddmmyytime-amount-user]\nตัวอย่าง: 0703262106-4-eurrai", delete_after=10)
        return
    
    try:
        msg = await ctx.send("🗑️ กำลังลบตั๋วนี้...")
        await save_ticket_transcript(channel, ctx.author)
        await asyncio.sleep(2)
        await channel.delete()
        print(f"✅ ลบตั๋ว {channel_name} โดย {ctx.author.name}")
        
    except Exception as e:
        print(f"❌ Error in tkd: {e}")
        traceback.print_exc()
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")

# ============ TY COMMAND - OPTIMIZED FOR SPEED ============

@bot.command()
@admin_only()
async def ty(ctx):
    """Give credit - Optimized for faster 'สั่งของต่อ' response"""
    global gamepass_stock, group_stock
    
    if not ctx.channel.name.startswith("ticket-") and not re.match(r'^\d{10}-\d+-[\w\u0E00-\u0E7F]+$', ctx.channel.name):
        await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะในตั๋วเท่านั้น", delete_after=5)
        return
    
    try:
        buyer = None
        channel_name = ctx.channel.name
        
        # Get buyer information
        if str(ctx.channel.id) in ticket_buyer_data:
            buyer_id = ticket_buyer_data[str(ctx.channel.id)].get("user_id")
            if buyer_id:
                buyer = ctx.guild.get_member(buyer_id)
        
        if not buyer and channel_name.startswith("ticket-"):
            parts = channel_name.split('-')
            if len(parts) >= 3:
                try:
                    user_id = int(parts[-1])
                    buyer = ctx.guild.get_member(user_id)
                except ValueError:
                    pass
        
        if not buyer:
            async for msg in ctx.channel.history(limit=50):
                if not msg.author.bot and msg.author != ctx.guild.me:
                    buyer = msg.author
                    break
        
        product_type = "Gamepass"
        if ctx.channel.category:
            if "group" in ctx.channel.category.name.lower() or "robux" in ctx.channel.category.name.lower():
                product_type = "Group"
        
        robux_amount = ticket_robux_data.get(str(ctx.channel.id), "0")
        try:
            robux_int = int(robux_amount)
        except:
            robux_int = 0
        
        # Start background tasks for heavy operations
        asyncio.create_task(save_ticket_transcript_background(ctx.channel, buyer, robux_int))
        
        # Handle stock adjustment
        if ctx.channel.category:
            category_name = ctx.channel.category.name.lower()
            if "gamepass" in category_name:
                async with bot.stock_lock:
                    gamepass_stock += 1
            elif "group" in category_name or "robux" in category_name:
                async with bot.stock_lock:
                    group_stock += 1
        
        save_stock_values()
        
        # Send immediate success message
        embed = discord.Embed(
            title="✅ ส่งของเรียบร้อย",
            description=(
                "**ขอบคุณที่ใช้บริการ Sushi Shop** 🍣\n"
                "ฝากให้เครดิต +1 ด้วยนะคะ ❤️\n\n"
                "⚠️ **หมายเหตุ:** ตั๋วนี้จะถูกลบใน 1 ชั่วโมง"
            ),
            color=0x00FF00
        )
        embed.set_footer(text="Sushi Shop 🍣❤️")
        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/717757556889747657/1403684950770847754/noFilter.png")
        
        view = View(timeout=None)
        credit_button = Button(
            label="ให้เครดิต⭐", 
            style=discord.ButtonStyle.link,
            url=f"https://discord.com/channels/{ctx.guild.id}/{CREDIT_CHANNEL_ID}",
            emoji="☑️"
        )
        view.add_item(credit_button)
        
        await ctx.send(embed=embed, view=view)
        
        # Handle "สั่งของต่อ" button - FIXED VERSION
        if product_type == "Gamepass" and buyer:
            order_more_view = View(timeout=None)
            order_more_btn = Button(label="สั่งของต่อ 📝", style=discord.ButtonStyle.success, emoji="🔄")
            
            async def order_more_cb(interaction):
                if interaction.channel.id != ctx.channel.id:
                    await interaction.response.send_message("❌ คุณไม่สามารถใช้ปุ่มนี้ในช่องอื่นได้", ephemeral=True)
                    return
                
                # Acknowledge immediately
                await interaction.response.defer(ephemeral=True)
                
                # Process order more in background
                await process_order_more_fixed(ctx.channel, buyer, interaction)
            
            order_more_btn.callback = order_more_cb
            order_more_view.add_item(order_more_btn)
            await ctx.send("📝 ต้องการสั่งของเพิ่มมั้ยคะ? ", view=order_more_view)
        
        # Clean up data in background
        if str(ctx.channel.id) in ticket_robux_data:
            del ticket_robux_data[str(ctx.channel.id)]
            save_json(ticket_robux_data_file, ticket_robux_data)
        
        if str(ctx.channel.id) in ticket_customer_data:
            del ticket_customer_data[str(ctx.channel.id)]
            save_json(ticket_customer_data_file, ticket_customer_data)
        
        # Move to delivered category and schedule removal in background
        asyncio.create_task(move_to_delivered_category_with_cleanup(ctx.channel, buyer))
        await update_main_channel()
        
        print(f"✅ คำสั่ง !ty ดำเนินการสำเร็จสำหรับห้อง {ctx.channel.name}")
        
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดใน !ty: {e}")
        traceback.print_exc()
        try:
            await ctx.send(f"✅ ให้เครดิตเรียบร้อยแล้ว")
        except:
            pass

async def process_order_more_fixed(channel, buyer, interaction):
    """Fixed background task for processing 'สั่งของต่อ'"""
    try:
        # Reset timer
        await reset_timer(channel, buyer)
        
        if is_timer_paused(channel.id):
            cancel_paused_timer(channel.id)
        
        # Reset channel name
        if buyer:
            await reset_channel_name(channel, buyer.id, "gamepass")
        
        # Move back to original category
        await move_to_original_category(channel, "gamepass")
        
        # Get admin role mention
        admin_role = channel.guild.get_role(1486330338539077713)
        admin_mention = admin_role.mention if admin_role else "@Admin"
        
        # Send the order form embed with admin mention
        order_embed = discord.Embed(
            title="🍣 Sushi Shop 🍣", 
            color=0x00FF99
        )
        order_embed.add_field(name="👤 ผู้ซื้อ", value=buyer.mention if buyer else "ไม่ระบุ", inline=False)
        order_embed.add_field(
            name="🎮 บริการกดเกมพาส", 
            value=f"📦 โรบัคคงเหลือ: **{format_number(gamepass_stock)}**\n💰 เรท: {gamepass_rate} (ปกติ) | {gamepass_rate_high} (>{gamepass_threshold} {ROBUX_EMOJI})", 
            inline=False
        )
        order_embed.add_field(name="👑 แจ้งผู้ดูแล", value=f"{admin_mention} กรุณาตรวจสอบด้วยค่ะ", inline=False)
        order_embed.set_footer(text="Sushi Shop")
        order_embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/717757556889747657/1403684950770847754/noFilter.png")
        
        ticket_view = View(timeout=None)
        form_btn = Button(label="📝 กรอกแบบฟอร์มเกมพาส", style=discord.ButtonStyle.primary, emoji="📝")
        
        async def form_callback(interaction2):
            if interaction2.channel.id == channel.id:
                modal = GamepassTicketModal()
                await interaction2.response.send_modal(modal)
            else:
                await interaction2.response.send_message("❌ คุณไม่สามารถใช้ปุ่มนี้ในช่องอื่นได้", ephemeral=True)
        
        form_btn.callback = form_callback
        ticket_view.add_item(form_btn)
        
        await channel.send(embed=order_embed, view=ticket_view)
        
        # Send followup to user that order more is ready
        await interaction.followup.send("✅ รีเซ็ตระบบเรียบร้อย! กรุณากรอกแบบฟอร์มด้านบนเพื่อสั่งของเพิ่ม", ephemeral=True)
        
        print(f"✅ Order more processed for {channel.name}")
        
    except Exception as e:
        print(f"❌ Error processing order more: {e}")
        try:
            await interaction.followup.send(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)
        except:
            pass
            
async def save_ticket_transcript_background(channel, buyer, robux_int):
    """Background task for saving transcript and renaming channel"""
    try:
        save_success, filename = await save_ticket_transcript(channel, buyer, robux_int, None)
        if save_success and filename:
            try:
                await channel.edit(name=filename[:100])
                print(f"✅ Channel renamed to: {filename[:100]}")
            except Exception as e:
                print(f"⚠️ Failed to rename channel: {e}")
    except Exception as e:
        print(f"❌ Error in background transcript save: {e}")

async def move_to_delivered_category_with_cleanup(channel, buyer):
    """Background task for moving to delivered category and scheduling removal"""
    try:
        # First ensure we're not already in delivered category
        if channel.category and channel.category.id != DELIVERED_CATEGORY_ID:
            await move_to_delivered_category(channel)
            print(f"✅ Moved {channel.name} to delivered category")
        else:
            print(f"ℹ️ Channel {channel.name} already in delivered category or category not found")
        
        # Schedule removal
        await schedule_removal(channel, buyer, 3600)
    except Exception as e:
        print(f"❌ Error moving to delivered category: {e}")

async def process_order_more(channel, buyer, interaction):
    """Background task for processing 'สั่งของต่อ'"""
    try:
        # Reset timer
        await reset_timer(channel, buyer)
        
        if is_timer_paused(channel.id):
            cancel_paused_timer(channel.id)
        
        # Reset channel name
        if buyer:
            await reset_channel_name(channel, buyer.id, "gamepass")
        
        # Move back to original category
        await move_to_original_category(channel, "gamepass")
        
        # Send the order form embed
        order_embed = discord.Embed(
            title="🍣 Sushi Shop 🍣", 
            color=0x00FF99
        )
        order_embed.add_field(name="👤 ผู้ซื้อ", value=buyer.mention if buyer else "ไม่ระบุ", inline=False)
        order_embed.add_field(
            name="🎮 บริการกดเกมพาส", 
            value=f"📦 โรบัคคงเหลือ: **{format_number(gamepass_stock)}**\n💰 เรท: {gamepass_rate} (ปกติ) | {gamepass_rate_high} (>{gamepass_threshold} {ROBUX_EMOJI})", 
            inline=False
        )
        order_embed.set_footer(text="Sushi Shop")
        order_embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/717757556889747657/1403684950770847754/noFilter.png")
        
        ticket_view = View(timeout=None)
        form_btn = Button(label="📝 กรอกแบบฟอร์มเกมพาส", style=discord.ButtonStyle.primary, emoji="📝")
        
        async def form_callback(interaction2):
            if interaction2.channel.id == channel.id:
                modal = GamepassTicketModal()
                await interaction2.response.send_modal(modal)
            else:
                await interaction2.response.send_message("❌ คุณไม่สามารถใช้ปุ่มนี้ในช่องอื่นได้", ephemeral=True)
        
        form_btn.callback = form_callback
        ticket_view.add_item(form_btn)
        
        await channel.send(embed=order_embed, view=ticket_view)
        print(f"✅ Order more processed for {channel.name}")
        
    except Exception as e:
        print(f"❌ Error processing order more: {e}")

# ============ DM COMMAND ============
@bot.command(name="dm")
@admin_only()
async def dm_cmd(ctx, user: discord.Member, *, message: str):
    """Send a DM to a user"""
    try:
        await user.send(message)
        await ctx.send(f"✅ ส่งข้อความไปยัง {user.mention} เรียบร้อยแล้ว", delete_after=5)
        print(f"✅ Sent DM to {user.name}: {message}")
    except discord.Forbidden:
        await ctx.send(f"❌ ไม่สามารถส่ง DM ไปยัง {user.mention} ได้ (ปิดการรับ DM)", delete_after=5)
    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=5)
        print(f"❌ Error sending DM: {e}")

# ============ PAYMENT COMMANDS ============

class PaymentView(View):
    def __init__(self):
        super().__init__(timeout=None)
        
        # Green button for QR Code (Krungsri)
        qr_btn = Button(label="สแกน QR ชำระเงิน", style=discord.ButtonStyle.success, emoji="📲")
        # Blue button for Bank Account (SCB)
        account_btn = Button(label="โอนผ่านเลขบัญชี", style=discord.ButtonStyle.primary, emoji="🏦")
        # Red button for TrueMoney Wallet
        truemoney_btn = Button(label="ทรูมันนี่วอเล็ต", style=discord.ButtonStyle.danger, emoji="🧡")
        
        qr_btn.callback = self.qr_callback
        account_btn.callback = self.account_callback
        truemoney_btn.callback = self.truemoney_callback
        
        self.add_item(qr_btn)
        self.add_item(account_btn)
        self.add_item(truemoney_btn)
    
    async def qr_callback(self, interaction: discord.Interaction):
        """Show Krungsri QR code"""
        embed = discord.Embed(
            title="ชำระเงินผ่าน QR Code (กรุงศรี)",
            description="⚠️ **โน๊ตสลิป:** เติมโรบัค Sushi Shop เฟส Can pattarapol",
            color=0x00FF00
        )
        embed.add_field(name="1. ชื่อบัญชี (กรุงศรี)", value="**สุทัตตา เถลิงสุข**", inline=False)
        embed.set_image(url="https://media.discordapp.net/attachments/1485285161955360963/1487457449416982568/Can_Can-1.png")
        embed.set_footer(text="Sushi Shop 🍣")
        
        # Add back button
        view = BackButtonView(self)
        await interaction.response.edit_message(embed=embed, view=view)
    
    async def account_callback(self, interaction: discord.Interaction):
        """Show SCB bank account"""
        embed = discord.Embed(
            title="🏦 ชำระเงินผ่านบัญชีธนาคาร (ไทยพานิชย์)",
            description="⚠️ **โน๊ตสลิป:** เติมโรบัค Sushi Shop เฟส Arisara Srijitjam",
            color=0x0099FF
        )
        embed.add_field(name="1. ชื่อบัญชี (SCB)", value="**หจก. วอเตอร์ เทค เซลล์ แอนด์ เซอร์วิส**", inline=False)
        embed.add_field(name="2. เลขบัญชี", value="**120-239181-3**", inline=False)
        embed.set_image(url="https://media.discordapp.net/attachments/1361004239043821610/1475334379550281768/Sushi_SCB_3.png")
        embed.set_footer(text="Sushi Shop 🍣")
        
        # Add back button
        view = BackButtonView(self)
        
        # Add copy button
        copy_btn = Button(label="📋 คัดลอกเลขบัญชี", style=discord.ButtonStyle.secondary, emoji="📋")
        
        async def copy_cb(i):
            await i.response.send_message("```1202391813```", ephemeral=True)
        
        copy_btn.callback = copy_cb
        view.add_item(copy_btn)
        
        await interaction.response.edit_message(embed=embed, view=view)
    
    async def truemoney_callback(self, interaction: discord.Interaction):
        """Show TrueMoney Wallet info"""
        embed = discord.Embed(
            title="💰 ชำระเงินผ่านทรูมันนี่วอเล็ต",
            description="**0892278408** ชื่อลัดดา",
            color=0xFF0000
        )
        embed.set_footer(text="Sushi Shop 🍣")
        
        # Add back button
        view = BackButtonView(self)
        
        await interaction.response.edit_message(embed=embed, view=view)


class BackButtonView(View):
    def __init__(self, parent_view: PaymentView):
        super().__init__(timeout=None)
        self.parent_view = parent_view
        
        back_btn = Button(label="◀ กลับ", style=discord.ButtonStyle.secondary, emoji="🔙")
        back_btn.callback = self.back_callback
        self.add_item(back_btn)
    
    async def back_callback(self, interaction: discord.Interaction):
        """Return to payment selection menu (edits the existing message)"""
        embed = discord.Embed(
            title="🍣 เลือกช่องทางชำระเงิน",
            color=0xFFA500
        )
        embed.set_footer(text="Sushi Shop 🍣")
        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/717757556889747657/1403684950770847754/noFilter.png")
        
        # Edit the existing message instead of sending a new one
        await interaction.response.edit_message(embed=embed, view=self.parent_view)

@bot.command(name="qr")
async def payment_cmd(ctx):
    """แสดงช่องทางการชำระเงิน"""
    try:
        await ctx.message.delete()
    except:
        pass
    
    embed = discord.Embed(
        title="🍣 เลือกช่องทางชำระเงิน",
        color=0xFFA500
    )
    embed.set_footer(text="Sushi Shop 🍣")
    embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/717757556889747657/1403684950770847754/noFilter.png")
    
    view = PaymentView()
    await ctx.send(embed=embed, view=view)

# ============ CALCULATOR COMMANDS ============
@bot.command(name="calc")
@admin_only()
async def calculator_cmd(ctx):
    """Show calculator - Admin only"""
    try:
        embed = discord.Embed(
            title="🍣 เครื่องคิดเลข Sushi Shop",
            description="เลือกปุ่มด้านล่างเพื่อคำนวณราคา",
            color=0xFFA500
        )
        embed.add_field(name="🎮 เกมพาส", value=f"เรท {gamepass_rate} (ปกติ) | {gamepass_rate_high} (>{gamepass_threshold} {ROBUX_EMOJI})\n1 บาท = {gamepass_rate} {ROBUX_EMOJI}", inline=True)
        embed.add_field(name="👥 โรกลุ่ม", value=f"เรท {group_rate_low} (ต่ำกว่า 500 บาท)\nเรท {group_rate_high} (500 บาทขึ้นไป)", inline=True)
        embed.set_image(url="https://media.discordapp.net/attachments/1485285161955360963/1485285565761847417/image.png")
        embed.set_footer(text="Sushi Shop 🍣")
        
        view = CalculatorView()
        await ctx.send(embed=embed, view=view)
    except Exception as e:
        print(f"❌ Error in calculator command: {e}")
        await ctx.send("❌ เกิดข้อผิดพลาดในการแสดงเครื่องคิดเลข")

# ============ SIMPLE CALCULATOR COMMANDS (Public) ============
@bot.command()
async def gp(ctx, *, expr):
    """Calculate gamepass price (Robux to Baht) - Public"""
    global gamepass_rate, gamepass_rate_high, gamepass_threshold
    try:
        expr_clean = expr.replace(",", "").lower().replace("x", "*").replace("÷", "/").replace(" ", "")
        robux = int(eval(expr_clean))
        
        rate = get_gamepass_rate(robux)
        price = robux / rate
        price_int = round_price(price)
        
        if robux > gamepass_threshold:
            await ctx.send(f"🎮 Gamepass {format_number(robux)} {ROBUX_EMOJI} = **{format_number(price_int)} บาท** (เรท {rate} - มากกว่า {gamepass_threshold} {ROBUX_EMOJI})")
        else:
            await ctx.send(f"🎮 Gamepass {format_number(robux)} {ROBUX_EMOJI} = **{format_number(price_int)} บาท** (เรท {rate})")
    except:
        await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง เช่น 500 หรือ 100+200", delete_after=5)

@bot.command()
async def g(ctx, *, expr):
    """Calculate group price (Robux to Baht) - Public"""
    global group_rate_low, group_rate_high
    try:
        expr_clean = expr.replace(",", "").lower().replace("x", "*").replace("÷", "/").replace(" ", "")
        robux = int(eval(expr_clean))
        
        price_baht_low = robux / group_rate_low
        price_baht_high = robux / group_rate_high
        
        if price_baht_high >= 500:
            rate = group_rate_high
            price = price_baht_high
            rate_text = f"เรท {group_rate_high} (500 บาทขึ้นไป)"
        else:
            rate = group_rate_low
            price = price_baht_low
            rate_text = f"เรท {group_rate_low} (ต่ำกว่า 500 บาท)"
        
        price_int = round_price(price)
        await ctx.send(f"👥 Group {format_number(robux)} {ROBUX_EMOJI} = **{format_number(price_int)} บาท** ({rate_text})")
    except Exception as e:
        await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง เช่น 500 หรือ 100+200", delete_after=5)

@bot.command()
async def gpb(ctx, *, expr):
    """Calculate gamepass price (Baht to Robux) - Public"""
    global gamepass_rate, gamepass_rate_high, gamepass_threshold
    try:
        expr_clean = expr.replace(",", "").replace(" ", "")
        baht = float(eval(expr_clean))
        
        robux_normal = int(baht * gamepass_rate)
        robux_high = int(baht * gamepass_rate_high)
        
        await ctx.send(f"🎮 {format_number(int(baht))} บาท = **{format_number(robux_normal)} {ROBUX_EMOJI}** (Gamepass เรท {gamepass_rate})\n หรือ = **{format_number(robux_high)} {ROBUX_EMOJI}** (เรท {gamepass_rate_high} สำหรับซื้อ >{gamepass_threshold} {ROBUX_EMOJI})")
    except:
        await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง เช่น 500 หรือ 100+200", delete_after=5)

@bot.command()
async def gb(ctx, *, expr):
    """Calculate group price (Baht to Robux) - Public"""
    global group_rate_low, group_rate_high
    try:
        expr_clean = expr.replace(",", "").replace(" ", "")
        baht = float(eval(expr_clean))
        
        if baht >= 500:
            rate = group_rate_high
            rate_text = f"เรท {group_rate_high} (500 บาทขึ้นไป)"
        else:
            rate = group_rate_low
            rate_text = f"เรท {group_rate_low} (ต่ำกว่า 500 บาท)"
        
        robux = int(baht * rate)
        await ctx.send(f"👥 {format_number(int(baht))} บาท = **{format_number(robux)} {ROBUX_EMOJI}** ({rate_text})")
    except Exception as e:
        await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง เช่น 500 หรือ 100+200 หรือ 100 + 200", delete_after=5)

@bot.command()
async def tax(ctx, *, expr):
    """Calculate tax deduction - Public"""
    try:
        expr = expr.replace(" ", "")
        if re.match(r"^\d+$", expr):
            number = int(expr)
            await ctx.send(f"💰 {format_number(number)} {ROBUX_EMOJI}ที่ได้หลังหัก 30% = **{format_number(int(number * 0.7))} {ROBUX_EMOJI}**")
        elif m := re.match(r"^(\d+)-(\d+)%$", expr):
            number = int(m[1])
            percent = int(m[2])
            await ctx.send(f"💰 {format_number(number)} {ROBUX_EMOJI}ที่ได้หลังหัก {percent}% = **{format_number(int(number * (1 - percent/100)))} {ROBUX_EMOJI}**")
        else:
            await ctx.send("❌ รูปแบบไม่ถูกต้อง\n\n**การใช้งาน:**\n`!tax 100` - หัก 30% อัตโนมัติ\n`!tax 100-30%` - หัก 30%\n`!tax 100-50%` - หัก 50%", delete_after=15)
    except:
        await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)

# ============ PUBLIC COMMANDS (Keep accessible to everyone) ============
@bot.command()
async def love(ctx):
    await ctx.send("# LOVE YOU<:sushiheart:1410484970291466300>")

@bot.command()
async def say(ctx, *, message):
    await ctx.send(f"# {message.upper()} <:sushiheart:1410484970291466300>")

# ============ BACKGROUND TASKS ============
@tasks.loop(minutes=1)
async def update_presence():
    await bot.change_presence(activity=discord.Game(name="🍣แมวส้มชื่อซูชิของ wforr🍣"))

@tasks.loop(minutes=5)
async def save_data():
    await save_all_data()

@tasks.loop(seconds=15)
async def save_data_frequent():
    await save_all_data()
    print(f"✅ Auto-save at {get_thailand_time().strftime('%H:%M:%S')}")

@tasks.loop(hours=1)
async def hourly_backup():
    backup_user_levels()
    print(f"✅ Hourly backup created at {get_thailand_time().strftime('%H:%M:%S')}")

# ============ SIGNAL HANDLERS ============
def signal_handler(signum, frame):
    print(f"\n⚠️ Received signal {signum}, saving data...")
    save_all_data_sync()
    backup_user_levels()
    print("✅ Data saved! Exiting...")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ============ EVENT HANDLERS ============
@bot.event
async def on_ready():
    print(f"✅ บอทออนไลน์แล้ว: {bot.user} (ID: {bot.user.id}")
    
    await bot.change_presence(activity=discord.Game(name="🍣แมวส้มชื่อซูชิของ wforr🍣"))
    
    print("\n📝 Registered prefix commands:")
    for cmd in bot.commands:
        print(f"   - !{cmd.name}")
    
    print("\n🔧 Slash commands will be synced...")
    
    print(f"\n📁 DATA_DIR: {DATA_DIR}")
    print(f"📁 Directory exists: {os.path.exists(DATA_DIR)}")
    
    if os.path.exists(user_levels_file):
        file_size = os.path.getsize(user_levels_file)
        print(f"📊 user_levels.json exists, size: {file_size} bytes")
    else:
        print(f"📊 user_levels.json does not exist yet")
    
    try:
        print("🔄 กำลัง sync slash commands...")
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash commands")
        for cmd in synced:
            print(f"   - /{cmd.name}")
        bot.commands_synced = True
    except Exception as e:
        print(f"❌ Error syncing commands: {e}")
    
    update_presence.start()
    save_data.start()
    save_data_frequent.start()
    hourly_backup.start()
    update_credit_channel_task.start()
    
    await update_credit_channel_name()
    await update_channel_name()
    await update_main_channel()
    
    total_sp = sum(data["sp"] for data in user_levels.values())
    print(f"\n📊 Loaded SP data: {len(user_levels)} users, total {format_number(total_sp)} SP")
    print("\n🎯 บอทพร้อมใช้งาน!")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    if message.channel.id == CREDIT_CHANNEL_ID:
        if message.author != bot.user:
            await asyncio.sleep(2)
            for emoji in ["❤️", "🍣", "💎"]:
                try:
                    await message.add_reaction(emoji)
                    await asyncio.sleep(1)
                except:
                    pass
    
    await bot.process_commands(message)

@bot.event
async def on_member_join(member):
    try:
        welcome_channel = bot.get_channel(WELCOME_CHANNEL_ID)
        if welcome_channel:
            welcome_text = random.choice(WELCOME_MESSAGES)
            welcome_message = welcome_text.format(member.mention)
            await welcome_channel.send(welcome_message)
            print(f"✅ Sent welcome message for {member.name}")
            
            if str(member.id) not in user_levels:
                user_levels[str(member.id)] = {"sp": 0, "total_robux": 0}
                save_json(user_levels_file, user_levels)
    except Exception as e:
        print(f"❌ Error sending welcome message: {e}")

# ============ MAIN ============
if __name__ == "__main__":
    keep_alive()
    
    print("⏳ รอ 30 วินาทีก่อนเริ่มบอท...")
    time.sleep(30)
    
    token = os.getenv("TOKEN")
    if not token:
        print("❌ ไม่พบ TOKEN ใน environment variables")
        exit(1)
    
    try:
        bot.run(token)
    except Exception as e:
        print(f"❌ Error running bot: {e}")
        traceback.print_exc()
