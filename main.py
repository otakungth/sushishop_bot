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
intents.messages = True
shop_open = True
group_ticket_enabled = True

# ตั้งค่าห้องหลักและ stock
MAIN_CHANNEL_ID = 1361044752975532152
SALES_LOG_CHANNEL_ID = 1402993077643120720
CREDIT_CHANNEL_ID = 1363250076549382246  # ID ห้องให้เครดิต
gamepass_stock = 67
group_stock = 67

# เก็บข้อมูลโน้ตส่วนตัว
user_notes = {}

# เก็บเวลาล่าสุดของกิจกรรมในตั๋ว
ticket_activity = {}

# สร้างบอท
bot = commands.Bot(
    command_prefix="!", 
    intents=intents,
    help_command=None
)

print("🔄 กำลังเริ่มต้นบอท...")

# --------------------------------------------------------------------------------------------------
# ฟังก์ชันลบข้อความอัตโนมัติ
async def auto_delete_messages(ctx, bot_message, delay=60):
    """ลบข้อความผู้ใช้และบอทหลังจากเวลาที่กำหนด"""
    try:
        await asyncio.sleep(delay)
        
        # ลบข้อความบอท
        try:
            await bot_message.delete()
        except:
            pass
            
        # ลบข้อความผู้ใช้
        try:
            await ctx.message.delete()
        except:
            pass
            
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการลบข้อความ: {e}")

# --------------------------------------------------------------------------------------------------
# ฟังก์ชันบันทึกกิจกรรมในตั๋ว
async def record_ticket_activity(channel_id):
    """บันทึกเวลาล่าสุดที่มีกิจกรรมในตั๋ว"""
    ticket_activity[channel_id] = datetime.datetime.now()

# --------------------------------------------------------------------------------------------------
# ฟังก์ชันตรวจสอบและลบตั๋วที่ไม่มีกิจกรรม
async def check_inactive_tickets():
    """ตรวจสอบและลบตั๋วที่ไม่มีกิจกรรมเกิน 1 ชั่วโมง"""
    while True:
        try:
            current_time = datetime.datetime.now()
            channels_to_delete = []
            
            for channel_id, last_activity in ticket_activity.items():
                # คำนวณเวลาที่ผ่านไปตั้งแต่กิจกรรมล่าสุด
                time_since_activity = current_time - last_activity
                
                # ถ้าไม่มีกิจกรรมเกิน 1 ชั่วโมง ให้เตรียมลบ
                if time_since_activity.total_seconds() > 3600:  # 1 ชั่วโมง = 3600 วินาที
                    channels_to_delete.append(channel_id)
            
            # ลบตั๋วที่ไม่มีกิจกรรม
            for channel_id in channels_to_delete:
                try:
                    channel = bot.get_channel(channel_id)
                    if channel and channel.name.startswith("ticket-"):
                        print(f"🕒 ลบตั๋ว {channel.name} เนื่องจากไม่มีกิจกรรมเกิน 1 ชั่วโมง")
                        
                        # คืน stock
                        global gamepass_stock, group_stock
                        if channel.category and "gamepass" in channel.category.name.lower():
                            gamepass_stock += 1
                        elif channel.category and "group" in channel.category.name.lower():
                            group_stock += 1
                        
                        await channel.delete()
                        
                        # ลบออกจากรายการติดตาม
                        if channel_id in ticket_activity:
                            del ticket_activity[channel_id]
                            
                except Exception as e:
                    print(f"❌ ไม่สามารถลบตั๋ว {channel_id}: {e}")
            
            # อัพเดท stock ในช่องหลัก
            await update_main_channel()
            
        except Exception as e:
            print(f"❌ ข้อผิดพลาดในการตรวจสอบตั๋ว: {e}")
        
        # ตรวจสอบทุก 5 นาที
        await asyncio.sleep(300)

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
                if role is None or role not in interaction.user.roles:
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
        # ตรวจสอบ stock ก่อนตอบกลับ
        if stock_type == "gamepass" and gamepass_stock <= 0:
            await interaction.response.send_message("❌ ขออภัย สินค้าหมดชั่วคราว", ephemeral=True)
            return
        elif stock_type == "group" and group_stock <= 0:
            await interaction.response.send_message("❌ ขออภัย สินค้าหมดชั่วคราว", ephemeral=True)
            return
            
        guild = interaction.guild
        user = interaction.user

        if guild is None:
            await interaction.response.send_message("❌ คำสั่งนี้ใช้ได้เฉพาะในเซิร์ฟเวอร์", ephemeral=True)
            return

        channel_name = f"ticket-{user.name}-{user.id}"
        
        # ตรวจสอบว่ามีตั๋วอยู่แล้วหรือไม่
        existing_channel = discord.utils.get(guild.text_channels, name=channel_name)
        if existing_channel:
            view = GoToTicketView(existing_channel)
            await interaction.response.send_message(
                "📌 คุณมีตั๋วเปิดอยู่แล้ว! กดปุ่มด้านล่างเพื่อไปที่ตั๋ว",
                view=view,
                ephemeral=True
            )
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        admin_role = guild.get_role(1361016912259055896)
        if admin_role:
            overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        category = discord.utils.get(guild.categories, name=category_name)
        if category is None:
            await interaction.response.send_message(f"❌ ไม่พบหมวดหมู่ {category_name}", ephemeral=True)
            return

        # ตอบกลับก่อนสร้างตั๋ว
        await interaction.response.send_message("🔄 กำลังเปิดตั๋ว...", ephemeral=True)

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
            
        # บันทึกกิจกรรมเริ่มต้น
        await record_ticket_activity(channel.id)
            
        # อัพเดทข้อความตอบกลับ
        await interaction.edit_original_response(
            content="📩 เปิดตั๋วเรียบร้อย!",
            view=GoToTicketView(channel)
        )

        # กำหนดข้อความตามประเภทตั๋ว
        if stock_type == "gamepass":
            service_info = f"**บริการกดเกมพาสเรท: {gamepass_rate}**\n📊 Stock เหลือ: **{gamepass_stock}**"
        else:
            service_info = f"**ระบบโรบัคกลุ่มเรท: {group_rate_low}-{group_rate_high}**\n📊 Stock เหลือ: **{group_stock}**"

        # แท็กพนักงานในตั๋วพร้อมข้อมูลบริการ
        if admin_role:
            await channel.send(content=f"{admin_role.mention} มีตั๋วใหม่!\n\n{service_info}")

        # ส่งข้อความต้อนรับในตั๋ว
        welcome_embed = discord.Embed(
            title="🍣 Sushi Shop 🍣",
            description=(
                "**ยินดีต้อนรับสู่บริการของเรา!**\n\n"
                f"👤 **ผู้ซื้อ:** {user.mention}\n"
                f"🛠️ **ทีมงาน:** {admin_role.mention if admin_role else 'รอพนักงานติดต่อ'}\n\n"
                f"**ข้อมูลบริการ:**\n"
                f"{service_info}\n\n"
                "**คำแนะนำ:**\n"
                "• กรุณาระบุสิ่งที่ต้องการซื้อ\n"
                "• สามารถใช้คำสั่ง !gp, !g เพื่อเช็คราคาได้\n"
                "• เช่น "!gp 799 / !gp 100x3\n"
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
            await interaction.response.send_message("❌ เกิดข้อผิดพลาดในการเปิดตั๋ว", ephemeral=True)
        except:
            try:
                await interaction.edit_original_response(content="❌ เกิดข้อผิดพลาดในการเปิดตั๋ว")
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
            # บันทึกกิจกรรม
            await record_ticket_activity(interaction.channel.id)
            await interaction.response.send_modal(self.modal_class())
        except Exception as e:
            await interaction.response.send_message("❌ เกิดข้อผิดพลาดในการเปิดฟอร์ม", ephemeral=True)

    @discord.ui.button(label="📤 ช่องทางการโอนเงิน", style=discord.ButtonStyle.success, emoji="📤")
    async def payment_info(self, interaction: discord.Interaction, button: Button):
        try:
            # บันทึกกิจกรรม
            await record_ticket_activity(interaction.channel.id)
            
            # สร้างข้อความเลขบัญชีที่สามารถกดค้างคัดลอกได้ (แยกช่อง)
            bank_accounts = (
                "**🏦 ช่องทางการโอนเงิน**\n\n"
                "**บัญชี 1:**\n"
                "```12345```\n"
                "**บัญชี 2:**\n"
                "```33333```\n"
                "*กดค้างที่เลขบัญชีเพื่อคัดลอก*"
            )
            
            embed = discord.Embed(
                title="📤 ช่องทางการโอนเงิน",
                description=bank_accounts,
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
        if self.channel.category and "gamepass" in self.channel.category.name.lower():
            gamepass_stock += 1
        elif self.channel.category and "group" in self.channel.category.name.lower():
            group_stock += 1
            
        # ลบออกจากรายการติดตามกิจกรรม
        if self.channel.id in ticket_activity:
            del ticket_activity[self.channel.id]
            
        try:
            await self.channel.delete()
        except Exception as e:
            print(f"❌ เกิดข้อผิดพลาดในการลบช่อง: {e}")

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
# View สำหรับให้เครดิตแบบใหม่ - พาไปที่ห้องเครดิตโดยตรง
class GiveCreditView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        # ปุ่มเดียวที่พาไปที่ห้องเครดิตโดยตรง
        self.add_item(
            discord.ui.Button(
                label="⭐ ให้เครดิตที่นี่", 
                url="https://discord.com/channels/1360990259311018077/1363250076549382246", 
                style=discord.ButtonStyle.link,
                emoji="⭐"
            )
        )

# --------------------------------------------------------------------------------------------------
# Main Shop View
class MainShopView(View):
    def __init__(self):
        super().__init__(timeout=None)
        
        # สร้างปุ่มแบบไดนามิก
        gamepass_button = Button(
            label="เปิดตั๋วกดเกมพาส" if shop_open and gamepass_stock > 0 else "สินค้าหมด",
            style=discord.ButtonStyle.success if shop_open and gamepass_stock > 0 else discord.ButtonStyle.danger,
            custom_id="open_gamepass_ticket",
            emoji="🎮",
            disabled=not shop_open or gamepass_stock <= 0
        )
        gamepass_button.callback = self.gamepass_ticket
        self.add_item(gamepass_button)
        
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
        try:
            if not shop_open:
                await interaction.response.send_message("❌ ร้านปิดชั่วคราว", ephemeral=True)
                return
            
            if gamepass_stock <= 0:
                await interaction.response.send_message("❌ สินค้าหมดชั่วคราว", ephemeral=True)
                return
            
            await handle_open_ticket(interaction, "🍣Sushi Gamepass 🍣", GamepassTicketModal, "gamepass")
        except Exception as e:
            print(f"❌ ข้อผิดพลาดใน gamepass_ticket: {e}")
            await interaction.response.send_message("❌ เกิดข้อผิดพลาด", ephemeral=True)

    async def group_ticket(self, interaction: discord.Interaction):
        """Callback สำหรับปุ่ม Group"""
        try:
            if not shop_open:
                await interaction.response.send_message("❌ ร้านปิดชั่วคราว", ephemeral=True)
                return
            
            if not group_ticket_enabled:
                await interaction.response.send_message("❌ บริการ Group ปิดชั่วคราว", ephemeral=True)
                return
                
            if group_stock <= 0:
                await interaction.response.send_message("❌ สินค้าหมดชั่วคราว", ephemeral=True)
                return
                
            await handle_open_ticket(interaction, "💰Robux Group💰", GroupTicketModal, "group")
        except Exception as e:
            print(f"❌ ข้อผิดพลาดใน group_ticket: {e}")
            await interaction.response.send_message("❌ เกิดข้อผิดพลาด", ephemeral=True)

    async def personal_notes(self, interaction: discord.Interaction):
        """Callback สำหรับปุ่มโน้ตส่วนตัว"""
        try:
            user_note = user_notes.get(str(interaction.user.id))
            modal = PersonalNoteModal()
            
            if user_note:
                modal.note.default = user_note["note"]
                
            await interaction.response.send_modal(modal)
        except Exception as e:
            print(f"❌ ข้อผิดพลาดใน personal_notes: {e}")
            await interaction.response.send_message("❌ เกิดข้อผิดพลาด", ephemeral=True)

# --------------------------------------------------------------------------------------------------
# อัปเดตช่องหลัก
async def update_main_channel():
    """อัปเดตข้อความในช่องหลัก"""
    try:
        channel = bot.get_channel(MAIN_CHANNEL_ID)
        if not channel:
            print("❌ ไม่พบช่องหลัก")
            return

        # ลบข้อความเก่าๆ ของบอทในช่องนี้
        async for msg in channel.history(limit=10):
            if msg.author == bot.user:
                try:
                    await msg.delete()
                    await asyncio.sleep(1)
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
                f"📌 กดเข้ากลุ่มนี้ :point_right: [VALKYs](https://www.roblox.com/communities/34713179/VALKYs) :point_left: \n"
                "📝จดวันที่เข้ากลุ่ม เพื่อบันทึกวันเข้ากลุ่ม\n"
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
        await channel.send(embed=embed, view=MainShopView())
        print("✅ สร้าง embed หลักใหม่เรียบร้อยแล้ว")
        
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการอัปเดตช่องหลัก: {e}")

# --------------------------------------------------------------------------------------------------
# Events
@bot.event
async def on_ready():
    print(f"✅ บอทออนไลน์แล้ว: {bot.user} (ID: {bot.user.id})")
    print(f"✅ Prefix: {bot.command_prefix}")
    print(f"✅ Guilds: {len(bot.guilds)}")
    
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="ร้าน Sushi Shop"))
    
    # ลงทะเบียน Persistent View
    bot.add_view(MainShopView())
    print("✅ ลงทะเบียน MainShopView เรียบร้อย")
    
    # เริ่มต้นระบบตรวจสอบตั๋ว
    bot.loop.create_task(check_inactive_tickets())
    print("✅ เริ่มต้นระบบตรวจสอบตั๋วอัตโนมัติเรียบร้อย")
    
    await update_main_channel()

@bot.event
async def on_message(message):
    """บันทึกกิจกรรมเมื่อมีข้อความใหม่ในตั๋ว"""
    # ข้ามถ้าเป็นข้อความจากบอทตัวเอง
    if message.author == bot.user:
        return
    
    # บันทึกกิจกรรมถ้าเป็นตั๋ว
    if message.channel.name.startswith("ticket-"):
        await record_ticket_activity(message.channel.id)
    
    # ต้องมีคำสั่งนี้เพื่อให้คำสั่งอื่นๆ ทำงานต่อ
    await bot.process_commands(message)

@bot.event
async def on_command_error(ctx, error):
    """จัดการข้อผิดพลาดของคำสั่ง"""
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", delete_after=5)
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send("❌ บอทไม่มีสิทธิ์ที่จำเป็น", delete_after=5)
    else:
        print(f"❌ ข้อผิดพลาดคำสั่ง: {error}")
        await ctx.send("❌ เกิดข้อผิดพลาดในการดำเนินการ", delete_after=5)

# --------------------------------------------------------------------------------------------------
# คำสั่งพื้นฐาน
@bot.command(name='help')
async def help_command(ctx):
    """แสดงคำสั่งทั้งหมด"""
    help_embed = discord.Embed(
        title="🍣 Sushi Shop - คำสั่งทั้งหมด",
        description="**คำสั่งคำนวณราคา (ลบอัตโนมัติใน 1 นาที):**\n"
                   "`!gp <จำนวน>` - คำนวณราคา Gamepass\n"
                   "`!g <จำนวน>` - คำนวณราคา Group\n"
                   "`!gpb <จำนวน>` - คำนวณ Robux จากเงิน (Gamepass)\n"
                   "`!gb <จำนวน>` - คำนวณ Robux จากเงิน (Group)\n"
                   "`!tax <จำนวน>` - คำนวณ Robux หลังหักภาษี\n\n"
                   "**คำสั่งคำนวณราคา (แสดงผลถาวร):**\n"
                   "`!gp p <จำนวน>` - คำนวณราคา Gamepass ถาวร\n"
                   "`!g p <จำนวน>` - คำนวณราคา Group ถาวร\n"
                   "`!gpb p <จำนวน>` - คำนวณ Robux จากเงิน ถาวร\n"
                   "`!gb p <จำนวน>` - คำนวณ Robux จากเงิน ถาวร\n\n"
                   "**คำสั่งสั่งซื้อ:**\n"
                   "`!od <จำนวน>` - สั่งซื้อ Gamepass\n"
                   "`!odg <จำนวน>` - สั่งซื้อ Group\n\n"
                   "**คำสั่งผู้ดูแล:**\n"
                   "`!stock` - ตรวจสอบ stock\n"
                   "`!sushi` - เปิด/ปิดร้าน\n"
                   "`!group <on/off>` - เปิด/ปิด Group ticket\n"
                   "`!ty` - ส่งของเรียบร้อย (ใช้ในตั๋ว)\n"
                   "`!qr` - แสดง QR Code\n"
                   "`!setup` - ตั้งค่าระบบใหม่\n"
                   "`!restart` - รีสตาร์ทระบบปุ่ม",
        color=0x00FF99
    )
    await ctx.send(embed=help_embed, delete_after=30)

# --------------------------------------------------------------------------------------------------
# คำสั่งจัดการ Stock
@bot.command()
@commands.has_permissions(administrator=True)
async def stock(ctx, stock_type: str = None, amount: int = None):
    """ตั้งค่าจำนวน stock (เฉพาะผู้ดูแล)"""
    global gamepass_stock, group_stock
    
    try:
        await ctx.message.delete()
    except:
        pass
    
    if stock_type is None:
        message = await ctx.send(
            f"📊 **โรบัคเหลือ:**\n"
            f"🎮 สต๊อกเกมพาส: **{gamepass_stock}**\n"
            f"👥 สต๊อกโรบัคกลุ่ม: **{group_stock}**"
        )
        await asyncio.sleep(5)
        try:
            await message.delete()
        except:
            pass
    elif stock_type.lower() in ["gp", "gamepass", "เกมพาส"]:
        if amount is None:
            message = await ctx.send(f"🎮 Gamepass Stock ปัจจุบัน: **{gamepass_stock}**")
            await asyncio.sleep(5)
            try:
                await message.delete()
            except:
                pass
        else:
            if amount < 0:
                await ctx.send("❌ จำนวน stock ต้องมากกว่าหรือเท่ากับ 0", delete_after=5)
                return
            
            gamepass_stock = amount
            await ctx.send(f"✅ ตั้งค่า สต๊อกเกมพาส เป็น **{gamepass_stock}** เรียบร้อยแล้ว", delete_after=5)
            await update_main_channel()
    
    elif stock_type.lower() in ["g", "group", "กรุ๊ป"]:
        if amount is None:
            message = await ctx.send(f"👥 สต๊อกโรบัคกลุ่ม ปัจจุบัน: **{group_stock}**")
            await asyncio.sleep(5)
            try:
                await message.delete()
            except:
                pass
        else:
            if amount < 0:
                await ctx.send("❌ จำนวน stock ต้องมากกว่าหรือเท่ากับ 0", delete_after=5)
                return
            
            group_stock = amount
            await ctx.send(f"✅ ตั้งค่า สต๊อกโรบัคกลุ่ม เป็น **{group_stock}** เรียบร้อยแล้ว", delete_after=5)
            await update_main_channel()
    
    else:
        message = await ctx.send(
            "❌ การใช้งาน:\n"
            "`!stock` - เช็ค stock ทั้งหมด\n"
            "`!stock gp <จำนวน>` - ตั้งค่า Gamepass stock\n" 
            "`!stock group <จำนวน>` - ตั้งค่า Group stock",
            delete_after=10
        )

# --------------------------------------------------------------------------------------------------
# คำสั่งเปิดปิดร้าน
@bot.command()
@commands.has_permissions(administrator=True)
async def sushi(ctx):
    """เปิด/ปิดร้าน (รวมทั้ง Gamepass และ Group)"""
    global shop_open
    shop_open = not shop_open

    try:
        await ctx.message.delete()
    except:
        pass

    status = "✅ ร้านเปิด" if shop_open else "❌ ร้านปิด"
    message = await ctx.send(f"📌 สถานะร้าน: **{status}**", delete_after=5)
    
    await update_main_channel()

# --------------------------------------------------------------------------------------------------
# คำสั่งเปิดปิด Group Ticket
@bot.command()
@commands.has_permissions(administrator=True)
async def group(ctx, status: str = None):
    """เปิด/ปิดปุ่ม Group Ticket"""
    global group_ticket_enabled
    
    try:
        await ctx.message.delete()
    except:
        pass
    
    if status is None:
        current_status = "✅ เปิด" if group_ticket_enabled else "❌ ปิด"
        message = await ctx.send(f"📌 สถานะ Group Ticket: **{current_status}**", delete_after=5)
    elif status.lower() in ["on", "enable", "เปิด"]:
        group_ticket_enabled = True
        message = await ctx.send("✅ เปิดปุ่ม Group Ticket เรียบร้อยแล้ว", delete_after=5)
    elif status.lower() in ["off", "disable", "ปิด"]:
        group_ticket_enabled = False
        message = await ctx.send("❌ ปิดปุ่ม Group Ticket เรียบร้อยแล้ว", delete_after=5)
    else:
        message = await ctx.send(
            "❌ การใช้งาน: !group [on/off] หรือ !group [enable/disable] หรือ !group [เปิด/ปิด]",
            delete_after=10
        )
    
    await update_main_channel()

# --------------------------------------------------------------------------------------------------
# คำสั่งคำนวณราคา (ลบอัตโนมัติใน 1 นาที)
@bot.command()
async def gp(ctx, *, expression: str):
    """คำนวณราคาจากจำนวน Robux (Gamepass) - ลบอัตโนมัติใน 1 นาที"""
    try:
        # ตรวจสอบว่าเป็นโหมดถาวรหรือไม่
        if expression.lower().startswith('p '):
            # โหมดถาวร - ไม่ลบ
            actual_expression = expression[2:].strip()
            permanent = True
        else:
            actual_expression = expression
            permanent = False

        actual_expression = actual_expression.replace(",", "").lower().replace("x", "*").replace("÷", "/")

        if not re.match(r"^[\d\s\+\-\*\/\(\)]+$", actual_expression):
            await ctx.send("❌ กรุณาใส่เฉพาะตัวเลข และเครื่องหมาย + - * / x ÷ ()", delete_after=10)
            return

        robux = eval(actual_expression)
        price = robux / gamepass_rate
        price_str = f"{price:,.0f} บาท"

        message = await ctx.send(f"🎮 Gamepass {robux:,} Robux = **{price_str}** (เรท {gamepass_rate})")

        # ถ้าไม่ใช่โหมดถาวร ให้ลบอัตโนมัติใน 1 นาที
        if not permanent:
            await auto_delete_messages(ctx, message, 60)

    except Exception as e:
        error_msg = await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=10)
        if not permanent:
            await auto_delete_messages(ctx, error_msg, 60)

@bot.command()
async def g(ctx, *, expression: str):
    """คำนวณราคาจากจำนวน Robux (Group) - ลบอัตโนมัติใน 1 นาที"""
    try:
        # ตรวจสอบว่าเป็นโหมดถาวรหรือไม่
        if expression.lower().startswith('p '):
            actual_expression = expression[2:].strip()
            permanent = True
        else:
            actual_expression = expression
            permanent = False

        actual_expression = actual_expression.replace(",", "").lower().replace("x", "*").replace("÷", "/")

        if not re.match(r"^[\d\s\+\-\*\/\(\)]+$", actual_expression):
            await ctx.send("❌ กรุณาใส่เฉพาะตัวเลข และเครื่องหมาย + - * / x ÷ ()", delete_after=10)
            return

        robux = eval(actual_expression)

        if robux < 1500:
            rate = group_rate_low
        else:
            rate = group_rate_high

        price = robux / rate
        price_str = f"{price:,.0f} บาท"

        message = await ctx.send(f"👥 Group {robux:,} Robux = **{price_str}** (เรท {rate})")

        # ถ้าไม่ใช่โหมดถาวร ให้ลบอัตโนมัติใน 1 นาที
        if not permanent:
            await auto_delete_messages(ctx, message, 60)

    except Exception as e:
        error_msg = await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=10)
        if not permanent:
            await auto_delete_messages(ctx, error_msg, 60)

@bot.command()
async def gpb(ctx, *, expression: str):
    """คำนวณจากจำนวนเงิน เป็น Robux (Gamepass) - ลบอัตโนมัติใน 1 นาที"""
    try:
        # ตรวจสอบว่าเป็นโหมดถาวรหรือไม่
        if expression.lower().startswith('p '):
            actual_expression = expression[2:].strip()
            permanent = True
        else:
            actual_expression = expression
            permanent = False

        actual_expression = actual_expression.replace(",", "").replace(" ", "")
        baht = eval(actual_expression)

        robux = baht * gamepass_rate
        message = await ctx.send(f"🎮 {baht:,.0f} บาท = **{robux:,.0f} Robux** (Gamepass เรท {gamepass_rate})")

        # ถ้าไม่ใช่โหมดถาวร ให้ลบอัตโนมัติใน 1 นาที
        if not permanent:
            await auto_delete_messages(ctx, message, 60)

    except Exception as e:
        error_msg = await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=10)
        if not permanent:
            await auto_delete_messages(ctx, error_msg, 60)

@bot.command()
async def gb(ctx, *, expression: str):
    """คำนวณจากจำนวนเงิน เป็น Robux (Group) - ลบอัตโนมัติใน 1 นาที"""
    try:
        # ตรวจสอบว่าเป็นโหมดถาวรหรือไม่
        if expression.lower().startswith('p '):
            actual_expression = expression[2:].strip()
            permanent = True
        else:
            actual_expression = expression
            permanent = False

        actual_expression = actual_expression.replace(",", "").replace(" ", "")
        baht = eval(actual_expression)

        if baht < 500:
            rate = group_rate_low
        else:
            rate = group_rate_high

        robux = baht * rate
        message = await ctx.send(f"👥 {baht:,.0f} บาท = **{robux:,.0f} Robux** (Group เรท {rate})")

        # ถ้าไม่ใช่โหมดถาวร ให้ลบอัตโนมัติใน 1 นาที
        if not permanent:
            await auto_delete_messages(ctx, message, 60)

    except Exception as e:
        error_msg = await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=10)
        if not permanent:
            await auto_delete_messages(ctx, error_msg, 60)

# --------------------------------------------------------------------------------------------------
# คำสั่ง !tax (คำนวณหัก Tax) - ลบอัตโนมัติใน 1 นาที
@bot.command()
async def tax(ctx, *, expression: str):
    """คำนวณ Robux หลังหัก % (ภาษีหรือส่วนลด) - ลบอัตโนมัติใน 1 นาที"""
    try:
        # ตรวจสอบว่าเป็นโหมดถาวรหรือไม่
        if expression.lower().startswith('p '):
            actual_expression = expression[2:].strip()
            permanent = True
        else:
            actual_expression = expression
            permanent = False

        actual_expression = actual_expression.replace(" ", "")
        
        if re.match(r"^\d+$", actual_expression):
            number = int(actual_expression)
            result = number * 0.7
            message = await ctx.send(f"💰 {number:,} Robux หลังหัก 30% = **{result:,.0f} Robux**")
            
        elif re.match(r"^\d+-\d+%$", actual_expression):
            parts = actual_expression.split('-')
            number = int(parts[0])
            percent = int(parts[1].replace('%', ''))
            
            if percent < 0 or percent > 100:
                message = await ctx.send("❌ เปอร์เซ็นต์ต้องอยู่ระหว่าง 0-100%", delete_after=10)
                if not permanent:
                    await auto_delete_messages(ctx, message, 60)
                return
            
            result = number * (1 - percent/100)
            message = await ctx.send(f"💰 {number:,} Robux หลังหัก {percent}% = **{result:,.0f} Robux**")
            
        else:
            message = await ctx.send(
                "❌ รูปแบบไม่ถูกต้อง\n\n"
                "**การใช้งาน:**\n"
                "`!tax 100` - หัก 30% อัตโนมัติ\n"
                "`!tax 100-30%` - หัก 30%\n"
                "`!tax 100-50%` - หัก 50%",
                delete_after=15
            )

        # ถ้าไม่ใช่โหมดถาวร ให้ลบอัตโนมัติใน 1 นาที
        if not permanent:
            await auto_delete_messages(ctx, message, 60)

    except Exception as e:
        error_msg = await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=10)
        if not permanent:
            await auto_delete_messages(ctx, error_msg, 60)

# --------------------------------------------------------------------------------------------------
# คำสั่งสั่งซื้อและบันทึกการขาย (!od, !odg)
@bot.command()
async def od(ctx, *, expression: str):
    """คำสั่งสั่งซื้อ Robux Gamepass"""
    try:
        expr = expression.replace(",", "").lower().replace("x", "*").replace("÷", "/")

        if not re.match(r"^[\d\s\+\-\*\/\(\)]+$", expr):
            await ctx.send("❌ กรุณาใส่เฉพาะตัวเลข และเครื่องหมาย + - * / x ÷ ()", delete_after=10)
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
        embed.add_field(name="💸 จำนวนโรบัค", value=f"{robux:,}", inline=True)
        embed.add_field(name="💰 ราคาตามเรท", value=price_str, inline=True)
        embed.add_field(name="😊 ผู้ซื้อ", value=ctx.author.mention, inline=False)
        embed.add_field(name="🚚 ผู้ส่งสินค้า", value=ctx.author.mention, inline=False)
        embed.set_footer(text="การสั่งซื้อสำเร็จ")

        await ctx.send(embed=embed)

        # ส่งไปยังห้องบันทึกการขาย
        sales_channel = bot.get_channel(SALES_LOG_CHANNEL_ID)
        if sales_channel:
            await sales_channel.send(embed=embed)

    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=10)

@bot.command()
async def odg(ctx, *, expression: str):
    """คำสั่งสั่งซื้อ Robux Group"""
    try:
        expr = expression.replace(",", "").lower().replace("x", "*").replace("÷", "/")

        if not re.match(r"^[\d\s\+\-\*\/\(\)]+$", expr):
            await ctx.send("❌ กรุณาใส่เฉพาะตัวเลข และเครื่องหมาย + - * / x ÷ ()", delete_after=10)
            return

        robux = int(eval(expr))
        rate = group_rate_low if robux < 1500 else group_rate_high
        price = robux / rate
        price_str = f"{price:,.0f} บาท"

        embed = discord.Embed(
            title="🍣 ใบเสร็จคำสั่งซื้อโรบัคกลุ่ม 🍣",
            color=0x00AAFF,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="📦 ประเภทสินค้า", value="Robux Group", inline=False)
        embed.add_field(name="💸 จำนวน Robux", value=f"{robux:,}", inline=True)
        embed.add_field(name="💰 ราคาตามเรท", value=price_str, inline=True)
        embed.add_field(name="📊 เรท", value=f"{rate}", inline=True)
        embed.add_field(name="😊 ผู้ซื้อ", value=ctx.author.mention, inline=False)
        embed.add_field(name="🚚 ผู้ส่งสินค้า", value=ctx.author.mention, inline=False)
        embed.set_footer(text="การสั่งซื้อสำเร็จ • Robux Group")

        await ctx.send(embed=embed)

        # ส่งไปยังห้องบันทึกการขาย
        sales_channel = bot.get_channel(SALES_LOG_CHANNEL_ID)
        if sales_channel:
            await sales_channel.send(embed=embed)

    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=10)

# --------------------------------------------------------------------------------------------------
# คำสั่ง !qr - แสดง QR Code และเลขบัญชี
@bot.command()
@commands.has_permissions(administrator=True)
async def qr(ctx):
    """แสดง QR Code และเลขบัญชีช่องทางการโอนเงิน"""
    try:
        await ctx.message.delete()
    except:
        pass
    
    # สร้างข้อความเลขบัญชีที่สามารถกดค้างคัดลอกได้ (แยกช่อง)
    bank_accounts = (
        "**🏦 ช่องทางการโอนเงิน**\n\n"
        "**:green_circle: ธนาคารกสิกร:**\n"
        "```160-1-43871-9```\n"
        "**:orange_circle: ทรูมันนี่วอเล็ต:**\n"
        "```065-506-0702```\n"
        "**:notepad_spiral:ชื่อ: อริสรา ศรีจิตต์แจ่ม**\n"
        "*กดค้างที่เลขบัญชีเพื่อคัดลอก*"
    )
    
    embed = discord.Embed(
        title="📱 สแกน QR เพื่อชำระเงิน",
        description=bank_accounts,
        color=0x00CCFF
    )
    embed.set_image(url="https://media.discordapp.net/attachments/722832040860319835/1402994996600111114/186-8-06559-8.png")
    await ctx.send(embed=embed)

# --------------------------------------------------------------------------------------------------
# คำสั่ง !ty - ส่งของเรียบร้อยแล้ว
@bot.command()
@commands.has_permissions(administrator=True)
async def ty(ctx):
    """ส่งของเรียบร้อยแล้ว"""
    try:
        await ctx.message.delete()
    except:
        pass
    
    if ctx.channel.name.startswith("ticket-"):
        # คืน stock เมื่อส่งของสำเร็จ
        global gamepass_stock, group_stock
        
        # ตรวจสอบหมวดหมู่เพื่อกำหนดประเภท
        if ctx.channel.category and "gamepass" in ctx.channel.category.name.lower():
            gamepass_stock += 1
        elif ctx.channel.category and "group" in ctx.channel.category.name.lower():
            group_stock += 1
            
        # หา embed การสั่งซื้อ
        sale_embed = None
        async for msg in ctx.channel.history():
            if msg.embeds and "รายละเอียดการสั่งซื้อ" in msg.embeds[0].title:
                sale_embed = msg.embeds[0]
                break

        if sale_embed:
            confirmed = any(field.name == "📋 ยืนยันโดย" for field in sale_embed.fields)
            if not confirmed:
                sale_embed.add_field(name="📋 ยืนยันโดย", value=ctx.author.mention, inline=False)

        # ย้ายไปหมวดหมู่ "ส่งของแล้ว"
        delivered_category = discord.utils.get(ctx.guild.categories, name="ส่งของแล้ว")
        if delivered_category:
            try:
                await ctx.channel.edit(category=delivered_category)
            except Exception as e:
                print(f"❌ ไม่สามารถย้ายหมวดหมู่: {e}")

        # บันทึกกิจกรรมล่าสุด
        await record_ticket_activity(ctx.channel.id)

        # สร้าง View สำหรับปุ่ม
        class TempCloseView(View):
            def __init__(self, channel):
                super().__init__(timeout=None)
                self.channel = channel

            @discord.ui.button(label="🔒 ปิดตั๋ว", style=discord.ButtonStyle.danger)
            async def close_button(self, interaction: discord.Interaction, button: Button):
                global gamepass_stock, group_stock
                if self.channel.category and "gamepass" in self.channel.category.name.lower():
                    gamepass_stock += 1
                elif self.channel.category and "group" in self.channel.category.name.lower():
                    group_stock += 1
                    
                # ลบออกจากรายการติดตามกิจกรรม
                if self.channel.id in ticket_activity:
                    del ticket_activity[self.channel.id]
                    
                await interaction.response.send_message("📪 กำลังปิดตั๋ว...", ephemeral=True)
                try:
                    await self.channel.delete()
                except:
                    pass

        # สร้าง View แยกสำหรับปุ่มลิงก์ให้เครดิต
        credit_view = GiveCreditView()
        
        # ส่งข้อความขอบคุณ
        embed = discord.Embed(
            title="✅ สินค้าถูกส่งเรียบร้อยแล้ว",
            description=(
                "ขอบคุณที่ใช้บริการกับเรา หากไม่มีปัญหาเพิ่มเติม "
                "สามารถกดปุ่มด้านล่างเพื่อปิดตั๋วได้เลย\n\n"
                "⏳ **ตั๋วจะถูกปิดอัตโนมัติใน 1 ชั่วโมง ถ้าไม่มีกิจกรรมเพิ่มเติม**"
            ),
            color=0x00FF00
        )
        
        await ctx.send(embed=embed, view=TempCloseView(ctx.channel))
        
        # ส่งปุ่มให้เครดิตแยกต่างหาก
        await ctx.send("กดปุ่มด้านล่างเพื่อให้เครดิตกับผู้ส่งสินค้า:", view=credit_view)

    else:
        await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะในตั๋วเท่านั้น", delete_after=5)

# --------------------------------------------------------------------------------------------------
# คำสั่งอื่นๆ
@bot.command()
@commands.has_permissions(administrator=True)
async def setup(ctx):
    """ตั้งค่าระบบใหม่"""
    try:
        await ctx.message.delete()
    except:
        pass
    
    message = await ctx.send("✅ ตั้งค่าระบบเรียบร้อยแล้ว", delete_after=5)
    await update_main_channel()

@bot.command()
@commands.has_permissions(administrator=True)
async def restart(ctx):
    """รีสตาร์ทระบบปุ่ม"""
    try:
        await ctx.message.delete()
    except:
        pass
    
    await update_main_channel()
    message = await ctx.send("🔄 รีสตาร์ทระบบปุ่มเรียบร้อยแล้ว", delete_after=5)

@bot.command()
@commands.has_permissions(administrator=True)
async def test(ctx):
    """ทดสอบคำสั่ง"""
    await ctx.send("✅ บอททำงานปกติ! คำสั่งใช้งานได้", delete_after=10)

# --------------------------------------------------------------------------------------------------
# เริ่มต้นบอท
print("🚀 กำลังเริ่มต้นบอท...")
try:
    server_on()
    bot.run(os.getenv("TOKEN"))
except Exception as e:
    print(f"❌ เกิดข้อผิดพลาดร้ายแรง: {e}")

