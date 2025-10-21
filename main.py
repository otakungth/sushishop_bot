import os
import datetime
import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import re
import asyncio

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

# สถานะร้าน
shop_open = True
group_open = True

# Stock
gamepass_stock = 1000  # จำนวน stock เริ่มต้น
group_stock = 1000     # จำนวน stock เริ่มต้น

# ห้องต่างๆ
MAIN_CHANNEL_ID = 1361044752975532152  # เปลี่ยนเป็น ID ห้องหลักที่ต้องการ
SALES_LOG_CHANNEL_ID = 1402993077643120720

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
# คำสั่ง Built-in (Slash Commands)
@bot.tree.command(name="gp", description="คำนวณราคาจากจำนวน Robux (Gamepass)")
async def gp(interaction: discord.Interaction, จำนวน: str):
    """คำนวณราคาจากจำนวน Robux (Gamepass)"""
    try:
        expression = จำนวน.replace(",", "").lower().replace("x", "*").replace("÷", "/")

        if not re.match(r"^[\d\s\+\-\*\/\(\)]+$", expression):
            await interaction.response.send_message("❌ กรุณาใส่เฉพาะตัวเลข และเครื่องหมาย + - * / x ÷ ()", ephemeral=True)
            return

        robux = int(eval(expression))
        price = robux / gamepass_rate
        price_str = f"{price:,.0f} บาท"

        await interaction.response.send_message(
            f"🎮 Gamepass {robux:,} Robux = **{price_str}** (เรท {gamepass_rate})", 
            ephemeral=True
        )

    except Exception as e:
        await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

@bot.tree.command(name="g", description="คำนวณราคาจากจำนวน Robux (Group)")
async def g(interaction: discord.Interaction, จำนวน: str):
    """คำนวณราคาจากจำนวน Robux (Group)"""
    try:
        expression = จำนวน.replace(",", "").lower().replace("x", "*").replace("÷", "/")

        if not re.match(r"^[\d\s\+\-\*\/\(\)]+$", expression):
            await interaction.response.send_message("❌ กรุณาใส่เฉพาะตัวเลข และเครื่องหมาย + - * / x ÷ ()", ephemeral=True)
            return

        robux = int(eval(expression))

        if robux < 1500:
            rate = group_rate_low
        else:
            rate = group_rate_high

        price = robux / rate
        price_str = f"{price:,.0f} บาท"

        await interaction.response.send_message(
            f"👥 Group {robux:,} Robux = **{price_str}** (เรท {rate})", 
            ephemeral=True
        )

    except Exception as e:
        await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

@bot.tree.command(name="gb", description="คำนวณจากจำนวนเงิน เป็น Robux (Group)")
async def gb(interaction: discord.Interaction, จำนวน: str):
    """คำนวณจากจำนวนเงิน เป็น Robux (Group)"""
    try:
        expression = จำนวน.replace(",", "").replace(" ", "")
        baht = eval(expression)

        if baht < 500:
            rate = group_rate_low
        else:
            rate = group_rate_high

        robux = baht * rate
        await interaction.response.send_message(
            f"👥 {baht:,.0f} บาท = **{robux:,.0f} Robux** (Group เรท {rate})", 
            ephemeral=True
        )

    except Exception as e:
        await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

@bot.tree.command(name="gpb", description="คำนวณจากจำนวนเงิน เป็น Robux (Gamepass)")
async def gpb(interaction: discord.Interaction, จำนวน: str):
    """คำนวณจากจำนวนเงิน เป็น Robux (Gamepass)"""
    try:
        expression = จำนวน.replace(",", "").replace(" ", "")
        baht = eval(expression)

        robux = baht * gamepass_rate
        await interaction.response.send_message(
            f"🎮 {baht:,.0f} บาท = **{robux:,.0f} Robux** (Gamepass เรท {gamepass_rate})", 
            ephemeral=True
        )

    except Exception as e:
        await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

@bot.tree.command(name="tax", description="คำนวณ Robux หลังหัก % (ภาษีหรือส่วนลด)")
async def tax(interaction: discord.Interaction, จำนวน: str):
    """คำนวณ Robux หลังหัก % (ภาษีหรือส่วนลด)"""
    try:
        expr = จำนวน.replace(" ", "")

        # รองรับรูปแบบ เช่น 1000-30% หรือ 500+15%
        expr = re.sub(
            r"(\d+)([+\-])(\d+)%", 
            lambda m: f"{m.group(1)}{m.group(2)}({m.group(1)}*{int(m.group(3))/100})", 
            expr
        )

        # แปลงเลขที่ลงท้ายด้วย % ให้กลายเป็น *0.XX เช่น 50% → *0.5
        expr = re.sub(r"(\d+)%", lambda m: f"*{int(m.group(1))/100}", expr)

        # คำนวณค่า
        robux = eval(expr)

        await interaction.response.send_message(
            f"💰 หลังหักภาษี/ส่วนลด = **{robux:,.0f} Robux**", 
            ephemeral=True
        )

    except Exception as e:
        await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

# --------------------------------------------------------------------------------------------------
# คำสั่งจัดการสำหรับแอดมิน
@bot.tree.command(name="sushi", description="เปิด/ปิดร้าน (Admin only)")
async def sushi(interaction: discord.Interaction):
    """เปิด/ปิดร้าน"""
    # ตรวจสอบสิทธิ์แอดมิน
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return
        
    global shop_open, group_open
    shop_open = not shop_open
    group_open = shop_open  # เปิด/ปิดพร้อมกันทั้งสองแบบ

    status = "✅ ร้านเปิด" if shop_open else "❌ ร้านปิด"
    await interaction.response.send_message(f"📌 สถานะร้านถูกเปลี่ยนเป็น: **{status}**", ephemeral=True)
    
    # อัปเดต embed
    if interaction.channel.id == MAIN_CHANNEL_ID:
        await update_main_embed(interaction.channel)

@bot.tree.command(name="stock", description="ตั้งค่าจำนวน stock (Admin only)")
async def stock(interaction: discord.Interaction, gamepass: int = None, group: int = None):
    """ตั้งค่าจำนวน stock"""
    # ตรวจสอบสิทธิ์แอดมิน
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return
        
    global gamepass_stock, group_stock
    
    if gamepass is not None:
        gamepass_stock = gamepass
    if group is not None:
        group_stock = group
        
    await interaction.response.send_message(
        f"✅ ตั้งค่า stock เรียบร้อย!\n🎮 Gamepass Stock: {gamepass_stock:,}\n👥 Group Stock: {group_stock:,}", 
        ephemeral=True
    )
    
    # อัปเดต embed
    if interaction.channel.id == MAIN_CHANNEL_ID:
        await update_main_embed(interaction.channel)

@bot.tree.command(name="openshop", description="แสดงหน้าหลักของร้าน (Admin only)")
async def openshop(interaction: discord.Interaction):
    """แสดงหน้าหลักของร้าน"""
    # ตรวจสอบสิทธิ์แอดมิน
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return
        
    if interaction.channel.id != MAIN_CHANNEL_ID:
        await interaction.response.send_message("❌ คำสั่งนี้ใช้ได้เฉพาะในช่องหลัก", ephemeral=True)
        return

    # ลบข้อความเก่าๆ ของบอทในช่องนี้
    async for msg in interaction.channel.history(limit=20):
        if msg.author == bot.user:
            await msg.delete()

    await update_main_embed(interaction.channel)
    await interaction.response.send_message("✅ สร้างหน้าหลักเรียบร้อย!", ephemeral=True)

async def update_main_embed(channel):
    """อัปเดต embed หลัก"""
    # สร้าง embed ของร้าน
    embed = discord.Embed(
        title="🍣 Sushi Shop 🍣",
        color=0xFFD700
    )
    
    # ส่วน Gamepass
    gamepass_status = "✅ เปิด" if shop_open else "❌ ปิด"
    embed.add_field(
        name="🎮 Gamepass Service",
        value=(
            f"**เรท {gamepass_rate}**\n"
            f"สถานะ: {gamepass_status}\n"
            f"```จำนวน stock: {gamepass_stock:,}```\n"
            "กดเกมพาสหรือสอบถามได้เลยครับ\n\n"
            "หากลูกค้ามีปัญหาได้รับของผิดสามารถติดต่อทีมงานได้เลยนะครับ"
        ),
        inline=False
    )
    
    # ส่วน Group
    group_status = "✅ เปิด" if group_open else "❌ ปิด"
    embed.add_field(
        name="👥 Group Service", 
        value=(
            f"**เรท {group_rate_low} (ซื้อมากกว่า 500 บาทเรท {group_rate_high})**\n"
            f"สถานะ: {group_status}\n"
            f"```จำนวน stock: {group_stock:,}```\n"
            "เข้ากลุ่มนี้: https://www.roblox.com/communities/34713179/VALKYs\n\n"
            "⚠️ กรุณาเข้ากลุ่มให้ครบ 15 วัน ⚠️\n\n"
            f"📌 จดวันที่เข้ากลุ่มได้ที่ <#1387421905941827615>\n\n"
            "หากลูกค้ามีปัญหาสามารถแจ้งทีมงานได้เลยครับ"
        ),
        inline=False
    )
    
    embed.set_thumbnail(url="https://media.discordapp.net/attachments/717757556889747657/1403684950770847754/noFilter.png")

    # ส่ง embed พร้อมปุ่ม
    await channel.send(embed=embed, view=MainTicketView())

# --------------------------------------------------------------------------------------------------
# Views และ Modals
class MainTicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        
        # ปุ่ม Gamepass
        if shop_open and gamepass_stock > 0:
            self.add_item(Button(label="เปิดตั๋ว Robux Gamepass", style=discord.ButtonStyle.success, custom_id="open_gamepass_ticket"))
        else:
            self.add_item(Button(label="❌ Gamepass ปิดชั่วคราว", style=discord.ButtonStyle.danger, disabled=True))
            
        # ปุ่ม Group
        if group_open and group_stock > 0:
            self.add_item(Button(label="เปิดตั๋ว Robux Group", style=discord.ButtonStyle.primary, custom_id="open_group_ticket"))
        else:
            self.add_item(Button(label="❌ Group ปิดชั่วคราว", style=discord.ButtonStyle.danger, disabled=True))

class GamepassTicketInfoModal(Modal, title="📋 แบบฟอร์มสั่งซื้อ Gamepass"):
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
        global gamepass_stock
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
            if robux > gamepass_stock:
                await interaction.response.send_message(f"❌ Stock ไม่พอ! Stock คงเหลือ: {gamepass_stock:,} Robux", ephemeral=True)
                return
                
            price = robux / gamepass_rate
            price_str = f"{price:,.0f} บาท"

            # ลด stock
            gamepass_stock -= robux

            # Embed ลูกค้า
            customer_embed = discord.Embed(title="📨 รายละเอียดการสั่งซื้อ Gamepass", color=0x00FF99)
            customer_embed.add_field(name="🗺️ แมพ", value=self.map_name.value, inline=False)
            customer_embed.add_field(name="🎟 เกมพาส", value=self.gamepass_name.value, inline=False)
            customer_embed.add_field(name="💸 จำนวน Robux", value=f"{robux:,}", inline=True)
            customer_embed.add_field(name="💰 ราคา", value=price_str, inline=True)
            customer_embed.add_field(name="📦 Stock คงเหลือ", value=f"{gamepass_stock:,} Robux", inline=True)
            customer_embed.set_footer(text="ทีมงานจะตอบกลับโดยเร็วที่สุดครับ")

            # Embed ยืนยัน
            confirm_embed = customer_embed.copy()
            confirm_embed.set_footer(text=f"🧾 ผู้ใช้: {interaction.user}")

            view = ConfirmTicketView(embed_data=confirm_embed, ticket_type="gamepass")
            await interaction.response.send_message(embed=customer_embed, view=view, ephemeral=False)

        except Exception as e:
            await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

class GroupTicketInfoModal(Modal, title="📋 แบบฟอร์มสั่งซื้อ Robux Group"):
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
        global group_stock
        try:
            robux = int(self.robux_amount.value)
            
            # ตรวจสอบ stock
            if robux > group_stock:
                await interaction.response.send_message(f"❌ Stock ไม่พอ! Stock คงเหลือ: {group_stock:,} Robux", ephemeral=True)
                return
                
            rate = group_rate_low if robux < 1500 else group_rate_high
            price = robux / rate
            price_str = f"{price:,.0f} บาท"

            # ลด stock
            group_stock -= robux

            customer_embed = discord.Embed(title="📨 รายละเอียดคำสั่งซื้อ Robux Group", color=0x00AAFF)
            customer_embed.add_field(name="🪪 ชื่อในเกม", value=self.user_name.value, inline=False)
            customer_embed.add_field(name="💸 จำนวน Robux", value=f"{robux:,}", inline=True)
            customer_embed.add_field(name="💰 ราคา", value=price_str, inline=True)
            customer_embed.add_field(name="📦 Stock คงเหลือ", value=f"{group_stock:,} Robux", inline=True)
            customer_embed.set_footer(text="ทีมงานจะตรวจสอบและตอบกลับโดยเร็วที่สุดครับ")

            confirm_embed = customer_embed.copy()
            confirm_embed.set_footer(text=f"🧾 ผู้ใช้: {interaction.user}")

            view = ConfirmTicketView(embed_data=confirm_embed, ticket_type="group")
            await interaction.response.send_message(embed=customer_embed, view=view, ephemeral=False)

        except ValueError:
            await interaction.response.send_message("❌ กรุณากรอกจำนวน Robux เป็นตัวเลข", ephemeral=True)

class ConfirmTicketView(View):
    def __init__(self, embed_data: discord.Embed, ticket_type: str):
        super().__init__(timeout=None)
        self.embed_data = discord.Embed.from_dict(embed_data.to_dict())
        self.ticket_type = ticket_type

    @discord.ui.button(label="✅ ส่งของเรียบร้อยแล้ว", style=discord.ButtonStyle.success, custom_id="confirm_ticket")
    async def confirm_button(self, interaction: discord.Interaction, button: Button):
        # ✅ ตรวจสอบสิทธิ์ ต้องมียศ 1361016912259055896
        role_id = 1361016912259055896
        role = interaction.guild.get_role(role_id)
        if role not in interaction.user.roles:
            await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ยืนยันการสั่งซื้อนี้", ephemeral=True)
            return

        # ถ้ามีการยืนยันไปแล้ว ห้ามยืนยันซ้ำ
        if any(field.name == "📋 ยืนยันโดย" for field in self.embed_data.fields):
            await interaction.response.send_message("⚠️ คำสั่งซื้อนี้ถูกยืนยันแล้ว", ephemeral=True)
            return

        # เพิ่มข้อมูลผู้ยืนยัน
        self.embed_data.add_field(name="📋 ยืนยันโดย", value=interaction.user.mention, inline=False)

        # ส่งบันทึก พร้อมผู้ส่งสินค้า
        await send_sale_log(self.embed_data, interaction=interaction, delivered_by=interaction.user)

        await interaction.response.send_message("✅ ส่งของเรียบร้อยแล้ว", ephemeral=True)
        await interaction.message.edit(view=None)

    @discord.ui.button(label="❌ ยกเลิกสินค้า", style=discord.ButtonStyle.danger, custom_id="cancel_ticket")
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        # คืน stock เมื่อยกเลิก
        global gamepass_stock, group_stock
        
        robux_value = next((f.value for f in self.embed_data.fields if f.name == "💸 จำนวน Robux"), "0")
        robux_amount = int(robux_value.replace(",", "").split(" ")[0])
        
        if self.ticket_type == "gamepass":
            gamepass_stock += robux_amount
        elif self.ticket_type == "group":
            group_stock += robux_amount

        # แจ้งว่าคำสั่งถูกยกเลิก
        cancel_embed = discord.Embed(
            title="❌ คำสั่งซื้อถูกยกเลิก",
            description=f"คำสั่งซื้อนี้ถูกยกเลิกโดย {interaction.user.mention}\n✅ Stock ถูกคืนแล้ว",
            color=0xFF0000
        )

        await interaction.response.send_message(embed=cancel_embed)
        await interaction.message.edit(view=None)

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

class TicketFullActionView(View):
    def __init__(self, channel: discord.TextChannel, owner: discord.Member, ticket_type: str):
        super().__init__(timeout=None)
        self.channel = channel
        self.owner = owner
        self.ticket_type = ticket_type

    @discord.ui.button(label="📝 กรอกแบบฟอร์ม", style=discord.ButtonStyle.primary)
    async def open_form(self, interaction: discord.Interaction, button: Button):
        if self.ticket_type == "gamepass":
            await interaction.response.send_modal(GamepassTicketInfoModal())
        else:
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

        sale_embed = None
        async for msg in self.channel.history():
            if msg.embeds and "รายละเอียดการสั่งซื้อ" in msg.embeds[0].title:
                sale_embed = msg.embeds[0]
                break

        if sale_embed:
            await send_sale_log(sale_embed, interaction=interaction)

        await interaction.response.send_message("📪 กำลังปิดตั๋วใน 5 วินาที...", ephemeral=True)
        await asyncio.sleep(5)
        await self.channel.delete()

# --------------------------------------------------------------------------------------------------
# Events
@bot.event
async def on_ready():
    print(f"✅ บอทออนไลน์แล้ว: {bot.user}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="ร้าน Sushi Shop"))
    
    # Sync commands กับ Discord
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"❌ Error syncing commands: {e}")

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        custom_id = interaction.data.get("custom_id")

        if custom_id == "open_gamepass_ticket":
            await handle_open_ticket(
                interaction,
                category_name="🍣Sushi Gamepass 🍣",
                ticket_type="gamepass"
            )

        elif custom_id == "open_group_ticket":
            await handle_open_ticket(
                interaction,
                category_name="💰Robux Group💰", 
                ticket_type="group"
            )

async def handle_open_ticket(interaction, category_name: str, ticket_type: str):
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
    if admin_role:
        await channel.send(content=admin_role.mention)

    # Embed แสดงข้อมูล
    service_name = "Gamepass" if ticket_type == "gamepass" else "Group"
    welcome_embed = discord.Embed(
        title=f"🍣 Sushi Shop {service_name} 🍣",
        description=(
            "ลูกค้า :\n\n"
            f"{user.mention}\n\n"
            "พนักงาน :\n\n"
            f"{admin_role.mention if admin_role else 'ไม่พบพนักงาน'}\n\n"
            f"** 🎟️ สนใจซื้อ {service_name} ระบุชื่อหรือรูปภาพมาได้เลยนะคะ **\n\n"
            "หากต้องการเช็คราคาให้พิมพ์คำสั่ง\n"
            f"`/{'gp' if ticket_type == 'gamepass' else 'g'} [จำนวน]`"
        ),
        color=0x00FF99
    )
    welcome_embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/717757556889747657/1403684950770847754/noFilter.png")
    welcome_embed.set_footer(text=f"Sushi {service_name} Service")

    await channel.send(embed=welcome_embed, view=TicketFullActionView(channel, user, ticket_type))

# --------------------------------------------------------------------------------------------------
# คำสั่งเก่าแบบ prefix (สำหรับทดสอบ)
@bot.command()
async def test_sync(ctx):
    """ทดสอบ sync commands"""
    try:
        synced = await bot.tree.sync()
        await ctx.send(f"✅ Synced {len(synced)} command(s)")
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

# --------------------------------------------------------------------------------------------------
# รันบอท
server_on()
bot.run(os.getenv("TOKEN"))
