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
gamepass_stock = 20000
group_stock = 25000

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
    5000: 1488073523946717356,
    10000: 1488073560030445569,
    25000: 1488073771662315614,
    50000: 1488073590162329640,
    100000: 1488073619543294153,
    555555: 1488075865337106563
}

# Level names
LEVEL_NAMES = {
    0: "🍣 | Sushi Lover",
    5000: "🐱 | Sushi Pass",
    10000: "😼 | Sushi Silver",
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
    global gamepass_stock, group_stock, gamepass_rate, group_rate_low, group_rate_high, shop_open, group_ticket_enabled
    stock_data = load_json(stock_file, {})
    if stock_data:
        gamepass_stock = stock_data.get("gamepass_stock", 20000)
        group_stock = stock_data.get("group_stock", 8500)
        gamepass_rate = stock_data.get("gamepass_rate", 6.5)
        group_rate_low = stock_data.get("group_rate_low", 4)
        group_rate_high = stock_data.get("group_rate_high", 4.5)
        shop_open = stock_data.get("shop_open", True)
        group_ticket_enabled = stock_data.get("group_ticket_enabled", True)

def save_stock_values():
    """Save stock values to JSON"""
    stock_data = {
        "gamepass_stock": gamepass_stock,
        "group_stock": group_stock,
        "gamepass_rate": gamepass_rate,
        "group_rate_low": group_rate_low,
        "group_rate_high": group_rate_high,
        "shop_open": shop_open,
        "group_ticket_enabled": group_ticket_enabled
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
    print(f"   - Stock: GP={gamepass_stock}, Group={group_stock}")

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
        print(f"   Please move bot's role above {new_role.name} in Server Settings → Roles")
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
    
    save_json(user_levels_file, user_levels)
    print(f"✅ Added {amount} SP to {user_id}: {old_sp} → {new_sp} SP")
    
    guild = None
    for g in bot.guilds:
        guild = g
        break
    
    if guild:
        member = guild.get_member(user_id)
        if member:
            await update_member_roles(member, new_sp, old_sp)
    
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

# ============ EXPRESSION EVALUATION FUNCTION (ADDED FOR CALCULATOR) ============
def evaluate_expression(expr: str) -> float:
    """
    Safely evaluate mathematical expression from user input.
    Supports +, -, *, /, and parentheses.
    """
    try:
        # Remove commas and spaces
        expr = expr.replace(",", "").replace(" ", "")
        
        # Replace x with * for multiplication
        expr = expr.lower().replace("x", "*")
        
        # Replace ÷ with / for division
        expr = expr.replace("÷", "/")
        
        # Check if expression contains only allowed characters
        allowed_chars = set("0123456789+-*/().")
        if not all(c in allowed_chars for c in expr):
            raise ValueError("Expression contains invalid characters")
        
        # Evaluate the expression
        result = eval(expr)
        
        # Convert to int if it's a whole number
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        
        # Check if result is positive
        if result < 0:
            raise ValueError("Result cannot be negative")
        
        return result
    except Exception as e:
        raise ValueError(f"Invalid expression: {str(e)}")

# ============ UPDATED VIEW CLASSES (CALCULATOR NOW SUPPORTS EXPRESSIONS) ============
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

# ============ UPDATED CALCULATOR MODALS (NOW SUPPORT EXPRESSIONS) ============
class GamepassCalculatorModal(Modal, title="🍣 คำนวณเกมพาส"):
    robux_amount = TextInput(
        label="จำนวนโรบัค",
        placeholder="พิมพ์ตัวเลขเช่น 500, 100+200, 1000x2",
        required=True,
        max_length=50
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Evaluate expression
            robux = evaluate_expression(self.robux_amount.value)
            robux = int(robux)
            
            if robux <= 0:
                await interaction.response.send_message("❌ กรุณากรอกจำนวนที่มากกว่า 0", ephemeral=True)
                return
            
            price = robux / gamepass_rate
            price_int = round_price(price)
            
            embed = discord.Embed(
                title=f"🎮 Gamepass {format_number(robux)} {ROBUX_EMOJI} = {format_number(price_int)} บาท (1 บาท = {gamepass_rate} {ROBUX_EMOJI})",
                color=0xFFA500
            )
            embed.add_field(name="📝 คำนวณ", value=f"`{self.robux_amount.value}`", inline=False)
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
            # Evaluate expression
            baht = evaluate_expression(self.baht_amount.value)
            baht = float(baht)
            
            if baht <= 0:
                await interaction.response.send_message("❌ กรุณากรอกจำนวนที่มากกว่า 0", ephemeral=True)
                return
            
            robux = int(baht * gamepass_rate)
            
            embed = discord.Embed(
                title=f"🎮 {format_number(int(baht))} บาท = {format_number(robux)} {ROBUX_EMOJI} (1 บาท = {gamepass_rate} {ROBUX_EMOJI})",
                color=0xFFA500
            )
            embed.add_field(name="📝 คำนวณ", value=f"`{self.baht_amount.value}`", inline=False)
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
            # Evaluate expression
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
            embed.add_field(name="📝 คำนวณ", value=f"`{self.robux_amount.value}`", inline=False)
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
            # Evaluate expression
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
            embed.add_field(name="📝 คำนวณ", value=f"`{self.baht_amount.value}`", inline=False)
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
        placeholder="พิมพ์ชื่อแมพ เช่น Gift Simulator", 
        required=True
    )
    gamepass_name = TextInput(
        label="💸 ชื่อเกมพาสอะไร?", 
        placeholder="พิมพ์ชื่อเกมพาส เช่น x3 Speed 3 ชิ้น", 
        required=True
    )
    robux_amount = TextInput(
        label="🎟 ราคาของเกมพาสเท่าไหร่บ้าง?", 
        placeholder="เช่น 300 หรือ 100+100+100 หรือ 100x3", 
        required=True
    )
    
    async def on_submit(self, i):
        global gamepass_rate
        
        try:
            if is_user_always_anonymous(i.user):
                ticket_anonymous_mode[str(i.channel.id)] = True
                ticket_customer_data[str(i.channel.id)] = "ไม่ระบุตัวตน"
                save_json(ticket_customer_data_file, ticket_customer_data)
            else:
                ticket_anonymous_mode[str(i.channel.id)] = False
            
            expr = self.robux_amount.value.lower().replace("x", "*").replace("÷", "/")
            if not re.match(r"^[\d\s\+\-\*\/\(\)]+$", expr):
                await i.response.send_message(
                    "❌ กรุณาใส่เฉพาะตัวเลข และเครื่องหมาย + - * / x ÷ ()", 
                    ephemeral=True
                )
                return
            
            robux = int(eval(expr))
            price = robux / gamepass_rate
            price_int = round_price(price)
            
            embed = discord.Embed(title="📨 รายละเอียดการสั่งซื้อ", color=0x00FF99)
            embed.add_field(name="🗺️ ชื่อแมพ", value=self.map_name.value, inline=False)
            embed.add_field(name="🎟 เกมพาส", value=self.gamepass_name.value, inline=False)
            embed.add_field(name=f"💸 ราคา{ROBUX_EMOJI}", value=f"{format_number(robux)}", inline=True)
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
            await i.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

class GroupTicketModal(Modal, title="📋 แบบฟอร์มสั่งซื้อ Robux Group"):
    user_name = TextInput(
        label="🪪 ชื่อในเกม", 
        placeholder="Username", 
        required=True
    )
    robux_amount = TextInput(
        label=f"💸 ต้องการซื้อกี่โรบัค ?", 
        placeholder="กรอกจำนวนโรบัคที่ต้องการ", 
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
            
            embed = discord.Embed(title="📨 รายละเอียดคำสั่งซื้อโรบัคกลุ่ม", color=0x00FF99)
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
    def __init__(self, channel, product_type, robux_amount, price, buyer):
        super().__init__(timeout=None)
        self.channel = channel
        self.product_type = product_type
        self.robux_amount = robux_amount
        self.price = price
        self.buyer = buyer
        self.delivered = False
        
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
                            await add_sp(self.buyer.id, self.robux_amount)
                            print(f"✅ Added {self.robux_amount} SP to {self.buyer.name}")
                    
                    receipt_color = 0xFFA500 if self.product_type == "Gamepass" else 0x00FFFF
                    
                    anonymous_mode = ticket_anonymous_mode.get(str(self.channel.id), False)
                    buyer_display = "ไม่ระบุตัวตน" if anonymous_mode else (self.buyer.mention if self.buyer else "ไม่ทราบ")
                    
                    receipt_embed = discord.Embed(
                        title=f"🍣 ใบเสร็จการสั่งซื้อ ({self.product_type}) 🍣", 
                        color=receipt_color
                    )
                    receipt_embed.add_field(name="😊 ผู้ซื้อ", value=buyer_display, inline=False)
                    receipt_embed.add_field(name=f"💸 จำนวน{ROBUX_EMOJI}", value=f"{format_number(self.robux_amount)}", inline=True)
                    price_int = round_price(self.price)
                    receipt_embed.add_field(name="💰 ราคาตามเรท", value=f"{format_number(price_int)} บาท", inline=True)
                    
                    if delivery_image:
                        receipt_embed.set_image(url=delivery_image)
                    
                    receipt_embed.set_footer(text=f"จัดส่งสินค้าสำเร็จ 🤗 • {get_thailand_time().strftime('%d/%m/%y, %H:%M')}")
                    
                    await self.channel.send(embed=receipt_embed)
                    
                    if self.buyer and not anonymous_mode:
                        try:
                            dm_embed = discord.Embed(
                                title=f"🧾 ใบเสร็จการซื้อสินค้า ({self.product_type})",
                                description="ขอบคุณที่ใช้บริการ Sushi Shop นะคะ 🍣",
                                color=receipt_color
                            )
                            dm_embed.add_field(name="📦 สินค้า", value=self.product_type, inline=True)
                            dm_embed.add_field(name=f"💸 จำนวน{ROBUX_EMOJI}", value=f"{format_number(self.robux_amount)}", inline=True)
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
        
        # Load all data from JSON
        load_all_data()
        
        # Create backup on startup
        backup_user_levels()
    
    async def setup_hook(self):
        print(f"✅ Setup hook completed")
    
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
    if str(channel_id) in ticket_removal_tasks:
        ticket_removal_tasks[str(channel_id)].cancel()
        del ticket_removal_tasks[str(channel_id)]
        print(f"✅ Cancelled removal timer for channel {channel_id}")
        return True
    return False

async def update_channel_name():
    try:
        channel = bot.get_channel(MAIN_CHANNEL_ID)
        if channel:
            new_name = "〔🟢เปิด〕กดสั่งซื้อห้องนี้" if shop_open else "〔🔴ปิดชั่วคราว〕"
            if channel.name != new_name:
                await bot.channel_edit_rate_limiter.acquire()
                await channel.edit(name=new_name)
                print(f"✅ เปลี่ยนชื่อช่องเป็น: {new_name}")
    except Exception as e:
        print(f"❌ Error updating channel name: {e}")

async def update_main_channel():
    try:
        channel = bot.get_channel(MAIN_CHANNEL_ID)
        if not channel:
            return
        
        embed = discord.Embed(title="🍣 Sushi Shop 🍣 เปิดให้บริการ", color=0xFFA500)
        embed.add_field(
            name=f"🎮 กดเกมพาส | 📦 Stock: {format_number(gamepass_stock)} {'🟢' if gamepass_stock > 0 else '🔴'}", 
            value=f"```เรท: {gamepass_rate}```", 
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
        
        if admin_role:
            await channel.send(content=f"{admin_role.mention} มีตั๋วใหม่!")
        
        embed = discord.Embed(
            title="🍣 Sushi Shop 🍣", 
            description="แจ้งแอดมินขอไม่ระบุตัวตนชื่อลูกค้าได้\n\nกรอกแบบฟอร์มเพื่อสั่งสินค้า", 
            color=0x00FF99
        )
        embed.add_field(name="👤 ผู้ซื้อ", value=interaction.user.mention, inline=False)
        
        if stock_type == "gamepass":
            embed.add_field(
                name="🎮 บริการกดเกมพาส", 
                value=f"📦 โรบัคคงเหลือ: **{format_number(gamepass_stock)}**\n💰 เรท: {gamepass_rate}", 
                inline=False
            )
        elif stock_type == "group":
            embed.add_field(
                name="👥 บริการเติมโรบัคกลุ่ม", 
                value=f"📦 โรบัคเหลือ: **{format_number(group_stock)}**\n💰 เรท: {group_rate_low} | 500 บาท+ เรท {group_rate_high}", 
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
            form_btn = Button(label="📝 กรอกแบบฟอร์มโรบัคกลุ่ม", style=discord.ButtonStyle.primary, emoji="📝")
            
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
                if admin_role and admin_role in i.user.roles:
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
        await asyncio.sleep(delay_seconds)
        
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
async def credit_channel_update_worker():
    global credit_channel_update_task_running
    credit_channel_update_task_running = True
    
    while not bot._shutdown_flag:
        try:
            change = await credit_channel_queue.get()
            
            channel = bot.get_channel(CREDIT_CHANNEL_ID)
            if not channel:
                print("❌ ไม่พบช่องเครดิต")
                credit_channel_queue.task_done()
                continue
            
            current_name = channel.name
            print(f"🔄 กำลังประมวลผล: {change} | ชื่อปัจจุบัน: {current_name}")
            
            try:
                if ":" in current_name:
                    parts = current_name.split(":")
                    if len(parts) >= 2:
                        current_count = int(parts[1].strip())
                        
                        if change == "new_message":
                            new_count = current_count + 1
                        elif change == "delete_message":
                            new_count = current_count - 1
                        elif change.startswith("bulk_delete_"):
                            delete_count = int(change.split("_")[2])
                            new_count = current_count - delete_count
                        else:
                            new_count = current_count
                        
                        new_name = f"☑️credit : {new_count}"
                        
                        if channel.name != new_name:
                            print(f"📊 เปลี่ยนจาก {current_count} เป็น {new_count}")
                            await bot.channel_edit_rate_limiter.acquire()
                            await channel.edit(name=new_name)
                            print(f"✅ อัพเดทชื่อเป็น: {new_name}")
                            
                            with open(os.path.join(DATA_DIR, "credit_message_count.txt"), "w") as f:
                                f.write(str(new_count))
                        else:
                            print(f"ℹ️ ชื่อยังคงเดิม: {new_name}")
                            
                        if credit_channel_queue.qsize() % 5 == 0:
                            print("🔍 ตรวจสอบความถูกต้อง...")
                            await asyncio.sleep(2)
                            await verify_credit_channel_count()
                else:
                    print(f"⚠️ รูปแบบชื่อไม่ถูกต้อง: {current_name}")
                    await verify_credit_channel_count()
                    
            except Exception as e:
                print(f"❌ Error ใน worker: {e}")
                await verify_credit_channel_count()
            
            credit_channel_queue.task_done()
            await asyncio.sleep(3)
            
        except Exception as e:
            print(f"❌ Credit channel worker error: {e}")
            await asyncio.sleep(5)

async def verify_credit_channel_count():
    try:
        channel = bot.get_channel(CREDIT_CHANNEL_ID)
        if not channel:
            return
        
        print("🔍 กำลังนับจำนวนข้อความจริง...")
        real_count = 0
        try:
            async for _ in channel.history(limit=None):
                real_count += 1
                if real_count >= 1000:
                    break
        except Exception as e:
            print(f"⚠️ ไม่สามารถนับข้อความได้: {e}")
            return
        
        current_name = channel.name
        if ":" in current_name:
            parts = current_name.split(":")
            if len(parts) >= 2:
                try:
                    current_count = int(parts[1].strip())
                    
                    if abs(real_count - current_count) > 5 or real_count >= 1000:
                        print(f"⚠️ ตัวเลขไม่ตรงกัน: ชื่อ={current_count}, จริง={real_count}")
                        
                        new_name = f"☑️credit : {real_count}"
                        if channel.name != new_name:
                            await bot.channel_edit_rate_limiter.acquire()
                            await channel.edit(name=new_name)
                            print(f"✅ แก้ไขชื่อเป็น: {new_name}")
                            
                            with open(os.path.join(DATA_DIR, "credit_message_count.txt"), "w") as f:
                                f.write(str(real_count))
                    else:
                        print(f"✅ ตัวเลขตรงกัน: {current_count}")
                except ValueError:
                    pass
    except Exception as e:
        print(f"❌ Error verifying count: {e}")

async def count_credit_channel_messages():
    try:
        credit_channel = bot.get_channel(CREDIT_CHANNEL_ID)
        if not credit_channel:
            return 0
        
        message_count = 0
        try:
            await bot.api_rate_limiter.acquire()
            
            last_id = None
            while True:
                try:
                    history_kwargs = {"limit": 100}
                    if last_id:
                        history_kwargs["before"] = discord.Object(id=last_id)
                    
                    async for message in credit_channel.history(**history_kwargs):
                        message_count += 1
                        last_id = message.id
                    
                    if message_count % 100 != 0:
                        break
                        
                    await asyncio.sleep(1)
                    
                except discord.HTTPException as e:
                    if e.status == 429:
                        retry_after = e.retry_after if hasattr(e, 'retry_after') else 5
                        print(f"⚠️ Rate limited รอ {retry_after} วินาที")
                        await asyncio.sleep(retry_after)
                        continue
                    else:
                        return 0
        except Exception as e:
            print(f"⚠️ ไม่สามารถนับข้อความได้: {e}")
            return 0
            
        print(f"📊 นับข้อความในช่องเครดิตได้: {message_count}")
        return message_count
        
    except Exception as e:
        print(f"❌ Error counting messages: {e}")
        return 0

async def update_credit_channel_name():
    try:
        async with credit_channel_update_lock:
            credit_channel = bot.get_channel(CREDIT_CHANNEL_ID)
            if not credit_channel:
                return
            
            message_count = await count_credit_channel_messages()
            new_name = f"☑️credit : {message_count}"
            
            if credit_channel.name != new_name:
                try:
                    await bot.channel_edit_rate_limiter.acquire()
                    await credit_channel.edit(name=new_name)
                    print(f"✅ เปลี่ยนชื่อช่องเครดิตเป็น: {new_name}")
                    
                    with open(os.path.join(DATA_DIR, "credit_message_count.txt"), "w") as f:
                        f.write(str(message_count))
                except Exception as e:
                    print(f"❌ ไม่สามารถเปลี่ยนชื่อได้: {e}")
    except Exception as e:
        print(f"❌ Error updating credit channel name: {e}")
        traceback.print_exc()

async def check_credit_channel_changes():
    try:
        current_count = await count_credit_channel_messages()
        
        last_count = 0
        try:
            count_file = os.path.join(DATA_DIR, "credit_message_count.txt")
            if os.path.exists(count_file):
                with open(count_file, "r") as f:
                    last_count = int(f.read().strip())
        except:
            pass
        
        if current_count != last_count:
            print(f"📊 จำนวนข้อความเปลี่ยนจาก {last_count} เป็น {current_count}")
            await update_credit_channel_name()
    except Exception as e:
        print(f"❌ Error checking credit channel: {e}")

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
    global gamepass_rate, group_rate_low, group_rate_high
    
    try:
        await ctx.message.delete()
    except:
        pass
    
    if rate_type is None:
        embed = discord.Embed(title="📊 เรทโรบัคปัจจุบัน", color=0x00FF99)
        embed.add_field(name="🎮 Gamepass Rate", value=f"**{gamepass_rate}**", inline=True)
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
        
    else:
        try:
            gamepass_rate = float(rate_type)
            save_stock_values()
            embed = discord.Embed(title="✅ เปลี่ยนเรทเกมพาสเรียบร้อย", description=f"ตั้งค่าเรทเกมพาสเป็น **{gamepass_rate}** เรียบร้อยแล้ว", color=0x00FF00)
            await ctx.send(embed=embed)
            await update_main_channel()
        except ValueError:
            await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)

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
        expr_clean = expr.replace(",", "").lower().replace("x", "*").replace("÷", "/")
        robux = int(eval(expr_clean))
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
        
        await ctx.send(embed=embed, view=DeliveryView(ctx.channel, "Gamepass", robux, price, buyer))
        await update_main_channel()
        
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
        expr_clean = expr.replace(",", "").lower().replace("x", "*").replace("÷", "/")
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
        
        await ctx.send(embed=embed, view=DeliveryView(ctx.channel, "Group", robux, price, buyer))
        await update_main_channel()
        
    except Exception as e:
        print(f"❌ Error in !odg: {e}")
        traceback.print_exc()
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")

# ============ DATA COMMANDS ============
@bot.command(name="savedata")
@admin_only()
async def save_data_cmd(ctx):
    """Manually save all data to disk"""
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

@bot.command(name="backupdata")
@admin_only()
async def backup_data_cmd(ctx):
    """Create backup of SP data"""
    await ctx.send("🔄 กำลังสร้าง backup...")
    backup_user_levels()
    await ctx.send("✅ สร้าง backup ข้อมูล SP เรียบร้อยแล้ว")

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
        for user_id_str, data in user_levels.items():
            try:
                member = ctx.guild.get_member(int(user_id_str))
                if member:
                    sp = data["sp"]
                    await update_member_roles(member, sp)
                    fixed_count += 1
                    await asyncio.sleep(0.5)
            except Exception as e:
                print(f"Error fixing roles for {user_id_str}: {e}")
        
        await ctx.send(f"✅ ซ่อมแซมบทบาทให้สมาชิก {fixed_count} คน เรียบร้อย")

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

@bot.command(name="tkd")
@admin_only()
async def tkd_cmd(ctx):
    """Close and delete ticket"""
    channel = ctx.channel
    channel_name = channel.name
    
    # Check if this is a ticket channel
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
        # Send confirmation message
        msg = await ctx.send("🗑️ กำลังลบตั๋วนี้...")
        
        # Save transcript before deleting
        await save_ticket_transcript(channel, ctx.author)
        
        # Wait a moment
        await asyncio.sleep(2)
        
        # Delete the channel
        await channel.delete()
        
        print(f"✅ ลบตั๋ว {channel_name} โดย {ctx.author.name}")
        
    except Exception as e:
        print(f"❌ Error in tkd: {e}")
        traceback.print_exc()
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")

# ============ TY COMMAND - FIXED ============
@bot.command()
@admin_only()
async def ty(ctx):
    """ส่งของและเพิ่ม SP ให้ลูกค้า"""
    global gamepass_stock, group_stock
    
    # ตรวจสอบว่าใช้ในช่องตั๋วหรือไม่
    if not ctx.channel.name.startswith("ticket-") and not re.match(r'^\d{10}-\d+-[\w\u0E00-\u0E7F]+$', ctx.channel.name):
        await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะในตั๋วเท่านั้น", delete_after=5)
        return
    
    processing_msg = None
    
    try:
        processing_msg = await ctx.send("🔄 กำลังดำเนินการ...")
        
        # หาผู้ซื้อ
        buyer = None
        channel_name = ctx.channel.name
        
        # วิธีที่ 1: จากข้อมูลที่บันทึกไว้
        if str(ctx.channel.id) in ticket_buyer_data:
            buyer_id = ticket_buyer_data[str(ctx.channel.id)].get("user_id")
            if buyer_id:
                buyer = ctx.guild.get_member(buyer_id)
                if buyer:
                    print(f"✅ Found buyer from stored data: {buyer.name}")
        
        # วิธีที่ 2: จากชื่อช่อง (ticket-username-userid)
        if not buyer and channel_name.startswith("ticket-"):
            parts = channel_name.split('-')
            if len(parts) >= 3:
                try:
                    user_id = int(parts[-1])
                    buyer = ctx.guild.get_member(user_id)
                    if buyer:
                        print(f"✅ Found buyer from ticket- format: {buyer.name}")
                except ValueError:
                    pass
        
        # วิธีที่ 3: จากชื่อไฟล์ transcript (ddmmyytime-amount-username)
        if not buyer and re.match(r'^\d{10}-\d+-[\w\u0E00-\u0E7F]+$', channel_name):
            parts = channel_name.split('-')
            if len(parts) >= 3:
                username_part = parts[-1].lower()
                for member in ctx.guild.members:
                    if member.name.lower() == username_part or member.display_name.lower() == username_part:
                        buyer = member
                        if buyer:
                            print(f"✅ Found buyer from filename format: {buyer.name}")
                            break
        
        # วิธีที่ 4: จากข้อมูลลูกค้าที่บันทึก
        if not buyer and str(ctx.channel.id) in ticket_customer_data:
            customer_name = ticket_customer_data[str(ctx.channel.id)]
            if customer_name != "ไม่ระบุตัวตน":
                for member in ctx.guild.members:
                    if member.name == customer_name or member.display_name == customer_name:
                        buyer = member
                        if buyer:
                            print(f"✅ Found buyer from customer data: {buyer.name}")
                            break
        
        # วิธีที่ 5: จากประวัติกิจกรรม
        if not buyer and ctx.channel.id in ticket_activity:
            buyer_id = ticket_activity[ctx.channel.id].get('buyer_id')
            if buyer_id:
                buyer = ctx.guild.get_member(buyer_id)
                if buyer:
                    print(f"✅ Found buyer from activity data: {buyer.name}")
        
        # วิธีที่ 6: จากประวัติข้อความ
        if not buyer:
            async for msg in ctx.channel.history(limit=50):
                if not msg.author.bot and msg.author != ctx.guild.me:
                    buyer = msg.author
                    if buyer:
                        print(f"✅ Found buyer from message history: {buyer.name}")
                        break
        
        # เพิ่มบทบาทผู้ซื้อ
        if buyer:
            await add_buyer_role(buyer, ctx.guild)
            print(f"✅ Found buyer: {buyer.name} (ID: {buyer.id})")
        else:
            print(f"⚠️ Could not find buyer for channel {ctx.channel.name}")
        
        # ดึงข้อมูลที่เก็บไว้
        robux_amount = ticket_robux_data.get(str(ctx.channel.id))
        customer_name = ticket_customer_data.get(str(ctx.channel.id))
        
        # ตรวจสอบประเภทสินค้า
        product_type = "Gamepass"
        price = 0
        delivery_image = None
        
        # ดึงข้อมูลจากใบเสร็จในแชท
        async for msg in ctx.channel.history(limit=50):
            if msg.author == bot.user and msg.embeds:
                for embed in msg.embeds:
                    if embed.title and "ใบเสร็จ" in embed.title:
                        for field in embed.fields:
                            if field.name == f"💸 จำนวน{ROBUX_EMOJI}":
                                try:
                                    robux_amount = int(field.value.replace(",", ""))
                                except:
                                    pass
                            elif field.name == "💰 ราคาตามเรท":
                                try:
                                    price = int(float(field.value.replace(" บาท", "").replace(",", "")))
                                except:
                                    pass
                        
                        if embed.image.url:
                            delivery_image = embed.image.url
                        
                        if "Gamepass" in embed.title:
                            product_type = "Gamepass"
                        elif "Group" in embed.title:
                            product_type = "Group"
                        
                        break
                if product_type:
                    break
        
        # สร้างใบเสร็จ
        receipt_color = 0xFFA500 if product_type == "Gamepass" else 0x00FFFF
        
        anonymous_mode = ticket_anonymous_mode.get(str(ctx.channel.id), False)
        buyer_display = "ไม่ระบุตัวตน" if anonymous_mode else (buyer.mention if buyer else "ไม่ทราบ")
        
        receipt_embed = discord.Embed(
            title=f"🍣 ใบเสร็จการสั่งซื้อ ({product_type}) 🍣", 
            color=receipt_color
        )
        receipt_embed.add_field(name="😊 ผู้ซื้อ", value=buyer_display, inline=False)
        receipt_embed.add_field(name=f"💸 จำนวน{ROBUX_EMOJI}", value=f"{format_number(robux_amount) if robux_amount else 0}", inline=True)
        price_int = round_price(price) if price > 0 else 0
        receipt_embed.add_field(name="💰 ราคาตามเรท", value=f"{format_number(price_int)} บาท" if price > 0 else "ไม่ระบุ", inline=True)
        
        if delivery_image:
            receipt_embed.set_image(url=delivery_image)
        
        receipt_embed.set_footer(text=f"จัดส่งสินค้าสำเร็จ 🤗 • {get_thailand_time().strftime('%d/%m/%y, %H:%M')}")
        
        # ส่งไปยังช่อง log
        log_channel = bot.get_channel(SALES_LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(embed=receipt_embed)
            print(f"✅ ส่งใบเสร็จไปยัง sales log channel เรียบร้อย")
        
        # บันทึก transcript
        save_success, filename = await save_ticket_transcript(ctx.channel, buyer, robux_amount, customer_name)
        
        if save_success:
            try:
                await ctx.channel.edit(name=filename[:100])
            except:
                pass
        
        # อัปเดตสต๊อก (เพิ่มกลับ)
        if ctx.channel.category:
            category_name = ctx.channel.category.name.lower()
            if "gamepass" in category_name:
                async with bot.stock_lock:
                    gamepass_stock += 1
            elif "group" in category_name or "robux" in category_name:
                async with bot.stock_lock:
                    group_stock += 1
        
        save_stock_values()
        
        # ลบข้อความกำลังดำเนินการ
        if processing_msg:
            await processing_msg.delete()
            processing_msg = None
        
        # ส่งข้อความสำเร็จ
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
        
        # เสนอให้สั่งเพิ่ม (เฉพาะเกมพาส)
        if product_type == "Gamepass" and buyer:
            order_more_view = View(timeout=None)
            order_more_btn = Button(label="สั่งของต่อ 📝", style=discord.ButtonStyle.secondary, emoji="🔄")
            
            async def order_more_cb(interaction):
                if interaction.channel.id != ctx.channel.id:
                    await interaction.response.send_message("❌ คุณไม่สามารถใช้ปุ่มนี้ในช่องอื่นได้", ephemeral=True)
                    return
                
                cancel_removal(ctx.channel.id)
                
                stock_type = "gamepass"
                
                if buyer:
                    await reset_channel_name(ctx.channel, buyer.id, stock_type)
                
                await move_to_original_category(ctx.channel, "gamepass")
                
                order_embed = discord.Embed(
                    title="🍣 Sushi Shop 🍣", 
                    description="แจ้งแอดมินขอไม่ระบุตัวตนชื่อลูกค้าได้\n\nกรอกแบบฟอร์มเพื่อสั่งสินค้า", 
                    color=0x00FF99
                )
                order_embed.add_field(name="👤 ผู้ซื้อ", value=interaction.user.mention, inline=False)
                order_embed.add_field(
                    name="🎮 บริการกดเกมพาส", 
                    value=f"📦 โรบัคคงเหลือ: **{format_number(gamepass_stock)}**\n💰 เรท: {gamepass_rate}", 
                    inline=False
                )
                order_embed.set_footer(text="Sushi Shop")
                order_embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/717757556889747657/1403684950770847754/noFilter.png")
                
                ticket_view = View(timeout=None)
                form_btn = Button(label="📝 กรอกแบบฟอร์มเกมพาส", style=discord.ButtonStyle.primary, emoji="📝")
                
                async def form_callback(interaction2):
                    if interaction2.channel.id == ctx.channel.id:
                        modal = GamepassTicketModal()
                        await interaction2.response.send_modal(modal)
                    else:
                        await interaction2.response.send_message("❌ คุณไม่สามารถใช้ปุ่มนี้ในช่องอื่นได้", ephemeral=True)
                
                form_btn.callback = form_callback
                ticket_view.add_item(form_btn)
                
                await interaction.response.send_message(embed=order_embed, view=ticket_view)
            
            order_more_btn.callback = order_more_cb
            order_more_view.add_item(order_more_btn)
            await ctx.send("📝 ต้องการสั่งสินค้าเพิ่ม?", view=order_more_view)
        
        # ล้างข้อมูลที่เก็บไว้
        if str(ctx.channel.id) in ticket_robux_data:
            del ticket_robux_data[str(ctx.channel.id)]
            save_json(ticket_robux_data_file, ticket_robux_data)
        
        if str(ctx.channel.id) in ticket_customer_data:
            del ticket_customer_data[str(ctx.channel.id)]
            save_json(ticket_customer_data_file, ticket_customer_data)
        
        # ย้ายไป category ส่งของแล้ว และตั้งเวลาลบ
        await move_to_delivered_category(ctx.channel)
        await schedule_removal(ctx.channel, buyer, 600)
        await update_main_channel()
        
        print(f"✅ คำสั่ง !ty ดำเนินการสำเร็จสำหรับห้อง {ctx.channel.name}")
        
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดใน !ty: {e}")
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

# ============ CALCULATOR COMMANDS ============
@bot.command(name="calculator")
async def calculator_cmd(ctx):
    try:
        embed = discord.Embed(
            title="🍣 เครื่องคิดเลข Sushi Shop",
            description="เลือกปุ่มด้านล่างเพื่อคำนวณราคา",
            color=0xFFA500
        )
        embed.add_field(name="🎮 เกมพาส", value=f"เรท {gamepass_rate}\n1 บาท = {gamepass_rate} {ROBUX_EMOJI}", inline=True)
        embed.add_field(name="👥 โรกลุ่ม", value=f"เรท {group_rate_low} (ต่ำกว่า 500 บาท)\nเรท {group_rate_high} (500 บาทขึ้นไป)", inline=True)
        embed.set_image(url="https://media.discordapp.net/attachments/1485285161955360963/1485285565761847417/image.png")
        embed.set_footer(text="Sushi Shop 🍣")
        
        view = CalculatorView()
        await ctx.send(embed=embed, view=view)
    except Exception as e:
        print(f"❌ Error in calculator command: {e}")
        await ctx.send("❌ เกิดข้อผิดพลาดในการแสดงเครื่องคิดเลข")

@bot.command()
async def gp(ctx, *, expr):
    global gamepass_rate
    try:
        expr_clean = expr.replace(",", "").lower().replace("x", "*").replace("÷", "/")
        robux = int(eval(expr_clean))
        price = robux / gamepass_rate
        price_int = round_price(price)
        await ctx.send(f"🎮 Gamepass {format_number(robux)} {ROBUX_EMOJI} = **{format_number(price_int)} บาท** (เรท {gamepass_rate})")
    except:
        await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)

@bot.command()
async def g(ctx, *, expr):
    global group_rate_low, group_rate_high
    try:
        expr_clean = expr.replace(",", "").lower().replace("x", "*").replace("÷", "/")
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
        await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)

@bot.command()
async def gpb(ctx, *, expr):
    global gamepass_rate
    try:
        baht = float(eval(expr.replace(",", "")))
        await ctx.send(f"🎮 {format_number(int(baht))} บาท = **{format_number(int(baht * gamepass_rate))} {ROBUX_EMOJI}** (Gamepass เรท {gamepass_rate})")
    except:
        await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)

@bot.command()
async def gb(ctx, *, expr):
    global group_rate_low, group_rate_high
    try:
        baht = float(eval(expr.replace(",", "")))
        
        if baht >= 500:
            rate = group_rate_high
            rate_text = f"เรท {group_rate_high} (500 บาทขึ้นไป)"
        else:
            rate = group_rate_low
            rate_text = f"เรท {group_rate_low} (ต่ำกว่า 500 บาท)"
        
        robux = int(baht * rate)
        await ctx.send(f"👥 {format_number(int(baht))} บาท = **{format_number(robux)} {ROBUX_EMOJI}** ({rate_text})")
    except Exception as e:
        await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)

@bot.command()
async def tax(ctx, *, expr):
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

@bot.command()
async def love(ctx):
    await ctx.send("# LOVE YOU<:sushiheart:1410484970291466300>")

@bot.command()
async def say(ctx, *, message):
    await ctx.send(f"# {message.upper()} <:sushiheart:1410484970291466300>")

@bot.command()
async def qr(ctx):
    try:
        await ctx.message.delete()
    except:
        pass
    
    embed = discord.Embed(title="⚠️โน๊ตสลิป: เติมโรบัค Sushi Shop เฟส Arisara Srijitjam", color=0x00CCFF)
    embed.add_field(name="1. ชื่อบัญชี (ไทยพานิชย์ SCB)", value="**หจก. วอเตอร์ เทค เซลล์ แอนด์ เซอร์วิส**", inline=False)
    embed.add_field(name="2. เลขบัญชี", value="**120-239181-3**", inline=False)
    embed.set_image(url="https://media.discordapp.net/attachments/1361004239043821610/1475334379550281768/Sushi_SCB_3.png")
    
    view = View(timeout=None)
    copy_btn = Button(label="คัดลอกเลขบัญชี", style=discord.ButtonStyle.success, emoji="📋")
    
    async def copy_cb(i):
        await i.response.send_message(f"``` 1202391813| 🟣SCB⚠️โน๊ตสลิป: เติมโรบัค Sushi Shop เฟส Arisara Srijitjam```", ephemeral=True)
    
    copy_btn.callback = copy_cb
    view.add_item(copy_btn)
    
    await ctx.send(embed=embed, view=view)

@bot.command()
async def qr2(ctx):
    try:
        await ctx.message.delete()
    except:
        pass
    
    embed = discord.Embed(title="⚠️โน๊ตสลิป: เติมโรบัค Sushi Shop เฟส Can pattarapol", color=0x00CCFF)
    embed.add_field(name="1. ชื่อบัญชี (กรุงศรี)", value="**สุทัตตา เถลิงสุข**", inline=False)
    embed.set_image(url="https://media.discordapp.net/attachments/1485285161955360963/1487457449416982568/Can_Can-1.png")
    
    await ctx.send(embed=embed)

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
    
    # Print all commands
    print("\n📝 Registered commands:")
    for cmd in bot.commands:
        print(f"   - !{cmd.name}")
    
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
