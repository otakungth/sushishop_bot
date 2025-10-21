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

# ตั้งค่า stock
gamepass_stock = 1000  # สามารถปรับค่าได้
group_stock = 500     # สามารถปรับค่าได้

# ห้องบันทึกการขาย
SALES_LOG_CHANNEL_ID = 1402993077643120720

# ID ช่องที่ต้องการแสดง embed
MAIN_CHANNEL_ID = 1361044752975532152  # เปลี่ยนเป็น ID ช่องที่คุณต้องการ

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
# คำสั่งจัดการ stock
@bot.command()
@commands.has_permissions(administrator=True)
async def stock(ctx, product: str = None, amount: int = None):
    """ปรับจำนวน stock ของสินค้า"""
    global gamepass_stock, group_stock
    
    if product is None or amount is None:
        embed = discord.Embed(
            title="📊 Stock ปัจจุบัน",
            color=0x00FF00
        )
        embed.add_field(name="🎮 Gamepass Stock", value=f"{gamepass_stock:,} Robux", inline=True)
        embed.add_field(name="👥 Group Stock", value=f"{group_stock:,} Robux", inline=True)
        embed.add_field(name="🔄 อัพเดทล่าสุด", value=f"<t:{int(datetime.datetime.now().timestamp())}:R>", inline=False)
        await ctx.send(embed=embed)
        return
    
    product = product.lower()
    if product in ["gamepass", "gp"]:
        gamepass_stock = amount
        await ctx.send(f"✅ ตั้งค่า Gamepass stock เป็น **{amount:,} Robux**")
    elif product in ["group", "g"]:
        group_stock = amount
        await ctx.send(f"✅ ตั้งค่า Group stock เป็น **{amount:,} Robux**")
    else:
        await ctx.send("❌ โปรดระบุประเภทสินค้า: `gamepass` หรือ `group`")
    
    # อัพเดท embed หลัก
    await update_main_embed(ctx)

async def update_main_embed(ctx=None):
    """อัพเดท embed หลักในช่องที่กำหนด"""
    try:
        channel = bot.get_channel(MAIN_CHANNEL_ID)
        if channel is None:
            print("❌ ไม่พบช่องหลัก")
            return

        # ลบข้อความเก่า ๆ ของบอทในช่องนี้
        async for msg in channel.history(limit=10):
            if msg.author == bot.user and msg.embeds:
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
                f"**เรท {gamepass_rate}**\n"
                f"```จำนวน stock: {gamepass_stock:,} Robux```\n"
                "กดปุ่ม 'เปิดตั๋ว Gamepass' เพื่อกดเกมพาสหรือสอบถามได้เลยครับ\n\n"
                "หากลูกค้ามีปัญหาได้รับของผิดสามารถติดต่อทีมงานได้เลยนะครับ"
            ),
            inline=False
        )
        
        # ส่วน Group
        embed.add_field(
            name="👥 Robux Group", 
            value=(
                f"**เรท {group_rate_low} (ซื้อมากกว่า 500 บาทเรท {group_rate_high})**\n"
                f"```จำนวน stock: {group_stock:,} Robux```\n"
                "กดปุ่ม 'เปิดตั๋ว Group' เพื่อสั่งซื้อได้เลยครับ\n\n"
                "เข้ากลุ่มนี้: https://www.roblox.com/communities/34713179/VALKYs\n\n"
                "⚠️ กรุณาเข้ากลุ่มให้ครบ 15 วัน ⚠️\n\n"
                f"📌 จดวันที่เข้ากลุ่มได้ที่ <#1387421905941827615>\n\n"
                "หากลูกค้ามีปัญหาสามารถแจ้งทีมงานได้เลยครับ"
            ),
            inline=False
        )
        
        embed.set_thumbnail(url="https://media.discordapp.net/attachments/717757556889747657/1403684950770847754/noFilter.png")
        embed.set_footer(text="อัพเดทล่าสุด")

        await channel.send(embed=embed, view=MainTicketView())
        
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการอัพเดท embed หลัก: {e}")

# --------------------------------------------------------------------------------------------------
# View หลักที่มีปุ่ม 2 อัน
class MainTicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        
        # ปุ่ม Gamepass
        gamepass_button = Button(
            label="เปิดตั๋ว Gamepass", 
            style=discord.ButtonStyle.success if shop_open else discord.ButtonStyle.danger,
            custom_id="open_gamepass_ticket",
            disabled=not shop_open
        )
        
        # ปุ่ม Group
        group_button = Button(
            label="เปิดตั๋ว Group", 
            style=discord.ButtonStyle.primary if shop_open else discord.ButtonStyle.danger,
            custom_id="open_group_ticket", 
            disabled=not shop_open
        )
        
        self.add_item(gamepass_button)
        self.add_item(group_button)

# --------------------------------------------------------------------------------------------------
# คำสั่งเปิด-ปิดร้าน
@bot.command()
@commands.has_permissions(administrator=True)
async def sushi(ctx):
    """เปิด-ปิดร้าน (ทั้ง Gamepass และ Group)"""
    global shop_open
    shop_open = not shop_open

    status = "✅ ร้านเปิด" if shop_open else "❌ ร้านปิด"
    embed = discord.Embed(
        title="🍣 สถานะร้าน",
        description=f"**{status}**",
        color=0x00FF00 if shop_open else 0xFF0000
    )
    await ctx.send(embed=embed, delete_after=5)
    await update_main_embed(ctx)
    await ctx.message.delete()

@bot.command()
@commands.has_permissions(administrator=True)
async def openshop(ctx):
    """เปิดร้านค้า"""
    global shop_open
    shop_open = True
    await ctx.send("✅ เปิดร้านค้าเรียบร้อยแล้ว", delete_after=5)
    await update_main_embed(ctx)
    await ctx.message.delete()

@bot.command()
@commands.has_permissions(administrator=True)
async def closeshop(ctx):
    """ปิดร้านค้า"""
    global shop_open
    shop_open = False
    await ctx.send("❌ ปิดร้านค้าเรียบร้อยแล้ว", delete_after=5)
    await update_main_embed(ctx)
    await ctx.message.delete()

# --------------------------------------------------------------------------------------------------
# คำสั่งแสดง QR
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

# --------------------------------------------------------------------------------------------------
# ส่วนที่เหลือของโค้ด (Modal, View, Events ต่างๆ) ให้คงเดิม
# โดยเปลี่ยน custom_id ใน event on_interaction ให้ตรงกับปุ่มใหม่

class TicketInfoModal(Modal, title="📋 แบบฟอร์มสั่งสินค้า"):
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
            
            # ตรวจสอบ stock
            global gamepass_stock
            if robux > gamepass_stock:
                await interaction.response.send_message(
                    f"❌ Stock ไม่เพียงพอ! Stock ปัจจุบัน: {gamepass_stock:,} Robux", 
                    ephemeral=True
                )
                return
                
            price = robux / gamepass_rate
            price_str = f"{price:,.0f} บาท"

            # Embed ลูกค้า
            customer_embed = discord.Embed(title="📨 รายละเอียดการสั่งซื้อ", color=0x00FF99)
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

class GroupTicketInfoModal(Modal, title="📋 แบบฟอร์ม Robux Group"):
    user_name = TextInput(label="🪪 ชื่อในเกม", placeholder="Username", required=True)
    robux_amount = TextInput(label="💸 ต้องการกดทั้งหมดกี่ Robux?", placeholder="กรอกจำนวน Robux ที่ต้องการ", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            robux = int(self.robux_amount.value)
            
            # ตรวจสอบ stock
            global group_stock
            if robux > group_stock:
                await interaction.response.send_message(
                    f"❌ Stock ไม่เพียงพอ! Stock ปัจจุบัน: {group_stock:,} Robux", 
                    ephemeral=True
                )
                return
                
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

            view = GroupConfirmTicketView(embed_data=confirm_embed)
            await interaction.response.send_message(embed=customer_embed, view=view, ephemeral=False)

        except ValueError:
            await interaction.response.send_message("❌ กรุณากรอกจำนวน Robux เป็นตัวเลข", ephemeral=True)

# --------------------------------------------------------------------------------------------------
# Events
@bot.event
async def on_ready():
    print(f"✅ บอทออนไลน์แล้ว: {bot.user}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="ร้าน Sushi Shop"))
    await update_main_embed()

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if not interaction.data:
        return

    custom_id = interaction.data.get("custom_id")

    if custom_id == "open_gamepass_ticket":
        await handle_open_ticket(
            interaction,
            category_name="🍣Sushi Gamepass 🍣",
            view_class=TicketFullActionView,
            mention_user=True,
            ticket_type="gamepass"
        )

    elif custom_id == "open_group_ticket":
        await handle_open_ticket(
            interaction,
            category_name="💰Robux Group💰",
            view_class=GroupTicketFullActionView,
            mention_user=False,
            ticket_type="group"
        )

# --------------------------------------------------------------------------------------------------
# ฟังก์ชันเปิดตั๋ว (อัพเดทให้ลด stock)
async def handle_open_ticket(interaction, category_name, view_class, mention_user=False, ticket_type=None):
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
    
    await interaction.response.send_message(
        content="📩 เปิดตั๋วเรียบร้อย!",
        view=GoToTicketView(channel),
        ephemeral=True
    )

    # แท็กเรียกพนักงานก่อน embed
    if admin_role and mention_user:
        await channel.send(content=admin_role.mention)

    # Embed แสดงข้อมูล
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
    welcome_embed.set_footer(text="Sushi Gamepass Service")

    await channel.send(embed=welcome_embed, view=view_class(channel, user))

# --------------------------------------------------------------------------------------------------
# View และส่วนอื่นๆ ที่เหลือให้คงเดิม (ConfirmTicketView, GroupConfirmTicketView, TicketFullActionView, GroupTicketFullActionView, CloseTicketView, GoToTicketView)
# โดยให้แน่ใจว่าเมื่อมีการขายสำเร็จ ให้ลด stock ด้วย

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

        # ดึงจำนวน Robux จาก embed และลด stock
        robux_field = next((f for f in self.embed_data.fields if f.name == "💸 จำนวน Robux"), None)
        if robux_field:
            try:
                robux_amount = int(robux_field.value.replace(",", "").replace(" Robux", "").strip())
                global gamepass_stock
                gamepass_stock -= robux_amount
                if gamepass_stock < 0:
                    gamepass_stock = 0
            except ValueError:
                pass

        self.embed_data.add_field(name="📋 ยืนยันโดย", value=interaction.user.mention, inline=False)
        await send_sale_log(self.embed_data, interaction=interaction, delivered_by=interaction.user)
        await interaction.response.send_message("✅ ส่งของเรียบร้อยแล้ว", ephemeral=True)
        await interaction.message.edit(view=None)
        
        # อัพเดท embed หลัก
        await update_main_embed()

    @discord.ui.button(label="❌ ยกเลิกสินค้า", style=discord.ButtonStyle.danger, custom_id="cancel_ticket")
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        cancel_embed = discord.Embed(
            title="❌ คำสั่งซื้อถูกยกเลิก",
            description=f"คำสั่งซื้อนี้ถูกยกเลิกโดย {interaction.user.mention}",
            color=0xFF0000
        )
        await interaction.response.send_message(embed=cancel_embed)
        await interaction.message.edit(view=None)

class GroupConfirmTicketView(View):
    def __init__(self, embed_data: discord.Embed):
        super().__init__(timeout=None)
        self.embed_data = discord.Embed.from_dict(embed_data.to_dict())

    @discord.ui.button(label="✅ ส่งสินค้าสำเร็จ", style=discord.ButtonStyle.success, custom_id="deliver_group_ticket")
    async def deliver_group(self, interaction: discord.Interaction, button: Button):
        role_id = 1361016912259055896
        role = interaction.guild.get_role(role_id)
        if role not in interaction.user.roles:
            await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้ปุ่มนี้", ephemeral=True)
            return

        if any(field.name == "📋 ยืนยันโดย" for field in self.embed_data.fields):
            await interaction.response.send_message("⚠️ คำสั่งซื้อนี้ถูกส่งแล้ว", ephemeral=True)
            return

        # ดึงจำนวน Robux จาก embed และลด stock
        robux_field = next((f for f in self.embed_data.fields if f.name == "💸 จำนวน Robux"), None)
        if robux_field:
            try:
                robux_amount = int(robux_field.value.replace(",", "").replace(" Robux", "").strip())
                global group_stock
                group_stock -= robux_amount
                if group_stock < 0:
                    group_stock = 0
            except ValueError:
                pass

        self.embed_data.add_field(name="📋 ยืนยันโดย", value=interaction.user.mention, inline=False)
        await send_sale_log(self.embed_data, interaction=interaction, delivered_by=interaction.user)
        await interaction.response.send_message("✅ ส่งสินค้าสำเร็จแล้ว", ephemeral=True)
        await interaction.message.edit(view=None)
        
        # อัพเดท embed หลัก
        await update_main_embed()

    @discord.ui.button(label="❌ ยกเลิกสินค้า", style=discord.ButtonStyle.danger, custom_id="cancel_group_ticket")
    async def cancel_group(self, interaction: discord.Interaction, button: Button):
        cancel_embed = discord.Embed(
            title="❌ คำสั่งซื้อถูกยกเลิก",
            description=f"คำสั่งซื้อนี้ถูกยกเลิกโดย {interaction.user.mention}",
            color=0xFF0000
        )
        await interaction.response.send_message(embed=cancel_embed)
        await interaction.message.edit(view=None)

# --------------------------------------------------------------------------------------------------
# ส่วนที่เหลือของโค้ด (TicketFullActionView, GroupTicketFullActionView, CloseTicketView, GoToTicketView, และคำสั่งอื่นๆ) 
# ให้คงเดิมตามโค้ดเดิมของคุณ โดยเพิ่มการอัพเดท stock เมื่อจำเป็น

class TicketFullActionView(View):
    def __init__(self, channel: discord.TextChannel, owner: discord.Member):
        super().__init__(timeout=None)
        self.channel = channel
        self.owner = owner

    @discord.ui.button(label="📝 กรอกแบบฟอร์ม", style=discord.ButtonStyle.primary)
    async def open_form(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(TicketInfoModal())

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

        sale_embed = None
        async for msg in self.channel.history():
            if msg.embeds and "รายละเอียดการสั่งซื้อ" in msg.embeds[0].title:
                sale_embed = msg.embeds[0]
                break

        if sale_embed:
            await send_sale_log(sale_embed, interaction=interaction)

        await interaction.response.send_message("📪 กำลังปิดตั๋วใน 5 วินาที...", ephemeral=True)
        await discord.utils.sleep_until(discord.utils.utcnow() + datetime.timedelta(seconds=5))
        await self.channel.delete()

class GroupTicketFullActionView(View):
    def __init__(self, channel: discord.TextChannel, owner: discord.Member):
        super().__init__(timeout=None)
        self.channel = channel
        self.owner = owner

    @discord.ui.button(label="📝 กรอกแบบฟอร์ม Robux Group", style=discord.ButtonStyle.primary)
    async def open_form(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(GroupTicketInfoModal())

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
        await self.channel.delete()

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
        await interaction.response.send_message("📪 กำลังปิดตั๋วใน 5 วินาที...", ephemeral=True)
        await discord.utils.sleep_until(discord.utils.utcnow() + datetime.timedelta(seconds=5))
        await self.channel.delete()

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

# --------------------------------------------------------------------------------------------------
# คำสั่งคำนวณต่างๆ (ให้คงเดิม)
@bot.command()
async def gp(ctx, *, expression: str):
    """คำนวณราคาจากจำนวน Robux (Gamepass)"""
    try:
        expression = expression.replace(",", "")
        expression = expression.lower().replace("x", "*").replace("÷", "/")

        if not re.match(r"^[\d\s\+\-\*\/\(\)]+$", expression):
            await ctx.send("❌ กรุณาใส่เฉพาะตัวเลข และเครื่องหมาย + - * / ÷ ()")
            return

        robux = eval(expression)
        price = robux / gamepass_rate
        price_str = f"{price:,.0f} บาท"

        await ctx.send(f"🎮 Gamepass {robux:,} Robux = **{price_str}** (เรท {gamepass_rate})")

    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")

@bot.command()
async def g(ctx, *, expression: str):
    """คำนวณราคาจากจำนวน Robux (Group)"""
    try:
        expression = expression.replace(",", "")
        expression = expression.lower().replace("x", "*").replace("÷", "/")

        if not re.match(r"^[\d\s\+\-\*\/\(\)]+$", expression):
            await ctx.send("❌ กรุณาใส่เฉพาะตัวเลข และเครื่องหมาย + - * / ÷ ()")
            return

        robux = eval(expression)

        if robux < 1500:
            rate = group_rate_low
        else:
            rate = group_rate_high

        price = robux / rate
        price_str = f"{price:,.0f} บาท"

        await ctx.send(f"👥 Group {robux:,} Robux = **{price_str}** (เรท {rate})")

    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")

@bot.command()
async def gb(ctx, *, expression: str):
    """คำนวณจากจำนวนเงิน เป็น Robux (Group)"""
    try:
        expression = expression.replace(",", "").replace(" ", "")
        baht = eval(expression)

        if baht < 500:
            rate = group_rate_low
        else:
            rate = group_rate_high

        robux = baht * rate
        await ctx.send(f"👥 {baht:,.0f} บาท = **{robux:,.0f} Robux** (Group เรท {rate})")

    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")

@bot.command()
async def gpb(ctx, *, expression: str):
    """คำนวณจากจำนวนเงิน เป็น Robux (Gamepass)"""
    try:
        expression = expression.replace(",", "").replace(" ", "")
        baht = eval(expression)

        robux = baht * gamepass_rate
        await ctx.send(f"🎮 {baht:,.0f} บาท = **{robux:,.0f} Robux** (Gamepass เรท {gamepass_rate})")

    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")

@bot.command()
async def tax(ctx, *, expression: str):
    """คำนวณ Robux หลังหัก % (ภาษีหรือส่วนลด)"""
    try:
        expr = expression.replace(" ", "")
        expr = re.sub(
            r"(\d+)([+\-])(\d+)%", 
            lambda m: f"{m.group(1)}{m.group(2)}({m.group(1)}*{int(m.group(3))/100})", 
            expr
        )
        expr = re.sub(r"(\d+)%", lambda m: f"*{int(m.group(1))/100}", expr)
        robux = eval(expr)
        await ctx.send(f"💰 หลังหักภาษี/ส่วนลด = **{robux:,.0f} Robux**")

    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")

@bot.command()
async def od(ctx, *, expression: str):
    """คำสั่งสั่งซื้อ Robux (Gamepass)"""
    try:
        expr = expression.replace(",", "").lower().replace("x", "*").replace("÷", "/")

        if not re.match(r"^[\d\s\+\-\*\/\(\)]+$", expr):
            await ctx.send("❌ กรุณาใส่เฉพาะตัวเลข และเครื่องหมาย + - * / x ÷ ()")
            return

        robux = int(eval(expr))
        price = robux / gamepass_rate
        price_str = f"{price:,.0f} บาท"

        embed = discord.Embed(
            title="🍣 ใบเสร็จคำสั่งซื้อ 🍣",
            color=0x00FF99,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="📦 ประเภทสินค้า", value="Robux Gamepass", inline=False)
        embed.add_field(name="💸 จำนวน Robux", value=f"{robux:,}", inline=True)
        embed.add_field(name="💰 ราคาตามเรท", value=price_str, inline=True)
        embed.add_field(name="🚚 ผู้ส่งสินค้า", value=ctx.author.mention, inline=False)
        embed.set_footer(text="การสั่งซื้อสำเร็จ")

        await ctx.send(embed=embed)
        sales_channel = bot.get_channel(SALES_LOG_CHANNEL_ID)
        if sales_ch



