import os
import datetime
import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, Select
import re
import json
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
shop_open = True
group_ticket_enabled = True

# ตั้งค่าห้องหลักและ stock
MAIN_CHANNEL_ID = 1361044752975532152
SALES_LOG_CHANNEL_ID = 1402993077643120720
stock_amount = 100

# เก็บข้อมูลฟอร์ม
user_forms = {}
user_notes = {}  # เก็บโน้ตส่วนตัวของผู้ใช้

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

        robux_amount = next((f.value for f in embed_data.fields if f.name == "💸 จำนวน Robux"), "ไม่ทราบ")
        price = next((f.value for f in embed_data.fields if f.name in ("💰 ราคาตามเรท", "💰 ราคา")), "ไม่ทราบ")
        user_name = next((f.value for f in embed_data.fields if f.name == "😊 ผู้ซื้อ"), "ไม่ทราบ")

        sale_type = "ไม่ทราบ"
        current_channel = interaction.channel if interaction else ctx.channel if ctx else None
        if current_channel:
            category_name = current_channel.category.name if current_channel.category else ""
            if "gamepass" in category_name.lower():
                sale_type = "Robux Gamepass"
            elif "group" in category_name.lower():
                sale_type = "Robux Group"

        ticket_creator = None
        if current_channel and current_channel.name.startswith("ticket-"):
            try:
                user_id = int(current_channel.name.split("-")[-1])
                ticket_creator = await current_channel.guild.fetch_member(user_id)
            except (IndexError, ValueError, discord.NotFound):
                pass

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
    else:
        if amount < 0:
            await ctx.send("❌ จำนวน stock ต้องมากกว่าหรือเท่ากับ 0", delete_after=5)
            return
        
        stock_amount = amount
        await ctx.send(f"✅ ตั้งค่า stock เป็น **{stock_amount}** เรียบร้อยแล้ว", delete_after=5)
    
    await ctx.message.delete()
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
    await ctx.message.delete()

    if ctx.channel.id == MAIN_CHANNEL_ID:
        await update_main_channel()

# --------------------------------------------------------------------------------------------------
# คำสั่งเปิดปิด Group Ticket
@bot.command()
@commands.has_permissions(administrator=True)
async def group(ctx, status: str = None):
    """เปิด/ปิดปุ่ม Group Ticket"""
    global group_ticket_enabled
    
    if status is None:
        current_status = "✅ เปิด" if group_ticket_enabled else "❌ ปิด"
        await ctx.send(f"📌 สถานะ Group Ticket: **{current_status}**", delete_after=5)
    elif status.lower() in ["on", "enable", "เปิด"]:
        group_ticket_enabled = True
        await ctx.send("✅ เปิดปุ่ม Group Ticket เรียบร้อยแล้ว", delete_after=5)
    elif status.lower() in ["off", "disable", "ปิด"]:
        group_ticket_enabled = False
        await ctx.send("❌ ปิดปุ่ม Group Ticket เรียบร้อยแล้ว", delete_after=5)
    else:
        await ctx.send("❌ การใช้งาน: !group [on/off] หรือ !group [enable/disable] หรือ !group [เปิด/ปิด]", delete_after=5)
    
    await ctx.message.delete()
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
        if msg.author == bot.user and len(msg.embeds) > 0:
            try:
                await msg.delete()
            except:
                pass

    # สร้าง embed หลักแบบใหม่ตามรูปภาพ
    embed = discord.Embed(
        title="🍣 Sushi Shop 🍣",
        color=0x2B2D31,
        timestamp=discord.utils.utcnow()
    )
    
    # ส่วน Gamepass - ออกแบบใหม่ให้สวยงาม
    embed.add_field(
        name="🎮 **Gamepass Service**",
        value=(
            "```\n"
            f"เรท: {gamepass_rate}\n"
            "บริการกดเกมพาสทุกเกม\n"
            "รองรับการสั่งซื้อจำนวนมาก\n"
            "```\n"
            "**กดปุ่มด้านล่างเพื่อเปิดตั๋วสั่งซื้อ**"
        ),
        inline=False
    )
    
    # ส่วน Group - ออกแบบใหม่ให้สวยงาม
    if group_ticket_enabled:
        group_value = (
            "```\n"
            f"เรท: {group_rate_low}-{group_rate_high}\n"
            "ซื้อมากกว่า 500 บาทเรท 4.5\n"
            "รองรับการสั่งซื้อจำนวนมาก\n"
            "```\n"
            f"📌 เข้ากลุ่ม: [VALKYs](https://www.roblox.com/communities/34713179/VALKYs)\n"
            "⚠️ กรุณาเข้ากลุ่มให้ครบ 15 วัน\n"
            "**กดปุ่มด้านล่างเพื่อเปิดตั๋วสั่งซื้อ**"
        )
    else:
        group_value = "```\n🚫 บริการปิดชั่วคราว\n```"
    
    embed.add_field(
        name="👥 **Robux Group Service**", 
        value=group_value,
        inline=False
    )
    
    # ส่วน Stock - ออกแบบใหม่
    stock_status = "🟢 พร้อมให้บริการ" if stock_amount > 0 else "🔴 สินค้าหมด"
    embed.add_field(
        name="📊 **Stock Information**",
        value=(
            f"```\n"
            f"จำนวน Stock: {stock_amount}\n"
            f"สถานะ: {stock_status}\n"
            "```"
        ),
        inline=False
    )
    
    # Footer แบบมืออาชีพ
    embed.set_footer(
        text="Sushi Shop • Professional Robux Service",
        icon_url="https://media.discordapp.net/attachments/717757556889747657/1403684950770847754/noFilter.png"
    )
    
    # ตั้งค่า thumbnail
    embed.set_thumbnail(url="https://media.discordapp.net/attachments/717757556889747657/1403684950770847754/noFilter.png")

    # ส่ง embed พร้อมปุ่ม
    try:
        await channel.send(embed=embed, view=MainShopView())
    except Exception as e:
        print(f"Error updating main channel: {e}")

# --------------------------------------------------------------------------------------------------
# Modal สำหรับโน้ตส่วนตัว
class PersonalNoteModal(Modal, title="📝 โน้ตส่วนตัวของคุณ"):
    note = TextInput(
        label="เขียนโน้ตส่วนตัวของคุณ",
        placeholder="เช่น: ชื่อในเกม, รายละเอียดเพิ่มเติม, ฯลฯ",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000
    )

    async def on_submit(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        user_notes[user_id] = {
            "note": self.note.value,
            "created_at": datetime.datetime.now().isoformat()
        }
        
        embed = discord.Embed(
            title="✅ บันทึกโน้ตเรียบร้อย",
            description="โน้ตส่วนตัวของคุณถูกบันทึกเรียบร้อยแล้ว",
            color=0x00FF00
        )
        embed.add_field(name="📝 โน้ตของคุณ", value=self.note.value, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

# --------------------------------------------------------------------------------------------------
# Views และ Modals หลัก
class MainShopView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎮 เปิดตั๋ว Gamepass", style=discord.ButtonStyle.success, custom_id="open_gamepass_ticket", emoji="🎮")
    async def gamepass_ticket(self, interaction: discord.Interaction, button: Button):
        if not shop_open or stock_amount <= 0:
            await interaction.response.send_message("❌ ร้านปิดชั่วคราวหรือสินค้าหมด", ephemeral=True)
            return
        await handle_open_ticket(interaction, "🍣Sushi Gamepass 🍣", GamepassTicketModal)

    @discord.ui.button(label="👥 เปิดตั๋ว Group", style=discord.ButtonStyle.success, custom_id="open_group_ticket", emoji="👥")
    async def group_ticket(self, interaction: discord.Interaction, button: Button):
        if not shop_open or stock_amount <= 0:
            await interaction.response.send_message("❌ ร้านปิดชั่วคราวหรือสินค้าหมด", ephemeral=True)
            return
        if not group_ticket_enabled:
            await interaction.response.send_message("❌ บริการ Group ปิดชั่วคราว", ephemeral=True)
            return
        await handle_open_ticket(interaction, "💰Robux Group💰", GroupTicketModal)

    @discord.ui.button(label="📝 จัดการฟอร์มของฉัน", style=discord.ButtonStyle.secondary, custom_id="manage_my_form", emoji="📝")
    async def manage_form(self, interaction: discord.Interaction, button: Button):
        view = FormManagementView(user_id=interaction.user.id)
        embed = discord.Embed(
            title="📝 จัดการฟอร์มของฉัน",
            description="**จัดการข้อมูลฟอร์มที่คุณบันทึกไว้:**\n\n"
                      "• 👀 **ดูข้อมูล** - ดูข้อมูลฟอร์มที่บันทึกไว้\n"
                      "• ✏️ **แก้ไข** - แก้ไขข้อมูลฟอร์ม\n"
                      "• 🗑️ **ลบ** - ลบข้อมูลฟอร์มออกจากระบบ\n"
                      "• 📝 **โน้ตส่วนตัว** - บันทึกโน้ตส่วนตัว\n\n"
                      "ข้อมูลจะถูกแสดงเฉพาะคุณเท่านั้น",
            color=0x5865F2
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# --------------------------------------------------------------------------------------------------
# Modal สำหรับ Gamepass
class GamepassTicketModal(Modal, title="📋 แบบฟอร์มสั่งซื้อ Gamepass"):
    def __init__(self, user_id=None, existing_data=None):
        super().__init__(timeout=300)  # เพิ่ม timeout
        self.user_id = user_id
        
        self.map_name = TextInput(
            label="🗺 ชื่อแมพที่จะกด?",
            placeholder="พิมพ์ชื่อแมพ เช่น All Star Tower Defense X",
            default=existing_data.get("map_name", "") if existing_data else "",
            required=True,
            max_length=100
        )
        
        self.gamepass_name = TextInput(
            label="💸 กดเกมพาสอะไร?",
            placeholder="พิมพ์ชื่อเกมพาส เช่น x3 Speed 3 ชิ้น",
            default=existing_data.get("gamepass_name", "") if existing_data else "",
            required=True,
            max_length=100
        )
        
        self.robux_amount = TextInput(
            label="🎟 รวมทั้งหมดกี่ Robux?",
            placeholder="เช่น 995 หรือ 100+100+100 หรือ 100x3",
            default=existing_data.get("robux_amount", "") if existing_data else "",
            required=True,
            max_length=50
        )
        
        self.add_item(self.map_name)
        self.add_item(self.gamepass_name)
        self.add_item(self.robux_amount)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # บันทึกข้อมูลฟอร์ม
            user_id = str(interaction.user.id)
            user_forms[user_id] = {
                "map_name": self.map_name.value,
                "gamepass_name": self.gamepass_name.value,
                "robux_amount": self.robux_amount.value,
                "type": "gamepass",
                "last_updated": datetime.datetime.now().isoformat()
            }
            
            # แปลง input ให้รองรับ x และ ÷
            expr = self.robux_amount.value.lower().replace("x", "*").replace("÷", "/")

            if not re.match(r"^[\d\s\+\-\*\/\(\)]+$", expr):
                await interaction.response.send_message("❌ กรุณาใส่เฉพาะตัวเลข และเครื่องหมาย + - * / x ÷ ()", ephemeral=True)
                return

            # คำนวณ robux
            robux = int(eval(expr))
            price = robux / gamepass_rate
            price_str = f"{price:,.0f} บาท"

            # Embed ลูกค้า
            customer_embed = discord.Embed(
                title="📨 รายละเอียดการสั่งซื้อ Gamepass", 
                color=0x00FF99,
                timestamp=discord.utils.utcnow()
            )
            customer_embed.add_field(name="🗺️ แมพ", value=self.map_name.value, inline=False)
            customer_embed.add_field(name="🎟 เกมพาส", value=self.gamepass_name.value, inline=False)
            customer_embed.add_field(name="💸 จำนวน Robux", value=f"{robux:,}", inline=True)
            customer_embed.add_field(name="💰 ราคา", value=price_str, inline=True)
            customer_embed.add_field(name="📝 สถานะฟอร์ม", value="✅ บันทึกเรียบร้อยแล้ว", inline=False)
            customer_embed.set_footer(text="ทีมงานจะตอบกลับโดยเร็วที่สุดครับ")

            view = ConfirmTicketView(embed_data=customer_embed)
            await interaction.response.send_message(
                content="✅ **บันทึกข้อมูลฟอร์มเรียบร้อยแล้ว!**\nคุณสามารถดูหรือแก้ไขข้อมูลได้โดยกดปุ่ม 'จัดการฟอร์มของฉัน'",
                embed=customer_embed, 
                view=view, 
                ephemeral=False
            )

        except Exception as e:
            await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

# --------------------------------------------------------------------------------------------------
# Modal สำหรับ Group
class GroupTicketModal(Modal, title="📋 แบบฟอร์มสั่งซื้อ Robux Group"):
    def __init__(self, user_id=None, existing_data=None):
        super().__init__(timeout=300)  # เพิ่ม timeout
        self.user_id = user_id
        
        self.user_name = TextInput(
            label="🪪 ชื่อในเกม", 
            placeholder="Username",
            default=existing_data.get("user_name", "") if existing_data else "",
            required=True,
            max_length=50
        )
        
        self.robux_amount = TextInput(
            label="💸 ต้องการกดทั้งหมดกี่ Robux?", 
            placeholder="กรอกจำนวน Robux ที่ต้องการ",
            default=existing_data.get("robux_amount", "") if existing_data else "",
            required=True,
            max_length=50
        )
        
        self.add_item(self.user_name)
        self.add_item(self.robux_amount)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # บันทึกข้อมูลฟอร์ม
            user_id = str(interaction.user.id)
            user_forms[user_id] = {
                "user_name": self.user_name.value,
                "robux_amount": self.robux_amount.value,
                "type": "group",
                "last_updated": datetime.datetime.now().isoformat()
            }
            
            robux = int(self.robux_amount.value)
            rate = group_rate_low if robux < 1500 else group_rate_high
            price = robux / rate
            price_str = f"{price:,.0f} บาท"

            customer_embed = discord.Embed(
                title="📨 รายละเอียดคำสั่งซื้อ Robux Group", 
                color=0x00FF99,
                timestamp=discord.utils.utcnow()
            )
            customer_embed.add_field(name="🪪 ชื่อในเกม", value=self.user_name.value, inline=False)
            customer_embed.add_field(name="💸 จำนวน Robux", value=f"{robux:,}", inline=True)
            customer_embed.add_field(name="💰 ราคา", value=price_str, inline=True)
            customer_embed.add_field(name="📝 สถานะฟอร์ม", value="✅ บันทึกเรียบร้อยแล้ว", inline=False)
            customer_embed.set_footer(text="ทีมงานจะตรวจสอบและตอบกลับโดยเร็วที่สุดครับ")

            view = ConfirmTicketView(embed_data=customer_embed)
            await interaction.response.send_message(
                content="✅ **บันทึกข้อมูลฟอร์มเรียบร้อยแล้ว!**\nคุณสามารถดูหรือแก้ไขข้อมูลได้โดยกดปุ่ม 'จัดการฟอร์มของฉัน'",
                embed=customer_embed, 
                view=view, 
                ephemeral=False
            )

        except ValueError:
            await interaction.response.send_message("❌ กรุณากรอกจำนวน Robux เป็นตัวเลข", ephemeral=True)

# --------------------------------------------------------------------------------------------------
# View สำหรับจัดการฟอร์มส่วนตัว
class FormManagementView(View):
    def __init__(self, user_id):
        super().__init__(timeout=60)
        self.user_id = user_id

    @discord.ui.button(label="👀 ดูข้อมูลฟอร์ม", style=discord.ButtonStyle.primary, emoji="👀")
    async def view_form(self, interaction: discord.Interaction, button: Button):
        user_data = user_forms.get(str(interaction.user.id))
        user_note = user_notes.get(str(interaction.user.id))
        
        if not user_data and not user_note:
            # ถ้าไม่มีข้อมูลทั้งฟอร์มและโน้ต ให้แสดง modal สำหรับกรอกโน้ต
            modal = PersonalNoteModal()
            await interaction.response.send_modal(modal)
            return
        
        embed = discord.Embed(
            title="📝 ข้อมูลฟอร์มของฉัน",
            description="**ข้อมูลที่คุณบันทึกไว้:**",
            color=0x00FF99
        )
        
        if user_data:
            embed.timestamp = datetime.datetime.fromisoformat(user_data["last_updated"])
            if user_data["type"] == "gamepass":
                embed.add_field(name="🗺️ แมพ", value=user_data["map_name"], inline=False)
                embed.add_field(name="🎟 เกมพาส", value=user_data["gamepass_name"], inline=False)
                embed.add_field(name="💸 จำนวน Robux", value=user_data["robux_amount"], inline=True)
            else:
                embed.add_field(name="🪪 ชื่อในเกม", value=user_data["user_name"], inline=False)
                embed.add_field(name="💸 จำนวน Robux", value=user_data["robux_amount"], inline=True)
                
            embed.add_field(name="📦 ประเภท", value="Gamepass" if user_data["type"] == "gamepass" else "Group", inline=True)
        
        if user_note:
            embed.add_field(name="📝 โน้ตส่วนตัว", value=user_note["note"], inline=False)
            embed.timestamp = datetime.datetime.fromisoformat(user_note["created_at"])
        
        embed.set_footer(text="อัปเดตล่าสุด")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="✏️ แก้ไขฟอร์ม", style=discord.ButtonStyle.secondary, emoji="✏️")
    async def edit_form(self, interaction: discord.Interaction, button: Button):
        user_data = user_forms.get(str(interaction.user.id))
        
        if not user_data:
            await interaction.response.send_message("❌ คุณยังไม่มีข้อมูลฟอร์มที่บันทึกไว้", ephemeral=True)
            return
        
        if user_data["type"] == "gamepass":
            modal = GamepassTicketModal(user_id=interaction.user.id, existing_data=user_data)
        else:
            modal = GroupTicketModal(user_id=interaction.user.id, existing_data=user_data)
            
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="🗑️ ลบฟอร์ม", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_form(self, interaction: discord.Interaction, button: Button):
        user_id = str(interaction.user.id)
        if user_id in user_forms:
            del user_forms[user_id]
            embed = discord.Embed(
                title="🗑️ ลบข้อมูลฟอร์ม",
                description="✅ **ลบข้อมูลฟอร์มเรียบร้อยแล้ว**\n\nคุณสามารถกรอกฟอร์มใหม่ได้เมื่อต้องการสั่งซื้อ",
                color=0x00FF00
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("❌ คุณไม่มีข้อมูลฟอร์มที่บันทึกไว้", ephemeral=True)

    @discord.ui.button(label="📝 โน้ตส่วนตัว", style=discord.ButtonStyle.primary, emoji="📝")
    async def personal_note(self, interaction: discord.Interaction, button: Button):
        user_note = user_notes.get(str(interaction.user.id))
        modal = PersonalNoteModal()
        
        if user_note:
            modal.note.default = user_note["note"]
            
        await interaction.response.send_modal(modal)

# --------------------------------------------------------------------------------------------------
# View สำหรับยืนยันตั๋ว
class ConfirmTicketView(View):
    def __init__(self, embed_data: discord.Embed):
        super().__init__(timeout=300)
        self.embed_data = embed_data

    @discord.ui.button(label="✅ ส่งของเรียบร้อยแล้ว", style=discord.ButtonStyle.success, custom_id="confirm_ticket")
    async def confirm_button(self, interaction: discord.Interaction, button: Button):
        try:
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
        except Exception as e:
            await interaction.response.send_message("❌ เกิดข้อผิดพลาดในการยืนยัน", ephemeral=True)

    @discord.ui.button(label="❌ ยกเลิกสินค้า", style=discord.ButtonStyle.danger, custom_id="cancel_ticket")
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        try:
            cancel_embed = discord.Embed(
                title="❌ คำสั่งซื้อถูกยกเลิก",
                description=f"คำสั่งซื้อนี้ถูกยกเลิกโดย {interaction.user.mention}",
                color=0xFF0000
            )
            await interaction.response.send_message(embed=cancel_embed)
            await interaction.message.edit(view=None)
        except Exception as e:
            await interaction.response.send_message("❌ เกิดข้อผิดพลาดในการยกเลิก", ephemeral=True)

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

async def handle_open_ticket(interaction, category_name, modal_class):
    global stock_amount
    
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

    try:
        channel = await guild.create_text_channel(
            name=channel_name,
            overwrites=overwrites,
            reason="New ticket",
            category=category
        )
        
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
                "**ยินดีต้อนรับสู่บริการของเรา!**\n\n"
                f"👤 **ลูกค้า:** {user.mention}\n"
                f"🛠️ **พนักงาน:** {admin_role.mention if admin_role else 'รอพนักงานติดต่อ'}\n\n"
                "**คำแนะนำ:**\n"
                "• กรุณาระบุรายละเอียดการสั่งซื้อให้ครบถ้วน\n"
                "• สามารถใช้คำสั่ง !gp, !g เพื่อคำนวณราคาได้\n"
                "• ทีมงานจะตอบกลับคุณโดยเร็วที่สุด\n\n"
                "**ขอบคุณที่ใช้บริการ!** 🎉"
            ),
            color=0x00FF99
        )
        welcome_embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/717757556889747657/1403684950770847754/noFilter.png")
        welcome_embed.set_footer(text="Sushi Shop Professional Service")

        view = TicketActionView(channel, user, modal_class)
        await channel.send(embed=welcome_embed, view=view)

    except Exception as e:
        await interaction.response.send_message("❌ เกิดข้อผิดพลาดในการเปิดตั๋ว", ephemeral=True)

# --------------------------------------------------------------------------------------------------
# View สำหรับตั๋ว
class TicketActionView(View):
    def __init__(self, channel: discord.TextChannel, owner: discord.Member, modal_class):
        super().__init__(timeout=None)
        self.channel = channel
        self.owner = owner
        self.modal_class = modal_class

    @discord.ui.button(label="📝 กรอกแบบฟอร์ม", style=discord.ButtonStyle.primary, emoji="📝")
    async def open_form(self, interaction: discord.Interaction, button: Button):
        user_data = user_forms.get(str(interaction.user.id))
        try:
            await interaction.response.send_modal(self.modal_class(
                user_id=interaction.user.id, 
                existing_data=user_data
            ))
        except Exception as e:
            await interaction.response.send_message("❌ เกิดข้อผิดพลาดในการเปิดฟอร์ม", ephemeral=True)

    @discord.ui.button(label="📤 ช่องทางการโอนเงิน", style=discord.ButtonStyle.success, emoji="📤")
    async def payment_info(self, interaction: discord.Interaction, button: Button):
        try:
            embed = discord.Embed(
                title="📤 ช่องทางการโอนเงิน",
                description="กรุณาโอนเงินตามจำนวนที่แจ้งไว้ด้านล่าง",
                color=0x00CCFF
            )
            embed.set_image(url="https://media.discordapp.net/attachments/722832040860319835/1402994996600111114/186-8-06559-8.png")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message("❌ เกิดข้อผิดพลาดในการแสดงข้อมูล", ephemeral=True)

    @discord.ui.button(label="🔒 ปิดตั๋ว", style=discord.ButtonStyle.danger, emoji="🔒")
    async def close_ticket(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.owner.id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ คุณไม่ใช่เจ้าของตั๋วนี้", ephemeral=True)
            return

        await interaction.response.send_message("📪 กำลังปิดตั๋วใน 5 วินาที...", ephemeral=True)
        await asyncio.sleep(5)
        
        global stock_amount
        stock_amount += 1
        await update_main_channel()
        
        try:
            await self.channel.delete()
        except:
            pass

# --------------------------------------------------------------------------------------------------
# Events
@bot.event
async def on_ready():
    print(f"✅ บอทออนไลน์แล้ว: {bot.user}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="ร้าน Sushi Shop"))
    bot.add_view(MainShopView())
    await update_main_channel()

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return

    custom_id = interaction.data.get("custom_id")
    
    try:
        if custom_id == "open_gamepass_ticket":
            if not shop_open or stock_amount <= 0:
                await interaction.response.send_message("❌ ร้านปิดชั่วคราวหรือสินค้าหมด", ephemeral=True)
                return
            await handle_open_ticket(interaction, "🍣Sushi Gamepass 🍣", GamepassTicketModal)

        elif custom_id == "open_group_ticket":
            if not shop_open or stock_amount <= 0:
                await interaction.response.send_message("❌ ร้านปิดชั่วคราวหรือสินค้าหมด", ephemeral=True)
                return
            if not group_ticket_enabled:
                await interaction.response.send_message("❌ บริการ Group ปิดชั่วคราว", ephemeral=True)
                return
            await handle_open_ticket(interaction, "💰Robux Group💰", GroupTicketModal)
            
        elif custom_id == "manage_my_form":
            view = FormManagementView(user_id=interaction.user.id)
            embed = discord.Embed(
                title="📝 จัดการฟอร์มของฉัน",
                description="**จัดการข้อมูลฟอร์มที่คุณบันทึกไว้:**\n\n"
                          "• 👀 **ดูข้อมูล** - ดูข้อมูลฟอร์มที่บันทึกไว้\n"
                          "• ✏️ **แก้ไข** - แก้ไขข้อมูลฟอร์ม\n"
                          "• 🗑️ **ลบ** - ลบข้อมูลฟอร์มออกจากระบบ\n"
                          "• 📝 **โน้ตส่วนตัว** - บันทึกโน้ตส่วนตัว\n\n"
                          "ข้อมูลจะถูกแสดงเฉพาะคุณเท่านั้น",
                color=0x5865F2
            )
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    except Exception as e:
        print(f"Interaction error: {e}")
        try:
            await interaction.response.send_message("❌ เกิดข้อผิดพลาดในการประมวลผล", ephemeral=True)
        except:
            pass

# --------------------------------------------------------------------------------------------------
# คำสั่ง !od (Gamepass)
@bot.command()
async def od(ctx, *, expression: str):
    """คำสั่งสั่งซื้อ Robux Gamepass"""
    try:
        expr = expression.replace(",", "").lower().replace("x", "*").replace("÷", "/")

        if not re.match(r"^[\d\s\+\-\*\/\(\)]+$", expr):
            await ctx.send("❌ กรุณาใส่เฉพาะตัวเลข และเครื่องหมาย + - * / x ÷ ()", ephemeral=True)
            await ctx.message.delete()
            return

        robux = int(eval(expr))
        price = robux / gamepass_rate
        price_str = f"{price:,.0f} บาท"

        embed = discord.Embed(
            title="🍣 ใบเสร็จคำสั่งซื้อ Gamepass 🍣",
            color=0x00FF99,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="📦 ประเภทสินค้า", value="Robux Gamepass", inline=False)
        embed.add_field(name="💸 จำนวน Robux", value=f"{robux:,}", inline=True)
        embed.add_field(name="💰 ราคาตามเรท", value=price_str, inline=True)
        embed.add_field(name="🚚 ผู้ส่งสินค้า", value=ctx.author.mention, inline=False)
        embed.set_footer(text="การสั่งซื้อสำเร็จ")

        await ctx.send(embed=embed)
        await ctx.message.delete()

        sales_channel = bot.get_channel(SALES_LOG_CHANNEL_ID)
        if sales_channel:
            await sales_channel.send(embed=embed)

    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)
        await ctx.message.delete()

# --------------------------------------------------------------------------------------------------
# คำสั่ง !odg (Group)
@bot.command()
async def odg(ctx, *, expression: str):
    """คำสั่งสั่งซื้อ Robux Group"""
    try:
        expr = expression.replace(",", "").lower().replace("x", "*").replace("÷", "/")

        if not re.match(r"^[\d\s\+\-\*\/\(\)]+$", expr):
            await ctx.send("❌ กรุณาใส่เฉพาะตัวเลข และเครื่องหมาย + - * / x ÷ ()", ephemeral=True)
            await ctx.message.delete()
            return

        robux = int(eval(expr))
        rate = group_rate_low if robux < 1500 else group_rate_high
        price = robux / rate
        price_str = f"{price:,.0f} บาท"

        embed = discord.Embed(
            title="🍣 ใบเสร็จคำสั่งซื้อ Robux Group 🍣",
            color=0x00AAFF,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="📦 ประเภทสินค้า", value="Robux Group", inline=False)
        embed.add_field(name="💸 จำนวน Robux", value=f"{robux:,}", inline=True)
        embed.add_field(name="💰 ราคาตามเรท", value=price_str, inline=True)
        embed.add_field(name="📊 เรทที่ใช้", value=f"{rate}", inline=True)
        embed.add_field(name="🚚 ผู้ส่งสินค้า", value=ctx.author.mention, inline=False)
        embed.set_footer(text="การสั่งซื้อสำเร็จ • Robux Group")

        await ctx.send(embed=embed)
        await ctx.message.delete()

        sales_channel = bot.get_channel(SALES_LOG_CHANNEL_ID)
        if sales_channel:
            await sales_channel.send(embed=embed)

    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)
        await ctx.message.delete()

# --------------------------------------------------------------------------------------------------
# คำสั่งคำนวณราคา (แบบเห็นเฉพาะผู้ใช้)
async def send_ephemeral_calculation(ctx, calculation_func, expression):
    """ส่งผลการคำนวณแบบเห็นเฉพาะผู้ใช้"""
    try:
        expression = expression.replace(",", "").lower().replace("x", "*").replace("÷", "/")

        if not re.match(r"^[\d\s\+\-\*\/\(\)]+$", expression):
            await ctx.send("❌ กรุณาใส่เฉพาะตัวเลข และเครื่องหมาย + - * / x ÷ ()", ephemeral=True)
            await ctx.message.delete()
            return

        result = calculation_func(expression)
        await ctx.send(result, ephemeral=True)
        await ctx.message.delete()

    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)
        await ctx.message.delete()

def calculate_gp(expression):
    robux = eval(expression)
    price = robux / gamepass_rate
    return f"🎮 **Gamepass**\n```\n{robux:,} Robux = {price:,.0f} บาท\nเรท: {gamepass_rate}\n```"

def calculate_g(expression):
    robux = eval(expression)
    rate = group_rate_low if robux < 1500 else group_rate_high
    price = robux / rate
    return f"👥 **Robux Group**\n```\n{robux:,} Robux = {price:,.0f} บาท\nเรท: {rate}\n```"

def calculate_gpb(expression):
    baht = eval(expression)
    robux = baht * gamepass_rate
    return f"🎮 **Gamepass**\n```\n{baht:,.0f} บาท = {robux:,.0f} Robux\nเรท: {gamepass_rate}\n```"

def calculate_gb(expression):
    baht = eval(expression)
    rate = group_rate_low if baht < 500 else group_rate_high
    robux = baht * rate
    return f"👥 **Robux Group**\n```\n{baht:,.0f} บาท = {robux:,.0f} Robux\nเรท: {rate}\n```"

# คำสั่งคำนวณราคาแบบเห็นเฉพาะผู้ใช้
@bot.command()
async def gp(ctx, *, expression: str):
    await send_ephemeral_calculation(ctx, calculate_gp, expression)

@bot.command()
async def g(ctx, *, expression: str):
    await send_ephemeral_calculation(ctx, calculate_g, expression)

@bot.command()
async def gpb(ctx, *, expression: str):
    await send_ephemeral_calculation(ctx, calculate_gpb, expression)

@bot.command()
async def gb(ctx, *, expression: str):
    await send_ephemeral_calculation(ctx, calculate_gb, expression)

# --------------------------------------------------------------------------------------------------
# คำสั่งอื่นๆ
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
async def setup(ctx):
    """ตั้งค่าระบบใหม่"""
    await update_main_channel()
    await ctx.send("✅ ตั้งค่าระบบเรียบร้อยแล้ว", delete_after=5)
    await ctx.message.delete()

# --------------------------------------------------------------------------------------------------
server_on()
bot.run(os.getenv("TOKEN"))
