import os, datetime, discord, re, asyncio, json, traceback, time, aiohttp, logging
from discord.ext import commands, tasks
from discord.ui import View, Button, Modal, TextInput
from flask import Flask, jsonify
from threading import Thread

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

user_data = {}
ticket_transcripts = {}
ticket_robux_data = {}
ticket_customer_data = {}
user_notes = {}
ticket_activity = {}

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
    except:
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
        if ctx.author.guild_permissions.administrator or ctx.guild.get_role(1361016912259055896) in ctx.author.roles:
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
    """เปลี่ยนชื่อช่องหลักตามสถานะร้าน"""
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
    """อัพเดทข้อความในช่องหลัก"""
    try:
        channel = bot.get_channel(MAIN_CHANNEL_ID)
        if not channel:
            return
        
        # Create embed
        embed = discord.Embed(title="🍣 Sushi Shop 🍣 เปิดให้บริการ", color=0xFFA500)
        embed.add_field(
            name=f"🎮 กดเกมพาส | 📊 Stock: {gamepass_stock} {'🟢' if gamepass_stock > 0 else '🔴'}", 
            value=f"```\nเรท: {gamepass_rate} | โรแท้ยัดกลุ่มได้\nเช็คราคา: !gp <จำนวน>\n```", 
            inline=False
        )
        embed.add_field(
            name=f"👥 โรบัคกลุ่ม | 📊 Stock: {group_stock} {'🟢' if group_stock > 0 else '🔴'}", 
            value=f"```\nเรท: {group_rate_low} | 500+ บาท เรท {group_rate_high}\n⚠️ต้องเข้ากลุ่ม 15 วันก่อนซื้อ⚠️\n```", 
            inline=False
        )
        embed.add_field(
            name="🏪 สถานะร้าน", 
            value=f"```\n{'🟢 เปิด' if shop_open else '🔴 ปิดชั่วคราว'}\n```", 
            inline=False
        )
        embed.set_footer(
            text="Sushi Shop • รับกดเกมพาสและอื่น ๆ", 
            icon_url="https://media.discordapp.net/attachments/717757556889747657/1403684950770847754/noFilter.png"
        )
        embed.set_thumbnail(url="https://media.discordapp.net/attachments/717757556889747657/1403684950770847754/noFilter.png")
        
        # Create view with current status
        view = View(timeout=None)
        
        # Gamepass button
        if not shop_open:
            gamepass_btn = Button(label="ร้านปิดชั่วคราว", style=discord.ButtonStyle.danger, emoji="🎮", disabled=True, custom_id="gamepass_btn")
        elif gamepass_stock <= 0:
            gamepass_btn = Button(label="สินค้าหมด", style=discord.ButtonStyle.danger, emoji="🎮", disabled=True, custom_id="gamepass_btn")
        else:
            gamepass_btn = Button(label="เปิดตั๋วกดเกมพาส", style=discord.ButtonStyle.success, emoji="🎮", custom_id="gamepass_btn")
        
        # Group button
        if not shop_open:
            group_btn = Button(label="ร้านปิดชั่วคราว", style=discord.ButtonStyle.danger, emoji="👥", disabled=True, custom_id="group_btn")
        elif not group_ticket_enabled:
            group_btn = Button(label="บริการปิดชั่วคราว", style=discord.ButtonStyle.danger, emoji="👥", disabled=True, custom_id="group_btn")
        elif group_stock <= 0:
            group_btn = Button(label="สินค้าหมด", style=discord.ButtonStyle.danger, emoji="👥", disabled=True, custom_id="group_btn")
        else:
            group_btn = Button(label="เปิดตั๋ว Group", style=discord.ButtonStyle.success, emoji="👥", custom_id="group_btn")
        
        notes_btn = Button(label="จดวันที่เข้ากลุ่ม", style=discord.ButtonStyle.secondary, emoji="📝", custom_id="notes_btn")
        level_btn = Button(label="ดูเลเวลของคุณ", style=discord.ButtonStyle.primary, emoji="⭐", custom_id="level_btn")
        
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
        
        # Find and update existing message
        async for msg in channel.history(limit=100):
            if msg.author == bot.user and msg.embeds:
                await bot.channel_edit_rate_limiter.acquire()
                await msg.edit(embed=embed, view=view)
                print("✅ Updated main channel")
                return
        
        # If no existing message, send new one
        await channel.send(embed=embed, view=view)
        print("✅ Sent new main channel message")
        
    except Exception as e:
        print(f"❌ Error updating main channel: {e}")
        traceback.print_exc()

# ==================== TICKET HANDLER ====================
async def handle_open_ticket(interaction, category_name, stock_type):
    global gamepass_stock, group_stock
    
    try:
        # Check stock and shop status
        if stock_type == "gamepass" and gamepass_stock <= 0:
            await interaction.response.send_message("❌ สินค้าหมดชั่วคราว", ephemeral=True)
            return
        
        if stock_type == "group" and group_stock <= 0:
            await interaction.response.send_message("❌ สินค้าหมดชั่วคราว", ephemeral=True)
            return
        
        if not shop_open:
            await interaction.response.send_message("❌ ร้านปิดชั่วคราว กรุณารอให้ร้านเปิด", ephemeral=True)
            return
        
        # Check for existing ticket
        existing = discord.utils.get(
            interaction.guild.text_channels, 
            name=f"ticket-{interaction.user.name}-{interaction.user.id}"
        )
        
        if existing:
            view = View()
            view.add_item(discord.ui.Button(
                label="📩 ไปที่ตั๋ว", 
                url=f"https://discord.com/channels/{existing.guild.id}/{existing.id}", 
                style=discord.ButtonStyle.link
            ))
            await interaction.response.send_message(
                "📌 คุณมีตั๋วเปิดอยู่แล้ว! กดปุ่มด้านล่างเพื่อไปที่ตั๋ว", 
                view=view, 
                ephemeral=True
            )
            return
        
        # Create channel overwrites
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        admin_role = interaction.guild.get_role(1361016912259055896)
        if admin_role:
            overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        # Get category
        category = discord.utils.get(interaction.guild.categories, name=category_name)
        if not category:
            await interaction.response.send_message(f"❌ ไม่พบหมวดหมู่ {category_name}", ephemeral=True)
            return
        
        # Create initial response
        await interaction.response.send_message("🔄 กำลังเปิดตั๋ว...", ephemeral=True)
        
        # Create channel
        channel = await interaction.guild.create_text_channel(
            name=f"ticket-{interaction.user.name}-{interaction.user.id}",
            overwrites=overwrites,
            category=category
        )
        
        # Track ticket activity
        ticket_activity[channel.id] = {
            'last_activity': get_thailand_time(), 
            'ty_used': False
        }
        
        # Save customer data
        ticket_customer_data[str(channel.id)] = interaction.user.name
        save_json(ticket_customer_data_file, ticket_customer_data)
        
        # Update stock
        if stock_type == "gamepass":
            async with bot.stock_lock:
                gamepass_stock -= 1
        else:
            async with bot.stock_lock:
                group_stock -= 1
        
        # Update main channel display
        await update_main_channel()
        
        # Send confirmation
        view = View()
        view.add_item(discord.ui.Button(
            label="📩 ไปที่ตั๋ว", 
            url=f"https://discord.com/channels/{channel.guild.id}/{channel.id}", 
            style=discord.ButtonStyle.link
        ))
        await interaction.edit_original_response(content="📩 เปิดตั๋วเรียบร้อย!", view=view)
        
        # Notify admin
        if admin_role:
            await channel.send(content=f"{admin_role.mention} มีตั๋วใหม่!")
        
        # Create welcome embed
        embed = discord.Embed(
            title="🍣 Sushi Shop 🍣", 
            description="ยินดีต้อนรับร้าน Sushi Shop\n\nโปรดกรอกแบบฟอร์มเพื่อสั่งไอเทม", 
            color=0x00FF99
        )
        embed.add_field(name="👤 ผู้ซื้อ", value=interaction.user.mention, inline=False)
        embed.add_field(
            name="🛠️ ทีมงาน", 
            value=admin_role.mention if admin_role else "รอพนักงานติดต่อ", 
            inline=False
        )
        
        if stock_type == "gamepass":
            embed.add_field(
                name="🎮 บริการกดเกมพาส", 
                value=f"📦 Stock คงเหลือ: **{gamepass_stock}**\n💰 เรท: {gamepass_rate}", 
                inline=False
            )
        else:
            embed.add_field(
                name="👥 บริการโรบัคกลุ่ม", 
                value=f"📦 Stock คงเหลือ: **{group_stock}**\n💰 เรท: {group_rate_low} - {group_rate_high}", 
                inline=False
            )
        
        embed.set_footer(text="Sushi Shop • กดปุ่มด้านล่างเพื่อกรอกแบบฟอร์ม")
        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/717757556889747657/1403684950770847754/noFilter.png")
        
        # Create ticket action view with form button
        ticket_view = View(timeout=None)
        
        if stock_type == "gamepass":
            form_btn = Button(
                label="📝 กรอกแบบฟอร์มเกมพาส", 
                style=discord.ButtonStyle.primary, 
                emoji="📝", 
                custom_id=f"gamepass_form_{channel.id}"
            )
            async def form_cb(i):
                if i.channel.id == channel.id:
                    await i.response.send_modal(GamepassTicketModal())
            form_btn.callback = form_cb
        else:
            form_btn = Button(
                label="📝 กรอกแบบฟอร์ม Group", 
                style=discord.ButtonStyle.primary, 
                emoji="📝", 
                custom_id=f"group_form_{channel.id}"
            )
            async def form_cb(i):
                if i.channel.id == channel.id:
                    await i.response.send_modal(GroupTicketModal())
            form_btn.callback = form_cb
        
        close_btn = Button(
            label="🔒 ปิดตั๋ว", 
            style=discord.ButtonStyle.danger, 
            emoji="🔒", 
            custom_id=f"close_ticket_{channel.id}"
        )
        
        async def close_cb(i):
            if i.channel.id == channel.id:
                if admin_role and admin_role in i.user.roles:
                    await save_ticket_transcript(channel, i.user)
                    await i.response.send_message("📪 กำลังปิดตั๋ว...")
                    await asyncio.sleep(2)
                    await channel.delete()
                else:
                    await i.response.send_message("❌ คุณไม่มีสิทธิ์ปิดตั๋วนี้", ephemeral=True)
        
        close_btn.callback = close_cb
        
        ticket_view.add_item(form_btn)
        ticket_view.add_item(close_btn)
        
        # Send welcome message
        await channel.send(embed=embed, view=ticket_view)
        
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

# ==================== HANDLE TICKET AFTER TY ====================
async def handle_ticket_after_ty(channel, user, robux_amount=None, customer_name=None):
    try:
        print(f"📝 กำลังจัดการตั๋วหลัง !ty: {channel.name}")
        guild = channel.guild
        
        if robux_amount is None and str(channel.id) in ticket_robux_data:
            robux_amount = ticket_robux_data[str(channel.id)]
        
        delivered_category = guild.get_channel(DELIVERED_CATEGORY_ID)
        if not delivered_category:
            print(f"❌ ไม่พบ category ส่งของแล้ว ID: {DELIVERED_CATEGORY_ID}")
            return False
        
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
                await channel.edit(name=filename[:100])  # Discord channel name max 100 chars
                print(f"✅ เปลี่ยนชื่อห้องเป็น: {filename}")
            except Exception as e:
                print(f"⚠️ ไม่สามารถเปลี่ยนชื่อห้อง: {e}")
        
        # Send credit message
        credit_embed = discord.Embed(
            title="✅ ส่งของเรียบร้อยแล้ว",
            description="สินค้าถูกจัดส่งเรียบร้อยแล้ว!\n\n**ขอบคุณที่ใช้บริการร้าน Sushi Shop 🍣**\nฝากกดเครดิตให้ด้วยนะคะ ⭐\n\n⚠️ **หมายเหตุ:** ตั๋วนี้จะถูกย้ายไปเก็บถาวรใน 10 นาที",
            color=0x00FF00
        )
        credit_embed.set_footer(text="Sushi Shop • ขอบคุณที่ใช้บริการ")
        
        await channel.send(embed=credit_embed)
        print(f"✅ ส่งข้อความให้เครดิตเรียบร้อย")
        
        # Send to credit channel
        credit_channel = bot.get_channel(CREDIT_CHANNEL_ID)
        if credit_channel:
            credit_msg = await credit_channel.send(
                f"🎉 {user.mention if user else 'ลูกค้า'} ได้รับสินค้าเรียบร้อย! กรุณากด ❤️ และ 🍣 เพื่อให้เครดิต"
            )
            await credit_msg.add_reaction("❤️")
            await credit_msg.add_reaction("🍣")
        
        # Schedule moving to archive after 10 minutes
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
                    title="📁 ตั๋วถูกย้ายไปเก็บถาวรแล้ว", 
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
        label="จดวันที่เข้ากลุ่มในนี้ ดูจากวันที่ปัจจุบัน", 
        placeholder="เช่น: 20/10 , 20 ตค", 
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
        label="💸 กดเกมพาสอะไร?", 
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
            embed.add_field(name="🗺️ แมพ", value=self.map_name.value, inline=False)
            embed.add_field(name="🎟 เกมพาส", value=self.gamepass_name.value, inline=False)
            embed.add_field(name="💸 ราคาโรบัค", value=f"{robux:,}", inline=True)
            embed.add_field(name="💰 ราคา", value=f"{price:,.0f} บาท", inline=True)
            embed.set_footer(text="ทีมงานจะตอบกลับโดยเร็วที่สุด")
            
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
            embed.set_footer(text="ทีมงานจะตรวจสอบและตอบกลับโดยเร็วที่สุด")
            
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
        
        deliver_btn = Button(
            label="ส่งสินค้าแล้ว ✅", 
            style=discord.ButtonStyle.success, 
            emoji="✅", 
            custom_id=f"deliver_{channel.id}"
        )
        cancel_btn = Button(
            label="ยกเลิก ❌", 
            style=discord.ButtonStyle.danger, 
            emoji="❌", 
            custom_id=f"cancel_{channel.id}"
        )
        
        async def deliver_cb(i):
            if i.channel.id != self.channel.id:
                return
            
            # Check permission
            admin_role = i.guild.get_role(1361016912259055896)
            if not i.user.guild_permissions.administrator and (not admin_role or admin_role not in i.user.roles):
                await i.response.send_message("❌ คุณไม่มีสิทธิ์ใช้ปุ่มนี้", ephemeral=True)
                return
            
            if self.delivered:
                await i.response.edit_message(content="✅ สินค้าถูกส่งเรียบร้อยแล้ว", embed=None, view=None)
                return
            
            # Check for delivery image
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
            
            # Create confirmation view
            confirm_view = View(timeout=300)
            confirm_btn = Button(label="ยืนยัน ✅", style=discord.ButtonStyle.success, emoji="✅")
            edit_btn = Button(label="แก้ไข", style=discord.ButtonStyle.secondary, emoji="✏️")
            
            async def confirm_cb(interaction):
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
                    name="💸 จำนวน Robux", 
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
                
                # Send DM to buyer
                if self.buyer:
                    try:
                        dm_embed = discord.Embed(
                            title=f"🧾 ใบเสร็จการซื้อสินค้า ({self.product_type})", 
                            description="ขอบคุณที่ใช้บริการ Sushi Shop นะคะ 🍣", 
                            color=receipt_color
                        )
                        dm_embed.add_field(name="📦 สินค้า", value=self.product_type, inline=True)
                        dm_embed.add_field(name="💸 จำนวน Robux", value=f"{self.robux_amount:,}", inline=True)
                        dm_embed.add_field(name="💰 ราคา", value=f"{self.price:,.0f} บาท", inline=True)
                        
                        if delivery_image:
                            dm_embed.set_image(url=delivery_image)
                        
                        dm_embed.add_field(
                            name="📝 หมายเหตุ", 
                            value="หากมีปัญหากรุณาติดต่อแอดมินในเซิร์ฟเวอร์", 
                            inline=False
                        )
                        dm_embed.set_footer(text="Sushi Shop • ขอบคุณที่ไว้วางใจ 💖")
                        
                        await self.buyer.send(embed=dm_embed)
                    except:
                        pass
                
                # Send to sales log
                log_channel = bot.get_channel(SALES_LOG_CHANNEL_ID)
                if log_channel:
                    await log_channel.send(embed=receipt_embed)
                
                # Send to channel
                await self.channel.send(embed=receipt_embed)
                await self.channel.send("✅ **ส่งสินค้าเรียบร้อยแล้ว!**")
                
                await interaction.response.edit_message(
                    content="✅ บันทึกการส่งสินค้าเรียบร้อยแล้ว", 
                    embed=None, 
                    view=None
                )
            
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
@bot.command()
@admin_only()
async def open(ctx):
    """เปิดร้าน"""
    global shop_open
    shop_open = True
    
    try:
        await ctx.message.delete()
    except:
        pass
    
    # Update channel name and main message
    await update_channel_name()
    await update_main_channel()
    
    embed = discord.Embed(
        title="✅ เปิดร้านเรียบร้อย", 
        description="ร้าน Sushi Shop เปิดให้บริการแล้ว!", 
        color=0x00FF00
    )
    msg = await ctx.send(embed=embed)
    
    await asyncio.sleep(3)
    
    try:
        await msg.delete()
    except:
        pass

@bot.command()
@admin_only()
async def close(ctx):
    """ปิดร้าน"""
    global shop_open
    shop_open = False
    
    try:
        await ctx.message.delete()
    except:
        pass
    
    # Update channel name and main message
    await update_channel_name()
    await update_main_channel()
    
    embed = discord.Embed(
        title="🔴 ปิดร้านเรียบร้อย", 
        description="ร้าน Sushi Shop ปิดให้บริการชั่วคราว", 
        color=0xFF0000
    )
    msg = await ctx.send(embed=embed)
    
    await asyncio.sleep(3)
    
    try:
        await msg.delete()
    except:
        pass

@bot.command()
@admin_only()
async def stock(ctx, stock_type=None, amount=None):
    """ตรวจสอบและตั้งค่า stock"""
    global gamepass_stock, group_stock
    
    try:
        await ctx.message.delete()
    except:
        pass
    
    if not stock_type:
        embed = discord.Embed(title="📊 สต๊อกโรบัค", color=0x00FF99)
        embed.add_field(name="🎮 Gamepass Stock", value=f"**{gamepass_stock:,}**", inline=True)
        embed.add_field(name="👥 Group Stock", value=f"**{group_stock:,}**", inline=True)
        msg = await ctx.send(embed=embed)
        await asyncio.sleep(3)
        try:
            await msg.delete()
        except:
            pass
        
    elif stock_type.lower() in ["gp", "gamepass", "เกมพาส"]:
        if amount is None:
            embed = discord.Embed(title="🎮 Gamepass Stock", description=f"**{gamepass_stock:,}**", color=0x00FF99)
            msg = await ctx.send(embed=embed)
            await asyncio.sleep(3)
            try:
                await msg.delete()
            except:
                pass
        else:
            try:
                gamepass_stock = int(amount.replace(",", ""))
                embed = discord.Embed(
                    title="✅ ตั้งค่า Stock เรียบร้อย", 
                    description=f"ตั้งค่า สต๊อกเกมพาส เป็น **{gamepass_stock:,}** เรียบร้อยแล้ว", 
                    color=0x00FF00
                )
                msg = await ctx.send(embed=embed)
                await asyncio.sleep(3)
                try:
                    await msg.delete()
                except:
                    pass
                await update_main_channel()
            except ValueError:
                await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)
            
    elif stock_type.lower() in ["g", "group", "กรุ๊ป"]:
        if amount is None:
            embed = discord.Embed(title="👥 Group Stock", description=f"**{group_stock:,}**", color=0x00FF99)
            msg = await ctx.send(embed=embed)
            await asyncio.sleep(3)
            try:
                await msg.delete()
            except:
                pass
        else:
            try:
                group_stock = int(amount.replace(",", ""))
                embed = discord.Embed(
                    title="✅ ตั้งค่า Stock เรียบร้อย", 
                    description=f"ตั้งค่า สต๊อกโรบัคกลุ่ม เป็น **{group_stock:,}** เรียบร้อยแล้ว", 
                    color=0x00FF00
                )
                msg = await ctx.send(embed=embed)
                await asyncio.sleep(3)
                try:
                    await msg.delete()
                except:
                    pass
                await update_main_channel()
            except ValueError:
                await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)
    else:
        embed = discord.Embed(
            title="❌ การใช้งานไม่ถูกต้อง", 
            description="**การใช้งาน:**\n`!stock` - เช็ค stock ทั้งหมด\n`!stock gp <จำนวน>` - ตั้งค่า Gamepass stock\n`!stock group <จำนวน>` - ตั้งค่า Group stock", 
            color=0xFF0000
        )
        msg = await ctx.send(embed=embed)
        await asyncio.sleep(5)
        try:
            await msg.delete()
        except:
            pass

@bot.command()
@admin_only()
async def group(ctx, status=None):
    """เปิด/ปิด Group ticket"""
    global group_ticket_enabled
    
    try:
        await ctx.message.delete()
    except:
        pass
    
    if status is None:
        current_status = "✅ เปิด" if group_ticket_enabled else "❌ ปิด"
        embed = discord.Embed(
            title="👥 สถานะ Group Ticket", 
            description=f"**{current_status}**", 
            color=0x00FF00 if group_ticket_enabled else 0xFF0000
        )
        msg = await ctx.send(embed=embed)
        await asyncio.sleep(3)
        try:
            await msg.delete()
        except:
            pass
        
    elif status.lower() in ["on", "enable", "เปิด"]:
        group_ticket_enabled = True
        embed = discord.Embed(
            title="✅ เปิดปุ่ม Group Ticket", 
            description="เปิดปุ่ม Group Ticket เรียบร้อยแล้ว", 
            color=0x00FF00
        )
        msg = await ctx.send(embed=embed)
        await asyncio.sleep(3)
        try:
            await msg.delete()
        except:
            pass
        await update_main_channel()
        
    elif status.lower() in ["off", "disable", "ปิด"]:
        group_ticket_enabled = False
        embed = discord.Embed(
            title="❌ ปิดปุ่ม Group Ticket", 
            description="ปิดปุ่ม Group Ticket เรียบร้อยแล้ว", 
            color=0xFF0000
        )
        msg = await ctx.send(embed=embed)
        await asyncio.sleep(3)
        try:
            await msg.delete()
        except:
            pass
        await update_main_channel()
    else:
        embed = discord.Embed(
            title="❌ การใช้งานไม่ถูกต้อง", 
            description="**การใช้งาน:**\n`!group` - เช็คสถานะ\n`!group on` - เปิด Group ticket\n`!group off` - ปิด Group ticket", 
            color=0xFF0000
        )
        msg = await ctx.send(embed=embed)
        await asyncio.sleep(5)
        try:
            await msg.delete()
        except:
            pass

@bot.command()
@admin_only()
async def rate(ctx, rate_type=None, low_rate=None, high_rate=None):
    """ตั้งค่าเรท"""
    global gamepass_rate, group_rate_low, group_rate_high
    
    try:
        await ctx.message.delete()
    except:
        pass
    
    if rate_type is None:
        embed = discord.Embed(title="📊 เรทโรกลุ่มปัจจุบัน", color=0x00FF99)
        embed.add_field(name="🎮 Gamepass Rate", value=f"**{gamepass_rate}**", inline=True)
        embed.add_field(name="👥 Group Rate", value=f"**{group_rate_low} - {group_rate_high}**", inline=True)
        msg = await ctx.send(embed=embed)
        await asyncio.sleep(5)
        try:
            await msg.delete()
        except:
            pass
        
    elif rate_type.lower() == "group":
        if low_rate is None or high_rate is None:
            embed = discord.Embed(
                title="❌ การใช้งานไม่ถูกต้อง", 
                description="**การใช้งาน:** `!rate group <low_rate> <high_rate>`", 
                color=0xFF0000
            )
            msg = await ctx.send(embed=embed)
            await asyncio.sleep(5)
            try:
                await msg.delete()
            except:
                pass
            return
        
        try:
            group_rate_low = float(low_rate)
            group_rate_high = float(high_rate)
            embed = discord.Embed(
                title="✅ เปลี่ยนเรท Group เรียบร้อย", 
                description=f"ตั้งค่าเรท Group เป็น **{group_rate_low} - {group_rate_high}** เรียบร้อยแล้ว", 
                color=0x00FF00
            )
            msg = await ctx.send(embed=embed)
            await asyncio.sleep(3)
            try:
                await msg.delete()
            except:
                pass
            await update_main_channel()
        except ValueError:
            await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)
        
    else:
        try:
            gamepass_rate = float(rate_type)
            embed = discord.Embed(
                title="✅ เปลี่ยนเรท Gamepass เรียบร้อย", 
                description=f"ตั้งค่าเรท Gamepass เป็น **{gamepass_rate}** เรียบร้อยแล้ว", 
                color=0x00FF00
            )
            msg = await ctx.send(embed=embed)
            await asyncio.sleep(3)
            try:
                await msg.delete()
            except:
                pass
            await update_main_channel()
        except ValueError:
            await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)

@bot.command()
@admin_only()
async def ty(ctx):
    """คำสั่งยืนยันการส่งสินค้า"""
    global gamepass_stock, group_stock
    
    try:
        await ctx.message.delete()
    except:
        pass
    
    if not ctx.channel.name.startswith("ticket-"):
        await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะในตั๋วเท่านั้น", delete_after=5)
        return
    
    try:
        # Determine ticket type and update stock
        if ctx.channel.category:
            category_name = ctx.channel.category.name.lower()
            if "gamepass" in category_name:
                async with bot.stock_lock:
                    gamepass_stock += 1
            elif "group" in category_name or "robux" in category_name:
                async with bot.stock_lock:
                    group_stock += 1

        # Get buyer information
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
        
        # Get stored data
        robux_amount = ticket_robux_data.get(str(ctx.channel.id))
        customer_name = ticket_customer_data.get(str(ctx.channel.id))
        
        # Handle the ticket after !ty
        handle_success = await handle_ticket_after_ty(ctx.channel, buyer, robux_amount, customer_name)
        
        if not handle_success:
            await ctx.send("❌ เกิดข้อผิดพลาดในการจัดการตั๋ว กรุณาลองใหม่อีกครั้ง", delete_after=5)
            return
        
        # Send DM notification if successful
        if handle_success and buyer:
            try:
                thank_you_embed = discord.Embed(
                    title="✅ การสั่งซื้อเสร็จสมบูรณ์",
                    description="สินค้าของคุณถูกจัดส่งเรียบร้อยแล้ว! ขอบคุณที่ใช้บริการ Sushi Shop นะคะ 🍣",
                    color=0x00FF00
                )
                thank_you_embed.add_field(
                    name="📌 หมายเหตุ", 
                    value="หากมีปัญหาหรือข้อสงสัย สามารถติดต่อแอดมินในเซิร์ฟเวอร์ได้เลยค่ะ", 
                    inline=False
                )
                thank_you_embed.set_footer(text="Sushi Shop • ขอบคุณที่ไว้วางใจ 💖")
                await buyer.send(embed=thank_you_embed)
                print(f"✅ ส่งข้อความยืนยันไปยัง DM ของ {buyer.name} เรียบร้อย")
            except:
                pass
        
        # Clean up stored data
        if str(ctx.channel.id) in ticket_robux_data:
            del ticket_robux_data[str(ctx.channel.id)]
            save_json(ticket_robux_data_file, ticket_robux_data)
        
        if str(ctx.channel.id) in ticket_customer_data:
            del ticket_customer_data[str(ctx.channel.id)]
            save_json(ticket_customer_data_file, ticket_customer_data)
        
        # Update main channel display
        await update_main_channel()
        
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดใน !ty: {e}")
        traceback.print_exc()
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=5)

@bot.command()
@admin_only()
async def od(ctx, *, expr):
    """รับออเดอร์ Gamepass"""
    global gamepass_stock, gamepass_rate
    
    if not ctx.channel.name.startswith("ticket-"):
        await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะในตั๋วเท่านั้น", delete_after=5)
        return
    
    try:
        # Calculate robux amount
        expr_clean = expr.replace(",", "").lower().replace("x", "*").replace("÷", "/")
        robux = int(eval(expr_clean))
        price = robux / gamepass_rate
        
        # Get buyer
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
        
        # Add exp
        if buyer:
            await add_exp(buyer.id, robux, ctx.guild)
        
        # Update stock
        async with bot.stock_lock:
            gamepass_stock = max(0, gamepass_stock - robux)
        
        # Save robux data
        ticket_robux_data[str(ctx.channel.id)] = str(robux)
        save_json(ticket_robux_data_file, ticket_robux_data)
        
        # Create embed
        embed = discord.Embed(title="🍣คำสั่งซื้อสินค้า🍣", color=0xFFA500)
        embed.add_field(name="📦 ประเภทสินค้า", value="Gamepass", inline=False)
        embed.add_field(name="💸 จำนวน Robux", value=f"{robux:,}", inline=True)
        embed.add_field(name="💰 ราคาตามเรท", value=f"{price:,.0f} บาท", inline=True)
        embed.set_footer(text=f"รับออร์เดอร์แล้ว 🤗 • {get_thailand_time().strftime('%d/%m/%y, %H:%M')}")
        
        # Send with delivery view
        await ctx.send(embed=embed, view=DeliveryView(ctx.channel, "Gamepass", robux, price, buyer))
        
        # Update main channel
        await update_main_channel()
        
    except Exception as e:
        print(f"❌ Error in !od: {e}")
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=10)

@bot.command()
@admin_only()
async def odg(ctx, *, expr):
    """รับออเดอร์ Group"""
    global group_stock, group_rate_low, group_rate_high
    
    if not ctx.channel.name.startswith("ticket-"):
        await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะในตั๋วเท่านั้น", delete_after=5)
        return
    
    try:
        # Calculate robux amount
        expr_clean = expr.replace(",", "").lower().replace("x", "*").replace("÷", "/")
        robux = int(eval(expr_clean))
        rate = group_rate_low if robux < 1500 else group_rate_high
        price = robux / rate
        
        # Get buyer
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
        
        # Add exp
        if buyer:
            await add_exp(buyer.id, robux, ctx.guild)
        
        # Update stock
        async with bot.stock_lock:
            group_stock = max(0, group_stock - robux)
        
        # Save robux data
        ticket_robux_data[str(ctx.channel.id)] = str(robux)
        save_json(ticket_robux_data_file, ticket_robux_data)
        
        # Create embed
        embed = discord.Embed(title="🍣คำสั่งซื้อสินค้า🍣", color=0x00FFFF)
        embed.add_field(name="📦 ประเภทสินค้า", value="Group", inline=False)
        embed.add_field(name="💸 จำนวน Robux", value=f"{robux:,}", inline=True)
        embed.add_field(name="💰 ราคาตามเรท", value=f"{price:,.0f} บาท", inline=True)
        embed.set_footer(text=f"รับออร์เดอร์แล้ว 🤗 • {get_thailand_time().strftime('%d/%m/%y, %H:%M')}")
        
        # Send with delivery view
        await ctx.send(embed=embed, view=DeliveryView(ctx.channel, "Group", robux, price, buyer))
        
        # Update main channel
        await update_main_channel()
        
    except Exception as e:
        print(f"❌ Error in !odg: {e}")
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=10)

@bot.command()
async def qr(ctx):
    """แสดง QR Code"""
    try:
        await ctx.message.delete()
    except:
        pass
    
    embed = discord.Embed(
        title="⚠️โน๊ตใต้สลิประบุชื่อสินค้าที่ซื้อด้วย⚠️ ช่องทางการโอนเงิน", 
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
        await i.response.send_message(f"```120-239181-3 : ธนาคาร SCB```", ephemeral=True)
    
    copy_btn.callback = copy_cb
    view.add_item(copy_btn)
    
    await ctx.send(embed=embed, view=view)

@bot.command()
async def gp(ctx, *, expr):
    """คำนวณราคา Gamepass"""
    global gamepass_rate
    
    try:
        expr_clean = expr.replace(",", "").lower().replace("x", "*").replace("÷", "/")
        robux = int(eval(expr_clean))
        await ctx.send(f"🎮 Gamepass {robux:,} Robux = **{robux/gamepass_rate:,.0f} บาท** (เรท {gamepass_rate})")
    except:
        await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)

@bot.command()
async def g(ctx, *, expr):
    """คำนวณราคา Group"""
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
    """คำนวณ Robux จากเงินบาท (Gamepass)"""
    global gamepass_rate
    
    try:
        baht = float(eval(expr.replace(",", "")))
        await ctx.send(f"🎮 {baht:,.0f} บาท = **{baht * gamepass_rate:,.0f} Robux** (Gamepass เรท {gamepass_rate})")
    except:
        await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)

@bot.command()
async def gb(ctx, *, expr):
    """คำนวณ Robux จากเงินบาท (Group)"""
    global group_rate_low, group_rate_high
    
    try:
        baht = float(eval(expr.replace(",", "")))
        rate = group_rate_low if baht < 500 else group_rate_high
        await ctx.send(f"👥 {baht:,.0f} บาท = **{baht * rate:,.0f} Robux** (Group เรท {rate})")
    except:
        await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)

@bot.command()
async def tax(ctx, *, expr):
    """คำนวณภาษี"""
    try:
        expr = expr.replace(" ", "")
        if re.match(r"^\d+$", expr):
            number = int(expr)
            await ctx.send(f"💰 {number:,} Robux หลังหัก 30% = **{number * 0.7:,.0f} Robux**")
        elif m := re.match(r"^(\d+)-(\d+)%$", expr):
            number = int(m[1])
            percent = int(m[2])
            await ctx.send(f"💰 {number:,} Robux หลังหัก {percent}% = **{number * (1 - percent/100):,.0f} Robux**")
        else:
            await ctx.send(
                "❌ รูปแบบไม่ถูกต้อง\n\n**การใช้งาน:**\n`!tax 100` - หัก 30% อัตโนมัติ\n`!tax 100-30%` - หัก 30%\n`!tax 100-50%` - หัก 50%", 
                delete_after=15
            )
    except:
        await ctx.send("❌ กรุณากรอกตัวเลขให้ถูกต้อง", delete_after=5)

@bot.command()
async def level(ctx, member=None):
    """เช็คเลเวล"""
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
    """คำสั่ง love"""
    await ctx.send("# LOVE YOU<:sushiheart:1410484970291466300>")

@bot.command()
async def say(ctx, *, message):
    """คำสั่ง say"""
    await ctx.send(f"# {message.upper()} <:sushiheart:1410484970291466300>")

@bot.command()
@admin_only()
async def setup(ctx):
    """ตั้งค่าระบบ"""
    try:
        await ctx.message.delete()
    except:
        pass
    
    await update_main_channel()
    await ctx.send(embed=discord.Embed(title="✅ ตั้งค่าระบบเรียบร้อยแล้ว", color=0x00FF00))

@bot.command()
@admin_only()
async def restart(ctx):
    """รีสตาร์ทปุ่ม"""
    try:
        await ctx.message.delete()
    except:
        pass
    
    await update_main_channel()
    await ctx.send(embed=discord.Embed(title="🔄 รีสตาร์ทระบบปุ่มเรียบร้อยแล้ว", color=0x00FF00))

@bot.command(name='help')
async def help_command(ctx):
    """แสดงคำสั่งทั้งหมด"""
    embed = discord.Embed(title="🍣 Sushi Shop - คำสั่งทั้งหมด", color=0x00FF99)
    embed.description = (
        "**คำสั่งทั่วไป:**\n"
        "`!gp <จำนวน>` - คำนวณราคา Gamepass\n"
        "`!g <จำนวน>` - คำนวณราคา Group\n"
        "`!gpb <จำนวน>` - คำนวณ Robux จากเงิน (Gamepass)\n"
        "`!gb <จำนวน>` - คำนวณ Robux จากเงิน (Group)\n"
        "`!tax <จำนวน>` - คำนวณ Robux หลังหักภาษี\n"
        "`!level` - เช็คเลเวลและ EXP ของคุณ\n"
        "`!love` - แสดงหัวใจ\n"
        "`!say <ข้อความ>` - บอทพูดตาม\n\n"
        "**คำสั่ง Slash Commands:**\n"
        "`/gamepass <จำนวน>` - คำนวณราคา Gamepass\n"
        "`/group <จำนวน>` - คำนวณราคา Group\n"
        "`/baht_gamepass <จำนวน>` - คำนวณ Robux จากเงิน (Gamepass)\n"
        "`/baht_group <จำนวน>` - คำนวณ Robux จากเงิน (Group)\n"
        "`/tax <จำนวน>` - คำนวณ Robux หลังหักภาษี\n"
        "`/help` - แสดงคำสั่งที่ใช้ได้\n\n"
        "**คำสั่งผู้ดูแลระบบเท่านั้น:**\n"
        "`!open` - เปิดร้าน\n"
        "`!close` - ปิดร้าน\n"
        "`!stock` - ตรวจสอบและตั้งค่า stock\n"
        "`!group <on/off>` - เปิด/ปิด Group ticket\n"
        "`!rate <เรท>` - ตั้งค่าเรท Gamepass\n"
        "`!rate group <ต่ำ> <สูง>` - ตั้งค่าเรท Group\n"
        "`!ty` - ส่งของเรียบร้อย (ใช้ในตั๋ว)\n"
        "`!qr` - แสดง QR Code\n"
        "`!od <จำนวน>` - รับออเดอร์ Gamepass\n"
        "`!odg <จำนวน>` - รับออเดอร์ Group\n"
        "`!setup` - ตั้งค่าระบบ\n"
        "`!restart` - รีสตาร์ทปุ่ม"
    )
    await ctx.send(embed=embed, delete_after=30)

# ==================== SLASH COMMANDS ====================
@bot.tree.command(name="gamepass", description="คำนวณราคา Gamepass")
async def gamepass_cmd(i, amount: str):
    global gamepass_rate
    
    try:
        expr_clean = amount.replace(",", "").replace("x", "*").replace("÷", "/")
        robux = int(eval(expr_clean))
        await i.response.send_message(f"🎮 Gamepass {robux:,} Robux = **{robux/gamepass_rate:,.0f} บาท** (เรท {gamepass_rate})")
    except:
        await i.response.send_message("❌ กรุณากรอกตัวเลขให้ถูกต้อง", ephemeral=True)

@bot.tree.command(name="group", description="คำนวณราคา Group")
async def group_cmd(i, amount: str):
    global group_rate_low, group_rate_high
    
    try:
        expr_clean = amount.replace(",", "").replace("x", "*").replace("÷", "/")
        robux = int(eval(expr_clean))
        rate = group_rate_low if robux < 2250 else group_rate_high
        await i.response.send_message(f"👥 Group {robux:,} Robux = **{robux/rate:,.0f} บาท** (เรท {rate})")
    except:
        await i.response.send_message("❌ กรุณากรอกตัวเลขให้ถูกต้อง", ephemeral=True)

@bot.tree.command(name="baht_gamepass", description="คำนวณ Robux จากเงินบาท")
async def baht_gamepass_cmd(i, amount: str):
    global gamepass_rate
    
    try:
        baht = float(eval(amount.replace(",", "")))
        await i.response.send_message(f"🎮 {baht:,.0f} บาท = **{baht * gamepass_rate:,.0f} Robux** (Gamepass เรท {gamepass_rate})")
    except:
        await i.response.send_message("❌ กรุณากรอกตัวเลขให้ถูกต้อง", ephemeral=True)

@bot.tree.command(name="baht_group", description="คำนวณเงินบาทเป็น Robux")
async def baht_group_cmd(i, amount: str):
    global group_rate_low, group_rate_high
    
    try:
        baht = float(eval(amount.replace(",", "")))
        rate = group_rate_low if baht < 500 else group_rate_high
        await i.response.send_message(f"👥 {baht:,.0f} บาท = **{baht * rate:,.0f} Robux** (Group เรท {rate})")
    except:
        await i.response.send_message("❌ กรุณากรอกตัวเลขให้ถูกต้อง", ephemeral=True)

@bot.tree.command(name="tax", description="คำนวณ Robux หลังหัก 30%")
async def tax_cmd(i, amount: str):
    try:
        amount = amount.replace(" ", "")
        if re.match(r"^\d+$", amount):
            number = int(amount)
            await i.response.send_message(f"💰 {number:,} Robux หลังหัก 30% = **{number * 0.7:,.0f} Robux**")
        elif m := re.match(r"^(\d+)-(\d+)%$", amount):
            number = int(m[1])
            percent = int(m[2])
            await i.response.send_message(f"💰 {number:,} Robux หลังหัก {percent}% = **{number * (1 - percent/100):,.0f} Robux**")
        else:
            await i.response.send_message(
                "❌ รูปแบบไม่ถูกต้อง\n\n**การใช้งาน:**\n`/tax 100` - หัก 30% อัตโนมัติ\n`/tax 100-30%` - หัก 30%\n`/tax 100-50%` - หัก 50%"
            )
    except:
        await i.response.send_message("❌ กรุณากรอกตัวเลขให้ถูกต้อง", ephemeral=True)

@bot.tree.command(name="help", description="แสดงคำสั่งทั้งหมดที่ใช้ได้")
async def help_cmd(i):
    embed = discord.Embed(title="🍣 Sushi Shop - คำสั่งทั้งหมด", color=0x00FF99)
    embed.description = (
        "**คำสั่ง Slash Commands (ใช้ /):**\n"
        "`/gamepass <จำนวน>` - คำนวณราคา Gamepass\n"
        "`/group <จำนวน>` - คำนวณราคา Group\n"
        "`/baht_gamepass <จำนวน>` - คำนวณ Robux จากจำนวนบาท\n"
        "`/baht_group <จำนวน>` - คำนวณ Robux จากจำนวนบาท\n"
        "`/tax <จำนวน>` - คำนวณ Robux หลังหักภาษี\n"
        "`/help` - แสดงคำสั่งที่ใช้ได้\n\n"
        "**หมายเหตุ:**\n"
        "• คำสั่งเหล่านี้ใช้ได้ทั้งในเซิร์ฟเวอร์และ DM\n"
        "• ในการสั่งซื้อจริง ต้องเปิดตั๋วในเซิร์ฟเวอร์เท่านั้น"
    )
    await i.response.send_message(embed=embed)

async def check_user_level(i):
    user_id = str(i.user.id)
    if user_id not in user_data:
        user_data[user_id] = {"exp": 0, "level": 0}
    
    user_exp = user_data[user_id]["exp"]
    user_level = user_data[user_id]["level"]
    
    embed = discord.Embed(title=f"🍣 ระดับของคุณ {i.user.display_name}", color=0x00FF99)
    
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
    await i.response.send_message(embed=embed, ephemeral=True)

# ==================== TASKS ====================
@tasks.loop(minutes=1)
async def update_presence():
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching, 
            name=f"ร้าน Sushi Shop | GP: {gamepass_stock} | Group: {group_stock}"
        )
    )

@tasks.loop(minutes=5)
async def save_data():
    save_json(user_data_file, user_data)
    save_json(ticket_transcripts_file, ticket_transcripts)
    save_json(ticket_robux_data_file, ticket_robux_data)
    save_json(ticket_customer_data_file, ticket_customer_data)

# ==================== EVENTS ====================
@bot.event
async def on_ready():
    print(f"✅ บอทออนไลน์แล้ว: {bot.user} (ID: {bot.user.id})")
    
    if not bot.commands_synced:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} commands")
        bot.commands_synced = True
    
    activity_text = f"ร้าน Sushi Shop | GP: {gamepass_stock} | Group: {group_stock}"
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching, 
            name=activity_text
        )
    )
    
    # Start background tasks
    update_presence.start()
    save_data.start()
    
    # Update channel and main message
    await update_channel_name()
    await update_main_channel()
    
    print("🎯 บอทพร้อมใช้งาน!")

@bot.event
async def on_message(message):
    # Handle credit channel reactions
    if message.channel.id == CREDIT_CHANNEL_ID and message.author != bot.user:
        await asyncio.sleep(2)
        for emoji in ["❤️", "🍣"]:
            try:
                await message.add_reaction(emoji)
                await asyncio.sleep(1)
            except:
                pass
    
    await bot.process_commands(message)

# ==================== START ====================
if __name__ == "__main__":
    keep_alive()
    print("⏳ รอ 30 วินาทีก่อนเริ่มบอท...")
    time.sleep(30)
    
    token = os.getenv("TOKEN")
    if not token:
        print("❌ ไม่พบ TOKEN ใน environment variables")
        exit(1)
    
    bot.run(token)
