import os, datetime, discord, re, asyncio, json, traceback, time, aiohttp, logging
import random
import math
import signal
import sys
from discord.ext import commands, tasks
from discord.ui import View, Button, Modal, TextInput, Select
from discord import app_commands
from flask import Flask, jsonify
from threading import Thread
from typing import Dict, List, Optional, Tuple

# ==================== CONFIG ====================
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
    def get_thailand_time(): return datetime.datetime.now(pytz.timezone('Asia/Bangkok'))
except:
    def get_thailand_time(): return datetime.datetime.utcnow() + datetime.timedelta(hours=7)

# ==================== GLOBALS ====================
intents = discord.Intents.all()
intents.message_content = True
gamepass_rate = 6
group_rate_low = 4
group_rate_high = 4.5
shop_open = True
group_ticket_enabled = True
gamepass_stock = 4999
group_stock = 8500

# Channel IDs
MAIN_CHANNEL_ID = 1475342278976606229
SALES_LOG_CHANNEL_ID = 1475344141419417612
CREDIT_CHANNEL_ID = 1475343873684406353
DELIVERED_CATEGORY_ID = 1475345768037482662
ARCHIVED_CATEGORY_ID = 1485235427500753059
BUYER_ROLE_ID = 1475346221605588992

# Files
user_data_file = "user_data.json"
ticket_transcripts_file = "ticket_transcripts.json"
ticket_counter_file = "ticket_counter.json"
ticket_robux_data_file = "ticket_robux_data.json"
ticket_customer_data_file = "ticket_customer_data.json"
stock_file = "stock_values.json"

user_data = {}
ticket_transcripts = {}
ticket_robux_data = {}
ticket_customer_data = {}
user_notes = {}
ticket_activity = {}

# Anonymous mode tracking per ticket
ticket_anonymous_mode = {}

# ==================== CREDIT CHANNEL QUEUE SYSTEM ====================
credit_channel_queue = asyncio.Queue()
credit_channel_update_task_running = False

# ==================== CREDIT CHANNEL VARIABLES ====================
credit_channel_last_update = 0
credit_channel_update_lock = asyncio.Lock()

# ==================== FILE HANDLERS ====================
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
        with open(file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"❌ Error saving {file}: {e}")
        return False

# ==================== STOCK SAVE/LOAD FUNCTIONS ====================
def save_stock_values():
    """Save current stock values to a file"""
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

def load_stock_values():
    """Load stock values from file"""
    global gamepass_stock, group_stock, gamepass_rate, group_rate_low, group_rate_high, shop_open, group_ticket_enabled
    stock_data = load_json(stock_file, {})
    if stock_data:
        gamepass_stock = stock_data.get("gamepass_stock", 4999)
        group_stock = stock_data.get("group_stock", 8500)
        gamepass_rate = stock_data.get("gamepass_rate", 6)
        group_rate_low = stock_data.get("group_rate_low", 4)
        group_rate_high = stock_data.get("group_rate_high", 4.5)
        shop_open = stock_data.get("shop_open", True)
        group_ticket_enabled = stock_data.get("group_ticket_enabled", True)
        print(f"✅ Loaded stock values from {stock_file}")

# ==================== SAVE ALL DATA FUNCTIONS ====================
async def save_all_data():
    """Save all bot data to JSON files"""
    save_json(user_data_file, user_data)
    save_json(ticket_transcripts_file, ticket_transcripts)
    save_json(ticket_robux_data_file, ticket_robux_data)
    save_json(ticket_customer_data_file, ticket_customer_data)
    save_stock_values()
    print(f"✅ All data saved at {get_thailand_time().strftime('%H:%M:%S')}")

def save_all_data_sync():
    """Sync version of save_all_data for shutdown handler"""
    save_json(user_data_file, user_data)
    save_json(ticket_transcripts_file, ticket_transcripts)
    save_json(ticket_robux_data_file, ticket_robux_data)
    save_json(ticket_customer_data_file, ticket_customer_data)
    save_stock_values()
    print("✅ All data saved (sync)")

# ==================== RATE LIMITER ====================
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

# ==================== CALCULATOR VIEW ====================
class CalculatorView(View):
    def __init__(self):
        super().__init__(timeout=None)
        
        # Add buttons
        gamepass_btn = Button(label="คำนวณเกมพาส", style=discord.ButtonStyle.primary, emoji="🎮")
        group_btn = Button(label="คำนวณโรกลุ่ม", style=discord.ButtonStyle.primary, emoji="👥")
        
        gamepass_btn.callback = self.gamepass_callback
        group_btn.callback = self.group_callback
        
        self.add_item(gamepass_btn)
        self.add_item(group_btn)
    
    async def gamepass_callback(self, interaction: discord.Interaction):
        """Show gamepass calculation form"""
        modal = GamepassCalculatorModal()
        await interaction.response.send_modal(modal)
    
    async def group_callback(self, interaction: discord.Interaction):
        """Show group calculation form"""
        modal = GroupCalculatorModal()
        await interaction.response.send_modal(modal)

class GamepassCalculatorModal(Modal, title="📊 คำนวณเกมพาส"):
    robux_amount = TextInput(
        label="จำนวน Robux",
        placeholder="พิมพ์เฉพาะตัวเลขเช่น 1000 หรือ 1,000",
        required=True,
        max_length=20
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Parse number (handle commas)
            amount_str = self.robux_amount.value.replace(",", "").strip()
            robux = int(amount_str)
            
            # Calculate price
            price = robux / 6  # Gamepass rate 6
            price_int = int(price)
            
            # Create embed with dynamic title showing calculation result
            embed = discord.Embed(
                title=f"🎮 Gamepass {format_number(robux)} Robux = {format_number(price_int)} บาท (เรท 6)",
                color=0xFFA500  # Orange color matching embedshop
            )
            embed.set_image(url="https://media.discordapp.net/attachments/1485285161955360963/1485285565761847417/image.png?ex=69c14f7a&is=69bffdfa&hm=33e4caba94fa708df0babfaf5aaf19437bf3d109012f88c11e226a40077c91f2&=&format=webp&quality=lossless&width=825&height=440")
            embed.set_footer(text="Sushi Shop 🍣")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except ValueError:
            await interaction.response.send_message("❌ กรุณาพิมพ์เฉพาะตัวเลข เช่น 1000 หรือ 1,000", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

class GroupCalculatorModal(Modal, title="📊 คำนวณโรกลุ่ม"):
    robux_amount = TextInput(
        label="จำนวน Robux",
        placeholder="พิมพ์เฉพาะตัวเลขเช่น 1000 หรือ 1,000",
        required=True,
        max_length=20
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Parse number (handle commas)
            amount_str = self.robux_amount.value.replace(",", "").strip()
            robux = int(amount_str)
            
            # Calculate price (using rate 4 for under 500 baht)
            price = robux / 4  # Group rate 4 for under 500 baht
            price_baht = int(price)
            
            # Determine rate message based on price
            if price_baht >= 500:
                rate_message = "เรท 4.5 (500 บาทขึ้นไป)"
            else:
                rate_message = "เรท 4 (ต่ำกว่า 500 บาท)"
            
            # Create embed
            embed = discord.Embed(
                title=f"👥 Group {format_number(robux)} Robux = {format_number(price_baht)} บาท ({rate_message})",
                color=0xFFA500  # Orange color matching embedshop
            )
            embed.set_footer(text="Sushi Shop 🍣")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except ValueError:
            await interaction.response.send_message("❌ กรุณาพิมพ์เฉพาะตัวเลข เช่น 1000 หรือ 1,000", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

# ==================== EMBEDSHOP VIEW ====================
class EmbedShopView(View):
    def __init__(self):
        super().__init__(timeout=None)
        
        # Add buttons (disabled if needed)
        gamepass_btn = Button(label="กดเกมพาส", style=discord.ButtonStyle.success, emoji="🎮")
        group_btn = Button(label="เติมโรกลุ่ม", style=discord.ButtonStyle.success, emoji="👥")
        notes_btn = Button(label="จดวันที่เข้ากลุ่ม", style=discord.ButtonStyle.secondary, emoji="📝")
        
        async def gamepass_cb(i):
            await handle_open_ticket(i, "🍣Sushi Gamepass 🍣", "gamepass")
        
        async def group_cb(i):
            await handle_open_ticket(i, "💰Robux Group💰", "group")
        
        async def notes_cb(i):
            await i.response.send_modal(PersonalNoteModal())
        
        gamepass_btn.callback = gamepass_cb
        group_btn.callback = group_cb
        notes_btn.callback = notes_cb
        
        self.add_item(gamepass_btn)
        self.add_item(group_btn)
        self.add_item(notes_btn)

# ==================== BOT CLASS ====================
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        self.last_update_time = 0
        self.is_reacting_to_credit_channel = False
        self.commands_synced = False
        self.stock_lock = asyncio.Lock()
        self.api_rate_limiter = RateLimiter()
        self.react_rate_limiter = RateLimiter(1, 0.5)
        self.channel_edit_rate_limiter = RateLimiter(1, 5)
        self.command_rate_limiter = RateLimiter(1, 2)
        self.ticket_counter = load_json(ticket_counter_file, {"counter": 1, "date": get_thailand_time().strftime("%d%m%y")})
        self.stock_message = None
        self.main_channel_message = None
        self._shutdown_flag = False
        
        # Load all data on startup
        self.load_all_data()
    
    def load_all_data(self):
        """Load all data from JSON files"""
        global user_data, ticket_transcripts, ticket_robux_data, ticket_customer_data
        
        # Load user data
        user_data = load_json(user_data_file, {})
        ticket_transcripts = load_json(ticket_transcripts_file, {})
        ticket_robux_data = load_json(ticket_robux_data_file, {})
        ticket_customer_data = load_json(ticket_customer_data_file, {})
        
        # Load stock values
        load_stock_values()
        
        print(f"✅ Loaded all data:")
        print(f"   - {len(user_data)} users")
        print(f"   - {len(ticket_transcripts)} tickets")
        print(f"   - Stock: GP={gamepass_stock}, Group={group_stock}")
        print(f"   - Rates: GP={gamepass_rate}, Group={group_rate_low}-{group_rate_high}")
    
    async def setup_hook(self):
        global user_data, ticket_transcripts, ticket_robux_data, ticket_customer_data
        print(f"✅ Setup hook completed")
    
    async def close(self):
        """Override close method to save data"""
        print("\n⚠️ กำลังปิดระบบอย่างปลอดภัย...")
        print("💾 กำลังบันทึกข้อมูลทั้งหมด...")
        
        # Save all data
        save_all_data_sync()
        
        print("✅ บันทึกข้อมูลเรียบร้อย!")
        print("👋 ลาก่อน!")
        
        await super().close()

bot = MyBot()

# ==================== UTILITY FUNCTIONS ====================
def get_next_ticket_number():
    current_date = get_thailand_time().strftime("%d%m%y")
    if bot.ticket_counter["date"] != current_date:
        bot.ticket_counter = {"counter": 1, "date": current_date}
    else:
        bot.ticket_counter["counter"] += 1
    save_json(ticket_counter_file, bot.ticket_counter)
    return bot.ticket_counter["counter"]

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

def format_number(num: int) -> str:
    """Format number with commas for thousands"""
    return f"{num:,}"

# ==================== NEW COMMANDS ====================

@bot.command(name="calculator")
async def calculator_cmd(ctx):
    """แสดงเครื่องคิดเลขคำนวณเรท (Gamepass และ Group)"""
    embed = discord.Embed(
        title="🧮 เครื่องคิดเลข Sushi Shop",
        description="เลือกปุ่มด้านล่างเพื่อคำนวณราคา",
        color=0xFFA500  # Orange color matching embedshop
    )
    embed.add_field(
        name="🎮 เกมพาส",
        value=f"เรท {gamepass_rate}\n1 Robux = {gamepass_rate} บาท",
        inline=True
    )
    embed.add_field(
        name="👥 โรกลุ่ม",
        value=f"เรท {group_rate_low} (ต่ำกว่า 500 บาท)\nเรท {group_rate_high} (500 บาทขึ้นไป)",
        inline=True
    )
    embed.set_image(url="https://media.discordapp.net/attachments/1485285161955360963/1485285565761847417/image.png?ex=69c14f7a&is=69bffdfa&hm=33e4caba94fa708df0babfaf5aaf19437bf3d109012f88c11e226a40077c91f2&=&format=webp&quality=lossless&width=825&height=440")
    embed.set_footer(text="Sushi Shop 🍣")
    
    view = CalculatorView()
    await ctx.send(embed=embed, view=view)

@bot.command(name="embedshop")
async def embedshop_cmd(ctx):
    """แสดง embed ร้านค้า"""
    embed = discord.Embed(
        title="🍣 Sushi Shop 🍣 เปิดให้บริการ",
        color=0xFFA500
    )
    embed.add_field(
        name=f"🎮 กดเกมพาส | 📊 Stock: {format_number(gamepass_stock)} {'🟢' if gamepass_stock > 0 else '🔴'}",
        value=f"เรท: {gamepass_rate}\nเช็คราคาพิมพ์: !gp <จำนวน>",
        inline=False
    )
    embed.add_field(
        name=f"👥 โรบัคกลุ่ม | 📊 Stock: {format_number(group_stock)} {'🟢' if group_stock > 0 else '🔴'}",
        value=f"เรท: {group_rate_low} | 500 บาท+ เรท {group_rate_high}\n⚠️เข้ากลุ่ม 15 วันก่อนซื้อ⚠️",
        inline=False
    )
    embed.add_field(
        name="🏪 สถานะร้าน",
        value=f"{'🟢 เปิด' if shop_open else '🔴 ปิดชั่วคราว'}",
        inline=False
    )
    # Updated image URL
    embed.set_image(url="https://media.discordapp.net/attachments/1485285161955360963/1485294818740404405/file_000000005b0c71fa89058cca4be5a881.png?ex=69c15818&is=69c00698&hm=1b0e3bd767dbe260fae388f1ec80adc9a3c895ecb75d7264dbc575b5d0b71678&=&format=webp&quality=lossless&width=788&height=525")
    embed.set_footer(
        text=f"Sushi Shop • รับกดเกมพาสและอื่น ๆ | อัปเดตล่าสุด: {get_thailand_time().strftime('%d/%m/%y %H:%M')}",
        icon_url="https://media.discordapp.net/attachments/717757556889747657/1403684950770847754/noFilter.png"
    )
    embed.set_thumbnail(url="https://media.discordapp.net/attachments/717757556889747657/1403684950770847754/noFilter.png")
    
    view = EmbedShopView()
    await ctx.send(embed=embed, view=view)

# ==================== HELP COMMAND (UPDATED) ====================
@bot.command(name="help")
async def help_command(ctx, command_name: str = None):
    """แสดงวิธีการใช้คำสั่งต่างๆ"""
    if command_name:
        # แสดงรายละเอียดคำสั่งเฉพาะ
        await show_command_help(ctx, command_name)
    else:
        # แสดงรายการคำสั่งทั้งหมด
        embed = discord.Embed(
            title="📚 Sushi Shop Bot Help",
            description="ยินดีต้อนรับสู่ Sushi Shop Bot! นี่คือคำสั่งทั้งหมดที่คุณสามารถใช้ได้",
            color=0x00AAFF
        )
        
        # คำสั่งทั่วไป
        general_commands = (
            "`!help` - แสดงเมนูช่วยเหลือนี้\n"
            "`!help [คำสั่ง]` - แสดงรายละเอียดคำสั่งเฉพาะ\n"
            "`!calculator` - แสดงเครื่องคิดเลขคำนวณเรท\n"
            "`!embedshop` - แสดง embed ร้านค้า\n"
            "`!link` - แสดงลิงก์กลุ่ม Roblox\n"
            "`!qr` - แสดง QR code สำหรับโอนเงิน\n"
            "`!love` - ส่งความรักให้บอท 💕\n"
            "`!say <ข้อความ>` - ให้บอทพูดตาม"
        )
        embed.add_field(name="📌 คำสั่งทั่วไป", value=general_commands, inline=False)
        
        # คำสั่งคำนวณ
        calc_commands = (
            "`!gp <จำนวน>` - คำนวณราคา Gamepass (บาท)\n"
            "`!g <จำนวน>` - คำนวณราคา Group (บาท)\n"
            "`!gpb <จำนวน>` - คำนวณ Gamepass จากบาท\n"
            "`!gb <จำนวน>` - คำนวณ Group จากบาท\n"
            "`!tax <จำนวน>` - คำนวณภาษี 30%"
        )
        embed.add_field(name="🧮 คำสั่งคำนวณ", value=calc_commands, inline=False)
        
        # คำสั่งแอดมิน (ซ่อน)
        if ctx.author.guild_permissions.administrator:
            admin_commands = (
                "`!open` / `!close` - เปิด/ปิดร้าน\n"
                "`!shop_open` / `!shop_close` - เปิด/ปิดร้าน\n"
                "`!stock [gp/group] [จำนวน]` - ดู/ตั้งค่า stock\n"
                "`!group [on/off]` - เปิด/ปิด Group ticket\n"
                "`!rate [group/low/high]` - ดู/ตั้งค่าเรท\n"
                "`!annoymous` / `!annoymous_off` - เปิด/ปิดโหมดไม่ระบุตัวตน\n"
                "`!tkd` - ลบตั๋ว (ใช้ในห้องตั๋ว)\n"
                "`!ty` / `!vouch` - ปิดตั๋วและส่งของ\n"
                "`!od` / `!odg` - รับออร์เดอร์ Gamepass/Group\n"
                "`!saveall` - บันทึกข้อมูลทั้งหมด\n"
                "`!setup` - ตั้งค่าระบบ\n"
                "`!restart` - รีสตาร์ทปุ่ม\n"
                "`!sync` - Sync Slash Commands"
            )
            embed.add_field(name="👑 คำสั่งแอดมิน", value=admin_commands, inline=False)
        
        embed.set_footer(text="พิมพ์ !help <คำสั่ง> เพื่อดูรายละเอียดเพิ่มเติม")
        await ctx.send(embed=embed)

async def show_command_help(ctx, command_name: str):
    """แสดงรายละเอียดของคำสั่งเฉพาะ"""
    commands_info = {
        "calculator": {
            "description": "แสดงเครื่องคิดเลขสำหรับคำนวณราคาเกมพาสและโรกลุ่ม",
            "usage": "!calculator",
            "example": "!calculator",
            "note": "มีปุ่มให้เลือกคำนวณเกมพาสและโรกลุ่ม"
        },
        "embedshop": {
            "description": "แสดง embed ร้านค้าพร้อมปุ่มกดเปิดตั๋ว",
            "usage": "!embedshop",
            "example": "!embedshop",
            "note": "แสดง stock และสถานะร้านปัจจุบัน"
        },
        "gp": {
            "description": "คำนวณราคา Gamepass จากจำนวน Robux",
            "usage": "!gp <จำนวน>",
            "example": "!gp 1000",
            "note": "แสดงราคาเป็นบาทตามเรทปัจจุบัน"
        },
        "g": {
            "description": "คำนวณราคา Group จากจำนวน Robux",
            "usage": "!g <จำนวน>",
            "example": "!g 1000",
            "note": "แสดงราคาเป็นบาทตามเรทปัจจุบัน (500 บาทขึ้นไปได้เรทพิเศษ)"
        },
        "gpb": {
            "description": "คำนวณจำนวน Robux Gamepass จากจำนวนบาท",
            "usage": "!gpb <จำนวน>",
            "example": "!gpb 500",
            "note": "แสดงจำนวน Robux ที่จะได้รับตามเรทปัจจุบัน"
        },
        "gb": {
            "description": "คำนวณจำนวน Robux Group จากจำนวนบาท",
            "usage": "!gb <จำนวน>",
            "example": "!gb 500",
            "note": "แสดงจำนวน Robux ที่จะได้รับตามเรทปัจจุบัน"
        },
        "tax": {
            "description": "คำนวณจำนวน Robux หลังจากหักภาษี",
            "usage": "!tax <จำนวน> หรือ !tax <จำนวน>-<เปอร์เซ็น>%",
            "example": "!tax 1000 หรือ !tax 1000-30%",
            "note": "ถ้าไม่ระบุเปอร์เซ็น จะหัก 30% อัตโนมัติ"
        },
        "annoymous": {
            "description": "เปิดโหมดไม่ระบุตัวตนในตั๋ว",
            "usage": "!annoymous",
            "note": "ใช้ในห้องตั๋วเท่านั้น จะซ่อนชื่อผู้ซื้อในใบเสร็จ"
        },
        "annoymous_off": {
            "description": "ปิดโหมดไม่ระบุตัวตนในตั๋ว",
            "usage": "!annoymous_off",
            "note": "ใช้ในห้องตั๋วเท่านั้น จะแสดงชื่อผู้ซื้อในใบเสร็จ"
        },
        "tkd": {
            "description": "ลบห้องตั๋ว",
            "usage": "!tkd",
            "note": "ใช้ในห้องตั๋วเท่านั้น รูปแบบห้อง: ticket-... หรือ [ddmmyytime-amount-user]"
        },
        "stock": {
            "description": "ดูหรือตั้งค่า stock สินค้า (เฉพาะแอดมิน)",
            "usage": "!stock หรือ !stock gp <จำนวน> หรือ !stock group <จำนวน>",
            "example": "!stock gp 1000",
            "note": "ถ้าไม่ระบุจำนวนจะแสดง stock ปัจจุบัน"
        },
        "rate": {
            "description": "ดูหรือตั้งค่าเรท (เฉพาะแอดมิน)",
            "usage": "!rate หรือ !rate group <low> <high> หรือ !rate <ค่า>",
            "example": "!rate group 4 4.5 หรือ !rate 6",
            "note": "!rate เฉยๆ แสดงเรทปัจจุบัน"
        }
    }
    
    if command_name in commands_info:
        info = commands_info[command_name]
        embed = discord.Embed(
            title=f"📖 วิธีใช้คำสั่ง !{command_name}",
            description=info["description"],
            color=0x00AAFF
        )
        embed.add_field(name="วิธีการใช้", value=f"`{info['usage']}`", inline=False)
        if "example" in info:
            embed.add_field(name="ตัวอย่าง", value=f"`{info['example']}`", inline=False)
        if "note" in info:
            embed.add_field(name="หมายเหตุ", value=info["note"], inline=False)
        
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"❌ ไม่พบคำสั่ง `{command_name}`")

# ==================== CHANNEL NAME UPDATE ====================
async def update_channel_name():
    try:
        channel = bot.get_channel(MAIN_CHANNEL_ID)
        if channel:
            new_name = "〔🟢เปิด〕กดสั่งซื้อที่นี่" if shop_open else "〔🔴ปิดชั่วคราว〕"
            if channel.name != new_name:
                await bot.channel_edit_rate_limiter.acquire()
                await channel.edit(name=new_name)
                print(f"✅ เปลี่ยนชื่อช่องเป็น: {new_name}")
    except Exception as e:
        print(f"❌ Error updating channel name: {e}")

# ==================== MAIN CHANNEL UPDATE ====================
async def update_main_channel():
    try:
        channel = bot.get_channel(MAIN_CHANNEL_ID)
        if not channel:
            return
        
        embed = discord.Embed(title="🍣 Sushi Shop 🍣 เปิดให้บริการ", color=0xFFA500)
        embed.add_field(
            name=f"🎮 กดเกมพาส | 📊 Stock: {format_number(gamepass_stock)} {'🟢' if gamepass_stock > 0 else '🔴'}", 
            value=f"```\nเรท: {gamepass_rate} \nเช็คราคาพิมพ์: !gp <จำนวน>\n```", 
            inline=False
        )
        embed.add_field(
            name=f"👥 โรบัคกลุ่ม | 📊 Stock: {format_number(group_stock)} {'🟢' if group_stock > 0 else '🔴'}", 
            value=f"```\nเรท: {group_rate_low} | 500 บาท+ เรท {group_rate_high}\n⚠️เข้ากลุ่ม 15 วันก่อนซื้อ⚠️\n```", 
            inline=False
        )
        embed.add_field(
            name="🏪 สถานะร้าน", 
            value=f"```\n{'🟢 เปิด' if shop_open else '🔴 ปิดชั่วคราว'}\n```", 
            inline=False
        )
        embed.set_footer(
            text=f"Sushi Shop • รับกดเกมพาสและอื่น ๆ | อัปเดตล่าสุด: {get_thailand_time().strftime('%d/%m/%y %H:%M')}", 
            icon_url="https://media.discordapp.net/attachments/717757556889747657/1403684950770847754/noFilter.png"
        )
        embed.set_thumbnail(url="https://media.discordapp.net/attachments/717757556889747657/1403684950770847754/noFilter.png")
        
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

# ==================== TICKET HANDLER ====================
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
            'ty_used': False
        }
        
        ticket_customer_data[str(channel.id)] = interaction.user.name
        save_json(ticket_customer_data_file, ticket_customer_data)
        
        if stock_type == "gamepass":
            async with bot.stock_lock:
                gamepass_stock -= 1
        else:
            async with bot.stock_lock:
                group_stock -= 1
        
        # Save stock immediately
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
        else:
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
            
        else:
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

# ==================== SAVE TICKET TRANSCRIPT ====================
async def save_ticket_transcript(channel, action_by=None, robux_amount=None, customer_name=None):
    try:
        print(f"📝 กำลังบันทึกประวัติตั๋ว: {channel.name}")
        ticket_number = get_next_ticket_number()
        now = get_thailand_time()
        date_str = now.strftime("%d%m%y")
        time_str = now.strftime("%H%M")
        
        if robux_amount:
            robux_str = robux_amount
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

# ==================== ฟังก์ชันย้ายไป category ส่งของแล้ว ====================
async def move_to_delivered_category(channel):
    """Move ticket to delivered category"""
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
        
        # Check if already in correct category
        if channel.category and channel.category.id == DELIVERED_CATEGORY_ID:
            print(f"ℹ️ ตั๋ว {channel.name} อยู่ใน category ส่งของแล้วแล้ว")
            return True
        
        await channel.edit(category=delivered_category)
        print(f"✅ ย้ายตั๋ว {channel.name} ไปยัง category ส่งของแล้ว")
        return True
        
    except Exception as e:
        print(f"❌ Error moving to delivered category: {e}")
        return False

async def remove_buyer_permission_after_delay(channel, buyer, delay_seconds):
    """Remove buyer's view permission after delay and move to delivered category"""
    try:
        print(f"⏳ กำลังรอ {delay_seconds} วินาทีก่อนดำเนินการกับตั๋ว {channel.name}")
        await asyncio.sleep(delay_seconds)
        
        if not channel or channel not in channel.guild.channels:
            print(f"❌ ตั๋ว {channel.name} ไม่มีอยู่แล้ว")
            return
        
        # First, move to delivered category
        await move_to_delivered_category(channel)
        
        # Then remove buyer's permission
        if buyer:
            try:
                # Remove buyer's permission to view the channel
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
    """Add buyer role if they don't have it"""
    try:
        if not buyer:
            return False
        
        buyer_role = guild.get_role(BUYER_ROLE_ID)
        if not buyer_role:
            print(f"❌ ไม่พบ role ID: {BUYER_ROLE_ID}")
            return False
        
        # Check if buyer already has the role
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

# ==================== CREDIT CHANNEL WORKER ====================
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
                            
                            with open("credit_message_count.txt", "w") as f:
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

# ==================== ฟังก์ชันตรวจสอบความถูกต้อง ====================
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
                            
                            with open("credit_message_count.txt", "w") as f:
                                f.write(str(real_count))
                    else:
                        print(f"✅ ตัวเลขตรงกัน: {current_count}")
                except ValueError:
                    pass
    except Exception as e:
        print(f"❌ Error verifying count: {e}")

# ==================== ฟังก์ชันนับจำนวนข้อความในช่องเครดิต ====================
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

# ==================== ฟังก์ชันอัพเดทชื่อช่องเครดิต ====================
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
                    
                    with open("credit_message_count.txt", "w") as f:
                        f.write(str(message_count))
                except Exception as e:
                    print(f"❌ ไม่สามารถเปลี่ยนชื่อได้: {e}")
    except Exception as e:
        print(f"❌ Error updating credit channel name: {e}")
        traceback.print_exc()

# ==================== ฟังก์ชันตรวจสอบการเปลี่ยนแปลง ====================
async def check_credit_channel_changes():
    try:
        current_count = await count_credit_channel_messages()
        
        last_count = 0
        try:
            if os.path.exists("credit_message_count.txt"):
                with open("credit_message_count.txt", "r") as f:
                    last_count = int(f.read().strip())
        except:
            pass
        
        if current_count != last_count:
            print(f"📊 จำนวนข้อความเปลี่ยนจาก {last_count} เป็น {current_count}")
            await update_credit_channel_name()
    except Exception as e:
        print(f"❌ Error checking credit channel: {e}")

# ==================== MODALS ====================
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
                "created_at": datetime.datetime.now().isoformat(), 
                "updated_at": datetime.datetime.now().isoformat()
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
    anonymous = TextInput(
        label="🕵️ ต้องการเปิดชื่อผู้ซื้อหรือไม่?", 
        placeholder="พิมพ์ 'แสดง' หรือ 'ปิด'", 
        required=True,
        max_length=10
    )
    
    async def on_submit(self, i):
        global gamepass_rate
        
        try:
            # Check anonymous option
            anonymous_option = self.anonymous.value.strip().lower()
            if anonymous_option not in ["แสดง", "ปิด"]:
                await i.response.send_message(
                    "❌ กรุณาพิมพ์ 'แสดง' หรือ 'ปิด' เท่านั้น", 
                    ephemeral=True
                )
                return
            
            expr = self.robux_amount.value.lower().replace("x", "*").replace("÷", "/")
            if not re.match(r"^[\d\s\+\-\*\/\(\)]+$", expr):
                await i.response.send_message(
                    "❌ กรุณาใส่เฉพาะตัวเลข และเครื่องหมาย + - * / x ÷ ()", 
                    ephemeral=True
                )
                return
            
            robux = int(eval(expr))
            price = robux / gamepass_rate
            
            # Save anonymous preference to ticket data
            if anonymous_option == "ปิด":
                ticket_anonymous_mode[str(i.channel.id)] = True
                ticket_customer_data[str(i.channel.id)] = "ไม่ระบุตัวตน"
                save_json(ticket_customer_data_file, ticket_customer_data)
            else:
                ticket_anonymous_mode[str(i.channel.id)] = False
            
            embed = discord.Embed(title="📨 รายละเอียดการสั่งซื้อ", color=0x00FF99)
            embed.add_field(name="🗺️ ชื่อแมพ", value=self.map_name.value, inline=False)
            embed.add_field(name="🎟 เกมพาส", value=self.gamepass_name.value, inline=False)
            embed.add_field(name="💸 ราคาโรบัค", value=f"{format_number(robux)}", inline=True)
            embed.add_field(name="💰 ราคา", value=f"{format_number(int(price))} บาท", inline=True)
            embed.add_field(name="🕵️ การแสดงชื่อ", value=f"{'แสดงชื่อ' if anonymous_option == 'แสดง' else 'ไม่ระบุตัวตน'}", inline=True)
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
        label="💸 ต้องการซื้อกี่โรบัค?", 
        placeholder="กรอกจำนวนโรบัคที่ต้องการ", 
        required=True
    )
    anonymous = TextInput(
        label="🕵️ ต้องการเปิดชื่อผู้ซื้อหรือไม่?", 
        placeholder="พิมพ์ 'แสดง' หรือ 'ปิด'", 
        required=True,
        max_length=10
    )
    
    async def on_submit(self, i):
        global group_rate_low, group_rate_high
        
        try:
            # Check anonymous option
            anonymous_option = self.anonymous.value.strip().lower()
            if anonymous_option not in ["แสดง", "ปิด"]:
                await i.response.send_message(
                    "❌ กรุณาพิมพ์ 'แสดง' หรือ 'ปิด' เท่านั้น", 
                    ephemeral=True
                )
                return
            
            robux = int(self.robux_amount.value)
            # ใช้ 500 บาทเป็นเกณฑ์
            price_baht = robux / group_rate_low
            rate = group_rate_low if price_baht < 500 else group_rate_high
            
            # Save anonymous preference to ticket data
            if anonymous_option == "ปิด":
                ticket_anonymous_mode[str(i.channel.id)] = True
                ticket_customer_data[str(i.channel.id)] = "ไม่ระบุตัวตน"
                save_json(ticket_customer_data_file, ticket_customer_data)
            else:
                ticket_anonymous_mode[str(i.channel.id)] = False
            
            embed = discord.Embed(title="📨 รายละเอียดคำสั่งซื้อโรบัคกลุ่ม", color=0x00FF99)
            embed.add_field(name="🪪 ชื่อในเกม", value=self.user_name.value, inline=False)
            embed.add_field(name="💸 จำนวนโรบัค", value=f"{format_number(robux)}", inline=True)
            embed.add_field(name="💰 ราคา", value=f"{format_number(int(robux/rate))} บาท", inline=True)
            embed.add_field(name="🕵️ การแสดงชื่อ", value=f"{'แสดงชื่อ' if anonymous_option == 'แสดง' else 'ไม่ระบุตัวตน'}", inline=True)
            embed.set_footer(text="แอดมินจะตอบกลับเร็วๆนี้")
            
            view = View(timeout=300)
            cancel_btn = Button(label="❌ ยกเลิกสินค้า", style=discord.ButtonStyle.danger)
            
            async def cancel_cb(interaction):
                await interaction.response.send_message("❌ คำสั่งซื้อถูกยกเลิก")
                await interaction.message.delete()
            
            cancel_btn.callback = cancel_cb
            view.add_item(cancel_btn)
            
            await i.response.send_message(embed=embed, view=view)
            
        except ValueError:
            await i.response.send_message("❌ กรุณากรอกจำนวนโรบัคเป็นตัวเลข", ephemeral=True)
        except Exception as e:
            await i.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

# ==================== DELIVERY VIEW ====================
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
                    
                    receipt_color = 0xFFA500 if self.product_type == "Gamepass" else 0x00FFFF
                    
                    # Check if anonymous mode is active
                    anonymous_mode = ticket_anonymous_mode.get(str(self.channel.id), False)
                    buyer_display = "ไม่ระบุตัวตน" if anonymous_mode else (self.buyer.mention if self.buyer else "ไม่ทราบ")
                    
                    receipt_embed = discord.Embed(
                        title=f"🍣 ใบเสร็จการสั่งซื้อ ({self.product_type}) 🍣", 
                        color=receipt_color
                    )
                    receipt_embed.add_field(
                        name="😊 ผู้ซื้อ", 
                        value=buyer_display, 
                        inline=False
                    )
                    receipt_embed.add_field(
                        name="💸 จำนวนโรบัค", 
                        value=f"{format_number(self.robux_amount)}", 
                        inline=True
                    )
                    receipt_embed.add_field(
                        name="💰 ราคาตามเรท", 
                        value=f"{format_number(int(self.price))} บาท", 
                        inline=True
                    )
                    
                    if delivery_image:
                        receipt_embed.set_image(url=delivery_image)
                    
                    receipt_embed.set_footer(
                        text=f"จัดส่งสินค้าสำเร็จ 🤗 • {get_thailand_time().strftime('%d/%m/%y, %H:%M')}"
                    )
                    
                    await self.channel.send(embed=receipt_embed)
                    
                    # ========== ส่งใบเสร็จไปยัง DM ผู้ซื้อ ==========
                    if self.buyer and not anonymous_mode:
                        try:
                            dm_embed = discord.Embed(
                                title=f"🧾 ใบเสร็จการซื้อสินค้า ({self.product_type})",
                                description="ขอบคุณที่ใช้บริการ Sushi Shop นะคะ 🍣",
                                color=receipt_color
                            )
                            dm_embed.add_field(name="📦 สินค้า", value=self.product_type, inline=True)
                            dm_embed.add_field(name="💸 จำนวนโรบัค", value=f"{format_number(self.robux_amount)}", inline=True)
                            dm_embed.add_field(name="💰 ราคา", value=f"{format_number(int(self.price))} บาท", inline=True)
                            
                            if delivery_image:
                                dm_embed.set_image(url=delivery_image)
                            
                            dm_embed.add_field(
                                name="📝 หมายเหตุ", 
                                value="หากมีปัญหากรุณาติดต่อแอดมินในเซิร์ฟ", 
                                inline=False
                            )
                            dm_embed.set_footer(text="Sushi Shop • ขอบคุณที่ใช้บริการ💖")
                            
                            await self.buyer.send(embed=dm_embed)
                            print(f"✅ ส่งใบเสร็จไปยัง DM ของ {self.buyer.name} เรียบร้อย")
                        except Exception as e:
                            print(f"⚠️ ไม่สามารถส่ง DM ถึง {self.buyer.name}: {e}")
                    
                    try:
                        await interaction.response.edit_message(
                            content="✅ บันทึกการส่งสินค้าเรียบร้อย", 
                            embed=None, 
                            view=None
                        )
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
            
            embed = discord.Embed(
                title="📦 ยืนยันการส่งสินค้า", 
                description="ยืนยันหลักฐานการส่งสินค้านี้หรือไม่?", 
                color=0x00FF00
            )
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

# ==================== COMMANDS ====================
@bot.command(name="open")
@admin_only()
async def open_cmd(ctx):
    """เปิดร้าน"""
    global shop_open
    shop_open = True
    
    try:
        await ctx.message.delete()
    except:
        pass
    
    await bot.command_rate_limiter.acquire()
    
    # Save immediately
    save_stock_values()
    
    await update_channel_name()
    await update_main_channel()
    
    embed = discord.Embed(
        title="✅ เปิดร้านเรียบร้อย", 
        description="ร้าน Sushi Shop เปิดให้บริการแล้ว", 
        color=0x00FF00
    )
    embed.set_footer(text=f"เวลา: {get_thailand_time().strftime('%d/%m/%y %H:%M')}")
    
    await ctx.send(embed=embed)

@bot.command(name="close")
@admin_only()
async def close_cmd(ctx):
    """ปิดร้าน"""
    global shop_open
    shop_open = False
    
    try:
        await ctx.message.delete()
    except:
        pass
    
    await bot.command_rate_limiter.acquire()
    
    # Save immediately
    save_stock_values()
    
    await update_channel_name()
    await update_main_channel()
    
    embed = discord.Embed(
        title="🔴 ปิดร้านแล้ว", 
        description="ร้าน Sushi Shop ปิดให้บริการชั่วคราว", 
        color=0xFF0000
    )
    embed.set_footer(text=f"เวลา: {get_thailand_time().strftime('%d/%m/%y %H:%M')}")
    
    await ctx.send(embed=embed)

@bot.command(name="shop_open")
@admin_only()
async def shop_open_cmd(ctx):
    global shop_open
    shop_open = True
    
    try:
        await ctx.message.delete()
    except:
        pass
    
    await bot.command_rate_limiter.acquire()
    
    # Save immediately
    save_stock_values()
    
    await update_channel_name()
    await update_main_channel()
    
    embed = discord.Embed(
        title="✅ เปิดร้านแล้ว", 
        description="ร้าน Sushi Shop เปิดให้บริการแล้ว", 
        color=0x00FF00
    )
    embed.set_footer(text=f"เวลา: {get_thailand_time().strftime('%d/%m/%y %H:%M')}")
    
    await ctx.send(embed=embed)

@bot.command(name="shop_close")
@admin_only()
async def shop_close_cmd(ctx):
    global shop_open
    shop_open = False
    
    try:
        await ctx.message.delete()
    except:
        pass
    
    await bot.command_rate_limiter.acquire()
    
    # Save immediately
    save_stock_values()
    
    await update_channel_name()
    await update_main_channel()
    
    embed = discord.Embed(
        title="🔴 ปิดร้านเรียบร้อย", 
        description="ร้าน Sushi Shop ปิดให้บริการชั่วคราว", 
        color=0xFF0000
    )
    embed.set_footer(text=f"เวลา: {get_thailand_time().strftime('%d/%m/%y %H:%M')}")
    
    await ctx.send(embed=embed)

@bot.command()
async def link(ctx):
    embed = discord.Embed(
        title="🔗 ลิงก์กลุ่ม",
        description="เข้ากลุ่มนี้ 15 วันก่อนซื้อโรกลุ่ม: https://www.roblox.com/communities/34713179/VALKYs",
        color=0x00FF00
    )
    embed.set_footer(text="Sushi Shop 🍣")
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
                # Save stock values
                save_stock_values()
                embed = discord.Embed(
                    title="✅ ตั้งค่า Stock เรียบร้อย", 
                    description=f"ตั้งค่า สต๊อกเกมพาส เป็น **{format_number(gamepass_stock)}** เรียบร้อยแล้ว", 
                    color=0x00FF00
                )
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
                # Save stock values
                save_stock_values()
                embed = discord.Embed(
                    title="✅ ตั้งค่า Stock เรียบร้อย", 
                    description=f"ตั้งค่า สต๊อกโรบัคกลุ่ม เป็น **{format_number(group_stock)}** เรียบร้อยแล้ว", 
                    color=0x00FF00
                )
                await ctx.send(embed=embed)
                await update_main_channel()
            except ValueError:
                await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)
    else:
        embed = discord.Embed(
            title="❌ การใช้งานไม่ถูกต้อง", 
            description="**การใช้งาน:**\n`!stock` - เช็ค stock ทั้งหมด\n`!stock gp <จำนวน>` - ตั้งค่า Gamepass stock\n`!stock group <จำนวน>` - ตั้งค่า Group stock", 
            color=0xFF0000
        )
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
        embed = discord.Embed(
            title="👥 สถานะบริการโรกลุ่ม", 
            description=f"**{current_status}**", 
            color=0x00FF00 if group_ticket_enabled else 0xFF0000
        )
        await ctx.send(embed=embed)
        
    elif status.lower() in ["on", "enable", "เปิด"]:
        group_ticket_enabled = True
        # Save immediately
        save_stock_values()
        embed = discord.Embed(
            title="✅ เปิดโรกลุ่ม", 
            description="เปิดตั๋วโรกลุ่มแล้ว", 
            color=0x00FF00
        )
        await ctx.send(embed=embed)
        await update_main_channel()
        
    elif status.lower() in ["off", "disable", "ปิด"]:
        group_ticket_enabled = False
        # Save immediately
        save_stock_values()
        embed = discord.Embed(
            title="❌ ปิดโรกลุ่ม", 
            description="ปิดตั๋วโรกลุ่มแล้ว", 
            color=0xFF0000
        )
        await ctx.send(embed=embed)
        await update_main_channel()
    else:
        embed = discord.Embed(
            title="❌ การใช้งานไม่ถูกต้อง", 
            description="**การใช้งาน:**\n`!group` - เช็คสถานะ\n`!group on` - เปิด Group ticket\n`!group off` - ปิด Group ticket", 
            color=0xFF0000
        )
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
            embed = discord.Embed(
                title="❌ การใช้งานไม่ถูกต้อง", 
                description="**การใช้งาน:** `!rate group <low_rate> <high_rate>`", 
                color=0xFF0000
            )
            await ctx.send(embed=embed)
            return
        
        try:
            group_rate_low = float(low_rate)
            group_rate_high = float(high_rate)
            # Save immediately
            save_stock_values()
            embed = discord.Embed(
                title="✅ เปลี่ยนเรทโรกลุ่มเรียบร้อย", 
                description=f"ตั้งค่าเรทโรกลุ่มเป็น **{group_rate_low} | 500 บาท+ เรท {group_rate_high}** เรียบร้อยแล้ว", 
                color=0x00FF00
            )
            await ctx.send(embed=embed)
            await update_main_channel()
        except ValueError:
            await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)
        
    else:
        try:
            gamepass_rate = float(rate_type)
            # Save immediately
            save_stock_values()
            embed = discord.Embed(
                title="✅ เปลี่ยนเรทเกมพาสเรียบร้อย", 
                description=f"ตั้งค่าเรทเกมพาสเป็น **{gamepass_rate}** เรียบร้อยแล้ว", 
                color=0x00FF00
            )
            await ctx.send(embed=embed)
            await update_main_channel()
        except ValueError:
            await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)

# ==================== ANONYMOUS COMMANDS ====================
@bot.command(name="annoymous")
@admin_only()
async def annoymous_cmd(ctx):
    """เปิดโหมดไม่ระบุตัวตน (ไม่เปลี่ยนชื่อห้อง)"""
    if not ctx.channel.name.startswith("ticket-"):
        await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะในตั๋วเท่านั้น", delete_after=5)
        return
    
    try:
        # Set anonymous mode for this ticket
        ticket_anonymous_mode[str(ctx.channel.id)] = True
        
        # Update ticket_customer_data
        ticket_customer_data[str(ctx.channel.id)] = "ไม่ระบุตัวตน"
        save_json(ticket_customer_data_file, ticket_customer_data)
        
        # Send confirmation message
        embed = discord.Embed(
            title="✅ ปิดชื่อผู้ซื้อแล้ว",
            description="โหมดไม่ระบุตัวตนถูกเปิดใช้งานแล้ว",
            color=0x00FF00
        )
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")

@bot.command(name="annoymous_off")
@admin_only()
async def annoymous_off_cmd(ctx):
    """ปิดโหมดไม่ระบุตัวตน"""
    if not ctx.channel.name.startswith("ticket-"):
        await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะในตั๋วเท่านั้น", delete_after=5)
        return
    
    try:
        # Get buyer info
        buyer = None
        channel_name = ctx.channel.name
        if channel_name.startswith("ticket-"):
            parts = channel_name.split('-')
            if len(parts) >= 3:
                try:
                    user_id = int(parts[-1])
                    buyer = ctx.guild.get_member(user_id)
                except ValueError:
                    pass
        
        if not buyer:
            async for msg in ctx.channel.history(limit=20):
                if not msg.author.bot and msg.author != ctx.guild.me:
                    buyer = msg.author
                    break
        
        # Turn off anonymous mode
        if str(ctx.channel.id) in ticket_anonymous_mode:
            del ticket_anonymous_mode[str(ctx.channel.id)]
        
        # Update ticket_customer_data with real name
        if buyer:
            ticket_customer_data[str(ctx.channel.id)] = buyer.name
            save_json(ticket_customer_data_file, ticket_customer_data)
        else:
            # If can't find buyer, just remove anonymous flag
            if str(ctx.channel.id) in ticket_customer_data and ticket_customer_data[str(ctx.channel.id)] == "ไม่ระบุตัวตน":
                del ticket_customer_data[str(ctx.channel.id)]
                save_json(ticket_customer_data_file, ticket_customer_data)
        
        # Send confirmation message
        embed = discord.Embed(
            title="✅ ระบุชื่อผู้ซื้อแล้ว",
            description="โหมดไม่ระบุตัวตนถูกปิดใช้งานแล้ว",
            color=0x00FF00
        )
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")

# ==================== TKD COMMAND ====================
@bot.command()
@admin_only()
async def tkd(ctx):
    """ลบตั๋วที่มีรูปแบบ [ticket-user-userid] หรือ [ddmmyytime-amount-user]"""
    channel = ctx.channel
    
    # ตรวจสอบว่าอยู่ใน channel ที่มีรูปแบบที่กำหนดหรือไม่
    channel_name = channel.name
    
    # รูปแบบที่อนุญาต
    valid_formats = False
    
    # รูปแบบ ticket-user-userid
    if channel_name.startswith("ticket-"):
        valid_formats = True
    
    # ตรวจสอบรูปแบบ [ddmmyytime-amount-user]
    # เช่น 0703262106-4-eurrai (10 ตัวเลขเวลา + ขีด + ตัวเลขจำนวน + ขีด + ชื่อ)
    # ddmmyyHHMM = 10 ตัวเลข (เช่น 0703262106 = 07/03/26 21:06)
    pattern = r'^\d{10}-\d+-[\w\u0E00-\u0E7F]+$'  # 10 ตัวเลข + ขีด + ตัวเลข + ขีด + ตัวอักษร/ไทย
    if re.match(pattern, channel_name):
        valid_formats = True
    
    if not valid_formats:
        await ctx.send(f"❌ คำสั่งนี้ใช้ได้เฉพาะในช่องตั๋วเท่านั้น\nรูปแบบที่ใช้ได้: ticket-... หรือ [ddmmyytime-amount-user]\nตัวอย่าง: 0703262106-4-eurrai", delete_after=10)
        return
    
    try:
        # บันทึก transcript ก่อนลบ
        await save_ticket_transcript(channel, ctx.author)
        
        # ส่งข้อความยืนยัน
        await ctx.send("🗑️ กำลังลบตั๋ว...")
        
        # รอ 2 วินาทีแล้วลบ
        await asyncio.sleep(2)
        await channel.delete()
        
        print(f"✅ ลบตั๋ว {channel_name} โดย {ctx.author.name}")
        
    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")

# ==================== คำสั่ง TY ====================
@bot.command()
@admin_only()
async def ty(ctx):
    """คำสั่ง !ty เหมือน !vouch แต่ส่ง embed ขอบคุณโดยไม่ส่งใบเสร็จไป sales log"""
    global gamepass_stock, group_stock
    
    try:
        await ctx.message.delete()
    except:
        pass
    
    if not ctx.channel.name.startswith("ticket-"):
        await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะในตั๋วเท่านั้น", delete_after=5)
        return
    
    try:
        processing_msg = await ctx.send("🔄 กำลังดำเนินการ...")
        
        buyer = None
        channel_name = ctx.channel.name
        if channel_name.startswith("ticket-"):
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
        
        # Add buyer role if they don't have it
        await add_buyer_role(buyer, ctx.guild)
        
        robux_amount = ticket_robux_data.get(str(ctx.channel.id))
        customer_name = ticket_customer_data.get(str(ctx.channel.id))
        
        # ค้นหาข้อมูลสินค้าและราคาจากประวัติแชท
        product_type = "Gamepass"  # ค่าเริ่มต้น
        price = 0
        delivery_image = None
        
        # ค้นหาข้อมูลการส่งสินค้าล่าสุด
        async for msg in ctx.channel.history(limit=50):
            if msg.author == bot.user and msg.embeds:
                for embed in msg.embeds:
                    if embed.title and "ใบเสร็จ" in embed.title:
                        # ดึงข้อมูลจาก embed ใบเสร็จ
                        for field in embed.fields:
                            if field.name == "💸 จำนวนโรบัค":
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
        
        # Save transcript first
        save_success, filename = await save_ticket_transcript(ctx.channel, buyer, robux_amount, customer_name)
        
        if save_success:
            try:
                await ctx.channel.edit(name=filename[:100])
            except:
                pass
        
        if ctx.channel.category:
            category_name = ctx.channel.category.name.lower()
            if "gamepass" in category_name:
                async with bot.stock_lock:
                    gamepass_stock += 1
            elif "group" in category_name or "robux" in category_name:
                async with bot.stock_lock:
                    group_stock += 1
        
        # Save stock immediately
        save_stock_values()
        
        await processing_msg.delete()
        
        # ส่ง embed ตามที่ต้องการ
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
        
        if str(ctx.channel.id) in ticket_robux_data:
            del ticket_robux_data[str(ctx.channel.id)]
            save_json(ticket_robux_data_file, ticket_robux_data)
        
        if str(ctx.channel.id) in ticket_customer_data:
            del ticket_customer_data[str(ctx.channel.id)]
            save_json(ticket_customer_data_file, ticket_customer_data)
        
        # Schedule to remove buyer permission and move category after 10 minutes
        bot.loop.create_task(remove_buyer_permission_after_delay(ctx.channel, buyer, 600))
        
        await update_main_channel()
        
        print(f"✅ คำสั่ง !ty ดำเนินการสำเร็จสำหรับห้อง {ctx.channel.name}")
        
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดใน !ty: {e}")
        traceback.print_exc()

# ==================== คำสั่ง VOUCH ====================
@bot.command()
@admin_only()
async def vouch(ctx):
    global gamepass_stock, group_stock
    
    try:
        await ctx.message.delete()
    except:
        pass
    
    if not ctx.channel.name.startswith("ticket-"):
        await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะในตั๋วเท่านั้น", delete_after=5)
        return
    
    try:
        processing_msg = await ctx.send("🔄 กำลังดำเนินการ...")
        
        buyer = None
        channel_name = ctx.channel.name
        if channel_name.startswith("ticket-"):
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
        
        # Add buyer role if they don't have it
        await add_buyer_role(buyer, ctx.guild)
        
        robux_amount = ticket_robux_data.get(str(ctx.channel.id))
        customer_name = ticket_customer_data.get(str(ctx.channel.id))
        
        # ค้นหาข้อมูลสินค้าและราคาจากประวัติแชท
        product_type = "Gamepass"  # ค่าเริ่มต้น
        price = 0
        delivery_image = None
        
        # ค้นหาข้อมูลการส่งสินค้าล่าสุด
        async for msg in ctx.channel.history(limit=50):
            if msg.author == bot.user and msg.embeds:
                for embed in msg.embeds:
                    if embed.title and "ใบเสร็จ" in embed.title:
                        # ดึงข้อมูลจาก embed ใบเสร็จ
                        for field in embed.fields:
                            if field.name == "💸 จำนวนโรบัค":
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
        
        receipt_color = 0xFFA500 if product_type == "Gamepass" else 0x00FFFF
        
        # Check if anonymous mode is active
        anonymous_mode = ticket_anonymous_mode.get(str(ctx.channel.id), False)
        buyer_display = "ไม่ระบุตัวตน" if anonymous_mode else (buyer.mention if buyer else "ไม่ทราบ")
        
        # สร้าง embed ใบเสร็จ
        receipt_embed = discord.Embed(
            title=f"🍣 ใบเสร็จการสั่งซื้อ ({product_type}) 🍣", 
            color=receipt_color
        )
        receipt_embed.add_field(
            name="😊 ผู้ซื้อ", 
            value=buyer_display, 
            inline=False
        )
        receipt_embed.add_field(
            name="💸 จำนวนโรบัค", 
            value=f"{format_number(robux_amount) if robux_amount else 0}", 
            inline=True
        )
        receipt_embed.add_field(
            name="💰 ราคาตามเรท", 
            value=f"{format_number(int(price))} บาท" if price > 0 else "ไม่ระบุ", 
            inline=True
        )
        
        if delivery_image:
            receipt_embed.set_image(url=delivery_image)
        
        receipt_embed.set_footer(
            text=f"จัดส่งสินค้าสำเร็จ 🤗 • {get_thailand_time().strftime('%d/%m/%y, %H:%M')}"
        )
        
        # ========== ส่งใบเสร็จไปยัง sales log channel ==========
        log_channel = bot.get_channel(SALES_LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(embed=receipt_embed)
            print(f"✅ ส่งใบเสร็จไปยัง sales log channel (ID: {SALES_LOG_CHANNEL_ID}) เรียบร้อย")
        
        save_success, filename = await save_ticket_transcript(ctx.channel, buyer, robux_amount, customer_name)
        
        if save_success:
            try:
                await ctx.channel.edit(name=filename[:100])
            except:
                pass
        
        if ctx.channel.category:
            category_name = ctx.channel.category.name.lower()
            if "gamepass" in category_name:
                async with bot.stock_lock:
                    gamepass_stock += 1
            elif "group" in category_name or "robux" in category_name:
                async with bot.stock_lock:
                    group_stock += 1
        
        # Save stock immediately
        save_stock_values()
        
        await processing_msg.delete()
        
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
        
        if str(ctx.channel.id) in ticket_robux_data:
            del ticket_robux_data[str(ctx.channel.id)]
            save_json(ticket_robux_data_file, ticket_robux_data)
        
        if str(ctx.channel.id) in ticket_customer_data:
            del ticket_customer_data[str(ctx.channel.id)]
            save_json(ticket_customer_data_file, ticket_customer_data)
        
        # Schedule to remove buyer permission and move category after 10 minutes
        bot.loop.create_task(remove_buyer_permission_after_delay(ctx.channel, buyer, 600))
        
        await update_main_channel()
        
        print(f"✅ คำสั่ง !vouch ดำเนินการสำเร็จสำหรับห้อง {ctx.channel.name}")
        
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดใน !vouch: {e}")
        traceback.print_exc()

@bot.command()
@admin_only()
async def od(ctx, *, expr):
    global gamepass_stock, gamepass_rate
    
    if not ctx.channel.name.startswith("ticket-"):
        await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะในตั๋วเท่านั้น", delete_after=5)
        return
    
    try:
        expr_clean = expr.replace(",", "").lower().replace("x", "*").replace("÷", "/")
        robux = int(eval(expr_clean))
        price = robux / gamepass_rate
        
        buyer = None
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
        
        async with bot.stock_lock:
            gamepass_stock = max(0, gamepass_stock - robux)
        
        # Save stock immediately
        save_stock_values()
        
        ticket_robux_data[str(ctx.channel.id)] = str(robux)
        save_json(ticket_robux_data_file, ticket_robux_data)
        
        embed = discord.Embed(title="🍣คำสั่งซื้อสินค้า🍣", color=0xFFA500)
        embed.add_field(name="📦 ประเภทสินค้า", value="Gamepass", inline=False)
        embed.add_field(name="💸 จำนวนโรบัค", value=f"{format_number(robux)}", inline=True)
        embed.add_field(name="💰 ราคาตามเรท", value=f"{format_number(int(price))} บาท", inline=True)
        embed.set_footer(text=f"รับออร์เดอร์แล้ว 🤗 • {get_thailand_time().strftime('%d/%m/%y, %H:%M')}")
        
        await ctx.send(embed=embed, view=DeliveryView(ctx.channel, "Gamepass", robux, price, buyer))
        
        await update_main_channel()
        
    except Exception as e:
        print(f"❌ Error in !od: {e}")

@bot.command()
@admin_only()
async def odg(ctx, *, expr):
    global group_stock, group_rate_low, group_rate_high
    
    if not ctx.channel.name.startswith("ticket-"):
        await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะในตั๋วเท่านั้น", delete_after=5)
        return
    
    try:
        expr_clean = expr.replace(",", "").lower().replace("x", "*").replace("÷", "/")
        robux = int(eval(expr_clean))
        # ใช้ 500 บาทเป็นเกณฑ์
        price_baht = robux / group_rate_low
        rate = group_rate_low if price_baht < 500 else group_rate_high
        price = robux / rate
        
        buyer = None
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
        
        async with bot.stock_lock:
            group_stock = max(0, group_stock - robux)
        
        # Save stock immediately
        save_stock_values()
        
        ticket_robux_data[str(ctx.channel.id)] = str(robux)
        save_json(ticket_robux_data_file, ticket_robux_data)
        
        embed = discord.Embed(title="🍣คำสั่งซื้อสินค้า🍣", color=0x00FFFF)
        embed.add_field(name="📦 ประเภทสินค้า", value="Group", inline=False)
        embed.add_field(name="💸 จำนวนโรบัค", value=f"{format_number(robux)}", inline=True)
        embed.add_field(name="💰 ราคาตามเรท", value=f"{format_number(int(price))} บาท", inline=True)
        embed.set_footer(text=f"รับออร์เดอร์แล้ว 🤗 • {get_thailand_time().strftime('%d/%m/%y, %H:%M')}")
        
        await ctx.send(embed=embed, view=DeliveryView(ctx.channel, "Group", robux, price, buyer))
        
        await update_main_channel()
        
    except Exception as e:
        print(f"❌ Error in !odg: {e}")

@bot.command()
async def qr(ctx):
    try:
        await ctx.message.delete()
    except:
        pass
    
    embed = discord.Embed(
        title="⚠️โน๊ตสลิปว่า: เติมโรบัคกับ Sushi Shop⚠️ ช่องทางการโอนเงิน", 
        color=0x00CCFF
    )
    embed.add_field(
        name="1. ชื่อบัญชี (ไทยพานิชย์ SCB)", 
        value="**หจก. วอเตอร์ เทค เซลล์ แอนด์ เซอร์วิส**", 
        inline=False
    )
    embed.add_field(
        name="2. เลขบัญชี", 
        value="**120-239181-3**", 
        inline=False
    )
    # Updated image link as requested
    embed.set_image(url="https://media.discordapp.net/attachments/1361004239043821610/1475334379550281768/Sushi_SCB_3.png?ex=699d1bb6&is=699bca36&hm=8d0aca020488ee0942aa7e4e1537c8a695b96033f8453552a1e840af93aaa029&=&format=webp&quality=lossless&width=1161&height=1061")
    
    view = View(timeout=None)
    copy_btn = Button(label="คัดลอกเลขบัญชี", style=discord.ButtonStyle.success, emoji="📋")
    
    async def copy_cb(i):
        await i.response.send_message(f"```120-239181-3 ⚠️โน๊ตสลิปว่า: เติมโรบัคกับ Sushi Shop⚠️```", ephemeral=True)
    
    copy_btn.callback = copy_cb
    view.add_item(copy_btn)
    
    await ctx.send(embed=embed, view=view)

@bot.command()
async def gp(ctx, *, expr):
    global gamepass_rate
    
    try:
        expr_clean = expr.replace(",", "").lower().replace("x", "*").replace("÷", "/")
        robux = int(eval(expr_clean))
        await ctx.send(f"🎮 Gamepass {format_number(robux)} Robux = **{format_number(int(robux/gamepass_rate))} บาท** (เรท {gamepass_rate})")
    except:
        await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)

@bot.command()
async def g(ctx, *, expr):
    """คำนวณราคา Group !g <จำนวน>"""
    global group_rate_low, group_rate_high
    
    try:
        expr_clean = expr.replace(",", "").lower().replace("x", "*").replace("÷", "/")
        robux = int(eval(expr_clean))
        
        # คำนวณราคาเป็นบาทก่อน
        price_baht_low = robux / group_rate_low  # ถ้าใช้ rate 4
        price_baht_high = robux / group_rate_high  # ถ้าใช้ rate 4.5
        
        # ตรวจสอบว่าควรใช้ rate อะไร
        if price_baht_high >= 500:
            # ถ้าใช้ rate 4.5 แล้วได้ราคาตั้งแต่ 500 บาทขึ้นไป
            rate = group_rate_high
            price = price_baht_high
            rate_text = f"เรท {group_rate_high} (500 บาทขึ้นไป)"
        else:
            # ถ้าใช้ rate 4.5 แล้วได้ราคาต่ำกว่า 500 บาท ให้ใช้ rate 4
            rate = group_rate_low
            price = price_baht_low
            rate_text = f"เรท {group_rate_low} (ต่ำกว่า 500 บาท)"
        
        await ctx.send(f"👥 Group {format_number(robux)} Robux = **{format_number(int(price))} บาท** ({rate_text})")
    except Exception as e:
        print(f"Error in !g: {e}")
        await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)

@bot.command()
async def gpb(ctx, *, expr):
    global gamepass_rate
    
    try:
        baht = float(eval(expr.replace(",", "")))
        await ctx.send(f"🎮 {format_number(int(baht))} บาท = **{format_number(int(baht * gamepass_rate))} Robux** (Gamepass เรท {gamepass_rate})")
    except:
        await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)

@bot.command()
async def gb(ctx, *, expr):
    """คำนวณ Group จากบาท !gb <จำนวน>"""
    global group_rate_low, group_rate_high
    
    try:
        baht = float(eval(expr.replace(",", "")))
        
        # ตรวจสอบว่าใช้ rate อะไร
        if baht >= 500:
            rate = group_rate_high
            rate_text = f"เรท {group_rate_high} (500 บาทขึ้นไป)"
        else:
            rate = group_rate_low
            rate_text = f"เรท {group_rate_low} (ต่ำกว่า 500 บาท)"
        
        robux = int(baht * rate)
        await ctx.send(f"👥 {format_number(int(baht))} บาท = **{format_number(robux)} Robux** ({rate_text})")
    except Exception as e:
        print(f"Error in !gb: {e}")
        await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)

@bot.command()
async def tax(ctx, *, expr):
    try:
        expr = expr.replace(" ", "")
        if re.match(r"^\d+$", expr):
            number = int(expr)
            await ctx.send(f"💰 {format_number(number)} โรบัคที่ได้หลังหัก 30% = **{format_number(int(number * 0.7))} Robux**")
        elif m := re.match(r"^(\d+)-(\d+)%$", expr):
            number = int(m[1])
            percent = int(m[2])
            await ctx.send(f"💰 {format_number(number)} โรบัคที่ได้หลังหัก {percent}% = **{format_number(int(number * (1 - percent/100)))} Robux**")
        else:
            await ctx.send(
                "❌ รูปแบบไม่ถูกต้อง\n\n**การใช้งาน:**\n`!tax 100` - หัก 30% อัตโนมัติ\n`!tax 100-30%` - หัก 30%\n`!tax 100-50%` - หัก 50%", 
                delete_after=15
            )
    except:
        await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)

@bot.command()
async def love(ctx):
    await ctx.send("# LOVE YOU<:sushiheart:1410484970291466300>")

@bot.command()
async def say(ctx, *, message):
    await ctx.send(f"# {message.upper()} <:sushiheart:1410484970291466300>")

@bot.command()
@admin_only()
async def setup(ctx):
    try:
        await ctx.message.delete()
    except:
        pass
    
    await update_main_channel()
    await ctx.send(embed=discord.Embed(title="✅ ตั้งค่าระบบเรียบร้อยแล้ว", color=0x00FF00))

@bot.command()
@admin_only()
async def restart(ctx):
    try:
        await ctx.message.delete()
    except:
        pass
    
    await update_main_channel()
    await ctx.send(embed=discord.Embed(title="🔄 รีสตาร์ทระบบปุ่มเรียบร้อยแล้ว", color=0x00FF00))

@bot.command()
@admin_only()
async def fixcredit(ctx):
    await ctx.send("🔍 กำลังตรวจสอบจำนวนข้อความในช่องเครดิต...")
    await verify_credit_channel_count()
    await ctx.send("✅ ตรวจสอบเสร็จสิ้น!")

@bot.command()
@admin_only()
async def saveall(ctx):
    """บันทึกข้อมูลทั้งหมดทันที"""
    await ctx.send("💾 กำลังบันทึกข้อมูลทั้งหมด...")
    await save_all_data()
    await ctx.send("✅ บันทึกข้อมูลเรียบร้อย!")

# ==================== SYNC COMMANDS ====================
@bot.command()
@admin_only()
async def sync(ctx):
    """Sync slash commands (admin only)"""
    try:
        synced = await bot.tree.sync()
        await ctx.send(f"✅ Synced {len(synced)} commands")
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

# ==================== TASKS ====================
@tasks.loop(minutes=1)
async def update_presence():
    await bot.change_presence(
        activity=discord.Game(name="บอทเครื่องคิดเลขของ wforr | !help")
    )

@tasks.loop(minutes=5)
async def save_data():
    await save_all_data()

@tasks.loop(minutes=10)
async def update_credit_channel_task():
    await check_credit_channel_changes()

# ==================== EVENTS ====================
@bot.event
async def on_ready():
    print(f"✅ บอทออนไลน์แล้ว: {bot.user} (ID: {bot.user.id})")
    
    # Change bot bio to the new one
    await bot.change_presence(
        activity=discord.Game(name="บอทเครื่องคิดเลขของ wforr | !help")
    )
    
    try:
        print("🔄 กำลัง sync slash commands...")
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} commands")
        bot.commands_synced = True
        
        for cmd in synced:
            print(f"   - /{cmd.name}")
            
    except Exception as e:
        print(f"❌ Error syncing commands: {e}")
        print("⚠️ กรุณาใช้คำสั่ง !sync เพื่อลอง sync อีกครั้ง")
    
    update_presence.start()
    save_data.start()
    update_credit_channel_task.start()
    
    if not credit_channel_update_task_running:
        bot.loop.create_task(credit_channel_update_worker())
        print("✅ เริ่ม credit channel update worker")
    
    await update_channel_name()
    await update_main_channel()
    await update_credit_channel_name()
    
    print("🎯 บอทพร้อมใช้งาน!")

@bot.event
async def on_message(message):
    if message.channel.id == CREDIT_CHANNEL_ID:
        if message.author != bot.user:
            await asyncio.sleep(2)
            for emoji in ["❤️", "🍣"]:
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

# ==================== START ====================
if __name__ == "__main__":
    keep_alive()
    
    print("⏳ รอ 30 วินาทีก่อนเริ่มบอท...")
    time.sleep(30)
    
    token = os.getenv("TOKEN")
    if not token:
        print("❌ ไม่พบ TOKEN ใน environment variables")
        # For testing, you can use a direct token (remove in production)
        # token = "YOUR_BOT_TOKEN_HERE"  
        exit(1)
    
    try:
        bot.run(token)
    except Exception as e:
        print(f"❌ Error running bot: {e}")
        traceback.print_exc()
