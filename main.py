import os, datetime, discord, re, asyncio, json, traceback, time, aivohttp, logging
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

# ==================== PERSISTENT STORAGE FOR REPLIT ====================
# This ensures your data never resets when you restart or redeploy
try:
    from replit import db
    REPLIT_DB_AVAILABLE = True
    print("✅ Replit DB connected - your data will be saved permanently!")
except ImportError:
    REPLIT_DB_AVAILABLE = False
    print("⚠️ Replit DB not available - data may reset on restart")

def save_json(file, data):
    """Save data to both file and Replit DB (permanent storage)"""
    try:
        # Save to file (for local backup)
        with open(file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # Save to Replit DB (permanent storage)
        if REPLIT_DB_AVAILABLE:
            db_key = file.replace('.', '_').replace('.json', '')
            db[db_key] = json.dumps(data)
            print(f"💾 Saved {file} to permanent storage")
        
        return True
    except Exception as e:
        print(f"❌ Error saving {file}: {e}")
        return False

def load_json(file, default):
    """Load data from Replit DB first (permanent), then file as backup"""
    try:
        # Try Replit DB first (permanent storage)
        if REPLIT_DB_AVAILABLE:
            db_key = file.replace('.', '_').replace('.json', '')
            if db_key in db:
                data = json.loads(db[db_key])
                print(f"📂 Loaded {file} from permanent storage")
                
                # Also save to file as backup
                with open(file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                return data
        
        # If not in DB, load from file
        if os.path.exists(file):
            with open(file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                print(f"📂 Loaded {file} from file")
                
                # Save to DB for next time
                if REPLIT_DB_AVAILABLE:
                    db_key = file.replace('.', '_').replace('.json', '')
                    db[db_key] = json.dumps(data)
                
                return data
        
        return default
    except Exception as e:
        print(f"❌ Error loading {file}: {e}")
        return default

print("✅ Persistent storage system initialized!")
# =============================================================

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
gamepass_stock = 0
group_stock = 10000
ROLL_COST = 50  # ค่าใช้จ่ายในการสุ่มไอเทม
STARTING_BALANCE = 300  # เงินเริ่มต้น

# Channel IDs
MAIN_CHANNEL_ID = 1361044752975532152
SALES_LOG_CHANNEL_ID = 1402993077643120720
CREDIT_CHANNEL_ID = 1363250076549382246
DELIVERED_CATEGORY_ID = 1419565515088597083
ARCHIVED_CATEGORY_ID = 1445086228113264650
BUYER_ROLE_ID = 1361555369825927249

# Files
user_data_file = "user_data.json"
ticket_transcripts_file = "ticket_transcripts.json"
ticket_counter_file = "ticket_counter.json"
ticket_robux_data_file = "ticket_robux_data.json"
ticket_customer_data_file = "ticket_customer_data.json"
rng_inventory_file = "rng_inventory.json"
rng_balance_file = "rng_balance.json"
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
        gamepass_stock = stock_data.get("gamepass_stock", 50000)
        group_stock = stock_data.get("group_stock", 0)
        gamepass_rate = stock_data.get("gamepass_rate", 6.5)
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
    save_json(rng_inventory_file, load_inventory())
    save_json(rng_balance_file, load_balances())
    save_stock_values()
    print(f"✅ All data saved at {get_thailand_time().strftime('%H:%M:%S')}")

def save_all_data_sync():
    """Sync version of save_all_data for shutdown handler"""
    save_json(user_data_file, user_data)
    save_json(ticket_transcripts_file, ticket_transcripts)
    save_json(ticket_robux_data_file, ticket_robux_data)
    save_json(ticket_customer_data_file, ticket_customer_data)
    save_json(rng_inventory_file, load_inventory())
    save_json(rng_balance_file, load_balances())
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
        self.pawn_data = {}
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
            value=f"```\nเรท: {gamepass_rate} | โรแท้\nเช็คราคาพิมพ์: !gp <จำนวน>\n```", 
            inline=False
        )
        embed.add_field(
            name=f"👥 โรบัคกลุ่ม | 📊 Stock: {format_number(group_stock)} {'🟢' if group_stock > 0 else '🔴'}", 
            value=f"```\nเรท: {group_rate_low} | 500 บาท+ เรท {group_rate_high}\n⚠️เข้ากลุ่ม 15 วันก่อนซื้อ⚠️\n```", 
            inline=False
        )
        embed.add_field(
            name="🏪 RNG GAME", 
            value=f"```\nค่าใช้จ่ายในการสุ่ม: {format_number(ROLL_COST)} 🪙\nเงินเริ่มต้น: {format_number(STARTING_BALANCE)} 🪙\n```", 
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
        
        view = View(timeout=None)
        
        if not shop_open:
            gamepass_btn = Button(label="ปิดชั่วคราว", style=discord.ButtonStyle.danger, emoji="🎮", disabled=True)
        elif gamepass_stock <= 0:
            gamepass_btn = Button(label="สินค้าหมด", style=discord.ButtonStyle.danger, emoji="🎮", disabled=True)
        else:
            gamepass_btn = Button(label="กดเกมพาส", style=discord.ButtonStyle.success, emoji="🎮")
        
        if not shop_open:
            group_btn = Button(label="ปิดชั่วคราว", style=discord.ButtonStyle.danger, emoji="👥", disabled=True)
        elif not group_ticket_enabled:
            group_btn = Button(label="ปิดชั่วคราว", style=discord.ButtonStyle.danger, emoji="👥", disabled=True)
        elif group_stock <= 0:
            group_btn = Button(label="สินค้าหมด", style=discord.ButtonStyle.danger, emoji="👥", disabled=True)
        else:
            group_btn = Button(label="เติมโรกลุ่ม", style=discord.ButtonStyle.success, emoji="👥")
        
        notes_btn = Button(label="จดวันที่เข้ากลุ่ม", style=discord.ButtonStyle.secondary, emoji="📝")
        rng_btn = Button(label="เล่นเกม RNG", style=discord.ButtonStyle.primary, emoji="🎲")
        
        async def gamepass_cb(i):
            await handle_open_ticket(i, "🍣Sushi Gamepass 🍣", "gamepass")
        
        async def group_cb(i):
            await handle_open_ticket(i, "💰Robux Group💰", "group")
        
        async def notes_cb(i):
            await i.response.send_modal(PersonalNoteModal())
        
        async def rng_cb(i):
            embed = discord.Embed(
                title="🎲 RNG Sushi Shop",
                description="ยินดีต้อนรับสู่เกมสุ่มไอเทม!\n\nเลือกปุ่มด้านล่างเพื่อเริ่มเล่น",
                color=0x00AAFF
            )
            embed.add_field(
                name="📊 อัตราการสุ่ม", 
                value=(
                    f"{get_rarity_emoji('common')} Common 60%\n"
                    f"{get_rarity_emoji('rare')} Rare 25%\n"
                    f"{get_rarity_emoji('epic')} Epic 10%\n"
                    f"{get_rarity_emoji('legendary')} Legendary 4%\n"
                    f"{get_rarity_emoji('mythic')} Mythic 1%"
                ), 
                inline=False
            )
            embed.add_field(
                name="💰 ค่าใช้จ่าย", 
                value=f"การสุ่มแต่ละครั้งใช้ {format_number(ROLL_COST)} 🪙",
                inline=False
            )
            embed.set_footer(text=f"ผู้เล่น: {i.user.display_name}")
            
            await i.response.send_message(embed=embed, view=RNGMainView(i.user), ephemeral=True)
        
        gamepass_btn.callback = gamepass_cb
        group_btn.callback = group_cb
        notes_btn.callback = notes_cb
        rng_btn.callback = rng_cb
        
        view.add_item(gamepass_btn)
        view.add_item(group_btn)
        view.add_item(notes_btn)
        view.add_item(rng_btn)
        
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
async def move_to_delivered_category(channel, user):
    try:
        guild = channel.guild
        
        delivered_category = guild.get_channel(DELIVERED_CATEGORY_ID)
        if not delivered_category or not isinstance(delivered_category, discord.CategoryChannel):
            delivered_category = discord.utils.get(guild.categories, id=DELIVERED_CATEGORY_ID)
            if not delivered_category:
                print(f"❌ ไม่พบ category ส่งของแล้ว (ID: {DELIVERED_CATEGORY_ID})")
                return False
        
        await channel.edit(category=delivered_category)
        print(f"✅ ย้ายตั๋วไปยัง category ส่งของแล้ว")
        return True
        
    except Exception as e:
        print(f"❌ Error moving to delivered category: {e}")
        return False

async def remove_buyer_permission_after_delay(channel, buyer, delay_seconds):
    """Remove buyer's view permission after delay"""
    try:
        print(f"⏳ กำลังรอ {delay_seconds} วินาทีก่อนลบสิทธิ์ผู้ซื้อ {channel.name}")
        await asyncio.sleep(delay_seconds)
        
        if not channel or channel not in channel.guild.channels:
            print(f"❌ ตั๋ว {channel.name} ไม่มีอยู่แล้ว")
            return
        
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
        
        # Also move to delivered category if not already there
        if channel.category.id != DELIVERED_CATEGORY_ID:
            delivered_category = channel.guild.get_channel(DELIVERED_CATEGORY_ID)
            if delivered_category:
                await bot.channel_edit_rate_limiter.acquire()
                await channel.edit(category=delivered_category)
                print(f"✅ ย้ายตั๋ว {channel.name} ไป category ส่งของแล้ว")
        
    except Exception as e:
        print(f"❌ Error removing buyer permission: {e}")

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

# ==================== FIXED ANONYMOUS COMMANDS ====================
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

# ==================== FIXED TKD COMMAND (Supports all your formats) ====================
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
    
    # ตรวจสอบรูปแบบ [ddmmyytime-amount-user] - รองรับทุกกรณี
    # เช่น 0703262106-4-eurrai, 0903261133-800-redviar4678, 1403262329-1099-ไม่ระบุตัวตน
    # รูปแบบ: 12 ตัวเลข (ddmmyyHHMM) + ขีด + ตัวเลข (amount) + ขีด + ตัวอักษร/ตัวเลข/ภาษาไทย
    pattern = r'^\d{12}-\d+-[\w\u0E00-\u0E7F]+$'
    if re.match(pattern, channel_name):
        valid_formats = True
    
    if not valid_formats:
        await ctx.send(f"❌ คำสั่งนี้ใช้ได้เฉพาะในช่องตั๋วเท่านั้น\nรูปแบบที่ใช้ได้: ticket-... หรือ [ddmmyytime-amount-user]\nตัวอย่าง: 0703262106-4-eurrai, 0903261133-800-redviar4678", delete_after=10)
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

# ==================== STORAGE CHECK COMMAND ====================
@bot.command()
@admin_only()
async def checkstorage(ctx):
    """ตรวจสอบสถานะการเก็บข้อมูล"""
    if REPLIT_DB_AVAILABLE:
        # นับจำนวนไฟล์ที่ถูกบันทึก
        saved_files = []
        data_files = [
            'user_data', 'ticket_transcripts', 'ticket_counter',
            'ticket_robux_data', 'ticket_customer_data',
            'rng_inventory', 'rng_balance', 'stock_values'
        ]
        
        for key in db.keys():
            if any(file in key for file in data_files):
                saved_files.append(key)
        
        embed = discord.Embed(
            title="💾 สถานะการเก็บข้อมูล",
            color=0x00FF00
        )
        embed.add_field(name="Replit DB", value="✅ เชื่อมต่อแล้ว", inline=True)
        embed.add_field(name="ไฟล์ที่บันทึก", value=str(len(saved_files)), inline=True)
        embed.add_field(name="ข้อมูลปลอดภัย", value="✅ ถาวร", inline=True)
        embed.add_field(name="วิธีการทำงาน", value="ข้อมูลทั้งหมดจะถูกบันทึกถาวร แม้รีสตาร์ทหรืออัปเดตบอท", inline=False)
        
        await ctx.send(embed=embed)
    else:
        await ctx.send("⚠️ Replit DB ไม่พร้อมใช้งาน - ข้อมูลอาจหายเมื่อรีสตาร์ท!")

# ==================== คำสั่ง COIN MANAGEMENT ====================
@bot.command()
@admin_only()
async def delcoin(ctx, user_id: str = None, amount: str = None):
    """ลบ SushiCoin จากผู้ใช้ !delcoin <userid> <amount>"""
    if not user_id or not amount:
        embed = discord.Embed(
            title="❌ การใช้งานไม่ถูกต้อง",
            description="**การใช้งาน:** `!delcoin <userid> <amount>`\n**ตัวอย่าง:** `!delcoin 900000000000000000 1000`",
            color=0xFF0000
        )
        await ctx.send(embed=embed)
        return
    
    try:
        user_id_str = str(user_id)
        amount_int = int(amount.replace(",", ""))
        
        # Load current balances
        balances = load_balances()
        
        if user_id_str not in balances:
            await ctx.send(f"❌ ไม่พบผู้ใช้ ID {user_id} ในระบบ RNG")
            return
        
        current_balance = balances.get(user_id_str, 0)
        
        if current_balance < amount_int:
            await ctx.send(f"❌ ผู้ใช้มีเงินไม่พอ! ปัจจุบัน: {format_number(current_balance)} 🪙 ต้องการลบ: {format_number(amount_int)} 🪙")
            return
        
        # Remove coins
        success = remove_user_balance(user_id_str, amount_int)
        
        if success:
            new_balance = get_user_balance(user_id_str)
            
            # Try to get user for display name
            try:
                user = await bot.fetch_user(int(user_id_str))
                display_name = user.display_name
            except:
                display_name = f"<@{user_id_str}>"
            
            embed = discord.Embed(
                title="✅ ลบ SushiCoin เรียบร้อย",
                description=f"ลบเงินจำนวน **{format_number(amount_int)}** 🪙 จาก {display_name}",
                color=0x00FF00
            )
            embed.add_field(name="💰 ยอดเงินคงเหลือ", value=f"**{format_number(new_balance)}** 🪙", inline=False)
            
            await ctx.send(embed=embed)
        else:
            await ctx.send("❌ เกิดข้อผิดพลาดในการลบเงิน")
            
    except ValueError:
        await ctx.send("❌ กรุณากรอกจำนวนเงินเป็นตัวเลข", delete_after=5)
    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")

@bot.command()
@admin_only()
async def addcoin(ctx, user_id: str = None, amount: str = None):
    """เพิ่ม SushiCoin ให้ผู้ใช้ !addcoin <userid> <amount>"""
    if not user_id or not amount:
        embed = discord.Embed(
            title="❌ การใช้งานไม่ถูกต้อง",
            description="**การใช้งาน:** `!addcoin <userid> <amount>`\n**ตัวอย่าง:** `!addcoin 900000000000000000 1000`",
            color=0xFF0000
        )
        await ctx.send(embed=embed)
        return
    
    try:
        user_id_str = str(user_id)
        amount_int = int(amount.replace(",", ""))
        
        if amount_int <= 0:
            await ctx.send("❌ กรุณากรอกจำนวนเงินที่มากกว่า 0", delete_after=5)
            return
        
        # Add coins
        new_balance = add_user_balance(user_id_str, amount_int)
        
        # Try to get user for display name
        try:
            user = await bot.fetch_user(int(user_id_str))
            display_name = user.display_name
        except:
            display_name = f"<@{user_id_str}>"
        
        embed = discord.Embed(
            title="✅ เพิ่ม SushiCoin เรียบร้อย",
            description=f"เพิ่มเงินจำนวน **{format_number(amount_int)}** 🪙 ให้ {display_name}",
            color=0x00FF00
        )
        embed.add_field(name="💰 ยอดเงินปัจจุบัน", value=f"**{format_number(new_balance)}** 🪙", inline=False)
        
        await ctx.send(embed=embed)
            
    except ValueError:
        await ctx.send("❌ กรุณากรอกจำนวนเงินเป็นตัวเลข", delete_after=5)
    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")

# ==================== คำสั่ง GIVE ITEM ====================
@bot.command()
@admin_only()
async def give(ctx, item_id: str = None, user_id: str = None, amount: str = None):
    """ให้ไอเทมแก่ผู้ใช้ !give <item_id> <userid> <amount>"""
    if not item_id or not user_id or not amount:
        embed = discord.Embed(
            title="❌ การใช้งานไม่ถูกต้อง",
            description="**การใช้งาน:** `!give <item_id> <userid> <amount>`\n"
                       "**ตัวอย่าง:** `!give myt_1 721699340464160829 50`\n\n"
                       "**รายการ item_id:**\n"
                       "• common_1 - common_10 (Common)\n"
                       "• rare_1 - rare_5 (Rare)\n"
                       "• epic_1 - epic_5 (Epic)\n"
                       "• legendary_1 - legendary_4 (Legendary)\n"
                       "• myt_1 - myt_3 (Mythic)",
            color=0xFF0000
        )
        await ctx.send(embed=embed)
        return
    
    try:
        # ตรวจสอบว่า item_id มีอยู่ใน ITEMS หรือไม่
        if item_id not in ITEMS:
            await ctx.send(f"❌ ไม่พบไอเทม `{item_id}` ในระบบ")
            return
        
        amount_int = int(amount.replace(",", ""))
        if amount_int <= 0:
            await ctx.send("❌ กรุณากรอกจำนวนที่มากกว่า 0", delete_after=5)
            return
        
        user_id_str = str(user_id)
        
        # ตรวจสอบว่าผู้ใช้มีตัวตนใน Discord หรือไม่
        try:
            target_user = await bot.fetch_user(int(user_id_str))
            display_name = target_user.display_name
        except:
            display_name = f"<@{user_id_str}>"
        
        # เพิ่มไอเทมให้ผู้ใช้
        item = ITEMS[item_id]
        add_item_to_inventory(user_id_str, item_id, amount_int)
        
        # สร้าง embed แจ้งเตือน
        embed = discord.Embed(
            title="✅ ให้ไอเทมเรียบร้อย",
            description=f"ให้ {item['emoji']} **{item['name']}** จำนวน **{format_number(amount_int)}** ชิ้น แก่ {display_name}",
            color=0x00FF00
        )
        embed.add_field(
            name="📊 รายละเอียด",
            value=f"**รหัสไอเทม:** `{item_id}`\n"
                  f"**ความหายาก:** {get_rarity_emoji(item['rarity'])} {item['rarity'].upper()}\n"
                  f"**มูลค่าต่อชิ้น:** {format_number(item['value'])} 🪙\n"
                  f"**มูลค่ารวม:** {format_number(item['value'] * amount_int)} 🪙",
            inline=False
        )
        
        # แสดงยอดเงินปัจจุบันของผู้ใช้ (ถ้ามี)
        balance = get_user_balance(user_id_str)
        embed.add_field(
            name="💰 ยอดเงินผู้รับ",
            value=f"**{format_number(balance)}** 🪙",
            inline=False
        )
        
        await ctx.send(embed=embed)
        
    except ValueError:
        await ctx.send("❌ กรุณากรอกจำนวนเงินเป็นตัวเลข", delete_after=5)
    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")

@bot.command()
@admin_only()
async def givelist(ctx):
    """แสดงรายการ item_id ที่สามารถใช้ได้"""
    embed = discord.Embed(
        title="📋 รายการไอเทมสำหรับคำสั่ง !give",
        description="ใช้คำสั่ง `!give <item_id> <userid> <amount>`",
        color=0x00AAFF
    )
    
    # Common items
    common_list = "\n".join([f"`{k}` - {v['emoji']} {v['name']}" for k, v in COMMON_ITEMS.items()])
    embed.add_field(name=f"{get_rarity_emoji('common')} Common (10 รายการ)", value=common_list, inline=False)
    
    # Rare items
    rare_list = "\n".join([f"`{k}` - {v['emoji']} {v['name']}" for k, v in RARE_ITEMS.items()])
    embed.add_field(name=f"{get_rarity_emoji('rare')} Rare (5 รายการ)", value=rare_list, inline=False)
    
    # Epic items
    epic_list = "\n".join([f"`{k}` - {v['emoji']} {v['name']}" for k, v in EPIC_ITEMS.items()])
    embed.add_field(name=f"{get_rarity_emoji('epic')} Epic (5 รายการ)", value=epic_list, inline=False)
    
    # Legendary items
    legendary_list = "\n".join([f"`{k}` - {v['emoji']} {v['name']}" for k, v in LEGENDARY_ITEMS.items()])
    embed.add_field(name=f"{get_rarity_emoji('legendary')} Legendary (4 รายการ)", value=legendary_list, inline=False)
    
    # Mythic items
    mythic_list = "\n".join([f"`{k}` - {v['emoji']} {v['name']}" for k, v in MYTHIC_ITEMS.items()])
    embed.add_field(name=f"{get_rarity_emoji('mythic')} Mythic (3 รายการ)", value=mythic_list, inline=False)
    
    embed.set_footer(text="ตัวอย่าง: !give myt_1 721699340464160829 50")
    
    await ctx.send(embed=embed)

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
        
        # Schedule to remove buyer permission after 10 minutes
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
        
        # Schedule to remove buyer permission after 10 minutes
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
    global group_rate_low, group_rate_high
    
    try:
        expr_clean = expr.replace(",", "").lower().replace("x", "*").replace("÷", "/")
        robux = int(eval(expr_clean))
        # ใช้ 500 บาทเป็นเกณฑ์
        price_baht = robux / group_rate_low
        rate = group_rate_low if price_baht < 500 else group_rate_high
        await ctx.send(f"👥 Group {format_number(robux)} Robux = **{format_number(int(robux/rate))} บาท** (เรท {rate})")
    except:
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
    global group_rate_low, group_rate_high
    
    try:
        baht = float(eval(expr.replace(",", "")))
        # แปลงบาทกลับเป็น Robux โดยใช้ rate ต่ำสุดก่อน
        robux_estimate = baht * group_rate_low
        # ถ้าประมาณการ Robux เกิน 2,250 (ซึ่งเท่ากับ 500 บาทที่ rate 4.5) ให้ใช้ rate สูง
        rate = group_rate_low if robux_estimate < 2250 else group_rate_high
        await ctx.send(f"👥 {format_number(int(baht))} บาท = **{format_number(int(baht * rate))} Robux** (Group เรท {rate})")
    except:
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

# ==================== BALANCE CHECK COMMANDS ====================
@bot.command()
@admin_only()
async def checkbalance(ctx, user_id: str = None):
    """ตรวจสอบยอดเงินของผู้ใช้ (admin only)"""
    if user_id is None:
        user_id = str(ctx.author.id)
    
    try:
        user_id_str = str(user_id)
        balance = get_user_balance(user_id_str)
        
        # Try to get user info
        try:
            user = await bot.fetch_user(int(user_id_str))
            display_name = user.display_name
        except:
            display_name = f"User {user_id_str}"
        
        embed = discord.Embed(
            title="💰 ตรวจสอบยอดเงิน",
            description=f"ผู้ใช้: {display_name}\nยอดเงิน: **{format_number(balance)}** 🪙",
            color=0x00AAFF
        )
        
        # Show if user exists in balances file
        balances = load_balances()
        if user_id_str in balances:
            embed.add_field(name="สถานะ", value="✅ มีข้อมูลในระบบ", inline=False)
        else:
            embed.add_field(name="สถานะ", value="⚠️ กำลังสร้างข้อมูลใหม่", inline=False)
            # Initialize if not exists
            initialize_user_balance(user_id_str)
            new_balance = get_user_balance(user_id_str)
            embed.add_field(name="ยอดเงินใหม่", value=f"**{format_number(new_balance)}** 🪙", inline=False)
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")

@bot.command()
@admin_only()
async def resetbalance(ctx, user_id: str = None):
    """รีเซ็ตยอดเงินผู้ใช้กลับไปที่ 300 (admin only)"""
    if user_id is None:
        user_id = str(ctx.author.id)
    
    try:
        user_id_str = str(user_id)
        balances = load_balances()
        balances[user_id_str] = STARTING_BALANCE
        save_balances(balances)
        
        # Try to get user info
        try:
            user = await bot.fetch_user(int(user_id_str))
            display_name = user.display_name
        except:
            display_name = f"User {user_id_str}"
        
        embed = discord.Embed(
            title="✅ รีเซ็ตยอดเงินเรียบร้อย",
            description=f"ผู้ใช้: {display_name}\nยอดเงินใหม่: **{format_number(STARTING_BALANCE)}** 🪙",
            color=0x00FF00
        )
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")

# ==================== RNG GACHA GAME ====================
ITEMS = {
    # Common (60%) - 10 ชิ้น
    "common_1": {"name": "Apple 🍎", "rarity": "common", "emoji": "🍎", "value": 50},
    "common_2": {"name": "Carrot 🥕", "rarity": "common", "emoji": "🥕", "value": 50},
    "common_3": {"name": "Bread 🍞", "rarity": "common", "emoji": "🍞", "value": 50},
    "common_4": {"name": "Egg 🥚", "rarity": "common", "emoji": "🥚", "value": 50},
    "common_5": {"name": "Milk 🥛", "rarity": "common", "emoji": "🥛", "value": 50},
    "common_6": {"name": "Cheese 🧀", "rarity": "common", "emoji": "🧀", "value": 50},
    "common_7": {"name": "Hamburger 🍔", "rarity": "common", "emoji": "🍔", "value": 50},
    "common_8": {"name": "French Fries 🍟", "rarity": "common", "emoji": "🍟", "value": 50},
    "common_9": {"name": "Hot Dog 🌭", "rarity": "common", "emoji": "🌭", "value": 50},
    "common_10": {"name": "Pizza 🍕", "rarity": "common", "emoji": "🍕", "value": 50},
    
    # Rare (25%) - 5 ชิ้น
    "rare_1": {"name": "Magic Wand 🪄", "rarity": "rare", "emoji": "🪄", "value": 250},
    "rare_2": {"name": "Charm Talisman 🧿", "rarity": "rare", "emoji": "🧿", "value": 250},
    "rare_3": {"name": "Balance Scale ⚖️", "rarity": "rare", "emoji": "⚖️", "value": 250},
    "rare_4": {"name": "Magic Feather 🪶", "rarity": "rare", "emoji": "🪶", "value": 250},
    "rare_5": {"name": "Lucky Envelope 🧧", "rarity": "rare", "emoji": "🧧", "value": 250},
    
    # Epic (10%) - 5 ชิ้น
    "epic_1": {"name": "Diamond 💎", "rarity": "epic", "emoji": "💎", "value": 500},
    "epic_2": {"name": "Crown 👑", "rarity": "epic", "emoji": "👑", "value": 500},
    "epic_3": {"name": "Trident 🔱", "rarity": "epic", "emoji": "🔱", "value": 500},
    "epic_4": {"name": "Money Bag 💰", "rarity": "epic", "emoji": "💰", "value": 500},
    "epic_5": {"name": "Gold Coin 🪙", "rarity": "epic", "emoji": "🪙", "value": 500},
    
    # Legendary (4%) - 4 ชิ้น
    "legendary_1": {"name": "Dragon 🐉", "rarity": "legendary", "emoji": "🐉", "value": 5000},
    "legendary_2": {"name": "Elf 🧝", "rarity": "legendary", "emoji": "🧝", "value": 5000},
    "legendary_3": {"name": "Fairy 🧚", "rarity": "legendary", "emoji": "🧚", "value": 5000},
    "legendary_4": {"name": "Vampire 🧛", "rarity": "legendary", "emoji": "🧛", "value": 5000},
    
    # Mythic (1%) - 3 ชิ้น
    "mythic_1": {"name": "Sushi 🍣", "rarity": "mythic", "emoji": "🍣", "value": 25000},
    "mythic_2": {"name": "Orange Cat 🐱", "rarity": "mythic", "emoji": "🐱", "value": 25000},
    "mythic_3": {"name": "Lucky Black Cat 🐈‍⬛", "rarity": "mythic", "emoji": "🐈‍⬛", "value": 25000},
}

# Group items by rarity
COMMON_ITEMS = {k: v for k, v in ITEMS.items() if v["rarity"] == "common"}
RARE_ITEMS = {k: v for k, v in ITEMS.items() if v["rarity"] == "rare"}
EPIC_ITEMS = {k: v for k, v in ITEMS.items() if v["rarity"] == "epic"}
LEGENDARY_ITEMS = {k: v for k, v in ITEMS.items() if v["rarity"] == "legendary"}
MYTHIC_ITEMS = {k: v for k, v in ITEMS.items() if v["rarity"] == "mythic"}

def load_inventory() -> Dict[str, Dict[str, int]]:
    try:
        if os.path.exists(rng_inventory_file):
            with open(rng_inventory_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"❌ Error loading inventory: {e}")
    return {}

def save_inventory(inventory: Dict[str, Dict[str, int]]):
    try:
        with open(rng_inventory_file, 'w', encoding='utf-8') as f:
            json.dump(inventory, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"❌ Error saving inventory: {e}")

def load_balances() -> Dict[str, int]:
    try:
        if os.path.exists(rng_balance_file):
            with open(rng_balance_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"❌ Error loading balances: {e}")
    return {}

def save_balances(balances: Dict[str, int]):
    try:
        with open(rng_balance_file, 'w', encoding='utf-8') as f:
            json.dump(balances, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"❌ Error saving balances: {e}")

def initialize_user_balance(user_id: str) -> int:
    """Initialize user with starting balance if they don't exist"""
    balances = load_balances()
    if user_id not in balances:
        balances[user_id] = STARTING_BALANCE
        save_balances(balances)
        print(f"✅ Initialized balance for user {user_id}: {STARTING_BALANCE} 🪙")
        return STARTING_BALANCE
    return balances[user_id]

def get_user_balance(user_id: str) -> int:
    balances = load_balances()
    if user_id not in balances:
        return initialize_user_balance(user_id)
    return balances.get(user_id, 0)

def add_user_balance(user_id: str, amount: int) -> int:
    balances = load_balances()
    current = balances.get(user_id, STARTING_BALANCE)
    new_balance = current + amount
    balances[user_id] = new_balance
    save_balances(balances)
    return new_balance

def remove_user_balance(user_id: str, amount: int) -> bool:
    balances = load_balances()
    current = balances.get(user_id, STARTING_BALANCE)
    if current < amount:
        return False
    new_balance = current - amount
    if new_balance == 0:
        balances[user_id] = 0
    else:
        balances[user_id] = new_balance
    save_balances(balances)
    return True

def get_user_inventory(user_id: str) -> Dict[str, int]:
    inventory = load_inventory()
    return inventory.get(user_id, {})

def add_item_to_inventory(user_id: str, item_id: str, amount: int = 1):
    inventory = load_inventory()
    if user_id not in inventory:
        inventory[user_id] = {}
    
    if item_id in inventory[user_id]:
        inventory[user_id][item_id] += amount
    else:
        inventory[user_id][item_id] = amount
    
    save_inventory(inventory)
    return True

def remove_item_from_inventory(user_id: str, item_id: str, amount: int = 1) -> bool:
    inventory = load_inventory()
    if user_id not in inventory:
        return False
    
    if item_id not in inventory[user_id]:
        return False
    
    if inventory[user_id][item_id] < amount:
        return False
    
    inventory[user_id][item_id] -= amount
    if inventory[user_id][item_id] <= 0:
        del inventory[user_id][item_id]
    
    save_inventory(inventory)
    return True

def remove_multiple_items_from_inventory(user_id: str, items: List[Tuple[str, int]]) -> bool:
    """Remove multiple items from inventory at once"""
    inventory = load_inventory()
    if user_id not in inventory:
        return False
    
    # Check if all items are available
    for item_id, amount in items:
        if item_id not in inventory[user_id] or inventory[user_id][item_id] < amount:
            return False
    
    # Remove items
    for item_id, amount in items:
        inventory[user_id][item_id] -= amount
        if inventory[user_id][item_id] <= 0:
            del inventory[user_id][item_id]
    
    save_inventory(inventory)
    return True

def calculate_total_inventory_value(user_id: str) -> int:
    """Calculate total value of all items in user's inventory"""
    inventory = get_user_inventory(user_id)
    total_value = 0
    for item_id, amount in inventory.items():
        if item_id in ITEMS:
            total_value += ITEMS[item_id]["value"] * amount
    return total_value

def random_item() -> tuple[str, dict]:
    """Random item with new rarity chances"""
    roll = random.random() * 100
    
    if roll < 60:  # 60% Common
        item_id = random.choice(list(COMMON_ITEMS.keys()))
        return item_id, COMMON_ITEMS[item_id]
    elif roll < 85:  # 25% Rare (60+25=85)
        item_id = random.choice(list(RARE_ITEMS.keys()))
        return item_id, RARE_ITEMS[item_id]
    elif roll < 95:  # 10% Epic (85+10=95)
        item_id = random.choice(list(EPIC_ITEMS.keys()))
        return item_id, EPIC_ITEMS[item_id]
    elif roll < 99:  # 4% Legendary (95+4=99)
        item_id = random.choice(list(LEGENDARY_ITEMS.keys()))
        return item_id, LEGENDARY_ITEMS[item_id]
    else:  # 1% Mythic
        item_id = random.choice(list(MYTHIC_ITEMS.keys()))
        return item_id, MYTHIC_ITEMS[item_id]

def get_rarity_color(rarity: str) -> int:
    """Return color based on rarity emoji color"""
    if rarity == "common":
        return 0x808080  # grey (⚪)
    elif rarity == "rare":
        return 0x00AAFF  # blue (🔵)
    elif rarity == "epic":
        return 0xAA00FF  # purple (🟣)
    elif rarity == "legendary":
        return 0xFFD700  # gold/yellow (🟡)
    else:  # mythic
        return 0xFF4500  # orange-red (🔴)

def get_rarity_emoji(rarity: str) -> str:
    """Return emoji based on rarity"""
    if rarity == "common":
        return "⚪"
    elif rarity == "rare":
        return "🔵"
    elif rarity == "epic":
        return "🟣"
    elif rarity == "legendary":
        return "🟡"
    else:  # mythic
        return "🔴"

def get_item_price_range(item: dict) -> Tuple[int, int]:
    """Get price range for item based on rarity"""
    if item["rarity"] == "common":
        return (10, 100)
    elif item["rarity"] == "rare":
        return (101, 500)
    elif item["rarity"] == "epic":
        return (501, 1000)
    elif item["rarity"] == "legendary":
        return (1001, 10000)
    else:  # mythic
        return (10001, 50000)

def get_item_price(item: dict) -> int:
    """Generate random price for item based on rarity"""
    min_price, max_price = get_item_price_range(item)
    return random.randint(min_price, max_price)

# ==================== RNG SLASH COMMANDS ====================
@bot.tree.command(name="rng", description="เล่นเกม RNG Sushi Shop (สุ่มไอเทม)")
async def rng_slash(interaction: discord.Interaction):
    # Initialize user balance if needed
    user_id = str(interaction.user.id)
    balance = get_user_balance(user_id)
    
    embed = discord.Embed(
        title="🎲 RNG Sushi Shop",
        description="ยินดีต้อนรับสู่เกมสุ่มไอเทม!\n\nเลือกปุ่มด้านล่างเพื่อเริ่มเล่น",
        color=0x00AAFF
    )
    embed.add_field(
        name="📊 อัตราการสุ่ม", 
        value=(
            f"{get_rarity_emoji('common')} Common 60%\n"
            f"{get_rarity_emoji('rare')} Rare 25%\n"
            f"{get_rarity_emoji('epic')} Epic 10%\n"
            f"{get_rarity_emoji('legendary')} Legendary 4%\n"
            f"{get_rarity_emoji('mythic')} Mythic 1%"
        ), 
        inline=False
    )
    embed.add_field(
        name="💰 ค่าใช้จ่าย", 
        value=f"การสุ่มแต่ละครั้งใช้ {format_number(ROLL_COST)} 🪙\nเงินของคุณ: {format_number(balance)} 🪙",
        inline=False
    )
    embed.set_footer(text=f"ผู้เล่น: {interaction.user.display_name}")
    
    await interaction.response.send_message(embed=embed, view=RNGMainView(interaction.user), ephemeral=True)

class RNGMainView(View):
    def __init__(self, user: discord.User):
        super().__init__(timeout=60)
        self.user = user
        
    @discord.ui.button(label="🎲 สุ่มไอเทม", style=discord.ButtonStyle.success, emoji="🎲", row=0)
    async def roll_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
            return
        
        user_id = str(interaction.user.id)
        balance = get_user_balance(user_id)
        
        # Check if user has enough coins
        if balance < ROLL_COST:
            embed = discord.Embed(
                title="❌ เงินไม่พอ",
                description=f"คุณต้องมี {format_number(ROLL_COST)} 🪙 ในการสุ่มแต่ละครั้ง\nเงินคุณ: {format_number(balance)} 🪙",
                color=0xFF0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Deduct coins
        remove_user_balance(user_id, ROLL_COST)
        
        # สุ่มไอเทม
        item_id, item = random_item()
        add_item_to_inventory(user_id, item_id)
        
        inventory = get_user_inventory(user_id)
        total_items = sum(inventory.values())
        new_balance = get_user_balance(user_id)
        total_value = calculate_total_inventory_value(user_id)
        
        embed = discord.Embed(
            title="🎲 ผลการสุ่ม",
            description=f"คุณได้รับ: {item['emoji']} **{item['name']}**",
            color=get_rarity_color(item["rarity"])
        )
        embed.set_footer(text=f"{get_rarity_emoji(item['rarity'])} {item['rarity'].upper()} | ไอเทมทั้งหมด: {format_number(total_items)} ชิ้น | 🪙 {format_number(new_balance)} | มูลค่ารวม: {format_number(total_value)} 🪙")
        
        # สร้าง View สำหรับปุ่ม "สุ่มต่อ"
        roll_again_view = RollAgainView(self.user, embed)
        
        # แก้ไข embed เดิม
        await interaction.response.edit_message(embed=embed, view=roll_again_view)
        
    @discord.ui.button(label="📦 ดู Inventory", style=discord.ButtonStyle.primary, emoji="📦", row=0)
    async def inventory_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
            return
        
        user_id = str(interaction.user.id)
        inventory = get_user_inventory(user_id)
        balance = get_user_balance(user_id)
        total_value = calculate_total_inventory_value(user_id)
        
        # Create embed even if inventory is empty
        embed = discord.Embed(title="📦 Inventory", color=0x00AAFF)
        
        if not inventory:
            embed.description = "ยังไม่มีไอเทม! กด 🎲 เพื่อสุ่มก่อน"
            embed.add_field(name="💰 ยอดเงิน", value=f"**{format_number(balance)}** 🪙", inline=False)
            embed.set_footer(text=f"ผู้เล่น: {self.user.display_name}")
            
            # Create view with "สุ่มไอเทม" and "กลับ" buttons
            empty_inventory_view = View(timeout=60)
            roll_btn = Button(label="สุ่มไอเทม", style=discord.ButtonStyle.success, emoji="🎲")
            
            async def roll_cb(roll_interaction):
                if roll_interaction.user != self.user:
                    await roll_interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
                    return
                
                # Check balance
                user_id = str(roll_interaction.user.id)
                balance = get_user_balance(user_id)
                
                if balance < ROLL_COST:
                    embed = discord.Embed(
                        title="❌ เงินไม่พอ",
                        description=f"คุณต้องมี {format_number(ROLL_COST)} 🪙 ในการสุ่ม\nเงินคุณ: {format_number(balance)} 🪙",
                        color=0xFF0000
                    )
                    await roll_interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                
                # Deduct coins and roll
                remove_user_balance(user_id, ROLL_COST)
                item_id, item = random_item()
                add_item_to_inventory(user_id, item_id)
                
                inventory = get_user_inventory(user_id)
                total_items = sum(inventory.values())
                new_balance = get_user_balance(user_id)
                total_value = calculate_total_inventory_value(user_id)
                
                embed = discord.Embed(
                    title="🎲 ผลการสุ่ม",
                    description=f"คุณได้รับ: {item['emoji']} **{item['name']}**",
                    color=get_rarity_color(item["rarity"])
                )
                embed.set_footer(text=f"{get_rarity_emoji(item['rarity'])} {item['rarity'].upper()} | ไอเทมทั้งหมด: {format_number(total_items)} ชิ้น | 🪙 {format_number(new_balance)} | มูลค่ารวม: {format_number(total_value)} 🪙")
                
                roll_again_view = RollAgainView(self.user, embed)
                await roll_interaction.response.edit_message(embed=embed, view=roll_again_view)
            
            roll_btn.callback = roll_cb
            empty_inventory_view.add_item(roll_btn)
            
            back_btn = Button(label="กลับ", style=discord.ButtonStyle.secondary, emoji="🔙")
            
            async def back_cb(back_interaction):
                if back_interaction.user != self.user:
                    await back_interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
                    return
                
                main_embed = discord.Embed(
                    title="🎲 RNG Sushi Shop",
                    description="ยินดีต้อนรับสู่เกมสุ่มไอเทม!\n\nเลือกปุ่มด้านล่างเพื่อเริ่มเล่น",
                    color=0x00AAFF
                )
                main_embed.add_field(
                    name="📊 อัตราการสุ่ม", 
                    value=(
                        f"{get_rarity_emoji('common')} Common 60%\n"
                        f"{get_rarity_emoji('rare')} Rare 25%\n"
                        f"{get_rarity_emoji('epic')} Epic 10%\n"
                        f"{get_rarity_emoji('legendary')} Legendary 4%\n"
                        f"{get_rarity_emoji('mythic')} Mythic 1%"
                    ), 
                    inline=False
                )
                main_embed.set_footer(text=f"ผู้เล่น: {self.user.display_name}")
                
                await back_interaction.response.edit_message(embed=main_embed, view=RNGMainView(self.user))
            
            back_btn.callback = back_cb
            empty_inventory_view.add_item(back_btn)
            
            await interaction.response.edit_message(embed=embed, view=empty_inventory_view)
            return
        
        # Prepare items list sorted by value (highest to lowest)
        items_list = []
        for item_id, amount in inventory.items():
            item = ITEMS[item_id]
            items_list.append((item_id, item, amount))
        
        # Sort by value (highest first)
        items_list.sort(key=lambda x: x[1]["value"], reverse=True)
        
        # Group items by rarity for display
        mythic_items = []
        legendary_items = []
        epic_items = []
        rare_items = []
        common_items = []
        
        for item_id, item, amount in items_list:
            if item["rarity"] == "mythic":
                mythic_items.append((item_id, item, amount))
            elif item["rarity"] == "legendary":
                legendary_items.append((item_id, item, amount))
            elif item["rarity"] == "epic":
                epic_items.append((item_id, item, amount))
            elif item["rarity"] == "rare":
                rare_items.append((item_id, item, amount))
            else:
                common_items.append((item_id, item, amount))
        
        # Create display list
        display_items = []
        
        if mythic_items:
            display_items.append(f"**{get_rarity_emoji('mythic')} Mythic**")
            for _, item, amount in mythic_items:
                display_items.append(f"  {item['emoji']} **{item['name']}** x{format_number(amount)} (มูลค่า {format_number(item['value'])} 🪙)")
        
        if legendary_items:
            display_items.append(f"**{get_rarity_emoji('legendary')} Legendary**")
            for _, item, amount in legendary_items:
                display_items.append(f"  {item['emoji']} **{item['name']}** x{format_number(amount)} (มูลค่า {format_number(item['value'])} 🪙)")
        
        if epic_items:
            display_items.append(f"**{get_rarity_emoji('epic')} Epic**")
            for _, item, amount in epic_items:
                display_items.append(f"  {item['emoji']} **{item['name']}** x{format_number(amount)} (มูลค่า {format_number(item['value'])} 🪙)")
        
        if rare_items:
            display_items.append(f"**{get_rarity_emoji('rare')} Rare**")
            for _, item, amount in rare_items:
                display_items.append(f"  {item['emoji']} **{item['name']}** x{format_number(amount)} (มูลค่า {format_number(item['value'])} 🪙)")
        
        if common_items:
            display_items.append(f"**{get_rarity_emoji('common')} Common**")
            for _, item, amount in common_items:
                display_items.append(f"  {item['emoji']} **{item['name']}** x{format_number(amount)} (มูลค่า {format_number(item['value'])} 🪙)")
        
        embed.add_field(
            name="📊 กระเป๋า",
            value=(
                f"{get_rarity_emoji('common')} Common: {format_number(len(common_items))} | "
                f"{get_rarity_emoji('rare')} Rare: {format_number(len(rare_items))} | "
                f"{get_rarity_emoji('epic')} Epic: {format_number(len(epic_items))} | "
                f"{get_rarity_emoji('legendary')} Legendary: {format_number(len(legendary_items))} | "
                f"{get_rarity_emoji('mythic')} Mythic: {format_number(len(mythic_items))}"
            ),
            inline=False
        )
        
        # Split items list if too long
        if len(display_items) > 20:
            first_half = "\n".join(display_items[:10])
            second_half = "\n".join(display_items[10:20])
            embed.add_field(name="📋 รายการไอเทม (1)", value=first_half, inline=False)
            embed.add_field(name="📋 รายการไอเทม (2)", value=second_half, inline=False)
        else:
            embed.add_field(name="📋 รายการไอเทม", value="\n".join(display_items[:20]), inline=False)
        
        embed.add_field(name="💰 การเงิน", value=f"ยอดเงิน: **{format_number(balance)}** 🪙\nมูลค่ารวมไอเทม: **{format_number(total_value)}** 🪙", inline=False)
        
        if len(display_items) > 20:
            embed.set_footer(text=f"แสดง 20 จาก {format_number(len(display_items))} รายการ")
        else:
            embed.set_footer(text=f"ผู้เล่น: {self.user.display_name}")
        
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="🏪 ร้านค้าไอเทม", style=discord.ButtonStyle.secondary, emoji="🏪", row=1)
    async def pawnshop_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="🏪 Sushi Shop",
            description="เลือกประเภทการค้าขายที่ต้องการ",
            color=0x00AAFF
        )
        embed.add_field(
            name="💰 ระบบราคา", 
            value=(
                f"{get_rarity_emoji('common')} Common: {format_number(10)}-{format_number(100)} 🪙\n"
                f"{get_rarity_emoji('rare')} Rare: {format_number(101)}-{format_number(500)} 🪙\n"
                f"{get_rarity_emoji('epic')} Epic: {format_number(501)}-{format_number(1000)} 🪙\n"
                f"{get_rarity_emoji('legendary')} Legendary: {format_number(1001)}-{format_number(10000)} 🪙\n"
                f"{get_rarity_emoji('mythic')} Mythic: {format_number(10001)}-{format_number(50000)} 🪙"
            ), 
            inline=False
        )
        embed.add_field(name="💰 ยอดเงินคุณ", value=f"**{format_number(get_user_balance(str(interaction.user.id)))}** 🪙", inline=False)
        
        pawn_view = PawnShopMainView(self.user)
        await interaction.response.edit_message(embed=embed, view=pawn_view)
    
    @discord.ui.button(label="🏆 Leaderboard", style=discord.ButtonStyle.primary, emoji="🏆", row=2)
    async def leaderboard_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
            return
        
        await show_leaderboard(interaction)
    
    @discord.ui.button(label="ℹ️ วิธีเล่น", style=discord.ButtonStyle.secondary, emoji="ℹ️", row=2)
    async def help_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
            return
        
        embed = discord.Embed(title="🎮 วิธีเล่น RNG Sushi", color=0x00AAFF)
        embed.add_field(
            name="📊 โอกาสได้รับไอเทม",
            value=(
                f"{get_rarity_emoji('common')} Common 60%\n"
                f"{get_rarity_emoji('rare')} Rare 25%\n"
                f"{get_rarity_emoji('epic')} Epic 10%\n"
                f"{get_rarity_emoji('legendary')} Legendary 4%\n"
                f"{get_rarity_emoji('mythic')} Mythic 1%"
            ),
            inline=False
        )
        embed.add_field(
            name="💰 ค่าใช้จ่าย",
            value=f"การสุ่มแต่ละครั้งใช้ {format_number(ROLL_COST)} 🪙\nผู้เล่นใหม่ได้รับ {format_number(STARTING_BALANCE)} 🪙 เริ่มต้น",
            inline=False
        )
        embed.add_field(
            name="🎮 วิธีเล่น",
            value=(
                "• มี 2 โหมด: ขายไอเทม / ซื้อไอเทม\n"
                "• ขายไอเทม = ขายของจากคลังให้ร้าน (เลือกได้สูงสุด 5 ชิ้น)\n"
                "• ซื้อไอเทม = ร้านสุ่มของมาให้เราเลือกซื้อ\n"
                "• ต่อรองราคาได้ครั้งละ ±5% ตามค่าความอดทน\n"
                "• ความพอใจมีผลต่อดีล แต่ยังมีโอกาสสำเร็จแม้พอใจต่ำ"
            ),
            inline=False
        )
        
        await interaction.response.edit_message(embed=embed, view=self)

class RollAgainView(View):
    def __init__(self, user: discord.User, current_embed: discord.Embed):
        super().__init__(timeout=60)
        self.user = user
        self.current_embed = current_embed
    
    @discord.ui.button(label="🎲 สุ่มต่อ", style=discord.ButtonStyle.success, emoji="🎲", row=0)
    async def roll_again_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
            return
        
        user_id = str(interaction.user.id)
        balance = get_user_balance(user_id)
        
        # Check if user has enough coins
        if balance < ROLL_COST:
            embed = discord.Embed(
                title="❌ เงินไม่พอ",
                description=f"คุณต้องมี {format_number(ROLL_COST)} 🪙 ในการสุ่ม\nเงินคุณ: {format_number(balance)} 🪙",
                color=0xFF0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Deduct coins
        remove_user_balance(user_id, ROLL_COST)
        
        # สุ่มไอเทมใหม่
        item_id, item = random_item()
        add_item_to_inventory(user_id, item_id)
        
        inventory = get_user_inventory(user_id)
        total_items = sum(inventory.values())
        new_balance = get_user_balance(user_id)
        total_value = calculate_total_inventory_value(user_id)
        
        new_embed = discord.Embed(
            title="🎲 ผลการสุ่ม",
            description=f"คุณได้รับ: {item['emoji']} **{item['name']}**",
            color=get_rarity_color(item["rarity"])
        )
        new_embed.set_footer(text=f"{get_rarity_emoji(item['rarity'])} {item['rarity'].upper()} | ไอเทมทั้งหมด: {format_number(total_items)} ชิ้น | 🪙 {format_number(new_balance)} | มูลค่ารวม: {format_number(total_value)} 🪙")
        
        # สร้าง View ใหม่สำหรับสุ่มต่อ
        new_roll_view = RollAgainView(self.user, new_embed)
        
        # แก้ไข embed เดิม
        await interaction.response.edit_message(embed=new_embed, view=new_roll_view)
    
    @discord.ui.button(label="🔙 กลับ", style=discord.ButtonStyle.secondary, emoji="🔙", row=0)
    async def back_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
            return
        
        # กลับไปที่หน้า main
        main_embed = discord.Embed(
            title="🎲 RNG Sushi Shop",
            description="ยินดีต้อนรับสู่เกมสุ่มไอเทม!\n\nเลือกปุ่มด้านล่างเพื่อเริ่มเล่น",
            color=0x00AAFF
        )
        main_embed.add_field(
            name="📊 อัตราการสุ่ม", 
            value=(
                f"{get_rarity_emoji('common')} Common 60%\n"
                f"{get_rarity_emoji('rare')} Rare 25%\n"
                f"{get_rarity_emoji('epic')} Epic 10%\n"
                f"{get_rarity_emoji('legendary')} Legendary 4%\n"
                f"{get_rarity_emoji('mythic')} Mythic 1%"
            ), 
            inline=False
        )
        main_embed.set_footer(text=f"ผู้เล่น: {self.user.display_name}")
        
        await interaction.response.edit_message(embed=main_embed, view=RNGMainView(self.user))

# ==================== PAWN SHOP SYSTEM ====================
CUSTOMER_NAMES = [
    "Sunny", "Mawin", "Kirin", "Theo", "Porsche",
    "Praewa", "Milin", "Kana", "Airi", "Nari",
    "Tawan", "Saifah", "Phupha", "Tiwa", "Namfah",
    "Kawin", "Thanwa", "Phakin", "Narin", "Lalin",
    "Mintra", "Ingdao", "Khaohom", "Praemai", "Faylin",
    "Zeno", "Kyro", "Riven", "Nyx", "Aero",
    "Zara", "Mila", "Luna", "Nova", "Aria",
    "Rio", "Leo", "Kai", "Zane", "Axel",
    "Koda", "Sora", "Yuki", "Ren", "Harry",
    "Blaze", "Pixel", "Cosmo", "Orbit", "Astro",
    "Jelly", "Peach", "Creamy", "Blossom", "Candy",
    "Storm", "Flare", "Ember", "Frost", "Spark",
    "Echo", "Vega", "Orion", "Atlas", "Draco",
    "Aiden", "Lucas", "Kevin", "Jayden", "Caleb",
    "Anya", "Zoe", "Amy", "Cara", "Eva"
]

CUSTOMER_AVATARS = [
    "👶", "🧒", "👦", "👧", "🧑‍🦱", "🧑‍🦰", "🧑‍🦳", "🧑‍🦲",
    "👨‍🦱", "👩‍🦱", "👨‍🦰", "👩‍🦰", "👨‍🦳", "👩‍🦳", "👨‍🦲", "👩‍🦲",
    "👮", "👮‍♂️", "👮‍♀️", "🕵️", "🕵️‍♂️", "🕵️‍♀️",
    "👷", "👷‍♂️", "👷‍♀️", "👨‍⚕️", "👩‍⚕️", "🧑‍⚕️",
    "👨‍🏫", "👩‍🏫", "🧑‍🏫", "👨‍🍳", "👩‍🍳", "🧑‍🍳",
    "👨‍💻", "👩‍💻", "🧑‍💻", "👨‍🎓", "👩‍🎓", "🧑‍🎓",
    "🙋", "🙋‍♂️", "🙋‍♀️", "🙆", "🙆‍♂️", "🙆‍♀️",
    "🤷", "🤷‍♂️", "🤷‍♀️", "🙎", "🙎‍♂️", "🙎‍♀️",
    "🙍", "🙍‍♂️", "🙍‍♀️", "💁", "💁‍♂️", "💁‍♀️",
    "🧙", "🧙‍♂️", "🧙‍♀️", "🧛", "🧛‍♂️", "🧛‍♀️",
    "🧝", "🧝‍♂️", "🧝‍♀️", "🧟", "🧟‍♂️", "🧟‍♀️",
    "🧞", "🧞‍♂️", "🧞‍♀️", "🧜", "🧜‍♂️", "🧜‍♀️"
]

class PawnCustomer:
    def __init__(self):
        self.name = random.choice(CUSTOMER_NAMES)
        self.avatar = random.choice(CUSTOMER_AVATARS)
        self.satisfaction = random.randint(30, 100)
        self.patience = random.randint(2, 5)
        self.deal_type = "sell"  # Default to sell (we sell to customer)
        
    def calculate_price_satisfaction(self, offered_price: int, base_price: int) -> Tuple[int, str]:
        price_diff_percent = ((offered_price - base_price) / base_price) * 100
        
        if self.deal_type == "sell":  # เราขายไอเทมให้ร้าน (ลูกค้าซื้อ)
            # เมื่อเราขอเพิ่มราคา (+%) ความพอใจควรลดลง
            # เมื่อเราขอลดราคา (-%) ความพอใจควรเพิ่มขึ้น
            satisfaction_change = -price_diff_percent * 0.5
        else:  # เราซื้อไอเทมจากร้าน (ลูกค้าขาย)
            # เมื่อเราขอซื้อแพงขึ้น (+%) ความพอใจควรเพิ่มขึ้น (ลูกค้าได้เงินมากขึ้น)
            # เมื่อเราขอซื้อถูกลง (-%) ความพอใจควรลดลง (ลูกค้าได้เงินน้อยลง)
            satisfaction_change = price_diff_percent * 0.5
        
        new_satisfaction = self.satisfaction + satisfaction_change
        new_satisfaction = max(0, min(100, new_satisfaction))
        
        if new_satisfaction >= 70:
            emoji = "😄"
        elif new_satisfaction >= 40:
            emoji = "😐"
        else:
            emoji = "😡"
            
        return int(new_satisfaction), emoji
    
    def can_negotiate(self) -> bool:
        return self.patience > 0
    
    def use_patience(self):
        self.patience -= 1

class MultiItemSelect(Select):
    def __init__(self, user: discord.User, items: List[Tuple[str, dict, int]], view):
        self.user = user
        self.parent_view = view
        
        # Sort items by value (highest first)
        items.sort(key=lambda x: x[1]["value"], reverse=True)
        
        options = []
        for item_id, item, amount in items:
            options.append(
                discord.SelectOption(
                    label=f"{item['name']} x{format_number(amount)}",
                    description=f"{get_rarity_emoji(item['rarity'])} {item['rarity'].upper()} | มูลค่า {format_number(item['value'])} 🪙",
                    emoji=item['emoji'],
                    value=item_id
                )
            )
        
        super().__init__(
            placeholder="เลือกไอเทมที่ต้องการขาย (เลือกได้สูงสุด 5 ชิ้น)...",
            options=options,
            min_values=1,
            max_values=min(5, len(options)),
            row=0
        )
    
    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
            return
        
        user_id = str(interaction.user.id)
        selected_ids = self.values
        
        # Get selected items details and sort by value
        selected_items = []
        for item_id in selected_ids:
            item = ITEMS[item_id]
            inventory = get_user_inventory(user_id)
            amount = inventory.get(item_id, 1)
            selected_items.append((item_id, item, amount))
        
        # Sort selected items by value (highest first)
        selected_items.sort(key=lambda x: x[1]["value"], reverse=True)
        
        # Store in parent view
        self.parent_view.selected_items = selected_items
        
        total_value = sum(item[1]["value"] * item[2] for item in selected_items)
        
        # Create display text with numbers
        items_text = []
        for idx, (item_id, item, amount) in enumerate(selected_items, 1):
            items_text.append(f"{idx}. {item['emoji']} **{item['name']}** x{format_number(amount)}")
        
        embed = discord.Embed(
            title="🏪 ขายไอเทม",
            description="\n".join(items_text),
            color=0x00AAFF
        )
        embed.add_field(
            name="💰 มูลค่ารวม",
            value=f"**{format_number(total_value)}** 🪙",
            inline=False
        )
        embed.set_footer(text=f"เลือก {format_number(len(selected_ids))} จาก 5 ชิ้น | กด 'ขาย' เพื่อดำเนินการต่อ")
        
        # Update the message without creating a new view
        await interaction.response.edit_message(embed=embed, view=self.parent_view)

class PawnShopMainView(View):
    def __init__(self, user: discord.User):
        super().__init__(timeout=60)
        self.user = user
        self.selected_items = []
    
    @discord.ui.button(label="💰 ขายไอเทม", style=discord.ButtonStyle.success, emoji="💰", row=0)
    async def sell_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
            return
        
        user_id = str(interaction.user.id)
        inventory = get_user_inventory(user_id)
        
        if not inventory:
            embed = discord.Embed(
                title="🏪 ขายไอเทม",
                description=f"คุณยังไม่มีไอเทม! ไปสุ่มก่อนนะ 🎲\n\n💰 ยอดเงินปัจจุบัน: **{format_number(get_user_balance(user_id))}** 🪙",
                color=0x808080
            )
            
            # Create view with "สุ่มไอเทม" and "กลับ" buttons
            no_items_view = View(timeout=60)
            roll_btn = Button(label="สุ่มไอเทม", style=discord.ButtonStyle.success, emoji="🎲")
            
            async def roll_cb(roll_interaction):
                if roll_interaction.user != self.user:
                    await roll_interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
                    return
                
                # Check balance
                user_id = str(roll_interaction.user.id)
                balance = get_user_balance(user_id)
                
                if balance < ROLL_COST:
                    embed = discord.Embed(
                        title="❌ เงินไม่พอ",
                        description=f"คุณต้องมี {format_number(ROLL_COST)} 🪙 ในการสุ่ม\nเงินคุณ: {format_number(balance)} 🪙",
                        color=0xFF0000
                    )
                    await roll_interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                
                # Deduct coins and roll
                remove_user_balance(user_id, ROLL_COST)
                item_id, item = random_item()
                add_item_to_inventory(user_id, item_id)
                
                inventory = get_user_inventory(user_id)
                total_items = sum(inventory.values())
                new_balance = get_user_balance(user_id)
                total_value = calculate_total_inventory_value(user_id)
                
                embed = discord.Embed(
                    title="🎲 ผลการสุ่ม",
                    description=f"คุณได้รับ: {item['emoji']} **{item['name']}**",
                    color=get_rarity_color(item["rarity"])
                )
                embed.set_footer(text=f"{get_rarity_emoji(item['rarity'])} {item['rarity'].upper()} | ไอเทมทั้งหมด: {format_number(total_items)} ชิ้น | 🪙 {format_number(new_balance)} | มูลค่ารวม: {format_number(total_value)} 🪙")
                
                roll_again_view = RollAgainView(self.user, embed)
                await roll_interaction.response.edit_message(embed=embed, view=roll_again_view)
            
            roll_btn.callback = roll_cb
            no_items_view.add_item(roll_btn)
            
            back_btn = Button(label="กลับ", style=discord.ButtonStyle.secondary, emoji="🔙")
            
            async def back_cb(back_interaction):
                if back_interaction.user != self.user:
                    await back_interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
                    return
                
                main_embed = discord.Embed(
                    title="🎲 RNG Sushi Shop",
                    description="ยินดีต้อนรับสู่เกมสุ่มไอเทม!\n\nเลือกปุ่มด้านล่างเพื่อเริ่มเล่น",
                    color=0x00AAFF
                )
                main_embed.add_field(
                    name="📊 อัตราการสุ่ม", 
                    value=(
                        f"{get_rarity_emoji('common')} Common 60%\n"
                        f"{get_rarity_emoji('rare')} Rare 25%\n"
                        f"{get_rarity_emoji('epic')} Epic 10%\n"
                        f"{get_rarity_emoji('legendary')} Legendary 4%\n"
                        f"{get_rarity_emoji('mythic')} Mythic 1%"
                    ), 
                    inline=False
                )
                main_embed.set_footer(text=f"ผู้เล่น: {self.user.display_name}")
                
                await back_interaction.response.edit_message(embed=main_embed, view=RNGMainView(self.user))
            
            back_btn.callback = back_cb
            no_items_view.add_item(back_btn)
            
            await interaction.response.edit_message(embed=embed, view=no_items_view)
            return
        
        # Prepare items list for selection - sorted by value (highest first)
        items_list = []
        for item_id, amount in inventory.items():
            item = ITEMS[item_id]
            items_list.append((item_id, item, amount))
        
        # Sort by value (highest first)
        items_list.sort(key=lambda x: x[1]["value"], reverse=True)
        
        # Reset selected items
        self.selected_items = []
        
        # Create a new view for the selection
        selection_view = View(timeout=60)
        select = MultiItemSelect(self.user, items_list, self)
        selection_view.add_item(select)
        
        # Create sell button
        sell_btn = Button(label="ขาย", style=discord.ButtonStyle.success, emoji="✅", row=1)
        
        async def sell_callback(sell_interaction: discord.Interaction):
            if sell_interaction.user != self.user:
                await sell_interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
                return
            
            if not self.selected_items:
                await sell_interaction.response.send_message("❌ กรุณาเลือกไอเทมก่อน", ephemeral=True)
                return
            
            user_id = str(sell_interaction.user.id)
            selected_items = self.selected_items
            
            # Calculate total value
            total_value = sum(item[1]["value"] * item[2] for item in selected_items)
            
            # Create customer
            customer = PawnCustomer()
            customer.deal_type = "sell"
            base_price = total_value  # Customer offers total value
            current_balance = get_user_balance(user_id)
            
            # Create items list text
            items_text = []
            for idx, (item_id, item, amount) in enumerate(selected_items, 1):
                items_text.append(f"{idx}. {item['emoji']} **{item['name']}** x{format_number(amount)}")
            
            embed = discord.Embed(
                title=f"🏪 ขายไอเทม {len(selected_items)} ชิ้น",
                description=f"{customer.avatar} **{customer.name}**\nสนใจซื้อไอเทมทั้งหมด\n\n" + "\n".join(items_text),
                color=0x00AAFF
            )
            embed.add_field(
                name="💰 ราคาที่เสนอ",
                value=f"**{format_number(base_price)}** 🪙 (จากมูลค่า {format_number(total_value)} 🪙)",
                inline=False
            )
            embed.add_field(
                name="📊 ข้อมูลลูกค้า",
                value=(
                    f"ความพอใจ: {customer.satisfaction}%\n"
                    f"ความอดทน: {customer.patience} ครั้ง\n"
                    f"มาเพื่อ: 💰 ซื้อไอเทม"
                ),
                inline=False
            )
            embed.add_field(
                name="💰 ยอดเงินคุณ",
                value=f"**{format_number(current_balance)}** 🪙",
                inline=False
            )
            
            # Store deal data
            bot.pawn_data[user_id] = {
                "items": [(item_id, amount) for item_id, item, amount in selected_items],
                "items_detail": selected_items,
                "customer": customer,
                "base_price": base_price,
                "current_price": base_price,
                "deal_type": "sell"
            }
            
            pawn_view = PawnShopDealView(self.user, selected_items, customer, base_price, current_balance, "sell")
            
            # Add Next and Back buttons
            next_btn = Button(label="คนถัดไป", style=discord.ButtonStyle.secondary, emoji="👤", row=2)
            back_btn = Button(label="🔙 กลับ", style=discord.ButtonStyle.secondary, emoji="🔙", row=2)
            
            async def next_callback(next_interaction):
                if next_interaction.user != self.user:
                    await next_interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
                    return
                
                # Create new customer for same items
                new_customer = PawnCustomer()
                new_customer.deal_type = "sell"
                new_base_price = total_value
                current_balance = get_user_balance(user_id)
                
                new_embed = discord.Embed(
                    title=f"🏪 ขายไอเทม {len(selected_items)} ชิ้น",
                    description=f"{new_customer.avatar} **{new_customer.name}**\nสนใจซื้อไอเทมทั้งหมด\n\n" + "\n".join(items_text),
                    color=0x00AAFF
                )
                new_embed.add_field(
                    name="💰 ราคาที่เสนอ",
                    value=f"**{format_number(new_base_price)}** 🪙 (จากมูลค่า {format_number(total_value)} 🪙)",
                    inline=False
                )
                new_embed.add_field(
                    name="📊 ข้อมูลลูกค้า",
                    value=(
                        f"ความพอใจ: {new_customer.satisfaction}%\n"
                        f"ความอดทน: {new_customer.patience} ครั้ง\n"
                        f"มาเพื่อ: 💰 ซื้อไอเทม"
                    ),
                    inline=False
                )
                new_embed.add_field(
                    name="💰 ยอดเงินคุณ",
                    value=f"**{format_number(current_balance)}** 🪙",
                    inline=False
                )
                
                bot.pawn_data[user_id] = {
                    "items": [(item_id, amount) for item_id, item, amount in selected_items],
                    "items_detail": selected_items,
                    "customer": new_customer,
                    "base_price": new_base_price,
                    "current_price": new_base_price,
                    "deal_type": "sell"
                }
                
                new_pawn_view = PawnShopDealView(self.user, selected_items, new_customer, new_base_price, current_balance, "sell")
                
                # Add buttons to new view
                new_next_btn = Button(label="คนถัดไป", style=discord.ButtonStyle.secondary, emoji="👤", row=2)
                new_next_btn.callback = next_callback
                new_pawn_view.add_item(new_next_btn)
                
                new_back_btn = Button(label="🔙 กลับ", style=discord.ButtonStyle.secondary, emoji="🔙", row=2)
                new_back_btn.callback = back_callback
                new_pawn_view.add_item(new_back_btn)
                
                await next_interaction.response.edit_message(embed=new_embed, view=new_pawn_view)
            
            async def back_callback(back_interaction):
                if back_interaction.user != self.user:
                    await back_interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
                    return
                
                # Go back to item selection
                await self.sell_button(back_interaction, None)
            
            next_btn.callback = next_callback
            back_btn.callback = back_callback
            
            pawn_view.add_item(next_btn)
            pawn_view.add_item(back_btn)
            
            await sell_interaction.response.edit_message(embed=embed, view=pawn_view)
        
        sell_btn.callback = sell_callback
        
        # Create back button
        back_btn = Button(label="🔙 กลับ", style=discord.ButtonStyle.secondary, emoji="🔙", row=1)
        
        async def back_callback(back_interaction):
            if back_interaction.user != self.user:
                await back_interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
                return
            
            # กลับไปที่หน้า RNG หลัก
            main_embed = discord.Embed(
                title="🎲 RNG Sushi Shop",
                description="ยินดีต้อนรับสู่เกมสุ่มไอเทม!\n\nเลือกปุ่มด้านล่างเพื่อเริ่มเล่น",
                color=0x00AAFF
            )
            main_embed.add_field(
                name="📊 อัตราการสุ่ม", 
                value=(
                    f"{get_rarity_emoji('common')} Common 60%\n"
                    f"{get_rarity_emoji('rare')} Rare 25%\n"
                    f"{get_rarity_emoji('epic')} Epic 10%\n"
                    f"{get_rarity_emoji('legendary')} Legendary 4%\n"
                    f"{get_rarity_emoji('mythic')} Mythic 1%"
                ), 
                inline=False
            )
            main_embed.set_footer(text=f"ผู้เล่น: {self.user.display_name}")
            
            await back_interaction.response.edit_message(embed=main_embed, view=RNGMainView(self.user))
        
        back_btn.callback = back_callback
        
        selection_view.add_item(sell_btn)
        selection_view.add_item(back_btn)
        
        embed = discord.Embed(
            title="🏪 ขายไอเทม",
            description=f"เลือกไอเทมที่ต้องการขาย (เลือกได้สูงสุด 5 ชิ้น)\n\n💰 ยอดเงินคุณ: **{format_number(get_user_balance(user_id))}** 🪙",
            color=0x00AAFF
        )
        
        await interaction.response.edit_message(embed=embed, view=selection_view)
    
    @discord.ui.button(label="🛒 ซื้อไอเทม", style=discord.ButtonStyle.primary, emoji="🛒", row=0)
    async def buy_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
            return
        
        user_id = str(interaction.user.id)
        
        # สุ่มไอเทมและลูกค้าใหม่
        await self.show_new_buy_deal(interaction, user_id)
    
    async def show_new_buy_deal(self, interaction: discord.Interaction, user_id: str):
        """แสดงดีลซื้อไอเทมใหม่"""
        item_id = random.choice(list(ITEMS.keys()))
        item = ITEMS[item_id]
        item_value = item["value"]
        
        customer = PawnCustomer()
        customer.deal_type = "buy"
        base_price = get_item_price(item)
        current_balance = get_user_balance(user_id)
        
        embed = discord.Embed(
            title=f"🏪 ซื้อ {item['emoji']} {item['name']}",
            description=f"{customer.avatar} **{customer.name}**\nสนใจขาย {item['emoji']} **{item['name']}**",
            color=get_rarity_color(item["rarity"])
        )
        embed.add_field(
            name="💰 ราคาที่เสนอ",
            value=f"**{format_number(base_price)}** 🪙 (จากมูลค่า {format_number(item_value)} 🪙)",
            inline=False
        )
        embed.add_field(
            name="📊 ข้อมูลลูกค้า",
            value=(
                f"ความพอใจ: {customer.satisfaction}%\n"
                f"ความอดทน: {customer.patience} ครั้ง\n"
                f"มาเพื่อ: 💸 ขายไอเทม"
            ),
            inline=False
        )
        embed.add_field(
            name="💰 ยอดเงินคุณ",
            value=f"**{format_number(current_balance)}** 🪙",
            inline=False
        )
        
        bot.pawn_data[user_id] = {
            "item_id": item_id,
            "item": item,
            "item_value": item_value,
            "customer": customer,
            "base_price": base_price,
            "current_price": base_price,
            "deal_type": "buy"
        }
        
        pawn_view = PawnShopDealView(self.user, [(item_id, item, 1)], customer, base_price, current_balance, "buy")
        
        # เพิ่มปุ่ม "คนถัดไป" สำหรับการซื้อ
        next_btn = Button(label="คนถัดไป", style=discord.ButtonStyle.secondary, emoji="👤", row=2)
        
        async def next_callback(next_interaction):
            if next_interaction.user != self.user:
                await next_interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
                return
            await self.show_new_buy_deal(next_interaction, user_id)
        
        next_btn.callback = next_callback
        pawn_view.add_item(next_btn)
        
        back_btn = Button(label="🔙 กลับ", style=discord.ButtonStyle.secondary, emoji="🔙", row=2)
        
        async def back_callback(back_interaction):
            if back_interaction.user != self.user:
                await back_interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="🏪 Sushi Shop",
                description="เลือกประเภทการค้าขายที่ต้องการ",
                color=0x00AAFF
            )
            embed.add_field(
                name="💰 ระบบราคา", 
                value=(
                    f"{get_rarity_emoji('common')} Common: {format_number(10)}-{format_number(100)} 🪙\n"
                    f"{get_rarity_emoji('rare')} Rare: {format_number(101)}-{format_number(500)} 🪙\n"
                    f"{get_rarity_emoji('epic')} Epic: {format_number(501)}-{format_number(1000)} 🪙\n"
                    f"{get_rarity_emoji('legendary')} Legendary: {format_number(1001)}-{format_number(10000)} 🪙\n"
                    f"{get_rarity_emoji('mythic')} Mythic: {format_number(10001)}-{format_number(50000)} 🪙"
                ), 
                inline=False
            )
            embed.add_field(name="💰 ยอดเงินคุณ", value=f"**{format_number(get_user_balance(user_id))}** 🪙", inline=False)
            
            await back_interaction.response.edit_message(embed=embed, view=PawnShopMainView(self.user))
        
        back_btn.callback = back_callback
        
        pawn_view.add_item(back_btn)
        
        await interaction.response.edit_message(embed=embed, view=pawn_view)
    
    @discord.ui.button(label="🔙 กลับ", style=discord.ButtonStyle.secondary, emoji="🔙", row=1)
    async def back_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
            return
        
        # กลับไปที่หน้า RNG หลัก
        main_embed = discord.Embed(
            title="🎲 RNG Sushi Shop",
            description="ยินดีต้อนรับสู่เกมสุ่มไอเทม!\n\nเลือกปุ่มด้านล่างเพื่อเริ่มเล่น",
            color=0x00AAFF
        )
        main_embed.add_field(
            name="📊 อัตราการสุ่ม", 
            value=(
                f"{get_rarity_emoji('common')} Common 60%\n"
                f"{get_rarity_emoji('rare')} Rare 25%\n"
                f"{get_rarity_emoji('epic')} Epic 10%\n"
                f"{get_rarity_emoji('legendary')} Legendary 4%\n"
                f"{get_rarity_emoji('mythic')} Mythic 1%"
            ), 
            inline=False
        )
        main_embed.set_footer(text=f"ผู้เล่น: {self.user.display_name}")
        
        await back_interaction.response.edit_message(embed=main_embed, view=RNGMainView(self.user))

class PawnShopDealView(View):
    def __init__(self, user: discord.User, items: List, customer: PawnCustomer, base_price: int, user_balance: int, action_type: str):
        super().__init__(timeout=120)
        self.user = user
        self.items = items  # List of (item_id, item, amount) or single item
        self.customer = customer
        self.base_price = base_price
        self.current_price = base_price
        self.user_balance = user_balance
        self.action_type = action_type
        
    def check_deal_success(self, satisfaction: int) -> bool:
        if satisfaction >= 70:
            return True
        elif satisfaction >= 50:
            return random.random() < 0.8
        elif satisfaction >= 30:
            return random.random() < 0.5
        elif satisfaction >= 10:
            return random.random() < 0.25
        else:
            return random.random() < 0.1
    
    async def show_new_customer_for_same_items(self, interaction: discord.Interaction):
        """แสดงลูกค้าใหม่สำหรับไอเทมเดิม"""
        if interaction.user != self.user:
            await interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
            return
        
        user_id = str(interaction.user.id)
        
        # สร้างลูกค้าใหม่สำหรับไอเทมเดิม
        new_customer = PawnCustomer()
        new_customer.deal_type = self.action_type
        
        if self.action_type == "sell":
            # For selling multiple items, calculate total value
            total_value = sum(item[1]["value"] * item[2] for item in self.items)
            new_base_price = total_value
            
            # Create items list text
            items_text = []
            for idx, (item_id, item, amount) in enumerate(self.items, 1):
                items_text.append(f"{idx}. {item['emoji']} **{item['name']}** x{format_number(amount)}")
            
            embed = discord.Embed(
                title=f"🏪 ขายไอเทม {len(self.items)} ชิ้น",
                description=f"{new_customer.avatar} **{new_customer.name}**\nสนใจซื้อไอเทมทั้งหมด\n\n" + "\n".join(items_text),
                color=0x00AAFF
            )
            embed.add_field(
                name="💰 ราคาที่เสนอ",
                value=f"**{format_number(new_base_price)}** 🪙 (จากมูลค่า {format_number(total_value)} 🪙)",
                inline=False
            )
        else:
            # For buying single item
            item = self.items[0][1] if isinstance(self.items[0], tuple) else self.items[0]
            item_id = self.items[0][0] if isinstance(self.items[0], tuple) else "unknown"
            item_value = item["value"]
            new_base_price = get_item_price(item)
            
            embed = discord.Embed(
                title=f"🏪 ซื้อ {item['emoji']} {item['name']}",
                description=f"{new_customer.avatar} **{new_customer.name}**\nสนใจขาย {item['emoji']} **{item['name']}**",
                color=get_rarity_color(item["rarity"])
            )
            embed.add_field(
                name="💰 ราคาที่เสนอ",
                value=f"**{format_number(new_base_price)}** 🪙 (จากมูลค่า {format_number(item_value)} 🪙)",
                inline=False
            )
        
        current_balance = get_user_balance(user_id)
        
        embed.add_field(
            name="📊 ข้อมูลลูกค้า",
            value=(
                f"ความพอใจ: {new_customer.satisfaction}%\n"
                f"ความอดทน: {new_customer.patience} ครั้ง\n"
                f"มาเพื่อ: {'💰 ซื้อไอเทม' if self.action_type == 'sell' else '💸 ขายไอเทม'}"
            ),
            inline=False
        )
        embed.add_field(
            name="💰 ยอดเงินคุณ",
            value=f"**{format_number(current_balance)}** 🪙",
            inline=False
        )
        
        # อัปเดต pawn_data
        if self.action_type == "sell":
            bot.pawn_data[user_id] = {
                "items": [(item_id, amount) for item_id, item, amount in self.items],
                "items_detail": self.items,
                "customer": new_customer,
                "base_price": new_base_price,
                "current_price": new_base_price,
                "deal_type": "sell"
            }
        else:
            item = self.items[0][1] if isinstance(self.items[0], tuple) else self.items[0]
            item_id = self.items[0][0] if isinstance(self.items[0], tuple) else "unknown"
            bot.pawn_data[user_id] = {
                "item_id": item_id,
                "item": item,
                "item_value": item["value"],
                "customer": new_customer,
                "base_price": new_base_price,
                "current_price": new_base_price,
                "deal_type": "buy"
            }
        
        # สร้าง view ใหม่
        new_pawn_view = PawnShopDealView(self.user, self.items, new_customer, new_base_price, current_balance, self.action_type)
        
        # เพิ่มปุ่ม "คนถัดไป" ใน view ใหม่
        next_btn = Button(label="คนถัดไป", style=discord.ButtonStyle.secondary, emoji="👤", row=2)
        next_btn.callback = self.show_new_customer_for_same_items
        new_pawn_view.add_item(next_btn)
        
        # เพิ่มปุ่มกลับ
        back_btn = Button(label="🔙 กลับ", style=discord.ButtonStyle.secondary, emoji="🔙", row=2)
        
        async def back_callback(back_interaction):
            if back_interaction.user != self.user:
                await back_interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
                return
            
            # กลับไปที่หน้าเลือกไอเทมขาย
            pawn_main_view = PawnShopMainView(self.user)
            
            if self.action_type == "sell":
                await pawn_main_view.sell_button(back_interaction, None)
            else:
                embed = discord.Embed(
                    title="🏪 Sushi Shop",
                    description="เลือกประเภทการค้าขายที่ต้องการ",
                    color=0x00AAFF
                )
                embed.add_field(
                    name="💰 ระบบราคา", 
                    value=(
                        f"{get_rarity_emoji('common')} Common: {format_number(10)}-{format_number(100)} 🪙\n"
                        f"{get_rarity_emoji('rare')} Rare: {format_number(101)}-{format_number(500)} 🪙\n"
                        f"{get_rarity_emoji('epic')} Epic: {format_number(501)}-{format_number(1000)} 🪙\n"
                        f"{get_rarity_emoji('legendary')} Legendary: {format_number(1001)}-{format_number(10000)} 🪙\n"
                        f"{get_rarity_emoji('mythic')} Mythic: {format_number(10001)}-{format_number(50000)} 🪙"
                    ), 
                    inline=False
                )
                embed.add_field(name="💰 ยอดเงินคุณ", value=f"**{format_number(get_user_balance(user_id))}** 🪙", inline=False)
                
                await back_interaction.response.edit_message(embed=embed, view=PawnShopMainView(self.user))
        
        back_btn.callback = back_callback
        new_pawn_view.add_item(back_btn)
        
        await interaction.response.edit_message(embed=embed, view=new_pawn_view)
        
    @discord.ui.button(label="✅ ตกลง", style=discord.ButtonStyle.success, row=0)
    async def accept_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
            return
        
        user_id = str(interaction.user.id)
        new_satisfaction, emoji = self.customer.calculate_price_satisfaction(self.current_price, self.base_price)
        
        deal_success = self.check_deal_success(new_satisfaction)
        
        if deal_success:
            if self.action_type == "sell":  # เราขาย
                # Prepare items to remove
                items_to_remove = []
                for item_id, item, amount in self.items:
                    items_to_remove.append((item_id, amount))
                
                success = remove_multiple_items_from_inventory(user_id, items_to_remove)
                if success:
                    new_balance = add_user_balance(user_id, self.current_price)
                    
                    # Create items list text for success message
                    items_text = []
                    for idx, (item_id, item, amount) in enumerate(self.items, 1):
                        items_text.append(f"{idx}. {item['emoji']} **{item['name']}** x{format_number(amount)}")
                    
                    embed = discord.Embed(
                        title=f"🤝 ดีลสำเร็จ! {emoji}",
                        description=f"✅ ดีลสำเร็จ! คุณขายไอเทม {len(self.items)} ชิ้น ในราคา {format_number(self.current_price)} 🪙\n\n" + "\n".join(items_text) + f"\n\n💰 ยอดเงินปัจจุบัน: {format_number(new_balance)} 🪙",
                        color=0x00FF00
                    )
                    
                    continue_view = View(timeout=60)
                    
                    # ปุ่ม "ขายไอเทมต่อ"
                    sell_again_btn = Button(label="ขายไอเทมต่อ", emoji="💰", style=discord.ButtonStyle.success)
                    
                    async def sell_again_callback(cont_interaction):
                        if cont_interaction.user != self.user:
                            await cont_interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
                            return
                        
                        # กลับไปที่หน้าเลือกไอเทมขาย
                        pawn_main_view = PawnShopMainView(self.user)
                        await pawn_main_view.sell_button(cont_interaction, None)
                    
                    sell_again_btn.callback = sell_again_callback
                    continue_view.add_item(sell_again_btn)
                    
                    back_to_main_btn = Button(label="🔙 กลับ", emoji="🔙", style=discord.ButtonStyle.secondary)
                    
                    async def back_to_main_callback(cont_interaction):
                        if cont_interaction.user != self.user:
                            await cont_interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
                            return
                        
                        # กลับไปที่หน้า RNG หลัก
                        main_embed = discord.Embed(
                            title="🎲 RNG Sushi Shop",
                            description="ยินดีต้อนรับสู่เกมสุ่มไอเทม!\n\nเลือกปุ่มด้านล่างเพื่อเริ่มเล่น",
                            color=0x00AAFF
                        )
                        main_embed.add_field(
                            name="📊 อัตราการสุ่ม", 
                            value=(
                                f"{get_rarity_emoji('common')} Common 60%\n"
                                f"{get_rarity_emoji('rare')} Rare 25%\n"
                                f"{get_rarity_emoji('epic')} Epic 10%\n"
                                f"{get_rarity_emoji('legendary')} Legendary 4%\n"
                                f"{get_rarity_emoji('mythic')} Mythic 1%"
                            ), 
                            inline=False
                        )
                        main_embed.set_footer(text=f"ผู้เล่น: {self.user.display_name}")
                        
                        await cont_interaction.response.edit_message(embed=main_embed, view=RNGMainView(self.user))
                    
                    back_to_main_btn.callback = back_to_main_callback
                    continue_view.add_item(back_to_main_btn)
                    
                    if user_id in bot.pawn_data:
                        del bot.pawn_data[user_id]
                    
                    await interaction.response.edit_message(embed=embed, view=continue_view)
                else:
                    embed = discord.Embed(
                        title="❌ ไม่มีไอเทมเหลือ",
                        description="คุณไม่มีไอเทมเหลือให้ขายแล้ว! ไปสุ่มไอเทมก่อนนะ 🎲",
                        color=0xFF0000
                    )
                    
                    # Add button to go back to RNG main
                    error_view = View(timeout=60)
                    back_btn = Button(label="🔙 กลับ", style=discord.ButtonStyle.secondary, emoji="🔙")
                    
                    async def back_callback(back_interaction):
                        if back_interaction.user != self.user:
                            await back_interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
                            return
                        
                        main_embed = discord.Embed(
                            title="🎲 RNG Sushi Shop",
                            description="ยินดีต้อนรับสู่เกมสุ่มไอเทม!\n\nเลือกปุ่มด้านล่างเพื่อเริ่มเล่น",
                            color=0x00AAFF
                        )
                        main_embed.add_field(
                            name="📊 อัตราการสุ่ม", 
                            value=(
                                f"{get_rarity_emoji('common')} Common 60%\n"
                                f"{get_rarity_emoji('rare')} Rare 25%\n"
                                f"{get_rarity_emoji('epic')} Epic 10%\n"
                                f"{get_rarity_emoji('legendary')} Legendary 4%\n"
                                f"{get_rarity_emoji('mythic')} Mythic 1%"
                            ), 
                            inline=False
                        )
                        main_embed.set_footer(text=f"ผู้เล่น: {self.user.display_name}")
                        
                        await back_interaction.response.edit_message(embed=main_embed, view=RNGMainView(self.user))
                    
                    back_btn.callback = back_callback
                    error_view.add_item(back_btn)
                    
                    await interaction.response.edit_message(embed=embed, view=error_view)
            else:  # เราซื้อ
                item = self.items[0][1] if isinstance(self.items[0], tuple) else self.items[0]
                item_id = self.items[0][0] if isinstance(self.items[0], tuple) else "unknown"
                
                if remove_user_balance(user_id, self.current_price):
                    add_item_to_inventory(user_id, item_id)
                    new_balance = get_user_balance(user_id)
                    
                    embed = discord.Embed(
                        title=f"🤝 ดีลสำเร็จ! {emoji}",
                        description=f"✅ ดีลสำเร็จ! คุณซื้อ {item['emoji']} **{item['name']}** ในราคา {format_number(self.current_price)} 🪙\n💰 ยอดเงินปัจจุบัน: {format_number(new_balance)} 🪙",
                        color=0x00FF00
                    )
                    
                    continue_view = View(timeout=60)
                    
                    continue_btn = Button(label="🏪 ร้านค้าไอเทม", emoji="🏪", style=discord.ButtonStyle.primary)
                    
                    async def continue_callback(cont_interaction):
                        if cont_interaction.user != self.user:
                            await cont_interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
                            return
                        
                        embed = discord.Embed(
                            title="🏪 Sushi Shop",
                            description="เลือกประเภทการค้าขายที่ต้องการ",
                            color=0x00AAFF
                        )
                        embed.add_field(
                            name="💰 ระบบราคา", 
                            value=(
                                f"{get_rarity_emoji('common')} Common: {format_number(10)}-{format_number(100)} 🪙\n"
                                f"{get_rarity_emoji('rare')} Rare: {format_number(101)}-{format_number(500)} 🪙\n"
                                f"{get_rarity_emoji('epic')} Epic: {format_number(501)}-{format_number(1000)} 🪙\n"
                                f"{get_rarity_emoji('legendary')} Legendary: {format_number(1001)}-{format_number(10000)} 🪙\n"
                                f"{get_rarity_emoji('mythic')} Mythic: {format_number(10001)}-{format_number(50000)} 🪙"
                            ), 
                            inline=False
                        )
                        embed.add_field(name="💰 ยอดเงินคุณ", value=f"**{format_number(get_user_balance(user_id))}** 🪙", inline=False)
                        
                        await cont_interaction.response.edit_message(embed=embed, view=PawnShopMainView(self.user))
                    
                    continue_btn.callback = continue_callback
                    continue_view.add_item(continue_btn)
                    
                    back_to_main_btn = Button(label="🔙 กลับ", emoji="🔙", style=discord.ButtonStyle.secondary)
                    
                    async def back_to_main_callback(cont_interaction):
                        if cont_interaction.user != self.user:
                            await cont_interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
                            return
                        
                        # กลับไปที่หน้า RNG หลัก
                        main_embed = discord.Embed(
                            title="🎲 RNG Sushi Shop",
                            description="ยินดีต้อนรับสู่เกมสุ่มไอเทม!\n\nเลือกปุ่มด้านล่างเพื่อเริ่มเล่น",
                            color=0x00AAFF
                        )
                        main_embed.add_field(
                            name="📊 อัตราการสุ่ม", 
                            value=(
                                f"{get_rarity_emoji('common')} Common 60%\n"
                                f"{get_rarity_emoji('rare')} Rare 25%\n"
                                f"{get_rarity_emoji('epic')} Epic 10%\n"
                                f"{get_rarity_emoji('legendary')} Legendary 4%\n"
                                f"{get_rarity_emoji('mythic')} Mythic 1%"
                            ), 
                            inline=False
                        )
                        main_embed.set_footer(text=f"ผู้เล่น: {self.user.display_name}")
                        
                        await cont_interaction.response.edit_message(embed=main_embed, view=RNGMainView(self.user))
                    
                    back_to_main_btn.callback = back_to_main_callback
                    continue_view.add_item(back_to_main_btn)
                    
                    if user_id in bot.pawn_data:
                        del bot.pawn_data[user_id]
                    
                    await interaction.response.edit_message(embed=embed, view=continue_view)
                else:
                    current_balance = get_user_balance(user_id)
                    await interaction.response.send_message(f"❌ เงินไม่พอ! คุณมี {format_number(current_balance)} 🪙 ต้องการ {format_number(self.current_price)} 🪙", ephemeral=True)
        else:
            embed = discord.Embed(
                title="❌ ดีลล้มเหลว",
                description=f"{emoji} **{self.customer.name}**: ราคานี้ไม่โอเคเลย! ลาก่อน!",
                color=0xFF0000
            )
            
            continue_view = View(timeout=60)
            
            # เพิ่มปุ่ม "คนถัดไป" สำหรับไอเทมเดิมเมื่อดีลล้มเหลว
            next_btn = Button(label="คนถัดไป", style=discord.ButtonStyle.secondary, emoji="👤", row=1)
            next_btn.callback = self.show_new_customer_for_same_items
            continue_view.add_item(next_btn)
            
            continue_btn = Button(label="🏪 ร้านค้าไอเทม", emoji="🏪", style=discord.ButtonStyle.primary, row=1)
            
            async def continue_callback(cont_interaction):
                if cont_interaction.user != self.user:
                    await cont_interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
                    return
                
                embed = discord.Embed(
                    title="🏪 Sushi Shop",
                    description="เลือกประเภทการค้าขายที่ต้องการ",
                    color=0x00AAFF
                )
                embed.add_field(
                    name="💰 ระบบราคา", 
                    value=(
                        f"{get_rarity_emoji('common')} Common: {format_number(10)}-{format_number(100)} 🪙\n"
                        f"{get_rarity_emoji('rare')} Rare: {format_number(101)}-{format_number(500)} 🪙\n"
                        f"{get_rarity_emoji('epic')} Epic: {format_number(501)}-{format_number(1000)} 🪙\n"
                        f"{get_rarity_emoji('legendary')} Legendary: {format_number(1001)}-{format_number(10000)} 🪙\n"
                        f"{get_rarity_emoji('mythic')} Mythic: {format_number(10001)}-{format_number(50000)} 🪙"
                    ), 
                    inline=False
                )
                embed.add_field(name="💰 ยอดเงินคุณ", value=f"**{format_number(get_user_balance(user_id))}** 🪙", inline=False)
                
                await cont_interaction.response.edit_message(embed=embed, view=PawnShopMainView(self.user))
            
            continue_btn.callback = continue_callback
            continue_view.add_item(continue_btn)
            
            back_to_main_btn = Button(label="🔙 กลับ", emoji="🔙", style=discord.ButtonStyle.secondary, row=1)
            
            async def back_to_main_callback(cont_interaction):
                if cont_interaction.user != self.user:
                    await cont_interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
                    return
                
                # กลับไปที่หน้า RNG หลัก
                main_embed = discord.Embed(
                    title="🎲 RNG Sushi Shop",
                    description="ยินดีต้อนรับสู่เกมสุ่มไอเทม!\n\nเลือกปุ่มด้านล่างเพื่อเริ่มเล่น",
                    color=0x00AAFF
                )
                main_embed.add_field(
                    name="📊 อัตราการสุ่ม", 
                    value=(
                        f"{get_rarity_emoji('common')} Common 60%\n"
                        f"{get_rarity_emoji('rare')} Rare 25%\n"
                        f"{get_rarity_emoji('epic')} Epic 10%\n"
                        f"{get_rarity_emoji('legendary')} Legendary 4%\n"
                        f"{get_rarity_emoji('mythic')} Mythic 1%"
                    ), 
                    inline=False
                )
                main_embed.set_footer(text=f"ผู้เล่น: {self.user.display_name}")
                
                await cont_interaction.response.edit_message(embed=main_embed, view=RNGMainView(self.user))
            
            back_to_main_btn.callback = back_to_main_callback
            continue_view.add_item(back_to_main_btn)
            
            user_id = str(interaction.user.id)
            if user_id in bot.pawn_data:
                del bot.pawn_data[user_id]
            
            await interaction.response.edit_message(embed=embed, view=continue_view)
    
    @discord.ui.button(label="❌ ปฏิเสธ", style=discord.ButtonStyle.danger, row=0)
    async def reject_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
            return
        
        user_id = str(interaction.user.id)
        
        embed = discord.Embed(
            title="🚫 ปฏิเสธข้อเสนอ",
            description=f"{self.customer.avatar} **{self.customer.name}**: ไม่เป็นไร ไว้คราวหน้านะครับ/คะ",
            color=0x808080
        )
        
        continue_view = View(timeout=60)
        
        # เพิ่มปุ่ม "คนถัดไป" สำหรับไอเทมเดิมเมื่อปฏิเสธ
        next_btn = Button(label="คนถัดไป", style=discord.ButtonStyle.secondary, emoji="👤", row=1)
        next_btn.callback = self.show_new_customer_for_same_items
        continue_view.add_item(next_btn)
        
        continue_btn = Button(label="🏪 ร้านค้าไอเทม", emoji="🏪", style=discord.ButtonStyle.primary, row=1)
        
        async def continue_callback(cont_interaction):
            if cont_interaction.user != self.user:
                await cont_interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="🏪 Sushi Shop",
                description="เลือกประเภทการค้าขายที่ต้องการ",
                color=0x00AAFF
            )
            embed.add_field(
                name="💰 ระบบราคา", 
                value=(
                    f"{get_rarity_emoji('common')} Common: {format_number(10)}-{format_number(100)} 🪙\n"
                    f"{get_rarity_emoji('rare')} Rare: {format_number(101)}-{format_number(500)} 🪙\n"
                    f"{get_rarity_emoji('epic')} Epic: {format_number(501)}-{format_number(1000)} 🪙\n"
                    f"{get_rarity_emoji('legendary')} Legendary: {format_number(1001)}-{format_number(10000)} 🪙\n"
                    f"{get_rarity_emoji('mythic')} Mythic: {format_number(10001)}-{format_number(50000)} 🪙"
                ), 
                inline=False
            )
            embed.add_field(name="💰 ยอดเงินคุณ", value=f"**{format_number(get_user_balance(user_id))}** 🪙", inline=False)
            
            await cont_interaction.response.edit_message(embed=embed, view=PawnShopMainView(self.user))
        
        continue_btn.callback = continue_callback
        continue_view.add_item(continue_btn)
        
        back_to_main_btn = Button(label="🔙 กลับ", emoji="🔙", style=discord.ButtonStyle.secondary, row=1)
        
        async def back_to_main_callback(cont_interaction):
            if cont_interaction.user != self.user:
                await cont_interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
                return
            
            # กลับไปที่หน้า RNG หลัก
            main_embed = discord.Embed(
                title="🎲 RNG Sushi Shop",
                description="ยินดีต้อนรับสู่เกมสุ่มไอเทม!\n\nเลือกปุ่มด้านล่างเพื่อเริ่มเล่น",
                color=0x00AAFF
            )
            main_embed.add_field(
                name="📊 อัตราการสุ่ม", 
                value=(
                    f"{get_rarity_emoji('common')} Common 60%\n"
                    f"{get_rarity_emoji('rare')} Rare 25%\n"
                    f"{get_rarity_emoji('epic')} Epic 10%\n"
                    f"{get_rarity_emoji('legendary')} Legendary 4%\n"
                    f"{get_rarity_emoji('mythic')} Mythic 1%"
                ), 
                inline=False
            )
            main_embed.set_footer(text=f"ผู้เล่น: {self.user.display_name}")
            
            await cont_interaction.response.edit_message(embed=main_embed, view=RNGMainView(self.user))
        
        back_to_main_btn.callback = back_to_main_callback
        continue_view.add_item(back_to_main_btn)
        
        if user_id in bot.pawn_data:
            del bot.pawn_data[user_id]
        
        await interaction.response.edit_message(embed=embed, view=continue_view)
    
    @discord.ui.button(label="💰 ขอเพิ่ม +5%", style=discord.ButtonStyle.primary, row=1)
    async def increase_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
            return
        
        if not self.customer.can_negotiate():
            await interaction.response.send_message("❌ ลูกค้าหมดความอดทนแล้ว!", ephemeral=True)
            return
        
        increase = math.ceil(self.current_price * 0.05)
        self.current_price += increase
        self.customer.use_patience()
        
        new_satisfaction, emoji = self.customer.calculate_price_satisfaction(self.current_price, self.base_price)
        self.customer.satisfaction = new_satisfaction
        
        # Create items list text for display
        if self.action_type == "sell" and len(self.items) > 1:
            items_text = []
            for idx, (item_id, item, amount) in enumerate(self.items, 1):
                items_text.append(f"{idx}. {item['emoji']} **{item['name']}** x{format_number(amount)}")
            items_display = "\n" + "\n".join(items_text)
        else:
            items_display = ""
        
        embed = discord.Embed(
            title="🤔 ต่อรอง",
            description=(
                f"{self.customer.avatar} **{self.customer.name}**{items_display}\n\n"
                f"ราคาปัจจุบัน: **{format_number(self.current_price)}** 🪙\n"
                f"ความพอใจ: {new_satisfaction}% {emoji}\n"
                f"โอกาสต่อรองเหลือ: {self.customer.patience} ครั้ง"
            ),
            color=0x00AAFF
        )
        
        embed.add_field(
            name="📊 ราคา",
            value=(
                f"ราคาพื้นฐาน: {format_number(self.base_price)} 🪙\n"
                f"ต่าง: {((self.current_price - self.base_price) / self.base_price * 100):+.1f}%"
            ),
            inline=False
        )
        
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="💸 ขอลด -5%", style=discord.ButtonStyle.primary, row=1)
    async def decrease_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
            return
        
        if not self.customer.can_negotiate():
            await interaction.response.send_message("❌ ลูกค้าหมดความอดทนแล้ว!", ephemeral=True)
            return
        
        decrease = math.ceil(self.current_price * 0.05)
        self.current_price = max(1, self.current_price - decrease)
        self.customer.use_patience()
        
        new_satisfaction, emoji = self.customer.calculate_price_satisfaction(self.current_price, self.base_price)
        self.customer.satisfaction = new_satisfaction
        
        # Create items list text for display
        if self.action_type == "sell" and len(self.items) > 1:
            items_text = []
            for idx, (item_id, item, amount) in enumerate(self.items, 1):
                items_text.append(f"{idx}. {item['emoji']} **{item['name']}** x{format_number(amount)}")
            items_display = "\n" + "\n".join(items_text)
        else:
            items_display = ""
        
        embed = discord.Embed(
            title="🤔 ต่อรอง",
            description=(
                f"{self.customer.avatar} **{self.customer.name}**{items_display}\n\n"
                f"ราคาปัจจุบัน: **{format_number(self.current_price)}** 🪙\n"
                f"ความพอใจ: {new_satisfaction}% {emoji}\n"
                f"โอกาสต่อรองเหลือ: {self.customer.patience} ครั้ง"
            ),
            color=0x00AAFF
        )
        
        embed.add_field(
            name="📊 ราคา",
            value=(
                f"ราคาพื้นฐาน: {format_number(self.base_price)} 🪙\n"
                f"ต่าง: {((self.current_price - self.base_price) / self.base_price * 100):+.1f}%"
            ),
            inline=False
        )
        
        await interaction.response.edit_message(embed=embed, view=self)

# ==================== LEADERBOARD SYSTEM ====================
async def show_leaderboard(interaction: discord.Interaction):
    """แสดง leaderboard ผู้เล่นที่มีเงินมากที่สุด 5 อันดับ"""
    balances = load_balances()
    
    if not balances:
        embed = discord.Embed(
            title="🏆 Leaderboard",
            description="ยังไม่มีผู้เล่นที่มีเงินในระบบ",
            color=0xFFD700
        )
        await interaction.response.edit_message(embed=embed, view=RNGMainView(interaction.user))
        return
    
    # Remove duplicate user entries by keeping the highest balance
    unique_balances = {}
    for user_id, balance in balances.items():
        if user_id not in unique_balances or balance > unique_balances[user_id]:
            unique_balances[user_id] = balance
    
    sorted_balances = sorted(unique_balances.items(), key=lambda x: x[1], reverse=True)
    top_5 = sorted_balances[:5]
    
    embed = discord.Embed(
        title="🏆 อันดับผู้เล่นที่มีเงินมากที่สุด",
        description="5 อันดับผู้เล่นที่รวยที่สุดใน RNG Sushi",
        color=0xFFD700
    )
    
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    leaderboard_text = ""
    
    for idx, (user_id, money) in enumerate(top_5):
        try:
            user = await interaction.client.fetch_user(int(user_id))
            username = user.display_name
        except:
            username = f"<@{user_id}>"
        
        medal = medals[idx] if idx < len(medals) else f"{idx+1}."
        leaderboard_text += f"{medal} **{username}** - {format_number(money)} 🪙\n"
    
    embed.add_field(name="💰 อันดับ", value=leaderboard_text, inline=False)
    
    caller_id = str(interaction.user.id)
    caller_balance = unique_balances.get(caller_id, 0)
    
    if caller_balance > 0:
        caller_rank = next((i+1 for i, (uid, _) in enumerate(sorted_balances) if uid == caller_id), None)
        if caller_rank:
            embed.add_field(
                name="📊 อันดับของคุณ",
                value=f"อันดับที่ {caller_rank} | {format_number(caller_balance)} 🪙",
                inline=False
            )
    
    embed.set_footer(text=f"ผู้เล่นทั้งหมด: {len(unique_balances)} คน | เรียกดูโดย: {interaction.user.display_name}")
    
    view = View(timeout=60)
    back_btn = Button(label="🔙 กลับ", style=discord.ButtonStyle.secondary, emoji="🔙")
    
    async def back_callback(back_interaction):
        if back_interaction.user != interaction.user:
            await back_interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
            return
        
        main_embed = discord.Embed(
            title="🎲 RNG Sushi Shop",
            description="ยินดีต้อนรับสู่เกมสุ่มไอเทม!\n\nเลือกปุ่มด้านล่างเพื่อเริ่มเล่น",
            color=0x00AAFF
        )
        main_embed.add_field(
            name="📊 อัตราการสุ่ม", 
            value=(
                f"{get_rarity_emoji('common')} Common 60%\n"
                f"{get_rarity_emoji('rare')} Rare 25%\n"
                f"{get_rarity_emoji('epic')} Epic 10%\n"
                f"{get_rarity_emoji('legendary')} Legendary 4%\n"
                f"{get_rarity_emoji('mythic')} Mythic 1%"
            ), 
            inline=False
        )
        main_embed.set_footer(text=f"ผู้เล่น: {interaction.user.display_name}")
        
        await back_interaction.response.edit_message(embed=main_embed, view=RNGMainView(interaction.user))
    
    back_btn.callback = back_callback
    view.add_item(back_btn)
    
    await interaction.response.edit_message(embed=embed, view=view)

# Slash commands for leaderboard
@bot.tree.command(name="leaderboard", description="ดูอันดับผู้เล่นที่มีเงินมากที่สุด 5 อันดับ")
async def leaderboard_slash(interaction: discord.Interaction):
    balances = load_balances()
    
    if not balances:
        embed = discord.Embed(
            title="🏆 Leaderboard",
            description="ยังไม่มีผู้เล่นที่มีเงินในระบบ",
            color=0xFFD700
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    # Remove duplicate user entries
    unique_balances = {}
    for user_id, balance in balances.items():
        if user_id not in unique_balances or balance > unique_balances[user_id]:
            unique_balances[user_id] = balance
    
    sorted_balances = sorted(unique_balances.items(), key=lambda x: x[1], reverse=True)
    top_5 = sorted_balances[:5]
    
    embed = discord.Embed(
        title="🏆 อันดับผู้เล่นที่มีเงินมากที่สุด",
        description="5 อันดับผู้เล่นที่รวยที่สุดใน RNG Sushi",
        color=0xFFD700
    )
    
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    leaderboard_text = ""
    
    for idx, (user_id, money) in enumerate(top_5):
        try:
            user = await bot.fetch_user(int(user_id))
            username = user.display_name
        except:
            username = f"<@{user_id}>"
        
        medal = medals[idx] if idx < len(medals) else f"{idx+1}."
        leaderboard_text += f"{medal} **{username}** - {format_number(money)} 🪙\n"
    
    embed.add_field(name="💰 อันดับ", value=leaderboard_text, inline=False)
    
    caller_id = str(interaction.user.id)
    caller_balance = unique_balances.get(caller_id, 0)
    
    if caller_balance > 0:
        caller_rank = next((i+1 for i, (uid, _) in enumerate(sorted_balances) if uid == caller_id), None)
        if caller_rank:
            embed.add_field(
                name="📊 อันดับของคุณ",
                value=f"อันดับที่ {caller_rank} | {format_number(caller_balance)} 🪙",
                inline=False
            )
    
    embed.set_footer(text=f"ผู้เล่นทั้งหมด: {len(unique_balances)} คน")
    await interaction.response.send_message(embed=embed)

# ==================== TASKS ====================
@tasks.loop(minutes=1)
async def update_presence():
    await bot.change_presence(
        activity=discord.Game(name="บอทเครื่องคิดเลขและเกม RNG ของ wforr")
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
        activity=discord.Game(name="บอทเครื่องคิดเลขและเกม RNG ของ wforr")
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
