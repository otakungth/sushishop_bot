import os
import datetime
import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import re

from server import server_on

# ตั้งค่าเรท
gamepass_rate = 6
group_rate_low = 4
group_rate_high = 4.5

# ตั้งค่าพื้นฐาน
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
shop_open = True

# ตั้งค่าห้องหลักและ stock
MAIN_CHANNEL_ID = 1361044752975532152  # เปลี่ยนเป็น ID ห้องหลักที่คุณต้องการ
SALES_LOG_CHANNEL_ID = 1402993077643120720
stock_amount = 100  # จำนวน stock เริ่มต้น

bot = commands.Bot(command_prefix="!", intents=intents)

# --------------------------------------------------------------------------------------------------
# ฟังก์ชันส่งบันทึกการขาย
async def send_sale_log(embed_data: discord.Embed, interaction: discord.Interaction = None, ctx: commands.Context = None, delivered_by: discord.Member = None):
    """ส่ง Embed ไปยังห้องบันทึกการขาย พร้อมผู้ส่งสินค้า"""
    try:
        channel = bot.get_channel(SALES_LOG_CHANNEL_ID)
        if channel is None:
            print("❌ ไม่พบห้องบันทึกการขาย")
            return

        # ข้อมูลจาก Embed เดิม
        robux_amount = next((f.value for f in embed_data.fields if f.name == "💸 จำนวน Robux"), "ไม่ทราบ")
        price = next((f.value for f in embed_data.fields if f.name in ("💰 ราคาตามเรท", "💰 ราคา")), "ไม่ทราบ")
        user_name = next((f.value for f in embed_data.fields if f.name == "😊 ผู้ซื้อ"), "ไม่ทราบ")

        # ประเภทสินค้า
        sale_type = "ไม่ทราบ"
        current_channel = interaction.channel if interaction else ctx.channel if ctx else None
        if current_channel:
            category_name = current_channel.category.name if current_channel.category else ""
            if "gamepass" in category_name.lower():
                sale_type = "Robux Gamepass"
            elif "group" in category_name.lower():
                sale_type = "Robux Group"

        # ผู้สร้างตั๋ว
        ticket_creator = None
        if current_channel and current_channel.name.startswith("ticket-"):
            try:
                user_id = int(current_channel.name.split("-")[-1])
                ticket_creator = await current_channel.guild.fetch_member(user_id)
            except (IndexError, ValueError, discord.NotFound):
                pass

        # สร้าง Embed ใหม่
        log_embed = discord.Embed(
            title="🍣 บันทึกการขายสำเร็จ 🍣",
            color=0x00FF00,
            timestamp=discord.utils.utcnow()
        )
        log_embed.add_field(name="📦 ประเภทสินค้า", value=sale_type, inline=False)
        log_embed.add_field(name="😊 ผู้ซื้อ", value=ticket_creator.mention if ticket_creator else user_name, inline=False)
        log_embed.add_field(name="💸 จำนวน Robux", value=robux_amount, inline=True)
        log_embed.add_field(name="💰 ราคา", value=price, inline=True)
        log_embed.add_field(name="🚚 ผู้ส่งสินค้า", value=delivered_by.mention if delivered_by else "ไม่ทราบ", inline=False)
        log_embed.set_footer(text="การสั่งซื้อสำเร็จ")

        await channel.send(embed=log_embed)

    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการส่งบันทึกการขาย: {e}")

# --------------------------------------------------------------------------------------------------
# คำสั่งจัดการ Stock
@bot.command()
@commands.has_permissions(administrator=True)
async def stock(ctx, amount: int = None):
    """ตั้งค่าจำนวน stock (เฉพาะผู้ดูแล)"""
    global stock_amount
    
    if amount is None:
        await ctx.send(f"📊 Stock ปัจจุบัน: **{stock_amount}**", delete_after=10)
        return
    
    if amount < 0:
        await ctx.send("❌ จำนวน stock ต้องมากกว่าหรือเท่ากับ 0", delete_after=5)
        return
    
    stock_amount = amount
    await ctx.send(f"✅ ตั้งค่า stock เป็น **{stock_amount}** เรียบร้อยแล้ว", delete_after=5)
    
    # อัปเดตข้อความในช่องหลัก
    await update_main_channel()

# --------------------------------------------------------------------------------------------------
# คำสั่งเปิดปิดร้าน
@bot.command()
@commands.has_permissions(administrator=True)
async def sushi(ctx):
    """เปิด/ปิดร้าน (รวมทั้ง Gamepass และ Group)"""
    global shop_open
    shop_open = not shop_open

    status = "✅ ร้านเปิด" if shop_open else "❌ ร้านปิด"
    await ctx.send(
        f"📌 สถานะร้านถูกเปลี่ยนเป็น: **{status}**",
        delete_after=5
    )

    if ctx.channel.id == MAIN_CHANNEL_ID:
        await update_main_channel()

# --------------------------------------------------------------------------------------------------
# อัปเดตช่องหลัก
async def update_main_channel():
    """อัปเดตข้อความในช่องหลัก"""
    channel = bot.get_channel(MAIN_CHANNEL_ID)
    if not channel:
        return

    # ลบข้อความเก่าๆ ของบอทในช่องนี้
    async for msg in channel.history(limit=20):
        if msg.author == bot.user:
            await msg.delete()

    # สร้าง embed หลัก
    embed = discord.Embed(
        title="🍣 Sushi Shop 🍣",
        color=0xFFD700
    )
    
    # ส่วน Gamepass
    embed.add_field(
        name="🎮 Gamepass",
        value=(
            f"เรท **{gamepass_rate}**\n"
            "กดปุ่ม 'เปิดตั๋ว Gamepass' เพื่อกดเกมพาสหรือสอบถามได้เลยครับ\n\n"
            "หากลูกค้ามีปัญหาได้รับของผิดสามารถติดต่อทีมงานได้เลยนะครับ"
        ),
        inline=False
    )
    
    # ส่วน Group
    embed.add_field(
        name="👥 Robux Group", 
        value=(
            f"🛒 โรกลุ่มเรท **{group_rate_low}** ซื้อมากกว่า 500 บาทเรท **{group_rate_high}**\n"
            "กดปุ่ม 'เปิดตั๋ว Group' เพื่อสั่งซื้อได้เลยครับ\n\n"
            "เข้ากลุ่มนี้: https://www.roblox.com/communities/34713179/VALKYs\n\n"
            "⚠️ กรุณาเข้ากลุ่มให้ครบ 15 วัน ⚠️\n\n"
            f"📌 จดวันที่เข้ากลุ่มได้ที่ <#1387421905941827615>\n\n"
            "หากลูกค้ามีปัญหาสามารถแจ้งทีมงานได้เลยครับ"
        ),
        inline=False
    )
    
    # เพิ่ม stock
    embed.add_field(
        name="📊 จำนวน Stock",
        value=f"**{stock_amount}**",
        inline=False
    )
    
    embed.set_thumbnail(
        url="https://media.discordapp.net/attachments/717757556889747657/1403684950770847754/noFilter.png"
    )

    # ส่ง embed พร้อมปุ่ม
    await channel.send(embed=embed, view=MainShopView())

# --------------------------------------------------------------------------------------------------
# Views และ Modals หลัก
class MainShopView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        
        if shop_open and stock_amount > 0:
            self.add_item(Button(label="เปิดตั๋ว Gamepass", style=discord.ButtonStyle.success, custom_id="open_gamepass_ticket"))
            self.add_item(Button(label="เปิดตั๋ว Group", style=discord.ButtonStyle.primary, custom_id="open_group_ticket"))
        else:
            self.add_item(Button(label="❌ ร้านปิดชั่วคราว", style=discord.ButtonStyle.danger, disabled=True))

# --------------------------------------------------------------------------------------------------
# Modal สำหรับ Gamepass
class GamepassTicketModal(Modal, title="📋 แบบฟอร์มสั่งซื้อ Gamepass"):
    map_name = TextInput(
        label="🗺 ชื่อแมพที่จะกด?",
        placeholder="พิมพ์ชื่อแมพ เช่น All Star Tower Defense X",
        required=True
    )
    gamepass_name = TextInput(
        label="💸 กดเกมพาสอะไร?",
        placeholder="พิมพ์ชื่อเกมพาส เช่น x3 Speed 3 ชิ้น",
        required=True
    )
    robux_amount = TextInput(
        label="🎟 รวมทั้งหมดกี่ Robux?",
        placeholder="เช่น 995 หรือ 100+100+100 หรือ 100x3",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # แปลง input ให้รองรับ x และ ÷
            expr = self.robux_amount.value.lower().replace("x", "*").replace("÷", "/")

            # ตรวจสอบว่า input มีแต่ตัวเลขและเครื่องหมายที่อนุญาต
            if not re.match(r"^[\d\s\+\-\*\/\(\)]+$", expr):
                await interaction.response.send_message("❌ กรุณาใส่เฉพาะตัวเลข และเครื่องหมาย + - * / x ÷ ()", ephemeral=True)
                return

            # คำนวณ robux
            robux = int(eval(expr))
            price = robux / gamepass_rate
            price_str = f"{price:,.0f} บาท"

            # Embed ลูกค้า
            customer_embed = discord.Embed(title="📨 รายละเอียดการสั่งซื้อ Gamepass", color=0x00FF99)
            customer_embed.add_field(name="🗺️ แมพ", value=self.map_name.value, inline=False)
            customer_embed.add_field(name="🎟 เกมพาส", value=self.gamepass_name.value, inline=False)
            customer_embed.add_field(name="💸 จำนวน Robux", value=f"{robux:,}", inline=True)
            customer_embed.add_field(name="💰 ราคา", value=price_str, inline=True)
            customer_embed.set_footer(text="ทีมงานจะตอบกลับโดยเร็วที่สุดครับ")

            # Embed ยืนยัน
            confirm_embed = customer_embed.copy()
            confirm_embed.set_footer(text=f"🧾 ผู้ใช้: {interaction.user}")

            view = ConfirmTicketView(embed_data=confirm_embed)
            await interaction.response.send_message(embed=customer_embed, view=view, ephemeral=False)

        except Exception as e:
            await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

# --------------------------------------------------------------------------------------------------
# Modal สำหรับ Group
class GroupTicketModal(Modal, title="📋 แบบฟอร์มสั่งซื้อ Robux Group"):
    user_name = TextInput(
        label="🪪 ชื่อในเกม", 
        placeholder="Username", 
        required=True
    )
    robux_amount = TextInput(
        label="💸 ต้องการกดทั้งหมดกี่ Robux?", 
        placeholder="กรอกจำนวน Robux ที่ต้องการ", 
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            robux = int(self.robux_amount.value)
            rate = group_rate_low if robux < 1500 else group_rate_high
            price = robux / rate
            price_str = f"{price:,.0f} บาท"

            customer_embed = discord.Embed(title="📨 รายละเอียดคำสั่งซื้อ Robux Group", color=0x00FF99)
            customer_embed.add_field(name="🪪 ชื่อในเกม", value=self.user_name.value, inline=False)
            customer_embed.add_field(name="💸 จำนวน Robux", value=f"{robux:,}", inline=True)
            customer_embed.add_field(name="💰 ราคา", value=price_str, inline=True)
            customer_embed.set_footer(text="ทีมงานจะตรวจสอบและตอบกลับโดยเร็วที่สุดครับ")

            confirm_embed = customer_embed.copy()
            confirm_embed.set_footer(text=f"🧾 ผู้ใช้: {interaction.user}")

            view = ConfirmTicketView(embed_data=confirm_embed)
            await interaction.response.send_message(embed=customer_embed, view=view, ephemeral=False)

        except ValueError:
            await interaction.response.send_message("❌ กรุณากรอกจำนวน Robux เป็นตัวเลข", ephemeral=True)

# --------------------------------------------------------------------------------------------------
# View สำหรับยืนยันตั๋ว
class ConfirmTicketView(View):
    def __init__(self, embed_data: discord.Embed):
        super().__init__(timeout=None)
        self.embed_data = discord.Embed.from_dict(embed_data.to_dict())

    @discord.ui.button(label="✅ ส่งของเรียบร้อยแล้ว", style=discord.ButtonStyle.success, custom_id="confirm_ticket")
    async def confirm_button(self, interaction: discord.Interaction, button: Button):
        role_id = 1361016912259055896
        role = interaction.guild.get_role(role_id)
        if role not in interaction.user.roles:
            await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ยืนยันการสั่งซื้อนี้", ephemeral=True)
            return

        if any(field.name == "📋 ยืนยันโดย" for field in self.embed_data.fields):
            await interaction.response.send_message("⚠️ คำสั่งซื้อนี้ถูกยืนยันแล้ว", ephemeral=True)
            return

        self.embed_data.add_field(name="📋 ยืนยันโดย", value=interaction.user.mention, inline=False)
        await send_sale_log(self.embed_data, interaction=interaction, delivered_by=interaction.user)

        await interaction.response.send_message("✅ ส่งของเรียบร้อยแล้ว", ephemeral=True)
        await interaction.message.edit(view=None)

    @discord.ui.button(label="❌ ยกเลิกสินค้า", style=discord.ButtonStyle.danger, custom_id="cancel_ticket")
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        cancel_embed = discord.Embed(
            title="❌ คำสั่งซื้อถูกยกเลิก",
            description=f"คำสั่งซื้อนี้ถูกยกเลิกโดย {interaction.user.mention}",
            color=0xFF0000
        )
        await interaction.response.send_message(embed=cancel_embed)
        await interaction.message.edit(view=None)

# --------------------------------------------------------------------------------------------------
# ฟังก์ชันจัดการการเปิดตั๋ว
class GoToTicketView(discord.ui.View):
    def __init__(self, channel):
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(
                label="ไปที่ตั๋ว",
                url=channel.jump_url,
                style=discord.ButtonStyle.link
            )
        )

async def handle_open_ticket(interaction, category_name, view_class, modal_class, mention_user=False):
    global stock_amount
    
    # ตรวจสอบ stock
    if stock_amount <= 0:
        await interaction.response.send_message("❌ ขออภัย สินค้าหมดชั่วคราว", ephemeral=True)
        return
        
    guild = interaction.guild
    user = interaction.user

    if guild is None:
        await interaction.response.send_message("❌ คำสั่งนี้ใช้ได้เฉพาะในเซิร์ฟเวอร์", ephemeral=True)
        return

    channel_name = f"ticket-{user.name}-{user.id}"
    existing_channel = discord.utils.get(guild.text_channels, name=channel_name)

    if isinstance(user, discord.Member) and existing_channel and existing_channel.permissions_for(user).read_messages:
        await interaction.response.send_message("📌 คุณมีตั๋วเปิดอยู่แล้ว!", ephemeral=True)
        return

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }

    admin_role = guild.get_role(1361016912259055896)
    if admin_role:
        overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

    category = discord.utils.get(guild.categories, name=category_name)
    if category is None:
        await interaction.response.send_message(f"❌ ไม่พบหมวดหมู่ {category_name}", ephemeral=True)
        return

    channel = await guild.create_text_channel(
        name=channel_name,
        overwrites=overwrites,
        reason="New ticket",
        category=category
    )
    
    # ลด stock
    stock_amount -= 1
    await update_main_channel()
    
    await interaction.response.send_message(
        content="📩 เปิดตั๋วเรียบร้อย!",
        view=GoToTicketView(channel),
        ephemeral=True
    )

    if admin_role:
        await channel.send(content=admin_role.mention)

    welcome_embed = discord.Embed(
        title="🍣 Sushi Shop 🍣",
        description=(
            "ลูกค้า :\n\n"
            f"{user.mention}\n\n"
            "พนักงาน :\n\n"
            f"{admin_role.mention if admin_role else 'ไม่พบพนักงาน'}\n\n"
            "** 🎟️ สนใจซื้ออะไรระบุชื่อหรือรูปภาพมาได้เลยนะคะ **\n\n"
            "หากต้องการเช็คราคาให้พิมพ์คำสั่ง\n"
            "!gp เช่น : ''!gp 799 / !gp 299+599 / !gp 59x7''"
        ),
        color=0x00FF99
    )
    welcome_embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/717757556889747657/1403684950770847754/noFilter.png")
    welcome_embed.set_footer(text="Sushi Shop Service")

    await channel.send(embed=welcome_embed, view=view_class(channel, user, modal_class))

# --------------------------------------------------------------------------------------------------
# View สำหรับตั๋ว
class TicketActionView(View):
    def __init__(self, channel: discord.TextChannel, owner: discord.Member, modal_class):
        super().__init__(timeout=None)
        self.channel = channel
        self.owner = owner
        self.modal_class = modal_class

    @discord.ui.button(label="📝 กรอกแบบฟอร์ม", style=discord.ButtonStyle.primary)
    async def open_form(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(self.modal_class())

    @discord.ui.button(label="📤 ช่องทางการโอนเงิน", style=discord.ButtonStyle.success)
    async def payment_info(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(title="📤 ช่องทางการโอนเงิน").set_image(
            url="https://media.discordapp.net/attachments/722832040860319835/1402994996600111114/186-8-06559-8.png"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🔒 ปิดตั๋ว", style=discord.ButtonStyle.danger)
    async def close_ticket(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.owner.id:
            await interaction.response.send_message("❌ คุณไม่ใช่เจ้าของตั๋วนี้", ephemeral=True)
            return

        await interaction.response.send_message("📪 กำลังปิดตั๋วใน 5 วินาที...", ephemeral=True)
        await discord.utils.sleep_until(discord.utils.utcnow() + datetime.timedelta(seconds=5))
        
        # คืน stock เมื่อปิดตั๋ว
        global stock_amount
        stock_amount += 1
        await update_main_channel()
        
        await self.channel.delete()

# --------------------------------------------------------------------------------------------------
# Events
@bot.event
async def on_ready():
    print(f"✅ บอทออนไลน์แล้ว: {bot.user}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="ร้าน Sushi Shop"))
    await update_main_channel()

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if not interaction.data:
        return

    custom_id = interaction.data.get("custom_id")

    if custom_id == "open_gamepass_ticket":
        await handle_open_ticket(
            interaction,
            category_name="🍣Sushi Gamepass 🍣",
            view_class=TicketActionView,
            modal_class=GamepassTicketModal,
            mention_user=True
        )

    elif custom_id == "open_group_ticket":
        await handle_open_ticket(
            interaction,
            category_name="💰Robux Group💰",
            view_class=TicketActionView,
            modal_class=GroupTicketModal,
            mention_user=False
        )

# --------------------------------------------------------------------------------------------------
# คำสั่งคำนวณราคา (แบบเห็นเฉพาะผู้ใช้)
async def send_ephemeral_calculation(ctx, calculation_func, expression, product_type):
    """ส่งผลการคำนวณแบบเห็นเฉพาะผู้ใช้"""
    try:
        expression = expression.replace(",", "").lower().replace("x", "*").replace("÷", "/")

        if not re.match(r"^[\d\s\+\-\*\/\(\)]+$", expression):
            await ctx.send("❌ กรุณาใส่เฉพาะตัวเลข และเครื่องหมาย + - * / x ÷ ()", ephemeral=True)
            return

        result = calculation_func(expression)
        await ctx.send(result, ephemeral=True)

    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

def calculate_gp(expression):
    """คำนวณราคา Gamepass"""
    robux = eval(expression)
    price = robux / gamepass_rate
    return f"🎮 Gamepass {robux:,} Robux = **{price:,.0f} บาท** (เรท {gamepass_rate})"

def calculate_g(expression):
    """คำนวณราคา Group"""
    robux = eval(expression)
    rate = group_rate_low if robux < 1500 else group_rate_high
    price = robux / rate
    return f"👥 Group {robux:,} Robux = **{price:,.0f} บาท** (เรท {rate})"

def calculate_gpb(expression):
    """คำนวณจากเงินเป็น Robux (Gamepass)"""
    baht = eval(expression)
    robux = baht * gamepass_rate
    return f"🎮 {baht:,.0f} บาท = **{robux:,.0f} Robux** (Gamepass เรท {gamepass_rate})"

def calculate_gb(expression):
    """คำนวณจากเงินเป็น Robux (Group)"""
    baht = eval(expression)
    rate = group_rate_low if baht < 500 else group_rate_high
    robux = baht * rate
    return f"👥 {baht:,.0f} บาท = **{robux:,.0f} Robux** (Group เรท {rate})"

# คำสั่งคำนวณราคาแบบเห็นเฉพาะผู้ใช้
@bot.command()
async def gp(ctx, *, expression: str):
    """คำนวณราคาจากจำนวน Robux (Gamepass) - เห็นเฉพาะคุณ"""
    await send_ephemeral_calculation(ctx, calculate_gp, expression, "Gamepass")

@bot.command()
async def g(ctx, *, expression: str):
    """คำนวณราคาจากจำนวน Robux (Group) - เห็นเฉพาะคุณ"""
    await send_ephemeral_calculation(ctx, calculate_g, expression, "Group")

@bot.command()
async def gpb(ctx, *, expression: str):
    """คำนวณจากจำนวนเงิน เป็น Robux (Gamepass) - เห็นเฉพาะคุณ"""
    await send_ephemeral_calculation(ctx, calculate_gpb, expression, "Gamepass")

@bot.command()
async def gb(ctx, *, expression: str):
    """คำนวณจากจำนวนเงิน เป็น Robux (Group) - เห็นเฉพาะคุณ"""
    await send_ephemeral_calculation(ctx, calculate_gb, expression, "Group")

# --------------------------------------------------------------------------------------------------
# คำสั่งอื่นๆ ที่เหลือ
@bot.command()
@commands.has_permissions(administrator=True)
async def qr(ctx):
    embed = discord.Embed(
        title="📱 สแกน QR เพื่อชำระเงิน",
        description="กรุณาสแกน QR นี้เพื่อชำระเงินตามราคาที่ระบุไว้",
        color=0x00CCFF)
    embed.set_image(url="https://media.discordapp.net/attachments/722832040860319835/1402994996600111114/186-8-06559-8.png")
    await ctx.send(embed=embed)
    await ctx.message.delete()

@bot.command()
@commands.has_permissions(administrator=True)
async def ty(ctx):
    if ctx.channel.name.startswith("ticket-"):
        # คืน stock เมื่อส่งของสำเร็จ
        global stock_amount
        stock_amount += 1
        await update_main_channel()
        
        # โค้ดเดิม...
        sale_embed = None
        async for msg in ctx.channel.history():
            if msg.embeds and "รายละเอียดการสั่งซื้อ" in msg.embeds[0].title:
                sale_embed = msg.embeds[0]
                break

        if sale_embed:
            confirmed = any(field.name == "📋 ยืนยันโดย" for field in sale_embed.fields)
            if not confirmed:
                sale_embed.add_field(name="📋 ยืนยันโดย", value=ctx.author.mention, inline=False)

        delivered_category = discord.utils.get(ctx.guild.categories, name="ส่งของแล้ว")
        if delivered_category:
            try:
                await ctx.channel.edit(category=delivered_category)
            except Exception as e:
                print(f"❌ ไม่สามารถย้ายหมวดหมู่: {e}")

        embed = discord.Embed(
            title="✅ สินค้าถูกส่งเรียบร้อยแล้ว",
            description=(
                "ขอบคุณที่ใช้บริการกับเรา หากไม่มีปัญหาเพิ่มเติม "
                "สามารถกดปุ่มด้านล่างเพื่อปิดตั๋วได้เลย\n\n"
                "⏳ **หากไม่ได้กดปิดตั๋ว ตั๋วจะถูกปิดอัตโนมัติใน 1 ชั่วโมง**"
            ),
            color=0x00FF00
        )
        await ctx.send(embed=embed, view=CloseTicketView(ctx.channel))

        async def auto_close():
            await discord.utils.sleep_until(discord.utils.utcnow() + datetime.timedelta(hours=1))
            if ctx.channel and ctx.channel.name.startswith("ticket-"):
                try:
                    await ctx.send("⏳ ไม่มีการตอบกลับ ตั๋วนี้จะถูกปิดอัตโนมัติ")
                    await ctx.channel.delete()
                except:
                    pass

        bot.loop.create_task(auto_close())

    await ctx.message.delete()

@bot.command()
@commands.has_permissions(administrator=True)
async def closeticket(ctx):
    if ctx.channel.name.startswith("ticket-"):
        # คืน stock เมื่อปิดตั๋ว
        global stock_amount
        stock_amount += 1
        await update_main_channel()
        
        sale_embed = None
        async for msg in ctx.channel.history():
            if msg.embeds and "รายละเอียดการสั่งซื้อ" in msg.embeds[0].title:
                sale_embed = msg.embeds[0]
                break

        if sale_embed:
            await send_sale_log(sale_embed, ctx=ctx)

        await ctx.send("📪 กำลังปิดตั๋วใน 5 วินาที...")
        await ctx.message.delete()
        await discord.utils.sleep_until(discord.utils.utcnow() + datetime.timedelta(seconds=5))
        await ctx.channel.delete()
    else:
        await ctx.message.delete()

class CloseTicketView(discord.ui.View):
    def __init__(self, channel: discord.TextChannel):
        super().__init__(timeout=None)
        self.channel = channel

        self.add_item(discord.ui.Button(
            label="📌 ให้เครดิต",
            style=discord.ButtonStyle.success,
            url="https://discord.com/channels/1360990259311018077/1361049580736745502"
        ))

    @discord.ui.button(label="🔒 ปิดตั๋ว", style=discord.ButtonStyle.danger)
    async def close_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # คืน stock เมื่อปิดตั๋ว
        global stock_amount
        stock_amount += 1
        await update_main_channel()
        
        await interaction.response.send_message("📪 กำลังปิดตั๋วใน 5 วินาที...", ephemeral=True)
        await discord.utils.sleep_until(discord.utils.utcnow() + datetime.timedelta(seconds=5))
        await self.channel.delete()

# --------------------------------------------------------------------------------------------------
server_on()
bot.run(os.getenv("TOKEN"))
