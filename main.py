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
# Check for Render persistent disk
PERSISTENT_DISK = "/app/data"

if os.path.exists(PERSISTENT_DISK) and os.access(PERSISTENT_DISK, os.W_OK):
    DATA_DIR = PERSISTENT_DISK
    print(f"✅ Using Render persistent disk: {DATA_DIR}")
else:
    DATA_DIR = os.getenv("DATA_DIR", ".")
    print(f"⚠️ Persistent disk not found or not writable, using: {DATA_DIR}")

# Create directory if it doesn't exist
try:
    os.makedirs(DATA_DIR, exist_ok=True)
    
    # Test write permission
    test_file = os.path.join(DATA_DIR, ".write_test")
    with open(test_file, 'w') as f:
        f.write("test")
    os.remove(test_file)
    
    print(f"✅ DATA_DIR: {DATA_DIR} (writable)")
    
except Exception as e:
    print(f"❌ Cannot use DATA_DIR={DATA_DIR}: {e}")
    print(f"⚠️ Falling back to current directory (.)")
    DATA_DIR = "."
    os.makedirs(DATA_DIR, exist_ok=True)
    
    # Test again
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
gamepass_rate = 6.5
group_rate_low = 4
group_rate_high = 4.5
shop_open = True
group_ticket_enabled = True
premium_ticket_enabled = True
gamepass_stock = 20000
group_stock = 25000
premium_stock = 9999

# Channel IDs
MAIN_CHANNEL_ID = 1475342278976606229
SALES_LOG_CHANNEL_ID = 1475344141419417612
CREDIT_CHANNEL_ID = 1475343873684406353
DELIVERED_CATEGORY_ID = 1475345768037482662
ARCHIVED_CATEGORY_ID = 1485235427500753059
BUYER_ROLE_ID = 1475346221605588992
WELCOME_CHANNEL_ID = 1475344769679888455
PREMIUM_CATEGORY_ID = 1486401158900613264
SUSHI_GAMEPASS_CATEGORY_ID = 1475342278976606228
ANONYMOUS_USER_ROLE_ID = 1486352633290821673

# Level roles - IMPORTANT: Thresholds in ascending order
LEVEL_ROLES = {
    0: 1475346221605588992,      # 0-4999 SP - 🍣 | Sushi Lover
    5000: 1488073523946717356,   # 5,000-9,999 SP - 🐠 | Sushi Pass
    10000: 1488073560030445569,  # 10,000-24,999 SP - 🐡 | Sushi Silver
    25000: 1488073771662315614,  # 25,000-49,999 SP - 🦈 | Sushi Platinum
    50000: 1488073590162329640,  # 50,000-99,999 SP - 🐙 | Sushi Emerald
    100000: 1488073619543294153, # 100,000-777,776 SP - 🐋 | Sushi Supreme
    777777: 1488075865337106563  # 777,777+ SP - 👑 | Superior
}

# Level names for display (using thresholds as keys)
LEVEL_NAMES = {
    0: "🍣 | Sushi Lover",
    5000: "🐠 | Sushi Pass",
    10000: "🐡 | Sushi Silver",
    25000: "🦈 | Sushi Platinum",
    50000: "🐙 | Sushi Emerald",
    100000: "🐋 | Sushi Supreme",
    777777: "👑 | Superior"
}

GAMEPASS_CATEGORY_NAME = "sushi gamepass"
GROUP_CATEGORY_NAME = "robux group"
ROBUX_EMOJI = "<:sushirobux:1486314072701141074>"

WELCOME_MESSAGES = [
    "ยินดีต้อนรับ {} สู่ร้าน Sushi Shop 🍣",
    "สวัสดีครับ {} ยินดีต้อนรับนะครับ 🍣",
    "ยินดีต้อนรับนะครับ {} 🍣",
    "สวัสดีค่ะ ยินดีต้อนรับ {} ค่า 🍣"
]

# File paths with persistent disk
user_data_file = os.path.join(DATA_DIR, "user_data.json")
ticket_transcripts_file = os.path.join(DATA_DIR, "ticket_transcripts.json")
ticket_counter_file = os.path.join(DATA_DIR, "ticket_counter.json")
ticket_robux_data_file = os.path.join(DATA_DIR, "ticket_robux_data.json")
ticket_customer_data_file = os.path.join(DATA_DIR, "ticket_customer_data.json")
stock_file = os.path.join(DATA_DIR, "stock_values.json")
ticket_buyer_data_file = os.path.join(DATA_DIR, "ticket_buyer_data.json")
user_levels_file = os.path.join(DATA_DIR, "user_levels.json")

print(f"📄 Data files will be saved to:")
print(f"   - {user_levels_file}")
print(f"   - {stock_file}")
print(f"   - {ticket_counter_file}")

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

credit_channel_queue = asyncio.Queue()
credit_channel_update_task_running = False
credit_channel_last_update = 0
credit_channel_update_lock = asyncio.Lock()

# ============ JSON FUNCTIONS ============
def load_json(file, default):
    """Load data from JSON file"""
    try:
        if os.path.exists(file):
            with open(file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return default
    except Exception as e:
        print(f"❌ Error loading {file}: {e}")
        return default

def save_json(file, data):
    """Save data to JSON file with backup"""
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
    """Create backup of user_levels.json"""
    if os.path.exists(user_levels_file):
        backup_file = os.path.join(DATA_DIR, f"user_levels_backup_{dt.now().strftime('%Y%m%d_%H%M%S')}.json")
        try:
            shutil.copy2(user_levels_file, backup_file)
            print(f"✅ Backup created: {backup_file}")
            
            # Delete backups older than 7 days
            for file in os.listdir(DATA_DIR):
                if file.startswith('user_levels_backup_') and file.endswith('.json'):
                    file_path = os.path.join(DATA_DIR, file)
                    if os.path.getmtime(file_path) < time.time() - 7 * 86400:
                        os.remove(file_path)
                        print(f"🗑️ Removed old backup: {file}")
        except Exception as e:
            print(f"❌ Error creating backup: {e}")

def load_user_levels():
    """Load user levels from JSON with validation"""
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
        # Try to load from backup
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
    """Load stock values from JSON"""
    global gamepass_stock, group_stock, premium_stock, gamepass_rate, group_rate_low, group_rate_high, shop_open, group_ticket_enabled, premium_ticket_enabled
    stock_data = load_json(stock_file, {})
    if stock_data:
        gamepass_stock = stock_data.get("gamepass_stock", 20000)
        group_stock = stock_data.get("group_stock", 8500)
        premium_stock = stock_data.get("premium_stock", 9999)
        gamepass_rate = stock_data.get("gamepass_rate", 6.5)
        group_rate_low = stock_data.get("group_rate_low", 4)
        group_rate_high = stock_data.get("group_rate_high", 4.5)
        shop_open = stock_data.get("shop_open", True)
        group_ticket_enabled = stock_data.get("group_ticket_enabled", True)
        premium_ticket_enabled = stock_data.get("premium_ticket_enabled", True)

def save_stock_values():
    """Save stock values to JSON"""
    stock_data = {
        "gamepass_stock": gamepass_stock,
        "group_stock": group_stock,
        "premium_stock": premium_stock,
        "gamepass_rate": gamepass_rate,
        "group_rate_low": group_rate_low,
        "group_rate_high": group_rate_high,
        "shop_open": shop_open,
        "group_ticket_enabled": group_ticket_enabled,
        "premium_ticket_enabled": premium_ticket_enabled
    }
    save_json(stock_file, stock_data)
    print(f"✅ Stock values saved")

def save_all_data_sync():
    """Synchronous save of all data to JSON"""
    success = True
    success &= save_json(user_data_file, user_data)
    success &= save_json(ticket_transcripts_file, ticket_transcripts)
    success &= save_json(ticket_robux_data_file, ticket_robux_data)
    success &= save_json(ticket_customer_data_file, ticket_customer_data)
    success &= save_json(ticket_buyer_data_file, ticket_buyer_data)
    success &= save_json(user_levels_file, user_levels)
    save_stock_values()
    print("✅ All data saved (sync)")
    return success

async def save_all_data():
    """Save all data to JSON"""
    success = True
    success &= save_json(user_data_file, user_data)
    success &= save_json(ticket_transcripts_file, ticket_transcripts)
    success &= save_json(ticket_robux_data_file, ticket_robux_data)
    success &= save_json(ticket_customer_data_file, ticket_customer_data)
    success &= save_json(ticket_buyer_data_file, ticket_buyer_data)
    success &= save_json(user_levels_file, user_levels)
    save_stock_values()
    print(f"✅ All data saved at {get_thailand_time().strftime('%H:%M:%S')}")
    return success

def load_all_data():
    """Load all data from JSON files"""
    global user_data, ticket_transcripts, ticket_robux_data, ticket_customer_data, ticket_buyer_data, user_levels, ticket_counter
    
    user_data = load_json(user_data_file, {})
    ticket_transcripts = load_json(ticket_transcripts_file, {})
    ticket_robux_data = load_json(ticket_robux_data_file, {})
    ticket_customer_data = load_json(ticket_customer_data_file, {})
    ticket_buyer_data = load_json(ticket_buyer_data_file, {})
    user_levels = load_user_levels()
    ticket_counter = load_json(ticket_counter_file, {"counter": 1, "date": get_thailand_time().strftime("%d%m%y")})
    
    load_stock_values()
    
    print(f"✅ Loaded all data from JSON:")
    print(f"   - {len(user_data)} users")
    print(f"   - {len(ticket_transcripts)} tickets")
    print(f"   - {len(ticket_buyer_data)} buyer records")
    print(f"   - {len(user_levels)} users with SP")
    print(f"   - Total SP: {sum(data['sp'] for data in user_levels.values())}")
    print(f"   - Stock: GP={gamepass_stock}, Group={group_stock}, Premium={premium_stock}")

# ============ LEVEL SYSTEM FUNCTIONS ============
def get_threshold_from_sp(sp):
    """Get the level threshold from SP amount"""
    sorted_thresholds = sorted(LEVEL_ROLES.keys(), reverse=True)
    for threshold in sorted_thresholds:
        if sp >= threshold:
            return threshold
    return 0

def get_role_for_sp(sp):
    """Get the role ID for a given SP amount"""
    sorted_thresholds = sorted(LEVEL_ROLES.keys(), reverse=True)
    for threshold in sorted_thresholds:
        if sp >= threshold:
            return LEVEL_ROLES[threshold]
    return LEVEL_ROLES[0]

def get_level_name_from_sp(sp):
    """Get level name from SP amount"""
    threshold = get_threshold_from_sp(sp)
    return LEVEL_NAMES.get(threshold, "🍣 | Sushi Lover")

def get_level_info(sp):
    """Get level information based on skill points"""
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
    """Get SP needed for next level"""
    sorted_levels = sorted(LEVEL_ROLES.keys())
    for threshold in sorted_levels:
        if sp < threshold:
            return threshold - sp
    return 0

async def send_level_up_dm(member, new_sp, old_sp):
    """Send level up DM to user"""
    try:
        old_level_name = get_level_name_from_sp(old_sp)
        new_level_name = get_level_name_from_sp(new_sp)
        
        # Don't send if no level change
        if old_level_name == new_level_name:
            print(f"ℹ️ No level change for {member.name} (SP: {old_sp} → {new_sp})")
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
    """Update member roles based on their skill points - FIXED VERSION"""
    if not member:
        print(f"❌ Cannot update roles: member is None")
        return False
    
    guild = member.guild
    bot_member = guild.me
    
    # Check bot permissions
    if not bot_member.guild_permissions.manage_roles:
        print(f"❌ Bot doesn't have Manage Roles permission in {guild.name}")
        return False
    
    # Get old SP if not provided
    if old_sp is None:
        user_id_str = str(member.id)
        if user_id_str in user_levels:
            old_sp = user_levels[user_id_str].get("sp", 0)
        else:
            old_sp = 0
    
    # Get role IDs based on SP thresholds
    old_role_id = get_role_for_sp(old_sp)
    new_role_id = get_role_for_sp(new_sp)
    
    # If role hasn't changed, no need to update
    if old_role_id == new_role_id:
        print(f"ℹ️ Role unchanged for {member.name} (SP: {new_sp})")
        return True
    
    old_role = guild.get_role(old_role_id) if old_role_id else None
    new_role = guild.get_role(new_role_id) if new_role_id else None
    
    if not new_role:
        print(f"❌ Cannot find new role with ID {new_role_id}")
        return False
    
    # Check if bot can manage the new role (role hierarchy)
    if new_role.position >= bot_member.top_role.position:
        print(f"⚠️ Bot cannot manage role {new_role.name} - role is higher than bot's highest role ({bot_member.top_role.name})")
        return False
    
    try:
        # Remove old role if user has it
        if old_role and old_role in member.roles:
            await member.remove_roles(old_role, reason=f"Level up from {old_sp} to {new_sp} SP")
            print(f"✅ Removed role {old_role.name} from {member.name}")
        
        # Add new role
        if new_role not in member.roles:
            await member.add_roles(new_role, reason=f"Reached {new_sp} SP")
            print(f"✅ Added role {new_role.name} to {member.name} (SP: {new_sp})")
            
            # Send level up DM
            await send_level_up_dm(member, new_sp, old_sp)
            return True
        else:
            print(f"ℹ️ {member.name} already has role {new_role.name}")
            return True
            
    except discord.Forbidden:
        print(f"❌ Forbidden: Bot cannot manage role {new_role.name}. Check role hierarchy!")
        return False
    except Exception as e:
        print(f"❌ Failed to update roles for {member.name}: {e}")
        return False

async def add_sp(user_id, amount):
    """Add skill points to a user and update roles"""
    if not user_id:
        return 0
    
    user_id_str = str(user_id)
    
    if user_id_str not in user_levels:
        user_levels[user_id_str] = {"sp": 0, "total_robux": 0}
    
    old_sp = user_levels[user_id_str]["sp"]
    user_levels[user_id_str]["sp"] += amount
    user_levels[user_id_str]["total_robux"] += amount
    new_sp = user_levels[user_id_str]["sp"]
    
    # Save immediately
    save_json(user_levels_file, user_levels)
    print(f"✅ Added {amount} SP to {user_id}: {old_sp} → {new_sp} SP")
    
    # Get guild and member
    guild = None
    for g in bot.guilds:
        guild = g
        break
    
    if guild:
        member = guild.get_member(user_id)
        if member:
            await update_member_roles(member, new_sp, old_sp)
        else:
            print(f"⚠️ Could not find member {user_id} in guild")
    else:
        print(f"⚠️ No guild found")
    
    return new_sp

async def remove_sp(user_id, amount):
    """Remove skill points from a user and update roles"""
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
    """Get next ticket number"""
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

# ============ CALCULATOR HELPER ============
def evaluate_expression(expr: str) -> int:
    """
    Evaluate a mathematical expression and return an integer.
    Supports +, -, *, /, x (as *), ÷ (as /)
    """
    # Remove commas and spaces
    expr_clean = expr.replace(",", "").replace(" ", "")
    
    # Replace x with * and ÷ with /
    expr_clean = expr_clean.lower().replace("x", "*").replace("÷", "/")
    
    # Validate characters (only numbers and operators)
    allowed_chars = set("0123456789+-*/.")
    for char in expr_clean:
        if char not in allowed_chars:
            raise ValueError(f"Invalid character: {char}")
    
    # Evaluate using Python's eval (safe because we validated input)
    result = eval(expr_clean)
    
    # Convert to integer (round if needed)
    if isinstance(result, float):
        result = int(round(result))
    
    return result

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
    def __init__(self, product_type, rate, is_baht=False):
        super().__init__(timeout=60)
        self.product_type = product_type
        self.rate = rate
        self.is_baht = is_baht
    
    @discord.ui.button(label="คำนวณ", style=discord.ButtonStyle.primary, emoji="🧮")
    async def calculate_button(self, interaction: discord.Interaction, button: Button):
        modal = CalculatorModal(self.product_type, self.rate, self.is_baht)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="ยกเลิก", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="ยกเลิกการคำนวณ", view=None)


class CalculatorModal(Modal):
    def __init__(self, product_type, rate, is_baht=False):
        super().__init__(title=f"คำนวณ {product_type}")
        self.product_type = product_type
        self.rate = rate
        self.is_baht = is_baht
        
        label = "จำนวน (บาท)" if is_baht else "จำนวน (Robux)"
        placeholder = "ตัวอย่าง: 1000, 500+200, 1000*2, 5000/2"
        
        self.amount_input = TextInput(
            label=label,
            placeholder=placeholder,
            required=True,
            style=discord.TextStyle.short
        )
        self.add_item(self.amount_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Evaluate the expression
            amount = evaluate_expression(self.amount_input.value)
            
            if amount <= 0:
                await interaction.response.send_message("❌ กรุณากรอกจำนวนที่มากกว่า 0", ephemeral=True)
                return
            
            if self.is_baht:
                # Convert THB to Robux
                robux = amount * self.rate
                robux_int = int(robux)
                embed = discord.Embed(
                    title=f"📊 ผลการคำนวณ {self.product_type}",
                    description=f"จากจำนวน **{format_number(amount)}** บาท",
                    color=0x00FF99
                )
                embed.add_field(name=f"💸 จำนวน {ROBUX_EMOJI}", value=f"**{format_number(robux_int)}**", inline=True)
                embed.add_field(name="💰 เรท", value=f"**{self.rate}** บาท/Robux", inline=True)
            else:
                # Convert Robux to THB
                price = amount / self.rate
                price_int = round_price(price)
                embed = discord.Embed(
                    title=f"📊 ผลการคำนวณ {self.product_type}",
                    description=f"จากจำนวน **{format_number(amount)}** {ROBUX_EMOJI}",
                    color=0x00FF99
                )
                embed.add_field(name="💰 ราคา", value=f"**{format_number(price_int)}** บาท", inline=True)
                embed.add_field(name="💰 เรท", value=f"**{self.rate}** บาท/Robux", inline=True)
            
            embed.set_footer(text="Sushi Shop 🍣")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except ValueError as e:
            await interaction.response.send_message(f"❌ รูปแบบตัวเลขไม่ถูกต้อง: {e}\nตัวอย่าง: 1000, 500+200, 1000*2, 5000/2", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)


class DeliveryView(View):
    def __init__(self, channel, product_type, robux, price, buyer):
        super().__init__(timeout=None)
        self.channel = channel
        self.product_type = product_type
        self.robux = robux
        self.price = price
        self.buyer = buyer
        
        deliver_btn = Button(label="ส่งของและเพิ่ม SP", style=discord.ButtonStyle.success, emoji="✅")
        deliver_btn.callback = self.deliver_callback
        self.add_item(deliver_btn)
    
    async def deliver_callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            admin_role = interaction.guild.get_role(1361016912259055896)
            if not admin_role or admin_role not in interaction.user.roles:
                await interaction.response.send_message("❌ เฉพาะแอดมินเท่านั้นที่ใช้ปุ่มนี้ได้", ephemeral=True)
                return
        
        await interaction.response.defer()
        
        # Add SP to buyer
        if self.buyer:
            await add_sp(self.buyer.id, self.robux)
        
        # Create receipt
        receipt_color = 0xFFA500 if self.product_type == "Gamepass" else 0x00FFFF
        embed = discord.Embed(
            title=f"🍣 ใบเสร็จการสั่งซื้อ ({self.product_type}) 🍣",
            color=receipt_color
        )
        embed.add_field(name="😊 ผู้ซื้อ", value=self.buyer.mention if self.buyer else "ไม่ทราบ", inline=False)
        embed.add_field(name=f"💸 จำนวน{ROBUX_EMOJI}", value=f"{format_number(self.robux)}", inline=True)
        embed.add_field(name="💰 ราคาตามเรท", value=f"{format_number(self.price)} บาท", inline=True)
        embed.set_footer(text=f"จัดส่งสินค้าสำเร็จ 🤗 • {get_thailand_time().strftime('%d/%m/%y, %H:%M')}")
        
        # Send to log channel
        log_channel = interaction.client.get_channel(SALES_LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(embed=embed)
        
        # Send success message in ticket
        success_embed = discord.Embed(
            title="✅ ส่งของเรียบร้อยแล้ว",
            description=f"เพิ่ม SP ให้ {self.buyer.mention if self.buyer else 'ผู้ซื้อ'} จำนวน **{format_number(self.robux)}** SP",
            color=0x00FF00
        )
        await self.channel.send(embed=success_embed)
        
        # Update stock
        if self.product_type == "Gamepass":
            async with interaction.client.stock_lock:
                global gamepass_stock
                gamepass_stock = max(0, gamepass_stock - self.robux)
        else:
            async with interaction.client.stock_lock:
                global group_stock
                group_stock = max(0, group_stock - self.robux)
        
        save_stock_values()
        await update_main_channel()
        
        # Clean up
        if str(self.channel.id) in ticket_robux_data:
            del ticket_robux_data[str(self.channel.id)]
            save_json(ticket_robux_data_file, ticket_robux_data)
        
        await interaction.followup.send("✅ ดำเนินการเรียบร้อย!", ephemeral=True)


class PremiumDeliveryView(View):
    def __init__(self, channel, product_type, amount, buyer):
        super().__init__(timeout=None)
        self.channel = channel
        self.product_type = product_type
        self.amount = amount
        self.buyer = buyer
        
        deliver_btn = Button(label="ส่งของและเพิ่ม SP", style=discord.ButtonStyle.success, emoji="✅")
        deliver_btn.callback = self.deliver_callback
        self.add_item(deliver_btn)
    
    async def deliver_callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            admin_role = interaction.guild.get_role(1361016912259055896)
            if not admin_role or admin_role not in interaction.user.roles:
                await interaction.response.send_message("❌ เฉพาะแอดมินเท่านั้นที่ใช้ปุ่มนี้ได้", ephemeral=True)
                return
        
        await interaction.response.defer()
        
        # Add SP to buyer (Premium gives 5000 SP)
        sp_amount = 5000
        if self.buyer:
            await add_sp(self.buyer.id, sp_amount)
        
        # Create receipt
        embed = discord.Embed(
            title=f"🍣 ใบเสร็จการสั่งซื้อ ({self.product_type}) 🍣",
            color=0x9B59B6
        )
        embed.add_field(name="😊 ผู้ซื้อ", value=self.buyer.mention if self.buyer else "ไม่ทราบ", inline=False)
        embed.add_field(name="✨ สินค้า", value="Premium Membership", inline=True)
        embed.add_field(name="💰 ราคา", value=f"{format_number(self.amount)} บาท", inline=True)
        embed.add_field(name="🎁 SP ที่ได้รับ", value=f"{format_number(sp_amount)} SP", inline=True)
        embed.set_footer(text=f"จัดส่งสินค้าสำเร็จ 🤗 • {get_thailand_time().strftime('%d/%m/%y, %H:%M')}")
        
        # Send to log channel
        log_channel = interaction.client.get_channel(SALES_LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(embed=embed)
        
        # Send success message in ticket
        success_embed = discord.Embed(
            title="✅ ส่งของเรียบร้อยแล้ว",
            description=f"เพิ่ม SP ให้ {self.buyer.mention if self.buyer else 'ผู้ซื้อ'} จำนวน **{format_number(sp_amount)}** SP",
            color=0x00FF00
        )
        await self.channel.send(embed=success_embed)
        
        # Update stock
        async with interaction.client.stock_lock:
            global premium_stock
            premium_stock = max(0, premium_stock - 1)
        
        save_stock_values()
        await update_main_channel()
        
        # Clean up
        if str(self.channel.id) in ticket_robux_data:
            del ticket_robux_data[str(self.channel.id)]
            save_json(ticket_robux_data_file, ticket_robux_data)
        
        await interaction.followup.send("✅ ดำเนินการเรียบร้อย!", ephemeral=True)


class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="เปิดตั๋ว Gamepass", style=discord.ButtonStyle.primary, emoji="🎮", custom_id="ticket_gamepass")
    async def ticket_gamepass(self, interaction: discord.Interaction, button: Button):
        await handle_open_ticket(interaction, "Gamepass")
    
    @discord.ui.button(label="เปิดตั๋ว Group", style=discord.ButtonStyle.primary, emoji="👥", custom_id="ticket_group")
    async def ticket_group(self, interaction: discord.Interaction, button: Button):
        if not group_ticket_enabled:
            await interaction.response.send_message("❌ ขณะนี้ปิดรับออเดอร์ Group ชั่วคราว", ephemeral=True)
            return
        await handle_open_ticket(interaction, "Group")
    
    @discord.ui.button(label="เปิดตั๋ว Premium", style=discord.ButtonStyle.primary, emoji="✨", custom_id="ticket_premium")
    async def ticket_premium(self, interaction: discord.Interaction, button: Button):
        if not premium_ticket_enabled:
            await interaction.response.send_message("❌ ขณะนี้ปิดรับออเดอร์ Premium ชั่วคราว", ephemeral=True)
            return
        await handle_open_ticket(interaction, "Premium")
    
    @discord.ui.button(label="เช็คสถานะ", style=discord.ButtonStyle.secondary, emoji="📊", custom_id="check_status")
    async def check_status(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(title="📊 สถานะร้าน Sushi Shop", color=0x00FF99)
        embed.add_field(name="🎮 Gamepass Stock", value=f"**{format_number(gamepass_stock)}**", inline=True)
        embed.add_field(name="👥 Group Stock", value=f"**{format_number(group_stock)}**", inline=True)
        embed.add_field(name="✨ Premium Stock", value=f"**{format_number(premium_stock)}**", inline=True)
        embed.add_field(name="🏪 สถานะร้าน", value="🟢 เปิด" if shop_open else "🔴 ปิด", inline=True)
        embed.add_field(name="👥 เปิดรับ Group", value="✅ เปิด" if group_ticket_enabled else "❌ ปิด", inline=True)
        embed.add_field(name="✨ เปิดรับ Premium", value="✅ เปิด" if premium_ticket_enabled else "❌ ปิด", inline=True)
        embed.set_footer(text="Sushi Shop 🍣")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class ConfirmView(View):
    def __init__(self, channel, buyer):
        super().__init__(timeout=60)
        self.channel = channel
        self.buyer = buyer
    
    @discord.ui.button(label="ใช่, ยืนยัน", style=discord.ButtonStyle.danger, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.buyer.id:
            await interaction.response.send_message("❌ เฉพาะผู้เปิดตั๋วเท่านั้นที่ยืนยันได้", ephemeral=True)
            return
        
        await interaction.response.edit_message(content="✅ ยืนยันการเปิดตั๋วแล้ว รอแอดมินมารับออเดอร์", view=None)
        
        # Send notification to admin channel
        admin_channel = interaction.client.get_channel(MAIN_CHANNEL_ID)
        if admin_channel:
            await admin_channel.send(f"🎫 มีตั๋วใหม่: {self.channel.mention} โดย {self.buyer.mention}")
    
    @discord.ui.button(label="ไม่, ยกเลิก", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.buyer.id:
            await interaction.response.send_message("❌ เฉพาะผู้เปิดตั๋วเท่านั้นที่ยกเลิกได้", ephemeral=True)
            return
        
        await interaction.response.edit_message(content="❌ ยกเลิกการเปิดตั๋ว", view=None)
        await asyncio.sleep(3)
        await self.channel.delete()


class EditRateView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="แก้ไขเรท Gamepass", style=discord.ButtonStyle.primary, emoji="🎮")
    async def edit_gamepass_rate(self, interaction: discord.Interaction, button: Button):
        modal = EditRateModal("Gamepass")
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="แก้ไขเรท Group", style=discord.ButtonStyle.primary, emoji="👥")
    async def edit_group_rate(self, interaction: discord.Interaction, button: Button):
        modal = EditGroupRateModal()
        await interaction.response.send_modal(modal)


class EditRateModal(Modal):
    def __init__(self, rate_type):
        super().__init__(title=f"แก้ไขเรท {rate_type}")
        self.rate_type = rate_type
        
        self.rate_input = TextInput(
            label=f"เรท {rate_type} (บาท/Robux)",
            placeholder="ตัวอย่าง: 6.5",
            required=True,
            style=discord.TextStyle.short
        )
        self.add_item(self.rate_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        global gamepass_rate
        
        try:
            new_rate = float(self.rate_input.value.replace(",", ""))
            if new_rate <= 0:
                await interaction.response.send_message("❌ เรทต้องมากกว่า 0", ephemeral=True)
                return
            
            gamepass_rate = new_rate
            save_stock_values()
            await update_main_channel()
            
            embed = discord.Embed(
                title="✅ แก้ไขเรทสำเร็จ",
                description=f"เรท Gamepass เปลี่ยนเป็น **{gamepass_rate}** บาท/Robux",
                color=0x00FF00
            )
            await interaction.response.send_message(embed=embed)
            
        except ValueError:
            await interaction.response.send_message("❌ กรุณากรอกตัวเลขให้ถูกต้อง", ephemeral=True)


class EditGroupRateModal(Modal):
    def __init__(self):
        super().__init__(title="แก้ไขเรท Group")
        
        self.low_rate_input = TextInput(
            label="เรทต่ำกว่า 500 บาท",
            placeholder="ตัวอย่าง: 4",
            required=True,
            style=discord.TextStyle.short
        )
        self.add_item(self.low_rate_input)
        
        self.high_rate_input = TextInput(
            label="เรท 500 บาทขึ้นไป",
            placeholder="ตัวอย่าง: 4.5",
            required=True,
            style=discord.TextStyle.short
        )
        self.add_item(self.high_rate_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        global group_rate_low, group_rate_high
        
        try:
            new_low_rate = float(self.low_rate_input.value.replace(",", ""))
            new_high_rate = float(self.high_rate_input.value.replace(",", ""))
            
            if new_low_rate <= 0 or new_high_rate <= 0:
                await interaction.response.send_message("❌ เรทต้องมากกว่า 0", ephemeral=True)
                return
            
            group_rate_low = new_low_rate
            group_rate_high = new_high_rate
            save_stock_values()
            await update_main_channel()
            
            embed = discord.Embed(
                title="✅ แก้ไขเรทสำเร็จ",
                description=f"เรท Group (ต่ำกว่า 500): **{group_rate_low}** บาท/Robux\nเรท Group (500+): **{group_rate_high}** บาท/Robux",
                color=0x00FF00
            )
            await interaction.response.send_message(embed=embed)
            
        except ValueError:
            await interaction.response.send_message("❌ กรุณากรอกตัวเลขให้ถูกต้อง", ephemeral=True)


class GroupTicketToggleView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="เปิด/ปิด รับออเดอร์ Group", style=discord.ButtonStyle.primary, emoji="👥")
    async def toggle_group_ticket(self, interaction: discord.Interaction, button: Button):
        global group_ticket_enabled
        group_ticket_enabled = not group_ticket_enabled
        save_stock_values()
        
        status = "เปิด" if group_ticket_enabled else "ปิด"
        embed = discord.Embed(
            title="✅ เปลี่ยนสถานะสำเร็จ",
            description=f"เปิดรับออเดอร์ Group: **{status}**",
            color=0x00FF00 if group_ticket_enabled else 0xFF0000
        )
        await interaction.response.send_message(embed=embed)
        await update_main_channel()


class PremiumTicketToggleView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="เปิด/ปิด รับออเดอร์ Premium", style=discord.ButtonStyle.primary, emoji="✨")
    async def toggle_premium_ticket(self, interaction: discord.Interaction, button: Button):
        global premium_ticket_enabled
        premium_ticket_enabled = not premium_ticket_enabled
        save_stock_values()
        
        status = "เปิด" if premium_ticket_enabled else "ปิด"
        embed = discord.Embed(
            title="✅ เปลี่ยนสถานะสำเร็จ",
            description=f"เปิดรับออเดอร์ Premium: **{status}**",
            color=0x00FF00 if premium_ticket_enabled else 0xFF0000
        )
        await interaction.response.send_message(embed=embed)
        await update_main_channel()


# ============ TICKET FUNCTIONS ============
async def schedule_removal(channel, buyer, delay_seconds):
    """Schedule a ticket for removal after delay"""
    async def remove_ticket():
        await asyncio.sleep(delay_seconds)
        if channel and not channel.deleted:
            try:
                await save_ticket_transcript(channel, buyer)
                await channel.delete()
                print(f"🗑️ Auto-deleted ticket {channel.name}")
            except Exception as e:
                print(f"❌ Error auto-deleting ticket: {e}")
    
    task = asyncio.create_task(remove_ticket())
    ticket_removal_tasks[channel.id] = task


async def move_to_delivered_category(channel):
    """Move channel to delivered category"""
    try:
        delivered_category = channel.guild.get_channel(DELIVERED_CATEGORY_ID)
        if delivered_category:
            await channel.edit(category=delivered_category)
            print(f"✅ Moved {channel.name} to delivered category")
    except Exception as e:
        print(f"❌ Error moving to delivered category: {e}")


async def move_to_original_category(channel, original_category_id):
    """Move channel back to original category"""
    try:
        original_category = channel.guild.get_channel(original_category_id)
        if original_category:
            await channel.edit(category=original_category)
            print(f"✅ Moved {channel.name} back to original category")
    except Exception as e:
        print(f"❌ Error moving back: {e}")


async def reset_channel_name(channel, original_name):
    """Reset channel name to original"""
    try:
        await channel.edit(name=original_name)
        print(f"✅ Reset channel name to {original_name}")
    except Exception as e:
        print(f"❌ Error resetting name: {e}")


async def remove_buyer_permission_after_delay(channel, buyer, delay_seconds):
    """Remove buyer's permission to view channel after delay"""
    await asyncio.sleep(delay_seconds)
    if channel and not channel.deleted:
        try:
            await channel.set_permissions(buyer, overwrite=None)
            print(f"🔒 Removed {buyer.name}'s access to {channel.name}")
        except Exception as e:
            print(f"❌ Error removing permission: {e}")


async def add_buyer_role(member, guild):
    """Add buyer role to member"""
    try:
        buyer_role = guild.get_role(BUYER_ROLE_ID)
        if buyer_role and buyer_role not in member.roles:
            await member.add_roles(buyer_role, reason="ซื้อสินค้าจากร้าน Sushi Shop")
            print(f"✅ Added buyer role to {member.name}")
    except Exception as e:
        print(f"❌ Error adding buyer role: {e}")


async def save_ticket_transcript(channel, buyer, robux_amount=None, customer_name=None):
    """Save ticket transcript to JSON"""
    try:
        transcript = []
        async for message in channel.history(limit=200, oldest_first=True):
            transcript.append({
                "author": str(message.author),
                "author_id": message.author.id,
                "content": message.content,
                "timestamp": message.created_at.isoformat(),
                "attachments": [a.url for a in message.attachments]
            })
        
        ticket_id = f"{channel.id}_{int(time.time())}"
        ticket_transcripts[ticket_id] = {
            "channel_name": channel.name,
            "buyer": str(buyer) if buyer else customer_name,
            "buyer_id": buyer.id if buyer else None,
            "robux_amount": robux_amount,
            "created_at": channel.created_at.isoformat(),
            "closed_at": dt.now().isoformat(),
            "transcript": transcript
        }
        
        save_json(ticket_transcripts_file, ticket_transcripts)
        print(f"✅ Saved transcript for {channel.name}")
        return True, ticket_id
        
    except Exception as e:
        print(f"❌ Error saving transcript: {e}")
        return False, None


async def handle_open_ticket(interaction: discord.Interaction, ticket_type: str):
    """Handle opening a new ticket"""
    if not shop_open:
        await interaction.response.send_message("❌ ร้านปิดให้บริการชั่วคราว", ephemeral=True)
        return
    
    # Check for existing open ticket
    existing_ticket = None
    for channel in interaction.guild.channels:
        if channel.name.startswith(f"ticket-{interaction.user.name.lower()}"):
            existing_ticket = channel
            break
    
    if existing_ticket:
        await interaction.response.send_message(f"❌ คุณมีตั๋วเปิดอยู่แล้ว: {existing_ticket.mention}", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    # Get category
    if ticket_type == "Gamepass":
        category = interaction.guild.get_channel(SUSHI_GAMEPASS_CATEGORY_ID)
    elif ticket_type == "Group":
        category = interaction.guild.get_channel(SUSHI_GAMEPASS_CATEGORY_ID)
    else:
        category = interaction.guild.get_channel(PREMIUM_CATEGORY_ID)
    
    if not category:
        await interaction.followup.send("❌ ไม่พบหมวดหมู่สำหรับตั๋วนี้", ephemeral=True)
        return
    
    # Get ticket number
    ticket_num = get_next_ticket_number()
    date_str = get_thailand_time().strftime("%d%m%y")
    channel_name = f"{date_str}-{ticket_num}-{interaction.user.name.lower()}"
    
    # Create channel
    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    }
    
    # Add admin role
    admin_role = interaction.guild.get_role(1361016912259055896)
    if admin_role:
        overwrites[admin_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
    
    channel = await category.create_text_channel(name=channel_name, overwrites=overwrites)
    
    # Store buyer data
    ticket_buyer_data[str(channel.id)] = {
        "user_id": interaction.user.id,
        "user_name": interaction.user.name,
        "ticket_type": ticket_type,
        "ticket_number": ticket_num
    }
    save_json(ticket_buyer_data_file, ticket_buyer_data)
    
    # Store customer name
    ticket_customer_data[str(channel.id)] = interaction.user.name
    save_json(ticket_customer_data_file, ticket_customer_data)
    
    # Send welcome message
    embed = discord.Embed(
        title=f"🍣 ตั๋ว {ticket_type} 🍣",
        description=f"ยินดีต้อนรับ {interaction.user.mention} สู่ร้าน Sushi Shop",
        color=0x00FF99
    )
    embed.add_field(name="📋 คำแนะนำ", value="กรุณาแจ้งจำนวน Robux ที่ต้องการซื้อ\nจากนั้นรอแอดมินมารับออเดอร์", inline=False)
    embed.add_field(name="💰 เรทปัจจุบัน", value=f"Gamepass: {gamepass_rate} บาท/Robux\nGroup: {group_rate_low}/{group_rate_high} บาท/Robux", inline=False)
    embed.set_footer(text="Sushi Shop 🍣")
    
    await channel.send(embed=embed)
    
    # Send confirmation view
    view = ConfirmView(channel, interaction.user)
    await interaction.followup.send(f"✅ สร้างตั๋ว {channel.mention} เรียบร้อยแล้ว", ephemeral=True)
    await channel.send(f"{interaction.user.mention} กรุณายืนยันการเปิดตั๋ว", view=view)


async def update_main_channel():
    """Update the main channel embed"""
    main_channel = bot.get_channel(MAIN_CHANNEL_ID)
    if not main_channel:
        return
    
    status_emoji = "🟢" if shop_open else "🔴"
    status_text = "เปิดให้บริการ" if shop_open else "ปิดให้บริการ"
    group_status = "✅ เปิด" if group_ticket_enabled else "❌ ปิด"
    premium_status = "✅ เปิด" if premium_ticket_enabled else "❌ ปิด"
    
    embed = discord.Embed(
        title="🍣 Sushi Shop 🍣",
        description=f"**ร้านขาย Gamepass และ Robux กลุ่ม ราคาถูก**\n\n{status_emoji} สถานะร้าน: **{status_text}**",
        color=0xFFA500
    )
    
    embed.add_field(
        name="📊 สต๊อกสินค้า",
        value=f"🎮 Gamepass: **{format_number(gamepass_stock)}**\n👥 Group: **{format_number(group_stock)}**\n✨ Premium: **{format_number(premium_stock)}**",
        inline=False
    )
    
    embed.add_field(
        name="💰 เรทราคา",
        value=f"🎮 Gamepass: **{gamepass_rate}** บาท/Robux\n👥 Group (<500): **{group_rate_low}** บาท/Robux\n👥 Group (500+): **{group_rate_high}** บาท/Robux\n✨ Premium: **5000 SP**",
        inline=False
    )
    
    embed.add_field(
        name="📝 วิธีการสั่งซื้อ",
        value="1. กดปุ่มด้านล่างเพื่อเปิดตั๋ว\n2. กรอกจำนวน Robux ที่ต้องการ\n3. รอแอดมินมารับออเดอร์\n4. ชำระเงินและรับสินค้า",
        inline=False
    )
    
    embed.add_field(name="👥 เปิดรับ Group", value=group_status, inline=True)
    embed.add_field(name="✨ เปิดรับ Premium", value=premium_status, inline=True)
    embed.add_field(name="🔗 ลิงก์กลุ่ม", value="[เข้ากลุ่มที่นี่](https://www.roblox.com/communities/34713179/VALKYs)", inline=True)
    
    embed.set_footer(text=f"Sushi Shop • อัพเดตล่าสุด {get_thailand_time().strftime('%d/%m/%y %H:%M')}")
    embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/717757556889747657/1403684950770847754/noFilter.png")
    
    # Check if message exists
    async for message in main_channel.history(limit=5):
        if message.author == bot.user and message.embeds:
            await message.edit(embed=embed, view=TicketView())
            return
    
    await main_channel.send(embed=embed, view=TicketView())


async def update_channel_name():
    """Update channel names with stock"""
    guild = None
    for g in bot.guilds:
        guild = g
        break
    
    if not guild:
        return
    
    gamepass_category = guild.get_channel(SUSHI_GAMEPASS_CATEGORY_ID)
    if gamepass_category:
        new_name = f"🎮 เกมพาส {format_number(gamepass_stock)}"
        if gamepass_category.name != new_name:
            try:
                await gamepass_category.edit(name=new_name)
            except:
                pass


async def update_credit_channel_name():
    """Update credit channel name with count"""
    credit_channel = bot.get_channel(CREDIT_CHANNEL_ID)
    if not credit_channel:
        return
    
    try:
        async for message in credit_channel.history(limit=None):
            pass
        message_count = credit_channel.id
    except:
        message_count = "?"
    
    new_name = f"⭐┃ให้เครดิต"
    if credit_channel.name != new_name:
        try:
            await credit_channel.edit(name=new_name)
        except:
            pass


# ============ CREDIT CHANNEL FUNCTIONS ============
async def check_credit_channel_changes():
    """Check for changes in credit channel"""
    credit_channel = bot.get_channel(CREDIT_CHANNEL_ID)
    if not credit_channel:
        return
    
    try:
        async for message in credit_channel.history(limit=1):
            pass
    except:
        pass


async def credit_channel_update_worker():
    """Worker to update credit channel"""
    global credit_channel_update_task_running
    credit_channel_update_task_running = True
    
    while True:
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"❌ Error in credit channel worker: {e}")


# ============ CALCULATOR COMMANDS ============
@bot.command(name="gp")
async def gp_cmd(ctx, *, expr: str = None):
    """คำนวณ Gamepass: จำนวน Robux → ราคาบาท"""
    if expr is None:
        view = CalculatorView("Gamepass", gamepass_rate, is_baht=False)
        embed = discord.Embed(
            title="🎮 เครื่องคิดเลข Gamepass",
            description="กดปุ่มด้านล่างเพื่อคำนวณ\n\n**รูปแบบที่ใช้ได้:**\n• ตัวเลข: `1000`\n• บวก: `500+200`\n• ลบ: `1000-300`\n• คูณ: `500*2` หรือ `500x2`\n• หาร: `1000/2` หรือ `1000÷2`",
            color=0xFFA500
        )
        embed.add_field(name="💰 เรทปัจจุบัน", value=f"{gamepass_rate} บาท/Robux", inline=False)
        await ctx.send(embed=embed, view=view)
        return
    
    try:
        robux = evaluate_expression(expr)
        if robux <= 0:
            await ctx.send("❌ กรุณากรอกจำนวนที่มากกว่า 0")
            return
        
        price = robux / gamepass_rate
        price_int = round_price(price)
        
        embed = discord.Embed(
            title="🎮 ผลการคำนวณ Gamepass",
            description=f"จากจำนวน **{format_number(robux)}** {ROBUX_EMOJI}",
            color=0xFFA500
        )
        embed.add_field(name="💰 ราคา", value=f"**{format_number(price_int)}** บาท", inline=True)
        embed.add_field(name="💰 เรท", value=f"**{gamepass_rate}** บาท/Robux", inline=True)
        embed.set_footer(text="Sushi Shop 🍣")
        await ctx.send(embed=embed)
        
    except ValueError as e:
        await ctx.send(f"❌ รูปแบบตัวเลขไม่ถูกต้อง: {e}\nตัวอย่าง: `1000`, `500+200`, `1000*2`, `5000/2`")
    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")


@bot.command(name="g")
async def g_cmd(ctx, *, expr: str = None):
    """คำนวณ Group: จำนวน Robux → ราคาบาท"""
    if expr is None:
        view = CalculatorView("Group", group_rate_low, is_baht=False)
        embed = discord.Embed(
            title="👥 เครื่องคิดเลข Group",
            description="กดปุ่มด้านล่างเพื่อคำนวณ\n\n**รูปแบบที่ใช้ได้:**\n• ตัวเลข: `1000`\n• บวก: `500+200`\n• ลบ: `1000-300`\n• คูณ: `500*2` หรือ `500x2`\n• หาร: `1000/2` หรือ `1000÷2`",
            color=0x00FFFF
        )
        embed.add_field(name="💰 เรทปัจจุบัน", value=f"ต่ำกว่า 500: {group_rate_low} บาท/Robux\n500+: {group_rate_high} บาท/Robux", inline=False)
        await ctx.send(embed=embed, view=view)
        return
    
    try:
        robux = evaluate_expression(expr)
        if robux <= 0:
            await ctx.send("❌ กรุณากรอกจำนวนที่มากกว่า 0")
            return
        
        rate = group_rate_low if robux * group_rate_low < 500 else group_rate_high
        price = robux / rate
        price_int = round_price(price)
        
        embed = discord.Embed(
            title="👥 ผลการคำนวณ Group",
            description=f"จากจำนวน **{format_number(robux)}** {ROBUX_EMOJI}",
            color=0x00FFFF
        )
        embed.add_field(name="💰 ราคา", value=f"**{format_number(price_int)}** บาท", inline=True)
        embed.add_field(name="💰 เรทที่ใช้", value=f"**{rate}** บาท/Robux", inline=True)
        embed.set_footer(text="Sushi Shop 🍣")
        await ctx.send(embed=embed)
        
    except ValueError as e:
        await ctx.send(f"❌ รูปแบบตัวเลขไม่ถูกต้อง: {e}\nตัวอย่าง: `1000`, `500+200`, `1000*2`, `5000/2`")
    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")


@bot.command(name="gpb")
async def gpb_cmd(ctx, *, expr: str = None):
    """คำนวณ Gamepass: จำนวนบาท → Robux"""
    if expr is None:
        view = CalculatorView("Gamepass", gamepass_rate, is_baht=True)
        embed = discord.Embed(
            title="🎮 เครื่องคิดเลข Gamepass (บาท → Robux)",
            description="กดปุ่มด้านล่างเพื่อคำนวณ\n\n**รูปแบบที่ใช้ได้:**\n• ตัวเลข: `1000`\n• บวก: `500+200`\n• ลบ: `1000-300`\n• คูณ: `500*2` หรือ `500x2`\n• หาร: `1000/2` หรือ `1000÷2`",
            color=0xFFA500
        )
        embed.add_field(name="💰 เรทปัจจุบัน", value=f"{gamepass_rate} บาท/Robux", inline=False)
        await ctx.send(embed=embed, view=view)
        return
    
    try:
        amount_baht = evaluate_expression(expr)
        if amount_baht <= 0:
            await ctx.send("❌ กรุณากรอกจำนวนที่มากกว่า 0")
            return
        
        robux = amount_baht * gamepass_rate
        robux_int = int(robux)
        
        embed = discord.Embed(
            title="🎮 ผลการคำนวณ Gamepass",
            description=f"จากจำนวน **{format_number(amount_baht)}** บาท",
            color=0xFFA500
        )
        embed.add_field(name=f"💸 จำนวน {ROBUX_EMOJI}", value=f"**{format_number(robux_int)}**", inline=True)
        embed.add_field(name="💰 เรท", value=f"**{gamepass_rate}** บาท/Robux", inline=True)
        embed.set_footer(text="Sushi Shop 🍣")
        await ctx.send(embed=embed)
        
    except ValueError as e:
        await ctx.send(f"❌ รูปแบบตัวเลขไม่ถูกต้อง: {e}\nตัวอย่าง: `1000`, `500+200`, `1000*2`, `5000/2`")
    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")


@bot.command(name="gb")
async def gb_cmd(ctx, *, expr: str = None):
    """คำนวณ Group: จำนวนบาท → Robux"""
    if expr is None:
        view = CalculatorView("Group", group_rate_low, is_baht=True)
        embed = discord.Embed(
            title="👥 เครื่องคิดเลข Group (บาท → Robux)",
            description="กดปุ่มด้านล่างเพื่อคำนวณ\n\n**รูปแบบที่ใช้ได้:**\n• ตัวเลข: `1000`\n• บวก: `500+200`\n• ลบ: `1000-300`\n• คูณ: `500*2` หรือ `500x2`\n• หาร: `1000/2` หรือ `1000÷2`",
            color=0x00FFFF
        )
        embed.add_field(name="💰 เรทปัจจุบัน", value=f"ต่ำกว่า 500: {group_rate_low} บาท/Robux\n500+: {group_rate_high} บาท/Robux", inline=False)
        await ctx.send(embed=embed, view=view)
        return
    
    try:
        amount_baht = evaluate_expression(expr)
        if amount_baht <= 0:
            await ctx.send("❌ กรุณากรอกจำนวนที่มากกว่า 0")
            return
        
        # We need to find which rate to use
        # This is an approximation - we check both rates
        robux_low = amount_baht / group_rate_low
        robux_high = amount_baht / group_rate_high
        
        # Use the appropriate rate based on resulting price
        if robux_low * group_rate_low < 500:
            robux = robux_low
            rate_used = group_rate_low
        else:
            robux = robux_high
            rate_used = group_rate_high
        
        robux_int = int(robux)
        
        embed = discord.Embed(
            title="👥 ผลการคำนวณ Group",
            description=f"จากจำนวน **{format_number(amount_baht)}** บาท",
            color=0x00FFFF
        )
        embed.add_field(name=f"💸 จำนวน {ROBUX_EMOJI}", value=f"**{format_number(robux_int)}**", inline=True)
        embed.add_field(name="💰 เรทที่ใช้", value=f"**{rate_used}** บาท/Robux", inline=True)
        embed.set_footer(text="Sushi Shop 🍣")
        await ctx.send(embed=embed)
        
    except ValueError as e:
        await ctx.send(f"❌ รูปแบบตัวเลขไม่ถูกต้อง: {e}\nตัวอย่าง: `1000`, `500+200`, `1000*2`, `5000/2`")
    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")


@bot.command(name="tax")
async def tax_cmd(ctx, amount: int = None):
    """คำนวณภาษี 7%"""
    if amount is None:
        await ctx.send("❌ กรุณาระบุจำนวนเงิน\nตัวอย่าง: `!tax 1000`")
        return
    
    try:
        tax = amount * 0.07
        total = amount + tax
        
        embed = discord.Embed(
            title="💰 คำนวณภาษี 7%",
            color=0x00FF99
        )
        embed.add_field(name="จำนวนเงิน", value=f"{format_number(amount)} บาท", inline=True)
        embed.add_field(name="ภาษี 7%", value=f"{format_number(int(tax))} บาท", inline=True)
        embed.add_field(name="รวมทั้งสิ้น", value=f"{format_number(int(total))} บาท", inline=True)
        embed.set_footer(text="Sushi Shop 🍣")
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")


@bot.command(name="love")
async def love_cmd(ctx):
    """💖"""
    await ctx.send(f"💖 {ctx.author.mention} รักนะจุ๊บๆ 💖")


@bot.command(name="say")
@admin_only()
async def say_cmd(ctx, channel_id: int, *, message: str):
    """ให้บอทพูดในช่องที่กำหนด"""
    channel = bot.get_channel(channel_id)
    if channel:
        await channel.send(message)
        await ctx.send(f"✅ ส่งข้อความไปยัง {channel.mention} เรียบร้อย", delete_after=5)
    else:
        await ctx.send("❌ ไม่พบช่องที่ระบุ", delete_after=5)


@bot.command(name="qr")
@admin_only()
async def qr_cmd(ctx, user: discord.Member = None, *, sp_amount: int = None):
    """เพิ่ม SP ให้ผู้ใช้ (QR Code)"""
    if user is None or sp_amount is None:
        await ctx.send("❌ การใช้งาน: `!qr @ผู้ใช้ จำนวนSP`")
        return
    
    await add_sp(user.id, sp_amount)
    
    embed = discord.Embed(
        title="✅ เพิ่ม SP สำเร็จ",
        description=f"เพิ่ม **{format_number(sp_amount)}** SP ให้ {user.mention}",
        color=0x00FF00
    )
    await ctx.send(embed=embed)


@bot.command(name="qr2")
@admin_only()
async def qr2_cmd(ctx, user: discord.Member = None, *, sp_amount: int = None):
    """ลบ SP จากผู้ใช้ (QR Code ลบ)"""
    if user is None or sp_amount is None:
        await ctx.send("❌ การใช้งาน: `!qr2 @ผู้ใช้ จำนวนSP`")
        return
    
    success = await remove_sp(user.id, sp_amount)
    
    if success:
        embed = discord.Embed(
            title="✅ ลบ SP สำเร็จ",
            description=f"ลบ **{format_number(sp_amount)}** SP จาก {user.mention}",
            color=0x00FF00
        )
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"❌ ลบ SP ไม่สำเร็จ (SP ของ {user.mention} อาจไม่พอ)")


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
    
    embed = discord.Embed(title="✅ เปิดร้านเรียบร้อย", description="ร้าน Sushi Shop เปิดให้บริการแล้ว", color=0x00FF00)
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
    
    embed = discord.Embed(title="🔴 ปิดร้านแล้ว", description="ร้าน Sushi Shop ปิดให้บริการชั่วคราว", color=0xFF0000)
    embed.set_footer(text=f"เวลา: {get_thailand_time().strftime('%d/%m/%y %H:%M')}")
    await ctx.send(embed=embed)


@bot.command()
async def link(ctx):
    await ctx.send("# 🔗 ลิงก์กลุ่ม\nเข้ากลุ่มนี้ 15 วันก่อนซื้อโรกลุ่ม: https://www.roblox.com/communities/34713179/VALKYs\nSushi Shop 🍣")


@bot.command()
@admin_only()
async def stock(ctx, stock_type=None, amount=None):
    global gamepass_stock, group_stock, premium_stock
    
    try:
        await ctx.message.delete()
    except:
        pass
    
    if not stock_type:
        embed = discord.Embed(title="📊 สต๊อกสินค้า", color=0x00FF99)
        embed.add_field(name="🎮 Gamepass Stock", value=f"**{format_number(gamepass_stock)}**", inline=True)
        embed.add_field(name="👥 Group Stock", value=f"**{format_number(group_stock)}**", inline=True)
        embed.add_field(name="✨ Premium Stock", value=f"**{format_number(premium_stock)}**", inline=True)
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
                
    elif stock_type.lower() in ["p", "premium", "พรีเมียม"]:
        if amount is None:
            embed = discord.Embed(title="✨ Premium Stock", description=f"**{format_number(premium_stock)}**", color=0x00FF99)
            await ctx.send(embed=embed)
        else:
            try:
                premium_stock = int(amount.replace(",", ""))
                save_stock_values()
                embed = discord.Embed(title="✅ ตั้งค่า Stock เรียบร้อย", description=f"ตั้งค่า สต๊อกพรีเมียม เป็น **{format_number(premium_stock)}** เรียบร้อยแล้ว", color=0x00FF00)
                await ctx.send(embed=embed)
                await update_main_channel()
            except ValueError:
                await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)
    else:
        embed = discord.Embed(title="❌ การใช้งานไม่ถูกต้อง", description="**การใช้งาน:**\n`!stock` - เช็ค stock ทั้งหมด\n`!stock gp <จำนวน>` - ตั้งค่า Gamepass stock\n`!stock group <จำนวน>` - ตั้งค่า Group stock\n`!stock premium <จำนวน>` - ตั้งค่า Premium stock", color=0xFF0000)
        await ctx.send(embed=embed)


# ============ LEVEL COMMANDS ============
@bot.command(name="level")
async def level_cmd(ctx):
    """Check your level and rank"""
    view = LevelCheckView(ctx.author.id)
    embed = discord.Embed(
        title="🍣 ระบบเลเวล Sushi Shop",
        description="กดปุ่มด้านล่างเพื่อเช็คเลเวลของคุณหรือดูอันดับ",
        color=0x00FF99
    )
    embed.add_field(
        name="✨ วิธีการได้ SP",
        value=f"ซื้อ 1 {ROBUX_EMOJI} = 1 SP\n(บันทึกเมื่อแอดมินกดส่งสินค้า)",
        inline=False
    )
    
    level_list = []
    sorted_levels = sorted(LEVEL_ROLES.keys())
    for threshold in sorted_levels:
        level_name = LEVEL_NAMES.get(threshold, f"Level {threshold}")
        
        if threshold == 0:
            level_list.append(f"1 SP - {level_name}")
        else:
            level_list.append(f"{format_number(threshold)} SP - {level_name}")
    
    embed.add_field(name="🏆 ระดับ", value="\n".join(level_list), inline=False)
    embed.set_footer(text="Sushi Shop 🍣")
    
    await ctx.send(embed=embed, view=view)


@bot.command(name="checklv")
async def check_lv_cmd(ctx, user: discord.Member = None):
    """Check level of a user"""
    if user is None:
        user = ctx.author
    
    if user != ctx.author and not ctx.author.guild_permissions.administrator:
        admin_role = ctx.guild.get_role(1361016912259055896)
        if not admin_role or admin_role not in ctx.author.roles:
            await ctx.send("❌ คุณไม่มีสิทธิ์เช็คเลเวลของผู้อื่น", delete_after=5)
            return
    
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
    embed.add_field(name="📊 อันดับ", value=f"{medal}", inline=True)
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


@bot.command(name="setsp")
@admin_only()
async def set_sp_cmd(ctx, user: discord.Member, amount: int):
    """Admin command to set a user's SP"""
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
    """Admin command to remove SP from a user"""
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


@bot.command(name="fixroles")
@admin_only()
async def fix_roles_cmd(ctx, user: discord.Member = None):
    """Fix roles for a user or all users"""
    if user:
        await ctx.send(f"🔄 กำลังซ่อมแซมบทบาทให้ {user.mention}...")
        
        user_id_str = str(user.id)
        if user_id_str in user_levels:
            sp = user_levels[user_id_str]["sp"]
            await update_member_roles(user, sp)
            await ctx.send(f"✅ ซ่อมแซมบทบาทให้ {user.mention} เรียบร้อย (SP: {sp})")
        else:
            await ctx.send(f"❌ ไม่พบข้อมูล SP ของ {user.mention}")
    else:
        await ctx.send("🔄 กำลังซ่อมแซมบทบาทให้สมาชิกทั้งหมด...")
        
        fixed_count = 0
        failed_count = 0
        
        for user_id_str, data in user_levels.items():
            try:
                member = ctx.guild.get_member(int(user_id_str))
                if member:
                    sp = data["sp"]
                    result = await update_member_roles(member, sp)
                    if result:
                        fixed_count += 1
                    else:
                        failed_count += 1
                    await asyncio.sleep(0.5)
            except Exception as e:
                print(f"Error fixing roles for {user_id_str}: {e}")
                failed_count += 1
        
        await ctx.send(f"✅ ซ่อมแซมบทบาทให้สมาชิก {fixed_count} คน เรียบร้อย\n❌ ล้มเหลว {failed_count} คน")


@bot.command(name="checkperms")
@admin_only()
async def check_perms_cmd(ctx):
    """Check bot permissions for role management"""
    bot_member = ctx.guild.me
    
    embed = discord.Embed(title="🔧 Bot Permissions Check", color=0xFFA500)
    
    has_manage_roles = bot_member.guild_permissions.manage_roles
    embed.add_field(
        name="Manage Roles Permission",
        value="✅ Yes" if has_manage_roles else "❌ No",
        inline=False
    )
    
    bot_top_role = bot_member.top_role
    embed.add_field(name="Bot's Highest Role", value=bot_top_role.mention, inline=True)
    embed.add_field(name="Bot's Role Position", value=str(bot_top_role.position), inline=True)
    
    embed.add_field(name="\u200b", value="**Level Roles Hierarchy:**", inline=False)
    sorted_levels = sorted(LEVEL_ROLES.items())
    for threshold, role_id in sorted_levels:
        role = ctx.guild.get_role(role_id)
        if role:
            can_manage = role.position < bot_top_role.position
            status = "✅ Can manage" if can_manage else "❌ Cannot manage (role too high)"
            embed.add_field(
                name=f"{LEVEL_NAMES.get(threshold, 'Unknown')} ({format_number(threshold)} SP)",
                value=f"{role.mention}\n{status}\nPosition: {role.position}",
                inline=False
            )
        else:
            embed.add_field(
                name=f"Level {threshold} SP",
                value=f"❌ Role not found! ID: {role_id}",
                inline=False
            )
    
    await ctx.send(embed=embed)


@bot.command(name="fixuserrole")
@admin_only()
async def fix_user_role_cmd(ctx, user: discord.Member):
    """Fix role for a specific user"""
    await ctx.send(f"🔄 กำลังซ่อมแซมบทบาทให้ {user.mention}...")
    
    user_id_str = str(user.id)
    if user_id_str in user_levels:
        sp = user_levels[user_id_str]["sp"]
        await update_member_roles(user, sp)
        await ctx.send(f"✅ ซ่อมแซมบทบาทให้ {user.mention} เรียบร้อย (SP: {sp})")
    else:
        await ctx.send(f"❌ ไม่พบข้อมูล SP ของ {user.mention}")


# ============ DATA COMMANDS ============
@bot.command(name="savedata")
@admin_only()
async def save_data_cmd(ctx):
    """Manually save all data to disk"""
    await ctx.send("💾 กำลังบันทึกข้อมูล...")
    
    success = save_all_data_sync()
    backup_user_levels()
    
    if success and os.path.exists(user_levels_file):
        file_size = os.path.getsize(user_levels_file)
        await ctx.send(f"✅ บันทึกข้อมูลเรียบร้อย! (ขนาดไฟล์: {file_size} bytes)")
    else:
        await ctx.send("❌ เกิดข้อผิดพลาดในการบันทึกข้อมูล")


@bot.command(name="checkdata")
@admin_only()
async def check_data_cmd(ctx):
    """Check SP data status"""
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


@bot.command(name="checkdir")
@admin_only()
async def check_dir_cmd(ctx):
    """Check data directory permissions"""
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


# ============ ORDER COMMANDS ============
@bot.command()
@admin_only()
async def od(ctx, *, expr):
    """รับออเดอร์เกมพาส"""
    global gamepass_stock, gamepass_rate
    
    if not ctx.channel.name.startswith("ticket-") and not re.match(r'^\d{10}-\d+-[\w\u0E00-\u0E7F]+$', ctx.channel.name):
        await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะในตั๋วเท่านั้น", delete_after=5)
        return
    
    try:
        robux = evaluate_expression(expr)
        if robux <= 0:
            await ctx.send("❌ กรุณากรอกจำนวนที่มากกว่า 0")
            return
        
        price = robux / gamepass_rate
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
        embed.set_footer(text=f"รับออร์เดอร์แล้ว 🤗 • {get_thailand_time().strftime('%d/%m/%y, %H:%M')}")
        
        await ctx.send(embed=embed, view=DeliveryView(ctx.channel, "Gamepass", robux, price_int, buyer))
        await update_main_channel()
        
    except ValueError as e:
        await ctx.send(f"❌ รูปแบบตัวเลขไม่ถูกต้อง: {e}\nตัวอย่าง: `1000`, `500+200`, `1000*2`, `5000/2`")
    except Exception as e:
        print(f"❌ Error in !od: {e}")
        traceback.print_exc()
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")


@bot.command()
@admin_only()
async def odg(ctx, *, expr):
    """รับออเดอร์โรกลุ่ม"""
    global group_stock, group_rate_low, group_rate_high
    
    if not ctx.channel.name.startswith("ticket-") and not re.match(r'^\d{10}-\d+-[\w\u0E00-\u0E7F]+$', ctx.channel.name):
        await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะในตั๋วเท่านั้น", delete_after=5)
        return
    
    try:
        robux = evaluate_expression(expr)
        if robux <= 0:
            await ctx.send("❌ กรุณากรอกจำนวนที่มากกว่า 0")
            return
        
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
        embed.set_footer(text=f"รับออร์เดอร์แล้ว 🤗 • {get_thailand_time().strftime('%d/%m/%y, %H:%M')}")
        
        await ctx.send(embed=embed, view=DeliveryView(ctx.channel, "Group", robux, price_int, buyer))
        await update_main_channel()
        
    except ValueError as e:
        await ctx.send(f"❌ รูปแบบตัวเลขไม่ถูกต้อง: {e}\nตัวอย่าง: `1000`, `500+200`, `1000*2`, `5000/2`")
    except Exception as e:
        print(f"❌ Error in !odg: {e}")
        traceback.print_exc()
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")


@bot.command()
@admin_only()
async def odp(ctx, *, expr):
    """รับออเดอร์พรีเมียม"""
    global premium_stock
    
    if not ctx.channel.name.startswith("ticket-") and not re.match(r'^\d{10}-\d+-[\w\u0E00-\u0E7F]+$', ctx.channel.name):
        await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะในตั๋วเท่านั้น", delete_after=5)
        return
    
    try:
        amount = evaluate_expression(expr)
        if amount <= 0:
            await ctx.send("❌ กรุณากรอกจำนวนที่มากกว่า 0")
            return
        
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
        
        if buyer:
            await add_buyer_role(buyer, ctx.guild)
        
        async with bot.stock_lock:
            premium_stock = max(0, premium_stock - 1)
        
        save_stock_values()
        
        ticket_robux_data[str(ctx.channel.id)] = str(amount)
        save_json(ticket_robux_data_file, ticket_robux_data)
        
        embed = discord.Embed(title="🍣คำสั่งซื้อสินค้า🍣", color=0x9B59B6)
        embed.add_field(name="📦 ประเภทสินค้า", value="Premium", inline=False)
        embed.add_field(name="✨ สินค้า", value="Premium Membership", inline=True)
        embed.add_field(name="💰 ราคา", value=f"{format_number(amount)} บาท", inline=True)
        embed.set_footer(text=f"รับออร์เดอร์แล้ว 🤗 • {get_thailand_time().strftime('%d/%m/%y, %H:%M')}")
        
        await ctx.send(embed=embed, view=PremiumDeliveryView(ctx.channel, "Premium Membership", amount, buyer))
        await update_main_channel()
        
    except ValueError as e:
        await ctx.send(f"❌ รูปแบบตัวเลขไม่ถูกต้อง: {e}\nตัวอย่าง: `1000`, `500+200`, `1000*2`, `5000/2`")
    except Exception as e:
        print(f"❌ Error in !odp: {e}")
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")


# ============ TICKET COMMANDS ============
@bot.command(name="tkd")
@admin_only()
async def tkd_cmd(ctx):
    """Close and delete ticket"""
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
        await ctx.send("🗑️ กำลังลบตั๋วนี้...")
        await save_ticket_transcript(channel, ctx.author)
        await asyncio.sleep(2)
        await channel.delete()
        print(f"✅ ลบตั๋ว {channel_name} โดย {ctx.author.name}")
        
    except Exception as e:
        print(f"❌ Error in tkd: {e}")
        traceback.print_exc()
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")


@bot.command()
@admin_only()
async def ty(ctx):
    """ส่งของและเพิ่ม SP ให้ลูกค้า"""
    global gamepass_stock, group_stock, premium_stock
    
    if not ctx.channel.name.startswith("ticket-") and not re.match(r'^\d{10}-\d+-[\w\u0E00-\u0E7F]+$', ctx.channel.name):
        await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะในตั๋วเท่านั้น", delete_after=5)
        return
    
    processing_msg = None
    
    try:
        processing_msg = await ctx.send("🔄 กำลังดำเนินการ...")
        
        # Find buyer
        buyer = None
        channel_name = ctx.channel.name
        
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
        
        if not buyer and re.match(r'^\d{10}-\d+-[\w\u0E00-\u0E7F]+$', channel_name):
            parts = channel_name.split('-')
            if len(parts) >= 3:
                username_part = parts[-1].lower()
                for member in ctx.guild.members:
                    if member.name.lower() == username_part or member.display_name.lower() == username_part:
                        buyer = member
                        break
        
        if not buyer and str(ctx.channel.id) in ticket_customer_data:
            customer_name = ticket_customer_data[str(ctx.channel.id)]
            if customer_name != "ไม่ระบุตัวตน":
                for member in ctx.guild.members:
                    if member.name == customer_name or member.display_name == customer_name:
                        buyer = member
                        break
        
        if not buyer and ctx.channel.id in ticket_activity:
            buyer_id = ticket_activity[ctx.channel.id].get('buyer_id')
            if buyer_id:
                buyer = ctx.guild.get_member(buyer_id)
        
        if not buyer:
            async for msg in ctx.channel.history(limit=50):
                if not msg.author.bot and msg.author != ctx.guild.me:
                    buyer = msg.author
                    break
        
        if buyer:
            await add_buyer_role(buyer, ctx.guild)
            print(f"✅ Found buyer: {buyer.name} (ID: {buyer.id})")
        
        # Get stored data
        robux_amount = ticket_robux_data.get(str(ctx.channel.id))
        customer_name = ticket_customer_data.get(str(ctx.channel.id))
        
        product_type = "Gamepass"
        price = 0
        delivery_image = None
        premium_type = None
        is_premium = False
        
        if ctx.channel.category and ctx.channel.category.id == PREMIUM_CATEGORY_ID:
            is_premium = True
            product_type = "Premium"
        
        # Extract from receipt
        async for msg in ctx.channel.history(limit=50):
            if msg.author == bot.user and msg.embeds:
                for embed in msg.embeds:
                    if embed.title and "คำสั่งซื้อสินค้า" in embed.title:
                        for field in embed.fields:
                            if field.name == f"💸 จำนวน{ROBUX_EMOJI}" and not is_premium:
                                try:
                                    robux_amount = int(field.value.replace(",", ""))
                                except:
                                    pass
                            elif field.name == "💰 ราคาตามเรท" and not is_premium:
                                try:
                                    price = int(float(field.value.replace(" บาท", "").replace(",", "")))
                                except:
                                    pass
                            elif field.name == "✨ สินค้า" and is_premium:
                                premium_type = field.value
                            elif field.name == "💰 ราคา" and is_premium:
                                try:
                                    price = int(float(field.value.replace(" บาท", "").replace(",", "")))
                                except:
                                    pass
                        
                        if embed.image and embed.image.url:
                            delivery_image = embed.image.url
                        
                        if "Gamepass" in embed.title:
                            product_type = "Gamepass"
                        elif "Group" in embed.title:
                            product_type = "Group"
                        elif "Premium" in embed.title:
                            product_type = "Premium"
                        
                        break
                if product_type:
                    break
        
        # Add SP to buyer
        if buyer:
            if is_premium:
                sp_amount = 5000
                await add_sp(buyer.id, sp_amount)
            elif robux_amount:
                await add_sp(buyer.id, int(robux_amount))
        
        # Create receipt
        receipt_color = 0xFFA500 if product_type == "Gamepass" else (0x00FFFF if product_type == "Group" else 0x9B59B6)
        
        anonymous_mode = ticket_anonymous_mode.get(str(ctx.channel.id), False)
        buyer_display = "ไม่ระบุตัวตน" if anonymous_mode else (buyer.mention if buyer else "ไม่ทราบ")
        
        receipt_embed = discord.Embed(
            title=f"🍣 ใบเสร็จการสั่งซื้อ ({product_type}) 🍣", 
            color=receipt_color
        )
        receipt_embed.add_field(name="😊 ผู้ซื้อ", value=buyer_display, inline=False)
        
        if is_premium:
            receipt_embed.add_field(name="✨ สินค้า", value=premium_type if premium_type else "Premium Membership", inline=True)
            receipt_embed.add_field(name="🎁 SP ที่ได้รับ", value="5000 SP", inline=True)
        else:
            receipt_embed.add_field(name=f"💸 จำนวน{ROBUX_EMOJI}", value=f"{format_number(robux_amount) if robux_amount else 0}", inline=True)
        
        price_int = round_price(price) if price > 0 else 0
        receipt_embed.add_field(name="💰 ราคาตามเรท", value=f"{format_number(price_int)} บาท" if price > 0 else "ไม่ระบุ", inline=True)
        
        if delivery_image:
            receipt_embed.set_image(url=delivery_image)
        
        receipt_embed.set_footer(text=f"จัดส่งสินค้าสำเร็จ 🤗 • {get_thailand_time().strftime('%d/%m/%y, %H:%M')}")
        
        # Send to log channel
        log_channel = bot.get_channel(SALES_LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(embed=receipt_embed)
        
        # Save transcript
        save_success, filename = await save_ticket_transcript(ctx.channel, buyer, robux_amount if not is_premium else price, customer_name)
        
        if save_success:
            try:
                await ctx.channel.edit(name=filename[:100])
            except:
                pass
        
        # Update stock
        if ctx.channel.category:
            category_name = ctx.channel.category.name.lower()
            if "gamepass" in category_name:
                async with bot.stock_lock:
                    gamepass_stock += 1
            elif "group" in category_name or "robux" in category_name:
                async with bot.stock_lock:
                    group_stock += 1
            elif ctx.channel.category.id == PREMIUM_CATEGORY_ID:
                async with bot.stock_lock:
                    premium_stock += 1
        
        save_stock_values()
        
        # Delete processing message
        if processing_msg:
            await processing_msg.delete()
        
        # Send success message
        embed = discord.Embed(
            title="✅ ส่งของเรียบร้อยแล้ว",
            description=(
                "**ขอบคุณที่ใช้บริการร้าน Sushi Shop** 🍣\n"
                "ฝากให้เครดิต +1 ให้ด้วยนะคะ ❤️\n\n"
                "⚠️ **หมายเหตุ:** ตั๋วนี้จะถูกลบใน 10 นาที"
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
        
        # Clean up
        if str(ctx.channel.id) in ticket_robux_data:
            del ticket_robux_data[str(ctx.channel.id)]
            save_json(ticket_robux_data_file, ticket_robux_data)
        
        if str(ctx.channel.id) in ticket_customer_data:
            del ticket_customer_data[str(ctx.channel.id)]
            save_json(ticket_customer_data_file, ticket_customer_data)
        
        # Move to delivered category and schedule removal
        await move_to_delivered_category(ctx.channel)
        await schedule_removal(ctx.channel, buyer, 600)
        await update_main_channel()
        
        print(f"✅ !ty completed for {ctx.channel.name}")
        
    except Exception as e:
        print(f"❌ Error in !ty: {e}")
        traceback.print_exc()
        if processing_msg:
            try:
                await processing_msg.delete()
            except:
                pass
        try:
            await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")
        except:
            pass


# ============ SETTINGS COMMANDS ============
@bot.command(name="setrate")
@admin_only()
async def set_rate_cmd(ctx):
    """ตั้งค่าเรทราคา"""
    view = EditRateView()
    embed = discord.Embed(
        title="💰 ตั้งค่าเรทราคา",
        description="กดปุ่มด้านล่างเพื่อแก้ไขเรท",
        color=0xFFA500
    )
    await ctx.send(embed=embed, view=view)


@bot.command(name="togglegroup")
@admin_only()
async def toggle_group_cmd(ctx):
    """เปิด/ปิด รับออเดอร์ Group"""
    global group_ticket_enabled
    group_ticket_enabled = not group_ticket_enabled
    save_stock_values()
    
    status = "เปิด" if group_ticket_enabled else "ปิด"
    embed = discord.Embed(
        title="✅ เปลี่ยนสถานะสำเร็จ",
        description=f"เปิดรับออเดอร์ Group: **{status}**",
        color=0x00FF00 if group_ticket_enabled else 0xFF0000
    )
    await ctx.send(embed=embed)
    await update_main_channel()


@bot.command(name="togglepremium")
@admin_only()
async def toggle_premium_cmd(ctx):
    """เปิด/ปิด รับออเดอร์ Premium"""
    global premium_ticket_enabled
    premium_ticket_enabled = not premium_ticket_enabled
    save_stock_values()
    
    status = "เปิด" if premium_ticket_enabled else "ปิด"
    embed = discord.Embed(
        title="✅ เปลี่ยนสถานะสำเร็จ",
        description=f"เปิดรับออเดอร์ Premium: **{status}**",
        color=0x00FF00 if premium_ticket_enabled else 0xFF0000
    )
    await ctx.send(embed=embed)
    await update_main_channel()


# ============ BACKGROUND TASKS ============
@tasks.loop(minutes=1)
async def update_presence():
    await bot.change_presence(activity=discord.Game(name="บอทเครื่องคิดเลขของ wforr | !help"))


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


@tasks.loop(minutes=10)
async def update_credit_channel_task():
    await check_credit_channel_changes()


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
    print(f"✅ บอทออนไลน์แล้ว: {bot.user} (ID: {bot.user.id})")
    
    await bot.change_presence(activity=discord.Game(name="บอทเครื่องคิดเลขของ wforr | !help"))
    
    print("\n📝 Registered commands:")
    for cmd in bot.commands:
        print(f"   - !{cmd.name}")
    
    print(f"\n📁 DATA_DIR: {DATA_DIR}")
    
    if os.path.exists(user_levels_file):
        file_size = os.path.getsize(user_levels_file)
        print(f"📊 user_levels.json exists, size: {file_size} bytes")
    else:
        print(f"📊 user_levels.json does not exist yet")
    
    try:
        print("🔄 กำลัง sync slash commands...")
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} commands")
        bot.commands_synced = True
    except Exception as e:
        print(f"❌ Error syncing commands: {e}")
    
    update_presence.start()
    save_data.start()
    save_data_frequent.start()
    hourly_backup.start()
    update_credit_channel_task.start()
    
    if not credit_channel_update_task_running:
        bot.loop.create_task(credit_channel_update_worker())
        print("✅ เริ่ม credit channel update worker")
    
    await update_channel_name()
    await update_main_channel()
    await update_credit_channel_name()
    
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
            
            await credit_channel_queue.put("new_message")
    
    await bot.process_commands(message)


@bot.event
async def on_message_delete(message):
    if message.channel.id == CREDIT_CHANNEL_ID:
        await asyncio.sleep(2)
        await credit_channel_queue.put("delete_message")


@bot.event
async def on_bulk_message_delete(messages):
    if messages and messages[0].channel.id == CREDIT_CHANNEL_ID:
        await asyncio.sleep(2)
        await credit_channel_queue.put(f"bulk_delete_{len(messages)}")


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


# ============ BOT SETUP ============
class SushiBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.stock_lock = asyncio.Lock()
        self.command_rate_limiter = RateLimiter(max_calls=1, period=1.0)
        self.commands_synced = False
    
    async def setup_hook(self):
        print("🔧 Setting up bot...")
        load_all_data()
        print("✅ Setup complete")


bot = SushiBot()


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
