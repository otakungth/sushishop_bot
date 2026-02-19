import os, datetime, discord, re, asyncio, json, traceback, time, aiohttp, logging
import random
import math
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
gamepass_rate = 6.5
group_rate_low = 4
group_rate_high = 4.5
shop_open = True
group_ticket_enabled = True
gamepass_stock = 50000
group_stock = 0

# Channel IDs
MAIN_CHANNEL_ID = 1361044752975532152
SALES_LOG_CHANNEL_ID = 1402993077643120720
CREDIT_CHANNEL_ID = 1363250076549382246
DELIVERED_CATEGORY_ID = 1419565515088597083
ARCHIVED_CATEGORY_ID = 1445086228113264650

# Files
user_data_file = "user_data.json"
ticket_transcripts_file = "ticket_transcripts.json"
ticket_counter_file = "ticket_counter.json"
ticket_robux_data_file = "ticket_robux_data.json"
ticket_customer_data_file = "ticket_customer_data.json"
rng_inventory_file = "rng_inventory.json"
rng_balance_file = "rng_balance.json"

user_data = {}
ticket_transcripts = {}
ticket_robux_data = {}
ticket_customer_data = {}
user_notes = {}
ticket_activity = {}

# ==================== CREDIT CHANNEL QUEUE SYSTEM ====================
credit_channel_queue = asyncio.Queue()
credit_channel_update_task_running = False

# ==================== CREDIT CHANNEL VARIABLES ====================
credit_channel_last_update = 0
credit_channel_update_lock = asyncio.Lock()

LEVELS = {
    1: {"exp": 1, "role_id": 1361555369825927249},
    2: {"exp": 5000, "role_id": 1432070662977093703},
    3: {"exp": 10000, "role_id": 1361555364776247297},
    4: {"exp": 20000, "role_id": 1432075600746643537},
    5: {"exp": 50000, "role_id": 1432075369179254804},
    6: {"exp": 100000, "role_id": 1361554929017294949},
    7: {"exp": 250000, "role_id": 1432077732862492722},
    8: {"exp": 500000, "role_id": 1363882685260365894},
    9: {"exp": 1000000, "role_id": 1406309272786047106}
}

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
        self.ticket_counter = load_json(ticket_counter_file, {"counter": 1, "date": get_thailand_time().strftime("%d%m%y")})
        self.stock_message = None
        self.main_channel_message = None
        self.pawn_data = {}
    
    async def setup_hook(self):
        global user_data, ticket_transcripts, ticket_robux_data, ticket_customer_data
        user_data = load_json(user_data_file, {})
        ticket_transcripts = load_json(ticket_transcripts_file, {})
        ticket_robux_data = load_json(ticket_robux_data_file, {})
        ticket_customer_data = load_json(ticket_customer_data_file, {})
        print(f"✅ Loaded data: {len(user_data)} users, {len(ticket_transcripts)} tickets")

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

async def add_exp(user_id, exp_amount, guild):
    user_id = str(user_id)
    if user_id not in user_data:
        user_data[user_id] = {"exp": 0, "level": 0}
    user_data[user_id]["exp"] += exp_amount
    
    old_level = user_data[user_id]["level"]
    new_level = 0
    
    for lvl, data in sorted(LEVELS.items(), reverse=True):
        if user_data[user_id]["exp"] >= data["exp"]:
            new_level = lvl
            break
    
    user_data[user_id]["level"] = new_level
    save_json(user_data_file, user_data)
    
    if new_level != old_level:
        member = guild.get_member(int(user_id))
        if member:
            if old_level > 0:
                old_role = guild.get_role(LEVELS[old_level]["role_id"])
                if old_role and old_role in member.roles:
                    await member.remove_roles(old_role)
            
            if new_level > 0:
                new_role = guild.get_role(LEVELS[new_level]["role_id"])
                if new_role and new_role not in member.roles:
                    await member.add_roles(new_role)
    
    return new_level, user_data[user_id]["exp"]

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
            name=f"🎮 กดเกมพาส | 📊 Stock: {gamepass_stock:,} {'🟢' if gamepass_stock > 0 else '🔴'}", 
            value=f"```\nเรท: {gamepass_rate} | โรแท้\nเช็คราคาพิมพ์: !gp <จำนวน>\n```", 
            inline=False
        )
        embed.add_field(
            name=f"👥 โรบัคกลุ่ม | 📊 Stock: {group_stock:,} {'🟢' if group_stock > 0 else '🔴'}", 
            value=f"```\nเรท: {group_rate_low} | 500+ บาท เรท {group_rate_high}\n⚠️เข้ากลุ่ม 15 วันก่อนซื้อ⚠️\n```", 
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
        level_btn = Button(label="เลเวลของคุณ", style=discord.ButtonStyle.primary, emoji="⭐")
        
        async def gamepass_cb(i):
            await handle_open_ticket(i, "🍣Sushi Gamepass 🍣", "gamepass")
        
        async def group_cb(i):
            await handle_open_ticket(i, "💰Robux Group💰", "group")
        
        async def notes_cb(i):
            await i.response.send_modal(PersonalNoteModal())
        
        async def level_cb(i):
            await check_user_level(i)
        
        gamepass_btn.callback = gamepass_cb
        group_btn.callback = group_cb
        notes_btn.callback = notes_cb
        level_btn.callback = level_cb
        
        view.add_item(gamepass_btn)
        view.add_item(group_btn)
        view.add_item(notes_btn)
        view.add_item(level_btn)
        
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
            description="ยินดีต้อนรับ Sushi Shop\n\nกรุณากรอกแบบฟอร์มเพื่อสั่งซื้อ", 
            color=0x00FF99
        )
        embed.add_field(name="👤 ผู้ซื้อ", value=interaction.user.mention, inline=False)
        
        if stock_type == "gamepass":
            embed.add_field(
                name="🎮 บริการกดเกมพาส", 
                value=f"📦 โรบัคคงเหลือ: **{gamepass_stock:,}**\n💰 เรท: {gamepass_rate}", 
                inline=False
            )
        else:
            embed.add_field(
                name="👥 บริการโรบัคกลุ่ม", 
                value=f"📦 โรบัคเหลือ: **{group_stock:,}**\n💰 เรท: {group_rate_low} - {group_rate_high}", 
                inline=False
            )
        
        embed.set_footer(text="Sushi Shop • กดปุ่มด้านล่างเพื่อกรอกแบบฟอร์ม")
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
                delivered_category = await guild.create_category("✅ ส่งของแล้ว")
                print(f"✅ สร้าง category ส่งของแล้วใหม่")
        
        await asyncio.sleep(5)
        
        await channel.edit(category=delivered_category)
        print(f"✅ ย้ายตั๋วไปยัง category ส่งของแล้ว")
        return True
        
    except Exception as e:
        print(f"❌ Error moving to delivered category: {e}")
        return False

# ==================== CREDIT CHANNEL WORKER ====================
async def credit_channel_update_worker():
    global credit_channel_update_task_running
    credit_channel_update_task_running = True
    
    while True:
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

# ==================== HANDLE TICKET AFTER TY ====================
async def handle_ticket_after_ty(channel, user, robux_amount=None, customer_name=None):
    try:
        print(f"📝 กำลังจัดการตั๋วหลัง !vouch: {channel.name}")
        guild = channel.guild
        
        if robux_amount is None and str(channel.id) in ticket_robux_data:
            robux_amount = ticket_robux_data[str(channel.id)]
        
        delivered_category = guild.get_channel(DELIVERED_CATEGORY_ID)
        if not delivered_category or not isinstance(delivered_category, discord.CategoryChannel):
            delivered_category = discord.utils.get(guild.categories, id=DELIVERED_CATEGORY_ID)
            if not delivered_category:
                delivered_category = await guild.create_category("✅ ส่งของแล้ว")
                print(f"✅ สร้าง category ส่งของแล้วใหม่")
        
        await bot.channel_edit_rate_limiter.acquire()
        await channel.edit(
            category=delivered_category, 
            reason=f"ย้ายไปห้องส่งของแล้วโดย {user.name if user else 'ระบบ'}"
        )
        print(f"✅ ย้ายตั๋วไปยัง category ส่งของแล้ว")
        
        save_success, filename = await save_ticket_transcript(channel, user, robux_amount, customer_name)
        
        if save_success:
            try:
                await bot.channel_edit_rate_limiter.acquire()
                await channel.edit(name=filename[:100])
                print(f"✅ เปลี่ยนชื่อห้องเป็น: {filename}")
            except Exception as e:
                print(f"⚠️ ไม่สามารถเปลี่ยนชื่อห้อง: {e}")
        
        credit_embed = discord.Embed(
            title="✅ ส่งของเรียบร้อยแล้ว",
            description="🎉 **ขอบคุณที่ใช้บริการร้าน Sushi Shop 🍣**\nฝากให้เครดิตด้วยนะคะ ⭐\n\n⚠️ **หมายเหตุ:** ตั๋วนี้จะถูกลบใน 10 นาที",
            color=0x00FF00
        )
        credit_embed.add_field(
            name="📦 รายละเอียด",
            value=f"**จำนวนโรบัค:** {robux_amount if robux_amount else 'ไม่ระบุ'}\n**ลูกค้า:** {customer_name if customer_name else 'ไม่ระบุ'}",
            inline=False
        )
        credit_embed.set_footer(text="Sushi Shop 🍣")
        credit_embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/717757556889747657/1403684950770847754/noFilter.png")
        
        await channel.send(embed=credit_embed)
        print(f"✅ ส่ง embed ให้เครดิตเรียบร้อย")
        
        credit_channel = bot.get_channel(CREDIT_CHANNEL_ID)
        if credit_channel:
            credit_embed_ch = discord.Embed(
                title="🎉 ส่งของเรียบร้อย",
                description=f"{user.mention if user else 'ลูกค้า'} ได้รับสินค้าแล้ว\n\nพิมพ์ +1 ให้เครดิตด้วยนะคะ ⭐",
                color=0x00FF00
            )
            credit_msg = await credit_channel.send(embed=credit_embed_ch)
            await credit_msg.add_reaction("❤️")
            await credit_msg.add_reaction("🍣")
        
        bot.loop.create_task(move_to_archive_after_delay(channel, user, 600))
        
        return True
        
    except Exception as e:
        print(f"❌ Error in handle_ticket_after_ty: {e}")
        traceback.print_exc()
        return False

async def move_to_archive_after_delay(channel, user, delay_seconds):
    try:
        print(f"⏳ กำลังรอ {delay_seconds} วินาทีก่อนย้ายตั๋ว {channel.name} ไป archive")
        await asyncio.sleep(delay_seconds)
        
        if not channel or channel not in channel.guild.channels:
            print(f"❌ ตั๋ว {channel.name} ไม่มีอยู่แล้ว")
            return
        
        archived_category = channel.guild.get_channel(ARCHIVED_CATEGORY_ID)
        if not archived_category or not isinstance(archived_category, discord.CategoryChannel):
            archived_category = discord.utils.get(channel.guild.categories, id=ARCHIVED_CATEGORY_ID)
            if not archived_category:
                archived_category = await channel.guild.create_category("📁 เก็บถาวร")
                print(f"✅ สร้าง category เก็บถาวรใหม่")
        
        if archived_category:
            if user:
                try:
                    overwrites = channel.overwrites
                    if user in overwrites:
                        overwrites[user].update(read_messages=False)
                        await bot.channel_edit_rate_limiter.acquire()
                        await channel.edit(overwrites=overwrites)
                except Exception as e:
                    print(f"⚠️ ไม่สามารถลบสิทธิ์ view ของผู้ซื้อ: {e}")
            
            await bot.channel_edit_rate_limiter.acquire()
            await channel.edit(category=archived_category, reason="ย้ายไปเก็บถาวรหลังจาก 10 นาที")
            print(f"✅ ย้ายตั๋ว {channel.name} ไปเก็บถาวรเรียบร้อยแล้ว")
            
            try:
                archive_embed = discord.Embed(
                    title="📁 เก็บถาวร", 
                    description=f"ตั๋วนี้ถูกย้ายไปเก็บถาวรเรียบร้อยแล้ว\n\n**ชื่อไฟล์ transcript:** `{channel.name}`", 
                    color=0x808080
                )
                await channel.send(embed=archive_embed)
            except:
                pass
                
    except Exception as e:
        print(f"❌ Error moving to archive: {e}")

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
    
    async def on_submit(self, i):
        global gamepass_rate
        
        try:
            expr = self.robux_amount.value.lower().replace("x", "*").replace("÷", "/")
            if not re.match(r"^[\d\s\+\-\*\/\(\)]+$", expr):
                await i.response.send_message(
                    "❌ กรุณาใส่เฉพาะตัวเลข และเครื่องหมาย + - * / x ÷ ()", 
                    ephemeral=True
                )
                return
            
            robux = int(eval(expr))
            price = robux / gamepass_rate
            
            embed = discord.Embed(title="📨 รายละเอียดการสั่งซื้อ", color=0x00FF99)
            embed.add_field(name="🗺️ ชื่อแมพ", value=self.map_name.value, inline=False)
            embed.add_field(name="🎟 เกมพาส", value=self.gamepass_name.value, inline=False)
            embed.add_field(name="💸 ราคาโรบัค", value=f"{robux:,}", inline=True)
            embed.add_field(name="💰 ราคา", value=f"{price:,.0f} บาท", inline=True)
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
    
    async def on_submit(self, i):
        global group_rate_low, group_rate_high
        
        try:
            robux = int(self.robux_amount.value)
            rate = group_rate_low if robux < 1500 else group_rate_high
            
            embed = discord.Embed(title="📨 รายละเอียดคำสั่งซื้อโรบัคกลุ่ม", color=0x00FF99)
            embed.add_field(name="🪪 ชื่อในเกม", value=self.user_name.value, inline=False)
            embed.add_field(name="💸 จำนวนโรบัค", value=f"{robux:,}", inline=True)
            embed.add_field(name="💰 ราคา", value=f"{robux/rate:,.0f} บาท", inline=True)
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
                    "❌ ผู้ส่งสินค้าต้องแนบไฟล์หลักฐานการส่งสินค้าก่อน !", 
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
                    
                    receipt_embed = discord.Embed(
                        title=f"🍣 ใบเสร็จการสั่งซื้อ ({self.product_type}) 🍣", 
                        color=receipt_color
                    )
                    receipt_embed.add_field(
                        name="😊 ผู้ซื้อ", 
                        value=self.buyer.mention if self.buyer else "ไม่ทราบ", 
                        inline=False
                    )
                    receipt_embed.add_field(
                        name="💸 จำนวนโรบัค", 
                        value=f"{self.robux_amount:,}", 
                        inline=True
                    )
                    receipt_embed.add_field(
                        name="💰 ราคาตามเรท", 
                        value=f"{self.price:,.0f} บาท", 
                        inline=True
                    )
                    
                    if delivery_image:
                        receipt_embed.set_image(url=delivery_image)
                    
                    receipt_embed.set_footer(
                        text=f"จัดส่งสินค้าสำเร็จ 🤗 • {get_thailand_time().strftime('%d/%m/%y, %H:%M')}"
                    )
                    
                    log_channel = bot.get_channel(SALES_LOG_CHANNEL_ID)
                    if log_channel:
                        await log_channel.send(embed=receipt_embed)
                    
                    await self.channel.send(embed=receipt_embed)
                    await self.channel.send("✅ **ส่งสินค้าเรียบร้อย**")
                    
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
                    "📝 กรุณาแนบไฟล์หลักฐานการส่งสินค้าใหม่ แล้วกดปุ่ม 'ส่งสินค้าแล้ว ✅' อีกครั้ง", 
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
@bot.command(name="shop_open")
@admin_only()
async def shop_open_cmd(ctx):
    global shop_open
    shop_open = True
    
    try:
        await ctx.message.delete()
    except:
        pass
    
    await update_channel_name()
    await update_main_channel()
    
    embed = discord.Embed(
        title="✅ เปิดร้านเรียบร้อย", 
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
        embed.add_field(name="🎮 Gamepass Stock", value=f"**{gamepass_stock:,}**", inline=True)
        embed.add_field(name="👥 Group Stock", value=f"**{group_stock:,}**", inline=True)
        await ctx.send(embed=embed)
        
    elif stock_type.lower() in ["gp", "gamepass", "เกมพาส"]:
        if amount is None:
            embed = discord.Embed(title="🎮 Gamepass Stock", description=f"**{gamepass_stock:,}**", color=0x00FF99)
            await ctx.send(embed=embed)
        else:
            try:
                gamepass_stock = int(amount.replace(",", ""))
                embed = discord.Embed(
                    title="✅ ตั้งค่า Stock เรียบร้อย", 
                    description=f"ตั้งค่า สต๊อกเกมพาส เป็น **{gamepass_stock:,}** เรียบร้อยแล้ว", 
                    color=0x00FF00
                )
                await ctx.send(embed=embed)
                await update_main_channel()
            except ValueError:
                await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)
            
    elif stock_type.lower() in ["g", "group", "กรุ๊ป"]:
        if amount is None:
            embed = discord.Embed(title="👥 Group Stock", description=f"**{group_stock:,}**", color=0x00FF99)
            await ctx.send(embed=embed)
        else:
            try:
                group_stock = int(amount.replace(",", ""))
                embed = discord.Embed(
                    title="✅ ตั้งค่า Stock เรียบร้อย", 
                    description=f"ตั้งค่า สต๊อกโรบัคกลุ่ม เป็น **{group_stock:,}** เรียบร้อยแล้ว", 
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
        embed = discord.Embed(
            title="✅ เปิดปุ่มตั๋วโรกลุ่ม", 
            description="เปิดปุ่มตั๋วโรกลุ่มแล้ว", 
            color=0x00FF00
        )
        await ctx.send(embed=embed)
        await update_main_channel()
        
    elif status.lower() in ["off", "disable", "ปิด"]:
        group_ticket_enabled = False
        embed = discord.Embed(
            title="❌ ปิดปุ่มตั๋วโรกลุ่ม", 
            description="ปิดปุ่มตั๋วโรกลุ่มแล้ว", 
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
        embed.add_field(name="👥 Group Rate", value=f"**{group_rate_low} - {group_rate_high}**", inline=True)
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
            embed = discord.Embed(
                title="✅ เปลี่ยนเรทโรกลุ่มเรียบร้อย", 
                description=f"ตั้งค่าเรทโรกลุ่มเป็น **{group_rate_low} - {group_rate_high}** เรียบร้อยแล้ว", 
                color=0x00FF00
            )
            await ctx.send(embed=embed)
            await update_main_channel()
        except ValueError:
            await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)
        
    else:
        try:
            gamepass_rate = float(rate_type)
            embed = discord.Embed(
                title="✅ เปลี่ยนเรทเกมพาสเรียบร้อย", 
                description=f"ตั้งค่าเรทเกมพาสเป็น **{gamepass_rate}** เรียบร้อยแล้ว", 
                color=0x00FF00
            )
            await ctx.send(embed=embed)
            await update_main_channel()
        except ValueError:
            await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)

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
        
        robux_amount = ticket_robux_data.get(str(ctx.channel.id))
        customer_name = ticket_customer_data.get(str(ctx.channel.id))
        
        await move_to_delivered_category(ctx.channel, buyer)
        
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
        
        await update_main_channel()
        bot.loop.create_task(move_to_archive_after_delay(ctx.channel, buyer, 600))
        
        print(f"✅ คำสั่ง !vouch ดำเนินการสำเร็จสำหรับห้อง {ctx.channel.name}")
        
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดใน !vouch: {e}")
        traceback.print_exc()
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=5)

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
        
        if buyer:
            await add_exp(buyer.id, robux, ctx.guild)
        
        async with bot.stock_lock:
            gamepass_stock = max(0, gamepass_stock - robux)
        
        ticket_robux_data[str(ctx.channel.id)] = str(robux)
        save_json(ticket_robux_data_file, ticket_robux_data)
        
        embed = discord.Embed(title="🍣คำสั่งซื้อสินค้า🍣", color=0xFFA500)
        embed.add_field(name="📦 ประเภทสินค้า", value="Gamepass", inline=False)
        embed.add_field(name="💸 จำนวนโรบัค", value=f"{robux:,}", inline=True)
        embed.add_field(name="💰 ราคาตามเรท", value=f"{price:,.0f} บาท", inline=True)
        embed.set_footer(text=f"รับออร์เดอร์แล้ว 🤗 • {get_thailand_time().strftime('%d/%m/%y, %H:%M')}")
        
        await ctx.send(embed=embed, view=DeliveryView(ctx.channel, "Gamepass", robux, price, buyer))
        
        # ส่งใบเสร็จไปยัง DM ผู้ซื้อ (เฉพาะคำสั่ง !od เท่านั้น) พร้อมรูปภาพ
        if buyer:
            try:
                delivery_image = None
                async for msg in ctx.channel.history(limit=20):
                    if msg.attachments:
                        for att in msg.attachments:
                            if any(att.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif']):
                                delivery_image = att.url
                                break
                        if delivery_image:
                            break
                
                dm_embed = discord.Embed(
                    title=f"🧾 ใบเสร็จการซื้อสินค้า (Gamepass)",
                    description="ขอบคุณที่ใช้บริการ Sushi Shop นะคะ 🍣",
                    color=0xFFA500
                )
                dm_embed.add_field(name="📦 สินค้า", value="Gamepass", inline=True)
                dm_embed.add_field(name="💸 จำนวนโรบัค", value=f"{robux:,}", inline=True)
                dm_embed.add_field(name="💰 ราคา", value=f"{price:,.0f} บาท", inline=True)
                
                if delivery_image:
                    dm_embed.set_image(url=delivery_image)
                
                dm_embed.add_field(
                    name="📝 หมายเหตุ", 
                    value="หากมีปัญหากรุณาติดต่อแอดมินในเซิร์ฟ", 
                    inline=False
                )
                dm_embed.set_footer(text="Sushi Shop • ขอบคุณที่ใช้บริการ💖")
                
                await buyer.send(embed=dm_embed)
                print(f"✅ ส่งใบเสร็จไปยัง DM ของ {buyer.name} เรียบร้อย")
            except Exception as e:
                print(f"⚠️ ไม่สามารถส่ง DM ถึง {buyer.name}: {e}")
        
        await update_main_channel()
        
    except Exception as e:
        print(f"❌ Error in !od: {e}")
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=10)

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
        rate = group_rate_low if robux < 1500 else group_rate_high
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
        
        if buyer:
            await add_exp(buyer.id, robux, ctx.guild)
        
        async with bot.stock_lock:
            group_stock = max(0, group_stock - robux)
        
        ticket_robux_data[str(ctx.channel.id)] = str(robux)
        save_json(ticket_robux_data_file, ticket_robux_data)
        
        embed = discord.Embed(title="🍣คำสั่งซื้อสินค้า🍣", color=0x00FFFF)
        embed.add_field(name="📦 ประเภทสินค้า", value="Group", inline=False)
        embed.add_field(name="💸 จำนวนโรบัค", value=f"{robux:,}", inline=True)
        embed.add_field(name="💰 ราคาตามเรท", value=f"{price:,.0f} บาท", inline=True)
        embed.set_footer(text=f"รับออร์เดอร์แล้ว 🤗 • {get_thailand_time().strftime('%d/%m/%y, %H:%M')}")
        
        await ctx.send(embed=embed, view=DeliveryView(ctx.channel, "Group", robux, price, buyer))
        
        # ส่งใบเสร็จไปยัง DM ผู้ซื้อ (เฉพาะคำสั่ง !odg เท่านั้น) พร้อมรูปภาพ
        if buyer:
            try:
                delivery_image = None
                async for msg in ctx.channel.history(limit=20):
                    if msg.attachments:
                        for att in msg.attachments:
                            if any(att.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif']):
                                delivery_image = att.url
                                break
                        if delivery_image:
                            break
                
                dm_embed = discord.Embed(
                    title=f"🧾 ใบเสร็จการซื้อสินค้า (Group)",
                    description="ขอบคุณที่ใช้บริการ Sushi Shop นะคะ 🍣",
                    color=0x00FFFF
                )
                dm_embed.add_field(name="📦 สินค้า", value="Group", inline=True)
                dm_embed.add_field(name="💸 จำนวนโรบัค", value=f"{robux:,}", inline=True)
                dm_embed.add_field(name="💰 ราคา", value=f"{price:,.0f} บาท", inline=True)
                
                if delivery_image:
                    dm_embed.set_image(url=delivery_image)
                
                dm_embed.add_field(
                    name="📝 หมายเหตุ", 
                    value="หากมีปัญหากรุณาติดต่อแอดมินในเซิร์ฟ", 
                    inline=False
                )
                dm_embed.set_footer(text="Sushi Shop • ขอบคุณที่ใช้บริการ💖")
                
                await buyer.send(embed=dm_embed)
                print(f"✅ ส่งใบเสร็จไปยัง DM ของ {buyer.name} เรียบร้อย")
            except Exception as e:
                print(f"⚠️ ไม่สามารถส่ง DM ถึง {buyer.name}: {e}")
        
        await update_main_channel()
        
    except Exception as e:
        print(f"❌ Error in !odg: {e}")
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=10)

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
        name="1. ชื่อบัญชี (ธนาคาร SCB)", 
        value="**หจก. วอเตอร์ เทค เซลล์ แอนด์ เซอร์วิส**", 
        inline=False
    )
    embed.add_field(
        name="2. เลขบัญชี", 
        value="**120-239181-3**", 
        inline=False
    )
    embed.set_image(url="https://media.discordapp.net/attachments/1361004239043821610/1473323355791949948/Sushi_SCB.png")
    
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
        await ctx.send(f"🎮 Gamepass {robux:,} Robux = **{robux/gamepass_rate:,.0f} บาท** (เรท {gamepass_rate})")
    except:
        await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)

@bot.command()
async def g(ctx, *, expr):
    global group_rate_low, group_rate_high
    
    try:
        expr_clean = expr.replace(",", "").lower().replace("x", "*").replace("÷", "/")
        robux = int(eval(expr_clean))
        rate = group_rate_low if robux < 2250 else group_rate_high
        await ctx.send(f"👥 Group {robux:,} Robux = **{robux/rate:,.0f} บาท** (เรท {rate})")
    except:
        await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)

@bot.command()
async def gpb(ctx, *, expr):
    global gamepass_rate
    
    try:
        baht = float(eval(expr.replace(",", "")))
        await ctx.send(f"🎮 {baht:,.0f} บาท = **{baht * gamepass_rate:,.0f} Robux** (Gamepass เรท {gamepass_rate})")
    except:
        await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)

@bot.command()
async def gb(ctx, *, expr):
    global group_rate_low, group_rate_high
    
    try:
        baht = float(eval(expr.replace(",", "")))
        rate = group_rate_low if baht < 500 else group_rate_high
        await ctx.send(f"👥 {baht:,.0f} บาท = **{baht * rate:,.0f} Robux** (Group เรท {rate})")
    except:
        await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)

@bot.command()
async def tax(ctx, *, expr):
    try:
        expr = expr.replace(" ", "")
        if re.match(r"^\d+$", expr):
            number = int(expr)
            await ctx.send(f"💰 {number:,} โรบัคที่ได้หลังหัก 30% = **{number * 0.7:,.0f} Robux**")
        elif m := re.match(r"^(\d+)-(\d+)%$", expr):
            number = int(m[1])
            percent = int(m[2])
            await ctx.send(f"💰 {number:,} โรบัคที่ได้หลังหัก {percent}% = **{number * (1 - percent/100):,.0f} Robux**")
        else:
            await ctx.send(
                "❌ รูปแบบไม่ถูกต้อง\n\n**การใช้งาน:**\n`!tax 100` - หัก 30% อัตโนมัติ\n`!tax 100-30%` - หัก 30%\n`!tax 100-50%` - หัก 50%", 
                delete_after=15
            )
    except:
        await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)

@bot.command()
async def level(ctx, member=None):
    if isinstance(member, str):
        member = ctx.guild.get_member_named(member) or ctx.author
    elif member is None:
        member = ctx.author
    
    user_id = str(member.id)
    if user_id not in user_data:
        user_data[user_id] = {"exp": 0, "level": 0}
    
    user_exp = user_data[user_id]["exp"]
    user_level = user_data[user_id]["level"]
    
    embed = discord.Embed(title=f"🍣 ระดับของคุณ {member.display_name}", color=0x00FF99)
    
    if user_level > 0:
        embed.add_field(name="🎮 ระดับปัจจุบัน", value=f"<@&{LEVELS[user_level]['role_id']}>", inline=True)
    else:
        embed.add_field(name="🎮 ระดับปัจจุบัน", value="Level 0", inline=True)
    
    embed.add_field(name="⭐ EXP สะสม", value=f"**{user_exp:,} EXP**", inline=True)
    
    if user_level < 9:
        next_exp = LEVELS[user_level + 1]["exp"]
        embed.add_field(
            name="🎯 ระดับถัดไป", 
            value=f"ต้องการอีก **{next_exp - user_exp:,} EXP** เพื่อยศ <@&{LEVELS[user_level + 1]['role_id']}>", 
            inline=False
        )
        
        current_level_exp = LEVELS[user_level]["exp"] if user_level > 0 else 0
        progress = user_exp - current_level_exp
        total = next_exp - current_level_exp
        
        if total > 0:
            pct = (progress / total * 100)
            bar_count = int(pct / 20)
            bar = "🟢" * bar_count + "⚫" * (5 - bar_count)
            embed.add_field(name="🌱 ความคืบหน้า", value=f"{bar} {pct:.1f}%", inline=False)
    else:
        embed.add_field(name="🏆 สูงสุดแล้ว!", value="คุณถึงระดับสูงสุดแล้ว! 🎉", inline=False)
    
    embed.set_footer(text="ได้รับ EXP จากการซื้อสินค้าในร้าน")
    await ctx.send(embed=embed)

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

# ==================== RNG GACHA GAME (SLASH COMMANDS ONLY) ====================
ITEMS = {
    # Common (50%) - 25 ชิ้น
    "common_1": {"name": "🍎 แอปเปิล", "rarity": "common", "emoji": "🍎", "value": 1},
    "common_2": {"name": "🍌 กล้วย", "rarity": "common", "emoji": "🍌", "value": 1},
    "common_3": {"name": "🍒 เชอร์รี่", "rarity": "common", "emoji": "🍒", "value": 1},
    "common_4": {"name": "🥕 แครอท", "rarity": "common", "emoji": "🥕", "value": 1},
    "common_5": {"name": "🥦 บร็อคโคลี่", "rarity": "common", "emoji": "🥦", "value": 1},
    "common_6": {"name": "🍞 ขนมปัง", "rarity": "common", "emoji": "🍞", "value": 1},
    "common_7": {"name": "🥚 ไข่", "rarity": "common", "emoji": "🥚", "value": 1},
    "common_8": {"name": "🥛 นม", "rarity": "common", "emoji": "🥛", "value": 1},
    "common_9": {"name": "🧀 ชีส", "rarity": "common", "emoji": "🧀", "value": 1},
    "common_10": {"name": "🍗 ไก่ทอด", "rarity": "common", "emoji": "🍗", "value": 1},
    "common_11": {"name": "🍖 ซี่โครง", "rarity": "common", "emoji": "🍖", "value": 1},
    "common_12": {"name": "🥩 สเต็ก", "rarity": "common", "emoji": "🥩", "value": 1},
    "common_13": {"name": "🍔 แฮมเบอร์เกอร์", "rarity": "common", "emoji": "🍔", "value": 1},
    "common_14": {"name": "🍟 เฟรนช์ฟรายส์", "rarity": "common", "emoji": "🍟", "value": 1},
    "common_15": {"name": "🌭 ฮอทดอก", "rarity": "common", "emoji": "🌭", "value": 1},
    "common_16": {"name": "🍕 พิซซ่า", "rarity": "common", "emoji": "🍕", "value": 1},
    "common_17": {"name": "🌮 ทาโก้", "rarity": "common", "emoji": "🌮", "value": 1},
    "common_18": {"name": "🌯 เบอร์ริโต", "rarity": "common", "emoji": "🌯", "value": 1},
    "common_19": {"name": "🥗 สลัด", "rarity": "common", "emoji": "🥗", "value": 1},
    "common_20": {"name": "🍜 ราเมน", "rarity": "common", "emoji": "🍜", "value": 1},
    "common_21": {"name": "🍣 ซูชิ", "rarity": "common", "emoji": "🍣", "value": 1},
    "common_22": {"name": "🍱 ข้าวกล่อง", "rarity": "common", "emoji": "🍱", "value": 1},
    "common_23": {"name": "🍛 แกงกะหรี่", "rarity": "common", "emoji": "🍛", "value": 1},
    "common_24": {"name": "🍚 ข้าวสวย", "rarity": "common", "emoji": "🍚", "value": 1},
    "common_25": {"name": "🍥 นารูโตะมากิ", "rarity": "common", "emoji": "🍥", "value": 1},
    
    # Rare (45%) - 15 ชิ้น
    "rare_1": {"name": "⚔️ ดาบไม้", "rarity": "rare", "emoji": "⚔️", "value": 5},
    "rare_2": {"name": "🛡️ โล่ไม้", "rarity": "rare", "emoji": "🛡️", "value": 5},
    "rare_3": {"name": "🏹 ธนู", "rarity": "rare", "emoji": "🏹", "value": 5},
    "rare_4": {"name": "🔮 ลูกแก้ววิเศษ", "rarity": "rare", "emoji": "🔮", "value": 5},
    "rare_5": {"name": "📜 ม้วนคัมภีร์", "rarity": "rare", "emoji": "📜", "value": 5},
    "rare_6": {"name": "🧪 ยาน้ำ", "rarity": "rare", "emoji": "🧪", "value": 5},
    "rare_7": {"name": "⚱️ โถโบราณ", "rarity": "rare", "emoji": "⚱️", "value": 5},
    "rare_8": {"name": "💎 เพทาย", "rarity": "rare", "emoji": "💎", "value": 5},
    "rare_9": {"name": "👑 มงกุฎทอง", "rarity": "rare", "emoji": "👑", "value": 5},
    "rare_10": {"name": "🔑 กุญแจทอง", "rarity": "rare", "emoji": "🔑", "value": 5},
    "rare_11": {"name": "⏳ นาฬิกาทราย", "rarity": "rare", "emoji": "⏳", "value": 5},
    "rare_12": {"name": "🧭 เข็มทิศ", "rarity": "rare", "emoji": "🧭", "value": 5},
    "rare_13": {"name": "💡 ตะเกียงวิเศษ", "rarity": "rare", "emoji": "💡", "value": 5},
    "rare_14": {"name": "🎭 หน้ากาก", "rarity": "rare", "emoji": "🎭", "value": 5},
    "rare_15": {"name": "🎨 พู่กันวิเศษ", "rarity": "rare", "emoji": "🎨", "value": 5},
    
    # Legendary (5%) - 10 ชิ้น
    "leg_1": {"name": "🐉 มังกรน้อย", "rarity": "legendary", "emoji": "🐉", "value": 50},
    "leg_2": {"name": "🦄 ยูนิคอร์น", "rarity": "legendary", "emoji": "🦄", "value": 50},
    "leg_3": {"name": "🧝 เอลฟ์", "rarity": "legendary", "emoji": "🧝", "value": 50},
    "leg_4": {"name": "🧙 พ่อมด", "rarity": "legendary", "emoji": "🧙", "value": 50},
    "leg_5": {"name": "🦹 ซูเปอร์ฮีโร่", "rarity": "legendary", "emoji": "🦹", "value": 50},
    "leg_6": {"name": "🧚 นางฟ้า", "rarity": "legendary", "emoji": "🧚", "value": 50},
    "leg_7": {"name": "🧜 เงือก", "rarity": "legendary", "emoji": "🧜", "value": 50},
    "leg_8": {"name": "🧛 แวมไพร์", "rarity": "legendary", "emoji": "🧛", "value": 50},
    "leg_9": {"name": "🧟 ซอมบี้", "rarity": "legendary", "emoji": "🧟", "value": 50},
    "leg_10": {"name": "👽 เอเลี่ยน", "rarity": "legendary", "emoji": "👽", "value": 50},
}

COMMON_ITEMS = {k: v for k, v in ITEMS.items() if v["rarity"] == "common"}
RARE_ITEMS = {k: v for k, v in ITEMS.items() if v["rarity"] == "rare"}
LEGENDARY_ITEMS = {k: v for k, v in ITEMS.items() if v["rarity"] == "legendary"}

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

def get_user_balance(user_id: str) -> int:
    balances = load_balances()
    return balances.get(user_id, 0)

def add_user_balance(user_id: str, amount: int) -> int:
    balances = load_balances()
    current = balances.get(user_id, 0)
    new_balance = current + amount
    balances[user_id] = new_balance
    save_balances(balances)
    return new_balance

def remove_user_balance(user_id: str, amount: int) -> bool:
    balances = load_balances()
    current = balances.get(user_id, 0)
    if current < amount:
        return False
    new_balance = current - amount
    if new_balance == 0:
        del balances[user_id]
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
    print(f"✅ เพิ่ม {item_id} ให้ {user_id}")
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

def random_item() -> tuple[str, dict]:
    roll = random.random() * 100
    
    if roll < 50:
        item_id = random.choice(list(COMMON_ITEMS.keys()))
        return item_id, COMMON_ITEMS[item_id]
    elif roll < 95:
        item_id = random.choice(list(RARE_ITEMS.keys()))
        return item_id, RARE_ITEMS[item_id]
    else:
        item_id = random.choice(list(LEGENDARY_ITEMS.keys()))
        return item_id, LEGENDARY_ITEMS[item_id]

# ==================== RNG SLASH COMMANDS ====================
@bot.tree.command(name="rng", description="เล่นเกม RNG Gacha (สุ่มไอเทม)")
async def rng_slash(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎲 RNG Gacha Game",
        description="ยินดีต้อนรับสู่เกมสุ่มไอเทม!\n\nเลือกปุ่มด้านล่างเพื่อเริ่มเล่น",
        color=0x00AAFF
    )
    embed.add_field(name="📊 อัตราการสุ่ม", value="🟤 Common 50% | 🔵 Rare 45% | 🟡 Legendary 5%", inline=False)
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
        
        item_id, item = random_item()
        user_id = str(interaction.user.id)
        add_item_to_inventory(user_id, item_id)
        
        inventory = get_user_inventory(user_id)
        total_items = sum(inventory.values())
        balance = get_user_balance(user_id)
        
        rarity_color = {"common": 0x808080, "rare": 0x00AAFF, "legendary": 0xFFD700}
        embed = discord.Embed(
            title="🎲 ผลการสุ่ม",
            description=f"คุณได้รับ: {item['emoji']} **{item['name']}**",
            color=rarity_color[item["rarity"]]
        )
        embed.set_footer(text=f"ความหายาก: {item['rarity'].upper()} | ไอเทมทั้งหมด: {total_items} ชิ้น | 🪙 {balance}")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    @discord.ui.button(label="📦 ดู Inventory", style=discord.ButtonStyle.primary, emoji="📦", row=0)
    async def inventory_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
            return
        
        user_id = str(interaction.user.id)
        inventory = get_user_inventory(user_id)
        balance = get_user_balance(user_id)
        
        if not inventory:
            embed = discord.Embed(
                title="📦 Inventory",
                description=f"ยังไม่มีไอเทม! กด 🎲 เพื่อสุ่มก่อน\n\n💰 ยอดเงิน: **{balance}** 🪙",
                color=0x808080
            )
            embed.set_footer(text=f"ผู้เล่น: {self.user.display_name}")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        items_list = []
        total_value = 0
        
        for item_id, amount in inventory.items():
            item = ITEMS[item_id]
            rarity_emoji = {"common": "🟤", "rare": "🔵", "legendary": "🟡"}[item["rarity"]]
            items_list.append(f"{rarity_emoji} {item['emoji']} **{item['name']}** x{amount}")
            total_value += amount * item["value"]
        
        common_count = sum(1 for k in inventory.keys() if k in COMMON_ITEMS)
        rare_count = sum(1 for k in inventory.keys() if k in RARE_ITEMS)
        leg_count = sum(1 for k in inventory.keys() if k in LEGENDARY_ITEMS)
        
        embed = discord.Embed(title="📦 Inventory", color=0x00AAFF)
        embed.add_field(
            name="📊 สถิติ",
            value=f"🟤 Common: {common_count} | 🔵 Rare: {rare_count} | 🟡 Legendary: {leg_count}",
            inline=False
        )
        embed.add_field(name="📋 รายการไอเทม", value="\n".join(items_list[:10]), inline=False)
        embed.add_field(name="💰 การเงิน", value=f"ยอดเงิน: **{balance}** 🪙\nมูลค่ารวมไอเทม: **{total_value}** 🪙", inline=False)
        
        if len(items_list) > 10:
            embed.set_footer(text=f"แสดง 10 จาก {len(items_list)} รายการ")
        else:
            embed.set_footer(text=f"ผู้เล่น: {self.user.display_name}")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(label="🏪 Pawn Shop", style=discord.ButtonStyle.secondary, emoji="🏪", row=1)
    async def pawnshop_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
            return
        
        user_id = str(interaction.user.id)
        inventory = get_user_inventory(user_id)
        balance = get_user_balance(user_id)
        
        if not inventory:
            embed = discord.Embed(
                title="🏪 Pawn Shop",
                description=f"คุณยังไม่มีไอเทม! ไปสุ่มไอเทมก่อนนะ 🎲\n\n💰 ยอดเงินปัจจุบัน: **{balance}** 🪙",
                color=0x808080
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        options = []
        items_data = list(inventory.items())
        
        for i, (item_id, amount) in enumerate(items_data[:10]):
            item = ITEMS[item_id]
            rarity_emoji = {"common": "🟤", "rare": "🔵", "legendary": "🟡"}[item["rarity"]]
            price_range = "1-1,000" if item["rarity"] == "common" else ("1,001-10,000" if item["rarity"] == "rare" else "10,001-100,000")
            
            options.append(
                discord.SelectOption(
                    label=f"{item['name']} x{amount}",
                    description=f"{rarity_emoji} {item['rarity'].upper()} - ราคา {price_range} 🪙",
                    emoji=item['emoji'],
                    value=item_id
                )
            )
        
        select = Select(
            placeholder="เลือกไอเทมที่ต้องการค้าขาย...",
            options=options,
            row=0
        )
        
        async def select_callback(select_interaction: discord.Interaction):
            if select_interaction.user != self.user:
                await select_interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
                return
            
            item_id = select_interaction.data["values"][0]
            item = ITEMS[item_id]
            
            customer = PawnCustomer()
            base_price = get_item_price(item)
            current_balance = get_user_balance(user_id)
            
            embed = discord.Embed(
                title=f"🏪 Pawn Shop - {item['emoji']} {item['name']}",
                description=f"{customer.avatar} **{customer.name}**\n\nฉันสนใจจะ{'ซื้อ' if customer.deal_type == 'buy' else 'ขาย'} {item['emoji']} **{item['name']}**\nราคาที่เหมาะสมน่าจะอยู่ที่ **{base_price:,}** 🪙",
                color=0x00AAFF
            )
            embed.add_field(
                name="📊 ข้อมูลลูกค้า",
                value=(
                    f"ความพอใจเริ่มต้น: {customer.satisfaction}%\n"
                    f"ความอดทน: {customer.patience} ครั้ง\n"
                    f"มาเพื่อ: {'💰 ซื้อ' if customer.deal_type == 'buy' else '💸 ขาย'}"
                ),
                inline=False
            )
            embed.add_field(
                name="💰 ยอดเงินคุณ",
                value=f"**{current_balance}** 🪙",
                inline=False
            )
            
            bot.pawn_data[user_id] = {
                "item_id": item_id,
                "item": item,
                "customer": customer,
                "base_price": base_price,
                "current_price": base_price
            }
            
            pawn_view = PawnShopSlashView(self.user, item_id, item, customer, base_price, current_balance)
            await select_interaction.response.send_message(embed=embed, view=pawn_view, ephemeral=True)
        
        select.callback = select_callback
        
        view = View(timeout=60)
        view.add_item(select)
        
        embed = discord.Embed(
            title="🏪 Pawn Shop",
            description=f"เลือกไอเทมที่ต้องการค้าขายกับลูกค้า\n\n💰 ยอดเงินคุณ: **{balance}** 🪙",
            color=0x00AAFF
        )
        embed.add_field(
            name="💰 ระบบราคา",
            value="🟤 Common: 1-1,000 🪙\n🔵 Rare: 1,001-10,000 🪙\n🟡 Legendary: 10,001-100,000 🪙",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="💰 เช็คเงิน", style=discord.ButtonStyle.success, emoji="🪙", row=1)
    async def balance_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
            return
        
        user_id = str(interaction.user.id)
        balance = get_user_balance(user_id)
        
        embed = discord.Embed(
            title="💰 ยอดเงินของคุณ",
            description=f"**{balance}** 🪙 Sushicoin",
            color=0xFFD700
        )
        embed.set_footer(text=f"ผู้เล่น: {self.user.display_name}")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(label="ℹ️ วิธีเล่น", style=discord.ButtonStyle.secondary, emoji="ℹ️", row=2)
    async def help_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
            return
        
        embed = discord.Embed(title="🎮 วิธีเล่น RNG Gacha Game", color=0x00AAFF)
        embed.add_field(
            name="📊 โอกาสได้รับไอเทม",
            value="🟤 Common 50% | 🔵 Rare 45% | 🟡 Legendary 5%",
            inline=False
        )
        embed.add_field(
            name="🎮 วิธีเล่น",
            value="1. กด 🎲 เพื่อสุ่มไอเทม\n2. กด 📦 เพื่อดู Inventory\n3. กด 🏪 เพื่อเปิด Pawn Shop\n4. กด 🪙 เพื่อเช็คยอดเงิน",
            inline=False
        )
        embed.add_field(
            name="🏪 Pawn Shop",
            value=(
                "• ลูกค้าสุ่มมา ซื้อ/ขาย\n"
                "• ถ้าลูกค้าซื้อ = เราขายไอเทม ได้เงิน\n"
                "• ถ้าลูกค้าขาย = เราซื้อไอเทม เสียเงิน\n"
                "• ต่อรองราคา +/- 5% ได้สูงสุดตามความอดทน\n"
                "• ความพอใจส่งผลต่อดีล"
            ),
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ==================== PAWN SHOP SYSTEM ====================
CUSTOMER_NAMES = [
    "คุณสมชาย", "คุณสมหญิง", "คุณอนันต์", "คุณประภาพร", "คุณวิชัย", "คุณกัญญา",
    "คุณธีรศักดิ์", "คุณนภัสสร", "คุณภาณุ", "คุณสิริยากร", "คุณทักษิณ", "คุณบุษบา",
    "คุณชัชชัย", "คุณจินตนา", "คุณปฏิภาณ", "คุณศิริวรรณ", "คุณสามารถ", "คุณอุบล",
    "คุณไพศาล", "คุณรัตนา", "คุณธนา", "คุณปาริชาติ", "คุณวรวุฒิ", "คุณสาวิตรี",
    "Mike", "John", "Sarah", "David", "Emma", "Chris", "Lisa", "Tom", "Anna", "James"
]

CUSTOMER_AVATARS = ["👨", "👩", "🧔", "👵", "👴", "🧑", "👱", "👲", "🧕", "👳"]

def get_item_price(item: dict) -> int:
    if item["rarity"] == "common":
        return random.randint(1, 1000)
    elif item["rarity"] == "rare":
        return random.randint(1001, 10000)
    else:
        return random.randint(10001, 100000)

class PawnCustomer:
    def __init__(self):
        self.name = random.choice(CUSTOMER_NAMES)
        self.avatar = random.choice(CUSTOMER_AVATARS)
        self.satisfaction = random.randint(30, 100)
        self.patience = random.randint(2, 5)
        self.deal_type = random.choice(["buy", "sell"])
        
    def calculate_price_satisfaction(self, offered_price: int, base_price: int) -> Tuple[int, str]:
        price_diff_percent = ((offered_price - base_price) / base_price) * 100
        
        if self.deal_type == "buy":
            satisfaction_change = -price_diff_percent * 0.5
        else:
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

class PawnShopSlashView(View):
    def __init__(self, user: discord.User, item_id: str, item: dict, customer: PawnCustomer, base_price: int, user_balance: int):
        super().__init__(timeout=120)
        self.user = user
        self.item_id = item_id
        self.item = item
        self.customer = customer
        self.base_price = base_price
        self.current_price = base_price
        self.user_balance = user_balance
        
    @discord.ui.button(label="✅ ตกลง", style=discord.ButtonStyle.success, row=0)
    async def accept_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
            return
        
        user_id = str(interaction.user.id)
        new_satisfaction, emoji = self.customer.calculate_price_satisfaction(self.current_price, self.base_price)
        
        if new_satisfaction >= 50:
            if self.customer.deal_type == "buy":
                success = remove_item_from_inventory(user_id, self.item_id)
                if success:
                    new_balance = add_user_balance(user_id, self.current_price)
                    result_msg = f"✅ ดีลสำเร็จ! คุณขาย {self.item['emoji']} **{self.item['name']}** ในราคา {self.current_price:,} 🪙\n💰 ยอดเงินปัจจุบัน: {new_balance} 🪙"
                    color = 0x00FF00
                else:
                    result_msg = f"❌ เกิดข้อผิดพลาด: ไม่พบไอเทมใน inventory"
                    color = 0xFF0000
            else:
                if remove_user_balance(user_id, self.current_price):
                    add_item_to_inventory(user_id, self.item_id)
                    new_balance = get_user_balance(user_id)
                    result_msg = f"✅ ดีลสำเร็จ! คุณซื้อ {self.item['emoji']} **{self.item['name']}** ในราคา {self.current_price:,} 🪙\n💰 ยอดเงินปัจจุบัน: {new_balance} 🪙"
                    color = 0x00FF00
                else:
                    current_balance = get_user_balance(user_id)
                    result_msg = f"❌ เงินไม่พอ! คุณมี {current_balance} 🪙 ต้องการ {self.current_price} 🪙"
                    color = 0xFF0000
            
            embed = discord.Embed(title=f"🤝 ดีลสำเร็จ! {emoji}", description=result_msg, color=color)
            
            continue_view = View(timeout=60)
            continue_btn = Button(label="เล่นต่อ", emoji="🎮", style=discord.ButtonStyle.primary)
            
            async def continue_callback(cont_interaction):
                if cont_interaction.user != self.user:
                    await cont_interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
                    return
                
                # กลับไปที่หน้า RNG หลัก
                main_embed = discord.Embed(
                    title="🎲 RNG Gacha Game",
                    description="ยินดีต้อนรับสู่เกมสุ่มไอเทม!\n\nเลือกปุ่มด้านล่างเพื่อเริ่มเล่น",
                    color=0x00AAFF
                )
                main_embed.add_field(name="📊 อัตราการสุ่ม", value="🟤 Common 50% | 🔵 Rare 45% | 🟡 Legendary 5%", inline=False)
                main_embed.set_footer(text=f"ผู้เล่น: {self.user.display_name}")
                
                await cont_interaction.response.edit_message(embed=main_embed, view=RNGMainView(self.user))
            
            continue_btn.callback = continue_callback
            continue_view.add_item(continue_btn)
            
            if user_id in bot.pawn_data:
                del bot.pawn_data[user_id]
            
            await interaction.response.edit_message(embed=embed, view=continue_view)
            
        else:
            result_msg = f"{emoji} **{self.customer.name}**: ราคานี้ไม่โอเคเลย! ลาก่อน!"
            embed = discord.Embed(title="❌ ดีลล้มเหลว", description=result_msg, color=0xFF0000)
            
            continue_view = View(timeout=60)
            continue_btn = Button(label="เล่นต่อ", emoji="🎮", style=discord.ButtonStyle.primary)
            
            async def continue_callback(cont_interaction):
                if cont_interaction.user != self.user:
                    await cont_interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
                    return
                
                # กลับไปที่หน้า RNG หลัก
                main_embed = discord.Embed(
                    title="🎲 RNG Gacha Game",
                    description="ยินดีต้อนรับสู่เกมสุ่มไอเทม!\n\nเลือกปุ่มด้านล่างเพื่อเริ่มเล่น",
                    color=0x00AAFF
                )
                main_embed.add_field(name="📊 อัตราการสุ่ม", value="🟤 Common 50% | 🔵 Rare 45% | 🟡 Legendary 5%", inline=False)
                main_embed.set_footer(text=f"ผู้เล่น: {self.user.display_name}")
                
                await cont_interaction.response.edit_message(embed=main_embed, view=RNGMainView(self.user))
            
            continue_btn.callback = continue_callback
            continue_view.add_item(continue_btn)
            
            if user_id in bot.pawn_data:
                del bot.pawn_data[user_id]
            
            await interaction.response.edit_message(embed=embed, view=continue_view)
    
    @discord.ui.button(label="❌ ปฏิเสธ", style=discord.ButtonStyle.danger, row=0)
    async def reject_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="🚫 ปฏิเสธข้อเสนอ",
            description=f"{self.customer.avatar} **{self.customer.name}**: ไม่เป็นไร ไว้คราวหน้านะครับ/คะ",
            color=0x808080
        )
        
        continue_view = View(timeout=60)
        continue_btn = Button(label="เล่นต่อ", emoji="🎮", style=discord.ButtonStyle.primary)
        
        async def continue_callback(cont_interaction):
            if cont_interaction.user != self.user:
                await cont_interaction.response.send_message("❌ ไม่ใช่เกมของคุณ!", ephemeral=True)
                return
            
            # กลับไปที่หน้า RNG หลัก
            main_embed = discord.Embed(
                title="🎲 RNG Gacha Game",
                description="ยินดีต้อนรับสู่เกมสุ่มไอเทม!\n\nเลือกปุ่มด้านล่างเพื่อเริ่มเล่น",
                color=0x00AAFF
            )
            main_embed.add_field(name="📊 อัตราการสุ่ม", value="🟤 Common 50% | 🔵 Rare 45% | 🟡 Legendary 5%", inline=False)
            main_embed.set_footer(text=f"ผู้เล่น: {self.user.display_name}")
            
            await cont_interaction.response.edit_message(embed=main_embed, view=RNGMainView(self.user))
        
        continue_btn.callback = continue_callback
        continue_view.add_item(continue_btn)
        
        user_id = str(interaction.user.id)
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
        
        embed = discord.Embed(
            title="🤔 การต่อรอง",
            description=(
                f"{self.customer.avatar} **{self.customer.name}**\n\n"
                f"ราคาปัจจุบัน: **{self.current_price:,}** 🪙\n"
                f"ความพอใจ: {new_satisfaction}% {emoji}\n"
                f"โอกาสต่อรองเหลือ: {self.customer.patience} ครั้ง"
            ),
            color=0x00AAFF
        )
        
        embed.add_field(
            name="📊 ราคา",
            value=(
                f"ราคาพื้นฐาน: {self.base_price:,} 🪙\n"
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
        
        embed = discord.Embed(
            title="🤔 การต่อรอง",
            description=(
                f"{self.customer.avatar} **{self.customer.name}**\n\n"
                f"ราคาปัจจุบัน: **{self.current_price:,}** 🪙\n"
                f"ความพอใจ: {new_satisfaction}% {emoji}\n"
                f"โอกาสต่อรองเหลือ: {self.customer.patience} ครั้ง"
            ),
            color=0x00AAFF
        )
        
        embed.add_field(
            name="📊 ราคา",
            value=(
                f"ราคาพื้นฐาน: {self.base_price:,} 🪙\n"
                f"ต่าง: {((self.current_price - self.base_price) / self.base_price * 100):+.1f}%"
            ),
            inline=False
        )
        
        await interaction.response.edit_message(embed=embed, view=self)

# ==================== TASKS ====================
@tasks.loop(minutes=1)
async def update_presence():
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching, 
            name=f"Sushi Shop | GP: {gamepass_stock:,} | กลุ่ม: {group_stock:,}"
        )
    )

@tasks.loop(minutes=5)
async def save_data():
    save_json(user_data_file, user_data)
    save_json(ticket_transcripts_file, ticket_transcripts)
    save_json(ticket_robux_data_file, ticket_robux_data)
    save_json(ticket_customer_data_file, ticket_customer_data)

@tasks.loop(minutes=10)
async def update_credit_channel_task():
    await check_credit_channel_changes()

# ==================== EVENTS ====================
@bot.event
async def on_ready():
    print(f"✅ บอทออนไลน์แล้ว: {bot.user} (ID: {bot.user.id})")
    
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
    
    activity_text = f"ร้าน Sushi Shop | GP: {gamepass_stock:,} | Group: {group_stock:,}"
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=activity_text))
    
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
        exit(1)
    
    try:
        bot.run(token)
    except Exception as e:
        print(f"❌ Error running bot: {e}")
        traceback.print_exc()
