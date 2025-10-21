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
gamepass_stock = 67
group_stock = 67

# เก็บข้อมูลโน้ตส่วนตัว
user_notes = {}

bot = commands.Bot(command_prefix="!", intents=intents)

# --------------------------------------------------------------------------------------------------
# ฟังก์ชันส่งบันทึกการขาย
async def send_sale_log(embed_data: discord.Embed, interaction: discord.Interaction = None, ctx: commands.Context = None, delivered_by: discord.Member = None):
    """ส่ง Embed ไปยังห้องบันทึกการขาย"""
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

        log_embed = discord.Embed(
            title="🍣 บันทึกการขายสำเร็จ 🍣",
            color=0x00FF00,
            timestamp=discord.utils.utcnow()
        )
        log_embed.add_field(name="📦 ประเภทสินค้า", value=sale_type, inline=False)
        log_embed.add_field(name="😊 ผู้ซื้อ", value=user_name, inline=False)
        log_embed.add_field(name="💸 จำนวน Robux", value=robux_amount, inline=True)
        log_embed.add_field(name="💰 ราคา", value=price, inline=True)
        log_embed.add_field(name="🚚 ผู้ส่งสินค้า", value=delivered_by.mention if delivered_by else "ไม่ทราบ", inline=False)
        log_embed.set_footer(text="การสั่งซื้อสำเร็จ")

        await channel.send(embed=log_embed)

    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการส่งบันทึกการขาย: {e}")

# --------------------------------------------------------------------------------------------------
# Modal สำหรับโน้ตส่วนตัว
class PersonalNoteModal(Modal, title="📝 จดวันที่เข้ากลุ่ม"):
    note = TextInput(
        label="จดวันที่เข้ากลุ่มในนี้ ดูจากวันที่ปัจจุบัน",
        placeholder="เช่น: 20/10 , 20 ตค",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000
    )

    async def on_submit(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        if self.note.value.strip():
            user_notes[user_id] = {
                "note": self.note.value,
                "created_at": datetime.datetime.now().isoformat(),
                "updated_at": datetime.datetime.now().isoformat()
            }
            embed = discord.Embed(
                title="✅ บันทึกโน้ตเรียบร้อย",
                description="โน้ตของคุณถูกบันทึกแล้ว",
                color=0x00FF00
            )
            embed.add_field(name="📝 จดวันที่เข้ากลุ่ม", value=self.note.value, inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            if user_id in user_notes:
                del user_notes[user_id]
                await interaction.response.send_message("🗑️ ลบโน้ตส่วนตัวเรียบร้อยแล้ว", ephemeral=True)
            else:
                await interaction.response.send_message("❌ คุณยังไม่มีโน้ตที่บันทึกไว้", ephemeral=True)

# --------------------------------------------------------------------------------------------------
# Modal สำหรับ Gamepass
class GamepassTicketModal(Modal, title="📋 แบบฟอร์มกดเกมพาส"):
    def __init__(self):
        super().__init__(timeout=300)
        
        self.map_name = TextInput(
            label="🗺 ชื่อแมพที่จะกด?",
            placeholder="พิมพ์ชื่อแมพ เช่น All Star Tower Defense X",
            required=True,
            max_length=100
        )
        
        self.gamepass_name = TextInput(
            label="💸 กดเกมพาสอะไร?",
            placeholder="พิมพ์ชื่อเกมพาส เช่น x3 Speed 3 ชิ้น",
            required=True,
            max_length=100
        )
        
        self.robux_amount = TextInput(
            label="🎟 ราคาของเกมพาสเท่าไหร่บ้าง?",
            placeholder="เช่น 995 หรือ 100+100+100 หรือ 100x3",
            required=True,
            max_length=50
        )
        
        self.add_item(self.map_name)
        self.add_item(self.gamepass_name)
        self.add_item(self.robux_amount)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            expr = self.robux_amount.value.lower().replace("x", "*").replace("÷", "/")

            if not re.match(r"^[\d\s\+\-\*\/\(\)]+$", expr):
                await interaction.response.send_message("❌ กรุณาใส่เฉพาะตัวเลข และเครื่องหมาย + - * / x ÷ ()", ephemeral=True)
                return

            robux = int(eval(expr))
            price = robux / gamepass_rate
            price_str = f"{price:,.0f} บาท"

            customer_embed = discord.Embed(
                title="📨 รายละเอียดการสั่งซื้อ", 
                color=0x00FF99,
                timestamp=discord.utils.utcnow()
            )
            customer_embed.add_field(name="🗺️ แมพ", value=self.map_name.value, inline=False)
            customer_embed.add_field(name="🎟 เกมพาส", value=self.gamepass_name.value, inline=False)
            customer_embed.add_field(name="💸 จำนวนโรบัค", value=f"{robux:,}", inline=True)
            customer_embed.add_field(name="💰 ราคา", value=price_str, inline=True)
            customer_embed.set_footer(text="ทีมงานจะตอบกลับโดยเร็วที่สุด")

            view = ConfirmTicketView(embed_data=customer_embed)
            await interaction.response.send_message(embed=customer_embed, view=view, ephemeral=False)

        except Exception as e:
            await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

# --------------------------------------------------------------------------------------------------
# Modal สำหรับ Group
class GroupTicketModal(Modal, title="📋 แบบฟอร์มสั่งซื้อ Robux Group"):
    def __init__(self):
        super().__init__(timeout=300)
        
        self.user_name = TextInput(
            label="🪪 ชื่อในเกม", 
            placeholder="Username",
            required=True,
            max_length=50
        )
        
        self.robux_amount = TextInput(
            label="💸 ต้องการซื้อกี่โรบัค?", 
            placeholder="กรอกจำนวนโรบัคที่ต้องการ",
            required=True,
            max_length=50
        )
        
        self.add_item(self.user_name)
        self.add_item(self.robux_amount)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            robux = int(self.robux_amount.value)
            rate = group_rate_low if robux < 1500 else group_rate_high
            price = robux / rate
            price_str = f"{price:,.0f} บาท"

            customer_embed = discord.Embed(
                title="📨 รายละเอียดคำสั่งซื้อโรบัคกลุ่ม", 
                color=0x00FF99,
                timestamp=discord.utils.utcnow()
            )
            customer_embed.add_field(name="🪪 ชื่อในเกม", value=self.user_name.value, inline=False)
            customer_embed.add_field(name="💸 จำนวนโรบัค", value=f"{robux:,}", inline=True)
            customer_embed.add_field(name="💰 ราคา", value=price_str, inline=True)
            customer_embed.set_footer(text="ทีมงานจะตรวจสอบและตอบกลับโดยเร็วที่สุด")

            view = ConfirmTicketView(embed_data=customer_embed)
            await interaction.response.send_message(embed=customer_embed, view=view, ephemeral=False)

        except ValueError:
            await interaction.response.send_message("❌ กรุณากรอกจำนวนโรบัคเป็นตัวเลข", ephemeral=True)

# --------------------------------------------------------------------------------------------------
# View สำหรับยืนยันตั๋ว
class ConfirmTicketView(View):
    def __init__(self, embed_data: discord.Embed):
        super().__init__(timeout=300)
        self.embed_data = embed_data

    @discord.ui.button(label="✅ ส่งของเรียบร้อยแล้ว", style=discord.ButtonStyle.success, custom_id="confirm_ticket")
    async def confirm_button(self, interaction: discord.Interaction, button: Button):
        try:
            if not interaction.user.guild_permissions.administrator:
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
            await interaction.message.edit(embed=self.embed_data, view=None)
            
        except Exception as e:
            print(f"❌ เกิดข้อผิดพลาดในการยืนยัน: {e}")
            await interaction.response.send_message("❌ เกิดข้อผิดพลาดในการยืนยัน", ephemeral=True)

    @discord.ui.button(label="❌ ยกเลิกสินค้า", style=discord.ButtonStyle.danger, custom_id="cancel_ticket")
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        try:
            await interaction.response.send_message("❌ คำสั่งซื้อถูกยกเลิก", ephemeral=True)
            await interaction.message.delete()
        except Exception as e:
            await interaction.response.send_message("❌ เกิดข้อผิดพลาดในการยกเลิก", ephemeral=True)

# --------------------------------------------------------------------------------------------------
# ฟังก์ชันจัดการการเปิดตั๋ว
async def handle_open_ticket(interaction, category_name, modal_class, stock_type):
    global gamepass_stock, group_stock
    
    try:
        # ตอบกลับทันทีเพื่อป้องกัน timeout
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        user = interaction.user

        if guild is None:
            await interaction.followup.send("❌ คำสั่งนี้ใช้ได้เฉพาะในเซิร์ฟเวอร์", ephemeral=True)
            return

        channel_name = f"ticket-{user.name}-{user.id}"
        
        # ตรวจสอบว่ามีตั๋วอยู่แล้วหรือไม่
        existing_channel = discord.utils.get(guild.text_channels, name=channel_name)
        if existing_channel:
            view = GoToTicketView(existing_channel)
            await interaction.followup.send(
                "📌 คุณมีตั๋วเปิดอยู่แล้ว! กดปุ่มด้านล่างเพื่อไปที่ตั๋ว",
                view=view,
                ephemeral=True
            )
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
            await interaction.followup.send(f"❌ ไม่พบหมวดหมู่ {category_name}", ephemeral=True)
            return

        # สร้างตั๋ว
        channel = await guild.create_text_channel(
            name=channel_name,
            overwrites=overwrites,
            reason="New ticket",
            category=category
        )
        
        # ลด stock ตามประเภท
        if stock_type == "gamepass":
            gamepass_stock -= 1
        else:
            group_stock -= 1
            
        # ส่งข้อความยืนยันไปยังผู้ใช้
        await interaction.followup.send(
            content="📩 เปิดตั๋วเรียบร้อย!",
            view=GoToTicketView(channel),
            ephemeral=True
        )

        # แท็กพนักงานในตั๋ว
        if admin_role:
            await channel.send(content=f"{admin_role.mention} มีตั๋วใหม่!")

        # ส่งข้อความต้อนรับในตั๋ว
        welcome_embed = discord.Embed(
            title="🍣 Sushi Shop 🍣",
            description=(
                "**ยินดีต้อนรับสู่บริการของเรา!**\n\n"
                f"👤 **ผู้ซื้อ:** {user.mention}\n"
                f"🛠️ **ทีมงาน:** {admin_role.mention if admin_role else 'รอพนักงานติดต่อ'}\n\n"
                "**คำแนะนำ:**\n"
                "• กรุณาระบุสิ่งที่ต้องการซื้อ\n"
                "• สามารถใช้คำสั่ง !gp, !g เพื่อคำนวณราคาได้\n"
                "**ขอบคุณที่ใช้บริการ!** 🎉"
            ),
            color=0x00FF99
        )
        welcome_embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/717757556889747657/1403684950770847754/noFilter.png")
        welcome_embed.set_footer(text="Sushi Shop Professional Service")

        view = TicketActionView(channel, user, modal_class)
        await channel.send(embed=welcome_embed, view=view)

    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการเปิดตั๋ว: {e}")
        try:
            await interaction.followup.send("❌ เกิดข้อผิดพลาดในการเปิดตั๋ว", ephemeral=True)
        except:
            pass

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
        try:
            await interaction.response.send_modal(self.modal_class())
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
        
        global gamepass_stock, group_stock
        if "gamepass" in self.channel.category.name.lower():
            gamepass_stock += 1
        elif "group" in self.channel.category.name.lower():
            group_stock += 1
            
        try:
            await self.channel.delete()
        except:
            pass

# --------------------------------------------------------------------------------------------------
# View สำหรับไปที่ตั๋ว
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
# Main Shop View (แก้ไขหลัก)
class MainShopView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        
        # ปุ่ม Gamepass
        gamepass_button = Button(
            label="เปิดตั๋วกดเกมพาส" if shop_open and gamepass_stock > 0 else "สินค้าหมด",
            style=discord.ButtonStyle.success if shop_open and gamepass_stock > 0 else discord.ButtonStyle.danger,
            custom_id="open_gamepass_ticket",
            emoji="🎮",
            disabled=not shop_open or gamepass_stock <= 0
        )
        gamepass_button.callback = self.gamepass_ticket
        self.add_item(gamepass_button)
        
        # ปุ่ม Group
        group_enabled = shop_open and group_ticket_enabled and group_stock > 0
        group_button = Button(
            label="เปิดตั๋ว Group" if group_enabled else "บริการปิดชั่วคราว",
            style=discord.ButtonStyle.success if group_enabled else discord.ButtonStyle.gray,
            custom_id="open_group_ticket", 
            emoji="👥",
            disabled=not group_enabled
        )
        group_button.callback = self.group_ticket
        self.add_item(group_button)
        
        # ปุ่มโน้ตส่วนตัว
        notes_button = Button(
            label="จดวันที่เข้ากลุ่ม",
            style=discord.ButtonStyle.secondary,
            custom_id="personal_notes",
            emoji="📝"
        )
        notes_button.callback = self.personal_notes
        self.add_item(notes_button)

    async def gamepass_ticket(self, interaction: discord.Interaction):
        """Callback สำหรับปุ่ม Gamepass"""
        await interaction.response.defer(ephemeral=True)
        
        if not shop_open:
            await interaction.followup.send("❌ ร้านปิดชั่วคราว", ephemeral=True)
            return
        
        if gamepass_stock <= 0:
            await interaction.followup.send("❌ สินค้าหมดชั่วคราว", ephemeral=True)
            return
        
        await handle_open_ticket(interaction, "🍣Sushi Gamepass 🍣", GamepassTicketModal, "gamepass")

    async def group_ticket(self, interaction: discord.Interaction):
        """Callback สำหรับปุ่ม Group"""
        await interaction.response.defer(ephemeral=True)
        
        if not shop_open:
            await interaction.followup.send("❌ ร้านปิดชั่วคราว", ephemeral=True)
            return
        
        if not group_ticket_enabled:
            await interaction.followup.send("❌ บริการ Group ปิดชั่วคราว", ephemeral=True)
            return
            
        if group_stock <= 0:
            await interaction.followup.send("❌ สินค้าหมดชั่วคราว", ephemeral=True)
            return
            
        await handle_open_ticket(interaction, "💰Robux Group💰", GroupTicketModal, "group")

    async def personal_notes(self, interaction: discord.Interaction):
        """Callback สำหรับปุ่มโน้ตส่วนตัว"""
        user_note = user_notes.get(str(interaction.user.id))
        modal = PersonalNoteModal()
        
        if user_note:
            modal.note.default = user_note["note"]
            
        await interaction.response.send_modal(modal)

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
            try:
                await msg.delete()
            except:
                pass

    # สร้าง embed หลักแบบใหม่
    embed = discord.Embed(
        title="🍣 Sushi Shop 🍣 เปิดบริการ",
        color=0x2B2D31,
        timestamp=discord.utils.utcnow()
    )
    
    # ส่วน Gamepass
    gamepass_stock_status = "🟢 พร้อมให้บริการ" if gamepass_stock > 0 else "🔴 สินค้าหมด"
    embed.add_field(
        name="🎮 **บริการกดเกมพาส**",
        value=(
            "```\n"
            f"เรท: {gamepass_rate}\n"
            "รับกดเกมพาสทุกเกมที่กิ๊ฟได้\n"
            "```\n"
            f"📊 Stock: **{gamepass_stock}** ({gamepass_stock_status})\n"
        ),
        inline=False
    )
    
    # ส่วน Group
    group_stock_status = "🟢 พร้อมให้บริการ" if group_stock > 0 else "🔴 สินค้าหมด"
    if group_ticket_enabled:
        group_value = (
            "```\n"
            f"เรท: {group_rate_low}-{group_rate_high}\n"
            "มากกว่า 500 บาทเรท 4.5 ⚠️เข้ากลุ่มให้ครบ 15 วันก่อนซื้อ⚠️\n"
            "```\n"
            f"📌 เข้ากลุ่ม: [VALKYs](https://www.roblox.com/communities/34713179/VALKYs)\n"
            "📝จดวันที่เข้ากลุ่ม - เพื่อบันทึกวันเข้ากลุ่ม\n"
            f"📊 Stock: **{group_stock}** ({group_stock_status})\n"
        )
    else:
        group_value = "```\n🚫 บริการปิดชั่วคราว\n```"
    
    embed.add_field(
        name="👥 **ระบบโรบัคกลุ่ม**", 
        value=group_value,
        inline=False
    )
    
    # สถานะร้าน
    shop_status = "🟢 เปิดให้บริการ" if shop_open else "🔴 ปิดชั่วคราว"
    embed.add_field(
        name="🏪 **สถานะร้าน**",
        value=f"```\n{shop_status}\n```",
        inline=False
    )
    
    embed.set_footer(
        text="Sushi Shop • รับกดเกมพาสและอื่น ๆ",
        icon_url="https://media.discordapp.net/attachments/717757556889747657/1403684950770847754/noFilter.png"
    )
    
    embed.set_thumbnail(url="https://media.discordapp.net/attachments/717757556889747657/1403684950770847754/noFilter.png")

    # ส่ง embed ใหม่
    try:
        await channel.send(embed=embed, view=MainShopView())
        print("✅ สร้าง embed หลักใหม่เรียบร้อยแล้ว")
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการอัปเดตช่องหลัก: {e}")

# --------------------------------------------------------------------------------------------------
# Events
@bot.event
async def on_ready():
    print(f"✅ บอทออนไลน์แล้ว: {bot.user}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="ร้าน Sushi Shop"))
    
    # ลงทะเบียน Persistent View
    bot.add_view(MainShopView())
    print("✅ ลงทะเบียน MainShopView เรียบร้อย")
    
    await update_main_channel()

@bot.event
async def on_interaction(interaction: discord.Interaction):
    """จัดการ interaction ที่ไม่ผ่าน View"""
    if interaction.type != discord.InteractionType.component:
        return

    custom_id = interaction.data.get("custom_id", "")
    
    try:
        if custom_id == "personal_notes":
            user_note = user_notes.get(str(interaction.user.id))
            modal = PersonalNoteModal()
            
            if user_note:
                modal.note.default = user_note["note"]
                
            await interaction.response.send_modal(modal)
            
        elif custom_id in ["disabled_gamepass", "disabled_group"]:
            await interaction.response.send_message("❌ บริการนี้ไม่พร้อมใช้งานในขณะนี้", ephemeral=True)
            
    except Exception as e:
        print(f"❌ Interaction error: {e}")
        try:
            await interaction.response.send_message("❌ เกิดข้อผิดพลาดในการประมวลผล", ephemeral=True)
        except:
            pass

# --------------------------------------------------------------------------------------------------
# คำสั่งต่างๆ (เหลือไว้เหมือนเดิม)
@bot.command()
@commands.has_permissions(administrator=True)
async def stock(ctx, stock_type: str = None, amount: int = None):
    """ตั้งค่าจำนวน stock"""
    global gamepass_stock, group_stock
    # ... (โค้ดเดิม)

@bot.command()
@commands.has_permissions(administrator=True)
async def sushi(ctx):
    """เปิด/ปิดร้าน"""
    global shop_open
    # ... (โค้ดเดิม)

@bot.command()
@commands.has_permissions(administrator=True)
async def group(ctx, status: str = None):
    """เปิด/ปิด Group Ticket"""
    global group_ticket_enabled
    # ... (โค้ดเดิม)

@bot.command()
@commands.has_permissions(administrator=True) 
async def restart(ctx):
    """รีสตาร์ทระบบ"""
    try:
        await ctx.message.delete()
    except:
        pass
    
    await update_main_channel()
    message = await ctx.send("🔄 รีสตาร์ทระบบปุ่มเรียบร้อยแล้ว", ephemeral=True)
    await asyncio.sleep(3)
    try:
        await message.delete()
    except:
        pass

# ... (คำสั่งอื่นๆ เหมือนเดิม)

# --------------------------------------------------------------------------------------------------
server_on()
bot.run(os.getenv("TOKEN"))
