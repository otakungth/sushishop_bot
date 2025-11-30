import os
import datetime
import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import re
import asyncio
import json
import traceback

from server import server_on

# ตั้งค่าเรท (ค่าเริ่มต้น)
gamepass_rate = 6
group_rate_low = 4
group_rate_high = 4.5

# ตั้งค่าพื้นฐาน
intents = discord.Intents.all()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.messages = True
intents.dm_messages = True
intents.dm_reactions = True
shop_open = True
group_ticket_enabled = True

# ตั้งค่าห้องหลักและ stock
MAIN_CHANNEL_ID = 1361044752975532152
SALES_LOG_CHANNEL_ID = 1402993077643120720
CREDIT_CHANNEL_ID = 1363250076549382246
gamepass_stock = 30000
group_stock = 0

# เก็บข้อมูลโน้ตส่วนตัว
user_notes = {}

# ระบบติดตามกิจกรรมในตั๋ว
ticket_activity = {}

# ระบบเก็บเลเวลและ EXP
user_data_file = "user_data.json"
ticket_transcripts_file = "ticket_transcripts.json"

# =======================================================================================
# ✅ ฟังก์ชันจัดการไฟล์ข้อมูล
# =======================================================================================

def load_user_data():
    """โหลดข้อมูลผู้ใช้จากไฟล์"""
    try:
        with open(user_data_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการโหลด user_data: {e}")
        return {}

def save_user_data():
    """บันทึกข้อมูลผู้ใช้ลงไฟล์"""
    try:
        with open(user_data_file, 'w', encoding='utf-8') as f:
            json.dump(user_data, f, ensure_ascii=False, indent=2)
        print("💾 บันทึกข้อมูลผู้ใช้เรียบร้อยแล้ว")
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการบันทึก user_data: {e}")

def load_ticket_transcripts():
    """โหลดประวัติตั๋วจากไฟล์"""
    try:
        with open(ticket_transcripts_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการโหลด ticket_transcripts: {e}")
        return {}

def save_ticket_transcripts():
    """บันทึกประวัติตั๋วลงไฟล์"""
    try:
        with open(ticket_transcripts_file, 'w', encoding='utf-8') as f:
            json.dump(ticket_transcripts, f, ensure_ascii=False, indent=2)
        print("💾 บันทึกประวัติตั๋วเรียบร้อยแล้ว")
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการบันทึก ticket_transcripts: {e}")

# =======================================================================================
# ✅ คลาสหลักของบอท - OPTIMIZED FOR USER INSTALL
# =======================================================================================

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
            allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False)
        )

    async def setup_hook(self):
        """ตั้งค่าและ sync คำสั่งสำหรับ User Install (Global DM)"""
        print("🔄 กำลังตั้งค่า slash commands สำหรับ User Install...")
        
        # ✅ โหลดข้อมูลทั้งหมดเมื่อบอทเริ่มทำงาน (ข้อ 1)
        global user_data, ticket_transcripts
        user_data = load_user_data()
        ticket_transcripts = load_ticket_transcripts()
        print(f"✅ โหลดข้อมูลผู้ใช้: {len(user_data)} users")
        print(f"✅ โหลดประวัติตั๋ว: {len(ticket_transcripts)} tickets")
        
        try:
            # Sync commands ไปยัง global scope
            synced = await self.tree.sync()
            print(f"✅ Sync Global Commands เรียบร้อย: {len(synced)} commands")
            
            # แสดงคำสั่งทั้งหมด
            for cmd in synced:
                print(f"   - /{cmd.name} | Global: True")
                
        except Exception as e:
            print(f"❌ เกิดข้อผิดพลาดในการ sync: {e}")

# =======================================================================================
# ✅ สร้าง instance ของบอท
# =======================================================================================
bot = MyBot()

# Custom decorator for User Install commands
def user_install_command(*args, **kwargs):
    """Custom decorator for User Install commands"""
    def decorator(func):
        # Get the original command decorator
        cmd = bot.tree.command(*args, **kwargs)(func)
        
        return cmd
    return decorator

# ตัวแปรเก็บข้อมูล
user_data = {}
ticket_transcripts = {}

# ระดับและ EXP
LEVELS = {
    1: {"exp": 1, "role_id": 1361555369825927249, "role_name": "Level 1"},
    2: {"exp": 5000, "role_id": 1432070662977093703, "role_name": "Level 2"},
    3: {"exp": 10000, "role_id": 1361555364776247297, "role_name": "Level 3"},
    4: {"exp": 20000, "role_id": 1432075600746643537, "role_name": "Level 4"},
    5: {"exp": 50000, "role_id": 1432075369179254804, "role_name": "Level 5"},
    6: {"exp": 100000, "role_id": 1361554929017294949, "role_name": "Level 6"},
    7: {"exp": 250000, "role_id": 1432077732862492722, "role_name": "Level 7"},
    8: {"exp": 500000, "role_id": 1363882685260365894, "role_name": "Level 8"},
    9: {"exp": 1000000, "role_id": 1406309272786047106, "role_name": "Level 9"}
}

print("🔄 กำลังเริ่มต้นบอท...")

# =======================================================================================
# ✅ ระบบนับเครดิต (ข้อ 2)
# =======================================================================================

async def update_credit_channel():
    """อัพเดทชื่อช่องเครดิตตามจำนวนข้อความ"""
    try:
        channel = bot.get_channel(CREDIT_CHANNEL_ID)
        if not channel:
            print("❌ ไม่พบช่องเครดิต")
            return
        
        # นับจำนวนข้อความทั้งหมดในช่อง
        message_count = 0
        async for _ in channel.history(limit=None):
            message_count += 1
        
        # อัพเดทชื่อช่อง
        new_name = f"✅credit : {message_count}"
        if channel.name != new_name:
            await channel.edit(name=new_name)
            print(f"✅ อัพเดทชื่อช่องเครดิตเป็น: {new_name}")
            
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการอัพเดทช่องเครดิต: {e}")

# =======================================================================================
# ✅ ฟังก์ชันบันทึกประวัติแชทในตั๋ว (ข้อ 4, 5)
# =======================================================================================

async def save_ticket_transcript(channel, action_by=None):
    """บันทึกประวัติแชทในตั๋วและส่งไปยัง DM เจ้าของบอท"""
    try:
        # เก็บข้อมูลตั๋ว
        transcript_data = {
            "channel_name": channel.name,
            "channel_id": channel.id,
            "category": channel.category.name if channel.category else "ไม่มีหมวดหมู่",
            "created_at": datetime.datetime.now().isoformat(),
            "closed_by": str(action_by) if action_by else "ระบบอัตโนมัติ",
            "messages": []
        }
        
        # เก็บข้อความทั้งหมดในตั๋ว
        messages = []
        async for message in channel.history(limit=None, oldest_first=True):
            message_data = {
                "timestamp": message.created_at.isoformat(),
                "author": str(message.author),
                "author_id": message.author.id,
                "content": message.content,
                "embeds": [embed.to_dict() for embed in message.embeds],
                "attachments": [att.url for att in message.attachments]
            }
            messages.append(message_data)
        
        transcript_data["messages"] = messages
        
        # บันทึกลงไฟล์
        ticket_transcripts[str(channel.id)] = transcript_data
        save_ticket_transcripts()
        
        # สร้างไฟล์ transcript
        transcript_text = await create_transcript_file(transcript_data)
        
        # ✅ ส่งไปยัง DM เจ้าของบอท (ข้อ 2)
        await send_transcript_to_owner(transcript_data, transcript_text, channel)
        
        print(f"✅ บันทึกประวัติตั๋วเรียบร้อย: {channel.name}")
        return transcript_text
        
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการบันทึกประวัติตั๋ว: {e}")
        return None

async def create_transcript_file(transcript_data):
    """สร้างไฟล์ transcript ในรูปแบบข้อความ"""
    try:
        transcript_lines = []
        transcript_lines.append(f"📝 ประวัติแชทตั๋ว: {transcript_data['channel_name']}")
        transcript_lines.append(f"📂 หมวดหมู่: {transcript_data['category']}")
        transcript_lines.append(f"🆔 ID ตั๋ว: {transcript_data['channel_id']}")
        transcript_lines.append(f"⏰ วันที่บันทึก: {transcript_data['created_at']}")
        transcript_lines.append(f"👤 ปิดโดย: {transcript_data['closed_by']}")
        transcript_lines.append("=" * 50)
        transcript_lines.append("")
        
        for msg in transcript_data["messages"]:
            timestamp = datetime.datetime.fromisoformat(msg["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
            transcript_lines.append(f"[{timestamp}] {msg['author']}: {msg['content']}")
            
            # เพิ่มข้อมูล embed ถ้ามี
            for embed in msg["embeds"]:
                if "title" in embed:
                    transcript_lines.append(f"   [EMBED] {embed['title']}")
                if "description" in embed:
                    transcript_lines.append(f"   [DESC] {embed['description']}")
            
            # เพิ่มข้อมูลไฟล์แนบ
            for att in msg["attachments"]:
                transcript_lines.append(f"   [ATTACHMENT] {att}")
        
        return "\n".join(transcript_lines)
        
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการสร้างไฟล์ transcript: {e}")
        return f"❌ เกิดข้อผิดพลาดในการสร้าง transcript: {e}"

async def send_transcript_to_owner(transcript_data, transcript_text, channel):
    """ส่งประวัติตั๋วไปยัง DM เจ้าของบอท"""
    try:
        # ✅ หา owner (คุณ) - แก้ไข ID ให้ถูกต้อง (ข้อ 2)
        owner_id = 1360990259311018077  # แทนที่ด้วย ID Discord ของคุณ
        owner = await bot.fetch_user(owner_id)
        
        if not owner:
            print("❌ ไม่พบเจ้าของบอท")
            return
        
        # สร้าง embed สรุป
        embed = discord.Embed(
            title=f"📝 ประวัติตั๋ว: {transcript_data['channel_name']}",
            color=0x00FF99,
            timestamp=datetime.datetime.now()
        )
        embed.add_field(name="📂 หมวดหมู่", value=transcript_data['category'], inline=True)
        embed.add_field(name="🆔 ID ตั๋ว", value=transcript_data['channel_id'], inline=True)
        embed.add_field(name="👤 ปิดโดย", value=transcript_data['closed_by'], inline=True)
        embed.add_field(name="💬 จำนวนข้อความ", value=len(transcript_data['messages']), inline=True)
        embed.add_field(name="⏰ วันที่บันทึก", value=transcript_data['created_at'][:19], inline=True)
        
        # ส่ง embed และไฟล์ transcript
        file_content = transcript_text.encode('utf-8')
        transcript_file = discord.File(
            filename=f"transcript_{transcript_data['channel_name']}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            file=file_content
        )
        
        await owner.send(embed=embed, file=transcript_file)
        print(f"✅ ส่งประวัติตั๋วไปยัง DM เจ้าของบอทแล้ว: {transcript_data['channel_name']}")
        
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการส่ง transcript ไปยัง owner: {e}")

# =======================================================================================
# ✅ View สำหรับส่งสินค้า (ข้อ 5)
# =======================================================================================

class DeliveryView(View):
    def __init__(self, channel, product_type, robux_amount, price, buyer):
        super().__init__(timeout=None)
        self.channel = channel
        self.product_type = product_type
        self.robux_amount = robux_amount
        self.price = price
        self.buyer = buyer

    @discord.ui.button(label="ส่งสินค้าแล้ว ✅", style=discord.ButtonStyle.success, emoji="✅")
    async def deliver_product(self, interaction: discord.Interaction, button: Button):
        """ปุ่มส่งสินค้า (เฉพาะแอดมิน)"""
        try:
            # ✅ ตรวจสอบสิทธิ์แอดมิน - แก้ไขให้แอดมินกดได้
            admin_role = interaction.guild.get_role(1361016912259055896)
            if not admin_role or admin_role not in interaction.user.roles:
                await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้ปุ่มนี้", ephemeral=True)
                return

            # ตรวจสอบว่ามีไฟล์รูปภาพในข้อความล่าสุดหรือไม่
            delivery_image = None
            async for message in self.channel.history(limit=10):
                if message.author == interaction.user and message.attachments:
                    for attachment in message.attachments:
                        if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif']):
                            delivery_image = attachment.url
                            break
                    if delivery_image:
                        break

            if not delivery_image:
                await interaction.response.send_message(
                    "❌ ผู้ส่งสินค้าต้องแนบไฟล์หลักฐานการส่งสินค้าก่อน !",
                    ephemeral=True
                )
                return

            # ถามยืนยัน
            confirm_embed = discord.Embed(
                title="📦 ยืนยันการส่งสินค้า",
                description="ยืนยันหลักฐานการส่งสินค้านี้หรือไม่?",
                color=0x00FF00
            )
            confirm_embed.set_image(url=delivery_image)
            
            confirm_view = ConfirmDeliveryView(
                self.channel, self.product_type, self.robux_amount, self.price, 
                self.buyer, delivery_image
            )
            
            await interaction.response.send_message(embed=confirm_embed, view=confirm_view, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

    @discord.ui.button(label="ยกเลิก ❌", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel_order(self, interaction: discord.Interaction, button: Button):
        """ปุ่มยกเลิกคำสั่งซื้อ"""
        try:
            await interaction.response.send_message("❌ คำสั่งซื้อถูกยกเลิก", ephemeral=True)
            await interaction.message.delete()
        except Exception as e:
            await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

class ConfirmDeliveryView(View):
    def __init__(self, channel, product_type, robux_amount, price, buyer, delivery_image):
        super().__init__(timeout=300)
        self.channel = channel
        self.product_type = product_type
        self.robux_amount = robux_amount
        self.price = price
        self.buyer = buyer
        self.delivery_image = delivery_image

    @discord.ui.button(label="ยืนยัน ✅", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm_delivery(self, interaction: discord.Interaction, button: Button):
        """ยืนยันการส่งสินค้า"""
        try:
            # สร้าง embed ใบเสร็จการสั่งซื้อ (ข้อ 4)
            receipt_color = 0xFFA500  # สีส้มสำหรับ Gamepass
            if self.product_type == "Group":
                receipt_color = 0x00FFFF  # สีฟ้าแบบ Cyan
            elif self.product_type == "Limited":
                receipt_color = 0x00FF00  # สีเขียว
            
            receipt_embed = discord.Embed(
                title=f"🍣 ใบเสร็จการสั่งซื้อ ({self.product_type}) 🍣",
                color=receipt_color,
                timestamp=datetime.datetime.now()
            )
            
            receipt_embed.add_field(name="😊 ผู้ซื้อ", value=self.buyer.mention if self.buyer else "ไม่ทราบ", inline=False)
            receipt_embed.add_field(name="💸 จำนวน Robux", value=f"{self.robux_amount:,}", inline=True)
            receipt_embed.add_field(name="💰 ราคาตามเรท", value=f"{self.price:,.0f} บาท", inline=True)
            
            if self.delivery_image:
                receipt_embed.set_image(url=self.delivery_image)
            
            receipt_embed.set_footer(text=f"จัดส่งสินค้าสำเร็จ 🤗 • {datetime.datetime.now().strftime('%d/%m/%y, %H:%M')}")
            
            # ส่งไปยังห้องบันทึกการขาย
            log_channel = bot.get_channel(SALES_LOG_CHANNEL_ID)
            if log_channel:
                await log_channel.send(embed=receipt_embed)
                print(f"✅ บันทึกใบเสร็จการสั่งซื้อในห้องบันทึกการขาย: {self.product_type}")
            
            # ส่งข้อความในตั๋ว
            await self.channel.send(embed=receipt_embed)
            
            # ✅ บันทึกประวัติตั๋วและส่งไปยัง DM (ข้อ 2)
            await save_ticket_transcript(self.channel, interaction.user)
            
            await interaction.response.edit_message(
                content="✅ บันทึกการส่งสินค้าเรียบร้อยและส่งประวัติตั๋วไปยัง DM แล้ว",
                embed=None,
                view=None
            )
            
        except Exception as e:
            await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

    @discord.ui.button(label="แก้ไข ✏️", style=discord.ButtonStyle.secondary, emoji="✏️")
    async def edit_delivery(self, interaction: discord.Interaction, button: Button):
        """แก้ไขหลักฐานการส่งสินค้า"""
        try:
            await interaction.response.send_message(
                "📝 กรุณาแนบไฟล์หลักฐานการส่งสินค้าใหม่ แล้วกดปุ่ม 'ส่งสินค้าแล้ว ✅' อีกครั้ง",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

# =======================================================================================
# ✅ View ต่างๆ
# =======================================================================================

# --------------------------------------------------------------------------------------------------
# ✅ View สำหรับ QR Code (แก้ไขข้อ 3)
class QRView(View):
    def __init__(self):
        super().__init__(timeout=None)
        
    @discord.ui.button(label="คัดลอกเลขบัญชี", style=discord.ButtonStyle.success, emoji="📋")
    async def copy_bank_account(self, interaction: discord.Interaction, button: Button):
        """ปุ่มคัดลอกเลขบัญชี SCB"""
        try:
            bank_info = "120-239181-3 (SCB ชื่อ: หจก. วอเตอร์ เทค เซลล์ แอนด์ เซอร์วิส) **กรุณาโน๊ตชื่อสินค้าที่ซื้อใต้สลิปเพื่อให้ทางร้านเริ่มดำเนินการจัดส่งสินค้า**"
            await interaction.response.send_message(bank_info, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

# --------------------------------------------------------------------------------------------------
# View สำหรับการดำเนินการในตั๋ว (แก้ไขข้อ 3 - ปุ่มปิดตั๋วเฉพาะแอดมิน)
class TicketActionView(View):
    def __init__(self, channel, user, modal_class):
        super().__init__(timeout=None)
        self.channel = channel
        self.user = user
        self.modal_class = modal_class

    @discord.ui.button(label="📝 กรอกแบบฟอร์มใหม่", style=discord.ButtonStyle.primary, emoji="📝")
    async def refill_form(self, interaction: discord.Interaction, button: Button):
        try:
            modal = self.modal_class()
            await interaction.response.send_modal(modal)
        except Exception as e:
            await interaction.response.send_message("❌ เกิดข้อผิดพลาดในการเปิดแบบฟอร์ม", ephemeral=True)

    @discord.ui.button(label="🔒 ปิดตั๋ว", style=discord.ButtonStyle.danger, emoji="🔒")
    async def close_ticket(self, interaction: discord.Interaction, button: Button):
        try:
            # ✅ ตรวจสอบสิทธิ์เฉพาะแอดมิน (ข้อ 3)
            admin_role = interaction.guild.get_role(1361016912259055896)
            if admin_role and admin_role in interaction.user.roles:
                await interaction.response.send_message("📪 กำลังปิดตั๋ว...")
                await asyncio.sleep(2)
                await self.channel.delete()
            else:
                await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ปิดตั๋วนี้", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message("❌ เกิดข้อผิดพลาดในการปิดตั๋ว", ephemeral=True)

# --------------------------------------------------------------------------------------------------
# View สำหรับให้เครดิต (แก้ไขข้อ 5 - บันทึกประวัติเมื่อผู้ใช้กดปิดตั๋ว)
class GiveCreditView(discord.ui.View):
    def __init__(self, channel):
        super().__init__(timeout=None)
        self.channel = channel
        
        # เพิ่มปุ่มให้เครดิต
        self.add_item(
            discord.ui.Button(
                label="ให้เครดิตที่นี่⭐", 
                url="https://discord.com/channels/1360990259311018077/1363250076549382246", 
                style=discord.ButtonStyle.link,
                emoji="⭐"
            )
        )
        
        # ✅ เพิ่มปุ่มปิดตั๋วที่ผู้ใช้ทั่วไปกดได้ (ข้อ 5)
        close_button = Button(
            label="🔒 ปิดตั๋ว", 
            style=discord.ButtonStyle.danger, 
            emoji="🔒",
            custom_id="user_close_ticket"
        )
        close_button.callback = self.user_close_ticket
        self.add_item(close_button)

    async def user_close_ticket(self, interaction: discord.Interaction):
        """ฟังก์ชันปิดตั๋วที่ผู้ใช้ทั่วไปกดได้ (ข้อ 5)"""
        try:
            # ✅ บันทึกประวัติตั๋วก่อนปิด (ข้อ 5)
            await save_ticket_transcript(self.channel, interaction.user)
            
            await interaction.response.send_message("📪 กำลังปิดตั๋ว... ขอบคุณที่ใช้บริการ!")
            await asyncio.sleep(3)
            await self.channel.delete()
            
        except Exception as e:
            await interaction.response.send_message("❌ เกิดข้อผิดพลาดในการปิดตั๋ว", ephemeral=True)

# --------------------------------------------------------------------------------------------------
# Decorator สำหรับตรวจสอบสิทธิ์แอดมิน
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

# --------------------------------------------------------------------------------------------------
# ฟังก์ชันจัดการเลเวลและ EXP (แก้ไขข้อ 2 - บันทึกข้อมูล)
async def add_exp(user_id, exp_amount, guild):
    """เพิ่ม EXP ให้ผู้ใช้และอัพเดทเลเวล"""
    user_id_str = str(user_id)
    
    if user_id_str not in user_data:
        user_data[user_id_str] = {"exp": 0, "level": 0}
    
    user_data[user_id_str]["exp"] += exp_amount
    
    old_level = user_data[user_id_str]["level"]
    
    new_level = 0
    for level, data in sorted(LEVELS.items(), reverse=True):
        if user_data[user_id_str]["exp"] >= data["exp"]:
            new_level = level
            break
    
    user_data[user_id_str]["level"] = new_level
    save_user_data()  # บันทึกข้อมูล
    
    if new_level != old_level:
        await update_user_roles(user_id, guild, old_level, new_level)
    
    return new_level, user_data[user_id_str]["exp"]

async def update_user_roles(user_id, guild, old_level, new_level):
    """อัพเดทยศผู้ใช้ตามเลเวล"""
    try:
        member = guild.get_member(user_id)
        if not member:
            return
        
        if old_level > 0 and old_level in LEVELS:
            old_role_id = LEVELS[old_level]["role_id"]
            old_role = guild.get_role(old_role_id)
            if old_role and old_role in member.roles:
                await member.remove_roles(old_role)
        
        if new_level > 0 and new_level in LEVELS:
            new_role_id = LEVELS[new_level]["role_id"]
            new_role = guild.get_role(new_role_id)
            if new_role and new_role not in member.roles:
                await member.add_roles(new_role)
                print(f"✅ เพิ่มยศ {LEVELS[new_level]['role_name']} ให้ {member.display_name}")
                
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการอัพเดทยศ: {e}")

# --------------------------------------------------------------------------------------------------
# ฟังก์ชันเปลี่ยนชื่อช่องหลัก
async def update_channel_name():
    """เปลี่ยนชื่อช่องหลักตามสถานะร้าน"""
    try:
        channel = bot.get_channel(MAIN_CHANNEL_ID)
        if channel:
            if shop_open:
                new_name = "〔🟢เปิด〕กดสั่งซื้อที่นี่"
            else:
                new_name = "〔🔴〕ปิดชั่วคราว"
            
            if channel.name != new_name:
                await channel.edit(name=new_name)
                print(f"✅ เปลี่ยนชื่อช่องเป็น: {new_name}")
            else:
                print(f"ℹ️ ชื่อช่องเป็นปัจจุบันอยู่แล้ว: {new_name}")
    except discord.Forbidden:
        print("❌ บอทไม่มีสิทธิ์ในการแก้ไขชื่อช่อง")
    except discord.HTTPException as e:
        print(f"❌ เกิดข้อผิดพลาดในการเปลี่ยนชื่อช่อง: {e}")
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดที่ไม่คาดคิด: {e}")

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
            customer_embed.add_field(name="💸 ราคาโรบัค", value=f"{robux:,}", inline=True)
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

    @discord.ui.button(label="❌ ยกเลิกสินค้า", style=discord.ButtonStyle.danger, custom_id="cancel_ticket")
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        try:
            await interaction.response.send_message("❌ คำสั่งซื้อถูกยกเลิกโดยผู้ดูแลระบบ")
            await interaction.message.delete()
        except Exception as e:
            await interaction.response.send_message("❌ เกิดข้อผิดพลาดในการยกเลิก")

# --------------------------------------------------------------------------------------------------
# View สำหรับไปที่ตั๋ว
class GoToTicketView(View):
    def __init__(self, channel):
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(
                label="📩 ไปที่ตั๋ว", 
                url=f"https://discord.com/channels/{channel.guild.id}/{channel.id}", 
                style=discord.ButtonStyle.link
            )
        )

# --------------------------------------------------------------------------------------------------
# ฟังก์ชันจัดการการเปิดตั๋ว
async def handle_open_ticket(interaction, category_name, modal_class, stock_type):
    global gamepass_stock, group_stock
    
    try:
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

        await interaction.response.send_message("🔄 กำลังเปิดตั๋ว...", ephemeral=True)

        channel = await guild.create_text_channel(
            name=channel_name,
            overwrites=overwrites,
            reason="New ticket",
            category=category
        )
        
        ticket_activity[channel.id] = {
            'last_activity': datetime.datetime.now(),
            'ty_used': False
        }
        
        if stock_type == "gamepass":
            gamepass_stock -= 1
        else:
            group_stock -= 1
            
        await interaction.edit_original_response(
            content="📩 เปิดตั๋วเรียบร้อย!",
            view=GoToTicketView(channel)
        )

        if admin_role:
            await channel.send(content=f"{admin_role.mention} มีตั๋วใหม่!")

        welcome_embed = discord.Embed(
            title="🍣 Sushi Shop 🍣",
            color=0x00FF99
        )
        welcome_embed.add_field(
            name="👤 ผู้ซื้อ", 
            value=user.mention, 
            inline=False
        )
        welcome_embed.add_field(
            name="🛠️ ทีมงาน", 
            value=admin_role.mention if admin_role else "รอพนักงานติดต่อ", 
            inline=False
        )
        
        if stock_type == "gamepass":
            welcome_embed.add_field(
                name="บริการกดเกมพาสเรท: 6",
                value=f"📦 Stock: **{gamepass_stock}**",
                inline=False
            )
            welcome_embed.add_field(
                name="คำแนะนำ:",
                value="• ระบุสิ่งที่ต้องการซื้อ\n• ใช้คำสั่ง !gp ตามด้วยจำนวนเพื่อเช็คราคา\nขอบคุณที่ใช้บริการ! 🎉",
                inline=False
            )
        else:
            welcome_embed.add_field(
                name="บริการโรบัคกลุ่ม",
                value=f"📦 Stock: **{group_stock}**",
                inline=False
            )
            welcome_embed.add_field(
                name="คำแนะนำ:",
                value="• ระบุจำนวนที่ต้องการซื้อ\n• รอทีมงานดำเนินการ\nขอบคุณที่ใช้บริการ! 🎉",
                inline=False
            )
            
        welcome_embed.set_footer(text="Sushi Shop บริการรับกดเกมพาส")
        welcome_embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/717757556889747657/1403684950770847754/noFilter.png")

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

# =======================================================================================
# ✅ คำสั่ง !od, !odg, !odl (แก้ไขข้อ 6)
# =======================================================================================

@bot.command()
@admin_only()
async def od(ctx, *, expression: str):
    global gamepass_stock
    
    try:
        if not ctx.channel.name.startswith("ticket-"):
            await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะในตั๋วเท่านั้น", delete_after=5)
            return

        expr = expression.replace(",", "").lower().replace("x", "*").replace("÷", "/")

        if not re.match(r"^[\d\s\+\-\*\/\(\)]+$", expr):
            await ctx.send("❌ กรุณาใส่เฉพาะตัวเลข และเครื่องหมาย + - * / x ÷ ()", delete_after=10)
            return

        robux = int(eval(expr))
        price = robux / gamepass_rate
        price_str = f"{price:,.0f} บาท"

        buyer = None
        channel_name = ctx.channel.name
        if channel_name.startswith("ticket-"):
            parts = channel_name.split('-')
            if len(parts) >= 3:
                user_id = int(parts[-1])
                buyer = ctx.guild.get_member(user_id)
        
        if not buyer:
            async for msg in ctx.channel.history(limit=20):
                if msg.author != ctx.author and not msg.author.bot and msg.author != ctx.guild.me:
                    buyer = msg.author
                    break

        exp_to_add = robux
        if buyer:
            new_level, total_exp = await add_exp(buyer.id, exp_to_add, ctx.guild)
            print(f"✅ เพิ่ม {exp_to_add} EXP ให้ {buyer.display_name} (เลเวล {new_level}, รวม {total_exp} EXP)")
        else:
            print("⚠️ ไม่พบผู้ซื้อในการเพิ่ม EXP")

        gamepass_stock -= robux
        if gamepass_stock < 0:
            gamepass_stock = 0
        
        # ✅ สร้าง Embed คำสั่งซื้อสินค้าใหม่ (ข้อ 6)
        order_embed = discord.Embed(
            title="🍣คำสั่งซื้อสินค้า🍣",
            color=0xFFA500,
            timestamp=datetime.datetime.now()
        )
        order_embed.add_field(name="📦 ประเภทสินค้า", value="Gamepass", inline=False)
        order_embed.add_field(name="💸 จำนวน Robux", value=f"{robux:,}", inline=True)
        order_embed.add_field(name="💰 ราคาตามเรท", value=f"{price:,.0f} บาท", inline=True)
        order_embed.set_footer(text=f"รับออร์เดอร์แล้ว 🤗 • {datetime.datetime.now().strftime('%d/%m/%y, %H:%M')}")
        
        # ✅ ส่ง Embed พร้อมปุ่ม DeliveryView
        delivery_view = DeliveryView(ctx.channel, "Gamepass", robux, price, buyer)
        await ctx.send(embed=order_embed, view=delivery_view)

        # ✅ อัพเดทช่องหลัก (ข้อ 4)
        await update_main_channel()

    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=10)

@bot.command()
@admin_only()
async def odg(ctx, *, expression: str):
    global group_stock
    
    try:
        if not ctx.channel.name.startswith("ticket-"):
            await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะในตั๋วเท่านั้น", delete_after=5)
            return

        expr = expression.replace(",", "").lower().replace("x", "*").replace("÷", "/")

        if not re.match(r"^[\d\s\+\-\*\/\(\)]+$", expr):
            await ctx.send("❌ กรุณาใส่เฉพาะตัวเลข และเครื่องหมาย + - * / x ÷ ()", delete_after=10)
            return

        robux = int(eval(expr))
        rate = group_rate_low if robux < 1500 else group_rate_high
        price = robux / rate
        price_str = f"{price:,.0f} บาท"

        buyer = None
        channel_name = ctx.channel.name
        if channel_name.startswith("ticket-"):
            parts = channel_name.split('-')
            if len(parts) >= 3:
                user_id = int(parts[-1])
                buyer = ctx.guild.get_member(user_id)
        
        if not buyer:
            async for msg in ctx.channel.history(limit=20):
                if msg.author != ctx.author and not msg.author.bot and msg.author != ctx.guild.me:
                    buyer = msg.author
                    break

        exp_to_add = robux
        if buyer:
            new_level, total_exp = await add_exp(buyer.id, exp_to_add, ctx.guild)
            print(f"✅ เพิ่ม {exp_to_add} EXP ให้ {buyer.display_name} (เลเวล {new_level}, รวม {total_exp} EXP)")
        else:
            print("⚠️ ไม่พบผู้ซื้อในการเพิ่ม EXP")

        group_stock -= robux
        if group_stock < 0:
            group_stock = 0
        
        # ✅ สร้าง Embed คำสั่งซื้อสินค้าใหม่ (ข้อ 6)
        order_embed = discord.Embed(
            title="🍣คำสั่งซื้อสินค้า🍣",
            color=0x00FFFF,  # สีฟ้าแบบ Cyan
            timestamp=datetime.datetime.now()
        )
        order_embed.add_field(name="📦 ประเภทสินค้า", value="Group", inline=False)
        order_embed.add_field(name="💸 จำนวน Robux", value=f"{robux:,}", inline=True)
        order_embed.add_field(name="💰 ราคาตามเรท", value=f"{price:,.0f} บาท", inline=True)
        order_embed.set_footer(text=f"รับออร์เดอร์แล้ว 🤗 • {datetime.datetime.now().strftime('%d/%m/%y, %H:%M')}")
        
        # ✅ ส่ง Embed พร้อมปุ่ม DeliveryView
        delivery_view = DeliveryView(ctx.channel, "Group", robux, price, buyer)
        await ctx.send(embed=order_embed, view=delivery_view)

        # ✅ อัพเดทช่องหลัก (ข้อ 4)
        await update_main_channel()

    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=10)

@bot.command()
@admin_only()
async def odl(ctx, item_name: str, value: str):
    try:
        if not ctx.channel.name.startswith("ticket-"):
            await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะในตั๋วเท่านั้น", delete_after=5)
            return

        value_clean = value.replace(",", "")
        
        if not re.match(r"^\d+$", value_clean):
            await ctx.send("❌ กรุณากรอกราคาเป็นตัวเลขที่ถูกต้อง", delete_after=10)
            return

        item_value = int(value_clean)

        buyer = None
        channel_name = ctx.channel.name
        if channel_name.startswith("ticket-"):
            parts = channel_name.split('-')
            if len(parts) >= 3:
                user_id = int(parts[-1])
                buyer = ctx.guild.get_member(user_id)
        
        if not buyer:
            async for msg in ctx.channel.history(limit=20):
                if msg.author != ctx.author and not msg.author.bot and msg.author != ctx.guild.me:
                    buyer = msg.author
                    break

        exp_to_add = item_value
        if buyer:
            new_level, total_exp = await add_exp(buyer.id, exp_to_add, ctx.guild)
            print(f"✅ เพิ่ม {exp_to_add} EXP ให้ {buyer.display_name} (เลเวล {new_level}, รวม {total_exp} EXP)")
        else:
            print("⚠️ ไม่พบผู้ซื้อในการเพิ่ม EXP")

        # ✅ สร้าง Embed คำสั่งซื้อสินค้าใหม่ (ข้อ 6)
        order_embed = discord.Embed(
            title="🍣คำสั่งซื้อสินค้า🍣",
            color=0x00FF00,  # สีเขียว
            timestamp=datetime.datetime.now()
        )
        order_embed.add_field(name="📦 ประเภทสินค้า", value="Limited", inline=False)
        order_embed.add_field(name="🎁 ชื่อไอเทม", value=item_name, inline=True)
        order_embed.add_field(name="💰 ราคา", value=f"{item_value:,} บาท", inline=True)
        order_embed.set_footer(text=f"รับออร์เดอร์แล้ว 🤗 • {datetime.datetime.now().strftime('%d/%m/%y, %H:%M')}")
        
        # ✅ ส่ง Embed พร้อมปุ่ม DeliveryView
        delivery_view = DeliveryView(ctx.channel, "Limited", 0, item_value, buyer)
        await ctx.send(embed=order_embed, view=delivery_view)

    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=10)

# =======================================================================================
# ✅ คำสั่ง !qr (แก้ไขข้อ 3)
# =======================================================================================

@bot.command()
@admin_only()
async def qr(ctx):
    try:
        await ctx.message.delete()
    except:
        pass
    
    # ✅ แก้ไขตามข้อ 3
    embed = discord.Embed(
        title="📱ช่องทางการโอนเงิน ⚠️ต้องโน๊ตใต้สลิประบุชื่อสินค้าที่ซื้อแล้วแจ้งสลิป⚠️",
        color=0x00CCFF
    )
    
    # ✅ เพิ่มข้อมูลบัญชีธนาคาร
    embed.add_field(
        name="1. ชื่อบัญชี", 
        value="**หจก. วอเตอร์ เทค เซลล์ แอนด์ เซอร์วิส**", 
        inline=False
    )
    embed.add_field(
        name="2. เลขบัญชี (SCB)", 
        value="**120-239181-3**", 
        inline=False
    )
    
    # ✅ ใช้ลิงก์รูปภาพใหม่ตามที่ต้องการ (ข้อ 3)
    embed.set_image(url="https://discord.com/channels/1360990259311018077/1361004239043821610/1444373113616728204")
    
    # ✅ ส่ง embed พร้อมปุ่มคัดลอกเลขบัญชี
    qr_view = QRView()
    await ctx.send(embed=embed, view=qr_view)

# =======================================================================================
# ✅ อัพเดทช่องหลัก (แก้ไขข้อ 4, 5)
# =======================================================================================

async def update_main_channel():
    """อัพเดทข้อความในช่องหลักโดยการ edit ข้อความเดิม"""
    try:
        channel = bot.get_channel(MAIN_CHANNEL_ID)
        if not channel:
            print("❌ ไม่พบช่องหลัก")
            return

        target_message = None
        async for msg in channel.history(limit=100):
            if msg.author == bot.user and msg.embeds:
                if msg.embeds and len(msg.embeds) > 0:
                    embed_title = msg.embeds[0].title or ""
                    if "Sushi Shop" in embed_title:
                        target_message = msg
                        break
        
        embed = discord.Embed(
            title="🍣 Sushi Shop 🍣 เปิดให้บริการ",
            color=0xFFA500,
            timestamp=discord.utils.utcnow()
        )
        
        # ✅ แก้ไขรูปแบบตามข้อ 3, 4, 5
        gamepass_status = "🟢" if gamepass_stock > 0 else "🔴"
        group_status = "🟢" if group_stock > 0 else "🔴"
        shop_status = "🟢 เปิด" if shop_open else "🔴 ปิดชั่วคราว"
        
        embed.add_field(
            name=f"🎮 กดเกมพาส | 📊 Stock: {gamepass_stock} {gamepass_status}",
            value=(
                "```\n"
                f"เรท: {gamepass_rate} | โรแท้ยัดกลุ่มได้\n"
                "เช็คราคา: !gp <จำนวน>\n"
                "```"
            ),
            inline=False
        )
        
        embed.add_field(
            name=f"👥 โรบัคกลุ่ม | 📊 Stock: {group_stock} {group_status}", 
            value=(
                "```\n"
                f"เรท: {group_rate_low} | 500+ บาท เรท {group_rate_high}\n"
                "⚠️ต้องเข้ากลุ่ม 15 วันก่อนซื้อ⚠️\n"
                "```"
            ),
            inline=False
        )
        
        # ✅ แก้ไขตามข้อ 5 - รวมสถานะร้านในบรรทัดเดียว
        embed.add_field(
            name="🏪 สถานะร้าน",
            value=f"```\n{shop_status}\n```",
            inline=False
        )
        
        embed.set_footer(
            text="Sushi Shop • รับกดเกมพาสและอื่น ๆ",
            icon_url="https://media.discordapp.net/attachments/717757556889747657/1403684950770847754/noFilter.png"
        )
        
        embed.set_thumbnail(url="https://media.discordapp.net/attachments/717757556889747657/1403684950770847754/noFilter.png")

        if target_message:
            try:
                await target_message.edit(embed=embed, view=MainShopView())
                print(f"✅ อัพเดท embed หลักเรียบร้อยแล้ว (แก้ไขข้อความ ID: {target_message.id})")
            except discord.NotFound:
                print("❌ ไม่พบข้อความเดิม ส่งข้อความใหม่")
                await channel.send(embed=embed, view=MainShopView())
            except Exception as e:
                print(f"❌ ไม่สามารถ edit ข้อความ: {e}")
                await channel.send(embed=embed, view=MainShopView())
        else:
            await channel.send(embed=embed, view=MainShopView())
            print("✅ สร้าง embed หลักใหม่เรียบร้อยแล้ว")
        
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการอัปเดตช่องหลัก: {e}")

# =======================================================================================
# ✅ Main Shop View
# =======================================================================================

class MainShopView(View):
    def __init__(self):
        super().__init__(timeout=None)
        
        gamepass_button = Button(
            label="เปิดตั๋วกดเกมพาส" if shop_open and gamepass_stock > 0 else "สินค้าหมด",
            style=discord.ButtonStyle.success if shop_open and gamepass_stock > 0 else discord.ButtonStyle.danger,
            custom_id="open_gamepass_ticket",
            emoji="🎮",
            disabled=not shop_open or gamepass_stock <= 0
        )
        gamepass_button.callback = self.gamepass_ticket
        self.add_item(gamepass_button)
        
        group_button_label = "เปิดตั๋ว Group"
        if not group_ticket_enabled:
            group_button_label = "บริการปิดชั่วคราว"
        elif group_stock <= 0:
            group_button_label = "สินค้าหมด"
            
        group_button_style = discord.ButtonStyle.success
        if not group_ticket_enabled:
            group_button_style = discord.ButtonStyle.secondary
        elif group_stock <= 0:
            group_button_style = discord.ButtonStyle.danger
            
        group_button = Button(
            label=group_button_label,
            style=group_button_style,
            custom_id="open_group_ticket", 
            emoji="👥",
            disabled=not group_ticket_enabled or group_stock <= 0
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
        
        level_button = Button(
            label="ดูเลเวลของคุณ⭐",
            style=discord.ButtonStyle.primary,
            custom_id="check_level",
            emoji="⭐"
        )
        level_button.callback = self.check_level
        self.add_item(level_button)

    async def gamepass_ticket(self, interaction: discord.Interaction):
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
        try:
            user_note = user_notes.get(str(interaction.user.id))
            modal = PersonalNoteModal()
            
            if user_note:
                modal.note.default = user_note["note"]
                
            await interaction.response.send_modal(modal)
        except Exception as e:
            print(f"❌ ข้อผิดพลาดใน personal_notes: {e}")
            await interaction.response.send_message("❌ เกิดข้อผิดพลาด", ephemeral=True)

    async def check_level(self, interaction: discord.Interaction):
        await check_user_level(interaction)

# =======================================================================================
# ✅ Events (เพิ่มระบบนับเครดิต - ข้อ 2)
# =======================================================================================

@bot.event
async def on_message(message):
    # ✅ ระบบนับเครดิต (ข้อ 2)
    if message.channel.id == CREDIT_CHANNEL_ID and not message.author.bot:
        await update_credit_channel()
    
    # ตรวจสอบว่าเป็น DM และไม่ใช่ข้อความจากบอทตัวเอง
    if isinstance(message.channel, discord.DMChannel) and message.author != bot.user:
        print(f"📨 DM จาก {message.author.name} ({message.author.id}): {message.content}")
        
        # ถ้าผู้ใช้พิมพ์ "/help" ใน DM
        if message.content.lower() in ["/help", "help", "คำสั่ง"]:
            help_embed = discord.Embed(
                title="🍣 Sushi Shop - คำสั่งใน DM",
                description=(
                    "**คำสั่ง Slash Commands ที่ใช้ได้:**\n\n"
                    "`/gamepass <จำนวน>` - คำนวณราคา Gamepass\n"
                    "`/group <จำนวน>` - คำนวณราคา Group\n"
                    "`/baht_gamepass <จำนวน>` - คำนวณ Robux จากเงินบาท\n"
                    "`/baht_group <จำนวน>` - คำนวณ Robux จากเงินบาท (Group)\n"
                    "`/tax <จำนวน>` - คำนวณ Robux หลังหักภาษี\n"
                    "`/help` - แสดงคำสั่งนี้\n\n"
                    "**วิธีการใช้:**\n"
                    "1. พิมพ์ `/` แล้วเลือกคำสั่งที่ต้องการ\n"
                    "2. หรือพิมพ์ `/help` ตรงๆ\n\n"
                    "**หมายเหตุ:**\n"
                    "• การสั่งซื้อจริงต้องทำในเซิร์ฟเวอร์เท่านั้น\n"
                    "• คำสั่งนี้ใช้ได้ใน DM กับเพื่อนทุกคน"
                ),
                color=0x00FF99
            )
            await message.channel.send(embed=help_embed)
            return
    
    # ต่อด้วยโค้ดเดิม...
    if message.author == bot.user:
        return await bot.process_commands(message)
    
    if (message.channel.name.startswith("ticket-") and 
        not message.content.startswith(bot.command_prefix) and
        not message.content.startswith('!')):
        
        ticket_activity[message.channel.id] = {
            'last_activity': datetime.datetime.now(),
            'ty_used': ticket_activity.get(message.channel.id, {}).get('ty_used', False)
        }
    
    await bot.process_commands(message)

@bot.event
async def on_command_completion(ctx):
    if (ctx.channel.name.startswith("ticket-") and 
        ctx.command.name == 'ty'):
        
        ticket_activity[ctx.channel.id] = {
            'last_activity': datetime.datetime.now(),
            'ty_used': True,
            'ty_time': datetime.datetime.now()
        }
        
        await start_auto_close_countdown(ctx.channel)

@bot.event
async def on_ready():
    print(f"✅ บอทออนไลน์แล้ว: {bot.user} (ID: {bot.user.id})")
    print(f"🌍 บอทพร้อมใช้งานใน: เซิร์ฟเวอร์, DM ส่วนตัว, และ Group DMs")
    
    # ✅ โหลดข้อมูลผู้ใช้เมื่อบอทเริ่มทำงาน (ข้อ 1)
    global user_data, ticket_transcripts
    user_data = load_user_data()
    ticket_transcripts = load_ticket_transcripts()
    print(f"✅ โหลดข้อมูลผู้ใช้: {len(user_data)} users")
    print(f"✅ โหลดประวัติตั๋ว: {len(ticket_transcripts)} tickets")
    
    # Sync slash commands สำหรับ User Install
    try:
        print("🔄 กำลัง sync slash commands สำหรับ User Install...")
        
        synced = await bot.tree.sync()
        
        print(f"✅ Sync Global Commands เรียบร้อย: {len(synced)} commands")
        print("📍 คำสั่งเหล่านี้จะแสดงใน:")
        print("   - เซิร์ฟเวอร์ทั้งหมดที่บอทอยู่")
        print("   - DM ส่วนตัวกับเพื่อน")
        print("   - Group DMs")
        print("   - DM กับบอทโดยตรง")
        
        for cmd in synced:
            print(f"   - /{cmd.name} | {cmd.description}")
            
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการ sync: {e}")
    
    # ตั้งค่าสถานะ
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching, 
            name="ร้าน Sushi Shop | พิมพ์ /help"
        )
    )
    
    print("✅ ตั้งค่าสถานะเรียบร้อย")
    
    # ลงทะเบียน Views
    bot.add_view(MainShopView())
    bot.add_view(QRView())
    print("✅ ลงทะเบียน Views เรียบร้อย")
    
    # อัพเดทช่องหลัก
    await update_channel_name()
    
    # เริ่มระบบตรวจสอบตั๋ว
    bot.loop.create_task(check_stale_tickets())
    print("✅ เริ่มระบบตรวจสอบตั๋วค้างเรียบร้อย")
    
    # อัพเดทช่องหลัก
    await update_main_channel()
    
    # ✅ อัพเดทช่องเครดิตเมื่อบอทเริ่มทำงาน (ข้อ 2)
    await update_credit_channel()
    
    print("\n🎯 บอทพร้อมใช้งานเต็มที่!")
    print("📨 ทดสอบใน DM เพื่อนโดย:")
    print("   1. เปิดแชทกับเพื่อน")
    print("   2. พิมพ์ '/' แล้วดูมีคำสั่งหรือไม่")
    print("   3. พิมพ์ '/help' ตรงๆ")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", delete_after=5)
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send("❌ บอทไม่มีสิทธิ์ที่จำเป็น", delete_after=5)
    else:
        print(f"❌ ข้อผิดพลาดคำสั่ง: {error}")
        await ctx.send("❌ เกิดข้อผิดพลาดในการดำเนินการ", delete_after=5)

# =======================================================================================
# ✅ ฟังก์ชันเช็คเลเวลผู้ใช้
# =======================================================================================

async def check_user_level(interaction: discord.Interaction):
    """แสดงเลเวลและ EXP ของผู้ใช้"""
    try:
        user_id = str(interaction.user.id)
        
        if user_id not in user_data:
            user_data[user_id] = {"exp": 0, "level": 0}
            save_user_data()
        
        user_exp = user_data[user_id]["exp"]
        user_level = user_data[user_id]["level"]
        
        if user_level == 0:
            current_display = "Level 0"
        else:
            current_role_id = LEVELS[user_level]["role_id"]
            current_display = f"<@&{current_role_id}>"
        
        if user_level < 9:
            next_level = user_level + 1
            next_level_exp = LEVELS[next_level]["exp"]
            next_role_id = LEVELS[next_level]["role_id"]
            next_display = f"<@&{next_role_id}>"
            exp_needed = next_level_exp - user_exp
        else:
            exp_needed = 0
            next_display = "สูงสุดแล้ว"
        
        embed = discord.Embed(
            title=f"🍣 ระดับของคุณ {interaction.user.display_name}",
            color=0x00FF99
        )
        embed.add_field(name="🎮 ระดับปัจจุบัน", value=current_display, inline=True)
        embed.add_field(name="⭐ EXP สะสม", value=f"**{user_exp:,} EXP**", inline=True)
        
        if user_level < 9:
            embed.add_field(
                name="🎯 ระดับถัดไป", 
                value=f"ต้องการอีก **{exp_needed:,} EXP** เพื่อยศ {next_display}", 
                inline=False
            )
        else:
            embed.add_field(
                name="🏆 สูงสุดแล้ว!", 
                value="คุณถึงระดับสูงสุดแล้ว! 🎉", 
                inline=False
            )
        
        if user_level < 9:
            current_level_exp = LEVELS[user_level]["exp"] if user_level > 0 else 0
            progress = user_exp - current_level_exp
            total_for_level = next_level_exp - current_level_exp
            percentage = (progress / total_for_level) * 100 if total_for_level > 0 else 0
            
            progress_bar = "🟢" * int(percentage / 20) + "⚫" * (5 - int(percentage / 20))
            embed.add_field(
                name="🌱 ความคืบหน้า",
                value=f"{progress_bar} {percentage:.1f}%",
                inline=False
            )
        
        embed.set_footer(text="ได้รับ EXP จากการซื้อสินค้าในร้าน")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการเช็คเลเวล: {e}")
        await interaction.response.send_message("❌ เกิดข้อผิดพลาดในการเช็คเลเวล", ephemeral=True)

# =======================================================================================
# ✅ คำสั่ง !ty (แก้ไขให้ใช้ GiveCreditView ใหม่)
# =======================================================================================

@bot.command()
@admin_only()
async def ty(ctx):
    try:
        await ctx.message.delete()
    except:
        pass
    
    if ctx.channel.name.startswith("ticket-"):
        global gamepass_stock, group_stock
        
        if ctx.channel.category and "gamepass" in ctx.channel.category.name.lower():
            gamepass_stock += 1
        elif ctx.channel.category and "group" in ctx.channel.category.name.lower():
            group_stock += 1

        delivered_category = discord.utils.get(ctx.guild.categories, name="ส่งของแล้ว")
        if delivered_category:
            try:
                await ctx.channel.edit(category=delivered_category)
            except Exception as e:
                print(f"❌ ไม่สามารถย้ายหมวดหมู่: {e}")

        # ✅ ใช้ GiveCreditView ใหม่ที่มีปุ่มปิดตั๋วสำหรับผู้ใช้
        credit_view = GiveCreditView(ctx.channel)
        
        embed = discord.Embed(
            title="✅ สินค้าถูกส่งเรียบร้อยแล้ว",
            description=(
                "ขอบคุณที่ใช้บริการกับเรา หากไม่มีปัญหาเพิ่มเติมสามารถกดปุ่มปิดตั๋วได้เลย\n\n"
                "⏳ หากไม่ได้กดปิดตั๋วเอง ตั๋วจะถูกปิดอัตโนมัติใน 10 นาที"
            ),
            color=0x00FF00
        )
        
        await ctx.send(embed=embed, view=credit_view)

        ticket_activity[ctx.channel.id] = {
            'last_activity': datetime.datetime.now(),
            'ty_used': True,
            'ty_time': datetime.datetime.now()
        }
        
        await start_auto_close_countdown(ctx.channel)
        
    else:
        await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะในตั๋วเท่านั้น", delete_after=5)

# =======================================================================================
# ✅ ระบบติดตามกิจกรรมในตั๋ว (โค้ดเดิม)
# =======================================================================================

async def start_auto_close_countdown(channel):
    print(f"🕐 เริ่มนับถอยหลังปิดตั๋วอัตโนมัติสำหรับ {channel.name} ใน 10 นาที")
    
    await asyncio.sleep(600)
    
    if (channel.id in ticket_activity and 
        ticket_activity[channel.id].get('ty_used', False)):
        
        last_activity = ticket_activity[channel.id]['last_activity']
        time_since_activity = datetime.datetime.now() - last_activity
        
        if time_since_activity.total_seconds() >= 600:
            print(f"⏰ ถึงเวลาปิดตั๋วอัตโนมัติ: {channel.name}")
            await close_ticket_automatically(channel)
        else:
            print(f"✅ ตั๋ว {channel.name} มีกิจกรรมใหม่ ไม่ปิดอัตโนมัติ")
    else:
        print(f"❌ ตั๋ว {channel.name} ไม่ได้ใช้ !ty หรือถูกลบไปแล้ว")

async def close_ticket_automatically(channel):
    try:
        global gamepass_stock, group_stock
        
        if not channel or channel not in channel.guild.channels:
            print(f"❌ ตั๋ว {channel.name} ไม่มีอยู่แล้ว")
            return
        
        if channel.category and "gamepass" in channel.category.name.lower():
            gamepass_stock += 1
            print(f"📦 คืน Gamepass stock: {gamepass_stock}")
        elif channel.category and "group" in channel.category.name.lower():
            group_stock += 1
            print(f"📦 คืน Group stock: {group_stock}")
        
        embed = discord.Embed(
            title="⏰ ปิดตั๋วอัตโนมัติ",
            description="ตั๋วถูกปิดอัตโนมัติเนื่องจากไม่มีกิจกรรมใน 10 นาทีหลังจากส่งสินค้าเรียบร้อย",
            color=0xFFA500
        )
        await channel.send(embed=embed)
        
        print(f"🔔 ส่งข้อความแจ้งปิดตั๋วอัตโนมัติใน {channel.name}")
        
        await asyncio.sleep(5)
        
        try:
            await channel.delete()
            print(f"✅ ลบตั๋วอัตโนมัติเรียบร้อย: {channel.name}")
        except discord.NotFound:
            print(f"❌ ตั๋ว {channel.name} ถูกลบไปแล้ว")
        except Exception as e:
            print(f"❌ เกิดข้อผิดพลาดในการลบตั๋ว: {e}")
        
        if channel.id in ticket_activity:
            del ticket_activity[channel.id]
            print(f"🗑️ ลบ {channel.name} ออกจาก tracking")
            
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการปิดตั๋วอัตโนมัติ: {e}")

async def check_stale_tickets():
    while True:
        await asyncio.sleep(300)
        
        current_time = datetime.datetime.now()
        channels_to_remove = []
        
        for channel_id, activity_data in ticket_activity.items():
            if activity_data.get('ty_used', False):
                last_activity = activity_data['last_activity']
                time_since_activity = current_time - last_activity
                
                if time_since_activity.total_seconds() >= 600:
                    channel = bot.get_channel(channel_id)
                    if channel:
                        print(f"🔍 พบตั๋วค้าง: {channel.name} (ผ่านไป {time_since_activity.total_seconds()/60:.1f} นาที)")
                        await close_ticket_automatically(channel)
                    channels_to_remove.append(channel_id)
        
        for channel_id in channels_to_remove:
            if channel_id in ticket_activity:
                del ticket_activity[channel_id]

# =======================================================================================
# ✅ คำสั่งอื่นๆ ที่เหลือ (ให้คงเดิม)
# =======================================================================================

# --------------------------------------------------------------------------------------------------
# ฟังก์ชันเช็คเลเวลผู้ใช้ (สำหรับคำสั่ง)
async def check_user_level_as_command(ctx, member):
    """แสดงเลเวลและ EXP ของผู้ใช้ (สำหรับคำสั่ง)"""
    try:
        user_id = str(member.id)
        
        if user_id not in user_data:
            user_data[user_id] = {"exp": 0, "level": 0}
            save_user_data()
        
        user_exp = user_data[user_id]["exp"]
        user_level = user_data[user_id]["level"]
        
        if user_level == 0:
            current_display = "Level 0"
        else:
            current_role_id = LEVELS[user_level]["role_id"]
            current_display = f"<@&{current_role_id}>"
        
        if user_level < 9:
            next_level = user_level + 1
            next_level_exp = LEVELS[next_level]["exp"]
            next_role_id = LEVELS[next_level]["role_id"]
            next_display = f"<@&{next_role_id}>"
            exp_needed = next_level_exp - user_exp
        else:
            exp_needed = 0
            next_display = "สูงสุดแล้ว"
        
        embed = discord.Embed(
            title=f"🍣 ระดับของคุณ {member.display_name}",
            color=0x00FF99
        )
        embed.add_field(name="🎮 ระดับปัจจุบัน", value=current_display, inline=True)
        embed.add_field(name="⭐ EXP สะสม", value=f"**{user_exp:,} EXP**", inline=True)
        
        if user_level < 9:
            embed.add_field(
                name="🎯 ระดับถัดไป", 
                value=f"ต้องการอีก **{exp_needed:,} EXP** เพื่อยศ {next_display}", 
                inline=False
            )
        else:
            embed.add_field(
                name="🏆 สูงสุดแล้ว!", 
                value="คุณถึงระดับสูงสุดแล้ว! 🎉", 
                inline=False
            )
        
        if user_level < 9:
            current_level_exp = LEVELS[user_level]["exp"] if user_level > 0 else 0
            progress = user_exp - current_level_exp
            total_for_level = next_level_exp - current_level_exp
            percentage = (progress / total_for_level) * 100 if total_for_level > 0 else 0
            
            progress_bar = "🟢" * int(percentage / 20) + "⚫" * (5 - int(percentage / 20))
            embed.add_field(
                name="🌱 ความคืบหน้า",
                value=f"{progress_bar} {percentage:.1f}%",
                inline=False
            )
        
        embed.set_footer(text="ได้รับ EXP จากการซื้อสินค้าในร้าน")
        await ctx.send(embed=embed)
        
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการเช็คเลเวล: {e}")
        await ctx.send("❌ เกิดข้อผิดพลาดในการเช็คเลเวล")

# --------------------------------------------------------------------------------------------------
# ฟังก์ชันตรวจสอบ EXP (สำหรับ debug)
@bot.command()
@admin_only()
async def check_exp(ctx, member: discord.Member = None):
    """ตรวจสอบ EXP ของผู้ใช้ (สำหรับ debug)"""
    if member is None:
        member = ctx.author
    
    user_id = str(member.id)
    
    if user_id not in user_data:
        user_data[user_id] = {"exp": 0, "level": 0}
        save_user_data()
    
    user_exp = user_data[user_id]["exp"]
    user_level = user_data[user_id]["level"]
    
    embed = discord.Embed(
        title=f"🔍 ตรวจสอบ EXP - {member.display_name}",
        color=0xFFA500
    )
    embed.add_field(name="🆔 User ID", value=user_id, inline=True)
    embed.add_field(name="🎮 Level", value=user_level, inline=True)
    embed.add_field(name="⭐ EXP", value=f"{user_exp:,}", inline=True)
    embed.add_field(name="📊 Data", value=f"```json\n{json.dumps(user_data[user_id], indent=2, ensure_ascii=False)}\n```", inline=False)
    
    await ctx.send(embed=embed)

# --------------------------------------------------------------------------------------------------
# ฟังก์ชันรีเซ็ต EXP (สำหรับ debug)
@bot.command()
@admin_only()
async def reset_exp(ctx, member: discord.Member = None):
    """รีเซ็ต EXP ของผู้ใช้ (สำหรับ debug)"""
    if member is None:
        member = ctx.author
    
    user_id = str(member.id)
    
    user_data[user_id] = {"exp": 0, "level": 0}
    save_user_data()
    
    embed = discord.Embed(
        title="✅ รีเซ็ต EXP เรียบร้อย",
        description=f"รีเซ็ต EXP ของ {member.mention} เรียบร้อยแล้ว",
        color=0x00FF00
    )
    embed.add_field(name="🆔 User ID", value=user_id, inline=True)
    embed.add_field(name="🎮 Level", value="0", inline=True)
    embed.add_field(name="⭐ EXP", value="0", inline=True)
    
    await ctx.send(embed=embed)

# --------------------------------------------------------------------------------------------------
# คำสั่งพื้นฐาน
@bot.command(name='help')
async def help_command(ctx):
    help_embed = discord.Embed(
        title="🍣 Sushi Shop - คำสั่งทั้งหมด",
        description="**คำสั่ง Text Commands (ใช้ ! ในเซิร์ฟเวอร์):**\n"
                   "`!gp <จำนวน>` - คำนวณราคา Gamepass\n"
                   "`!g <จำนวน>` - คำนวณราคา Group\n"
                   "`!gpb <จำนวน>` - คำนวณ Robux จากเงิน (Gamepass)\n"
                   "`!gb <จำนวน>` - คำนวณ Robux จากเงิน (Group)\n"
                   "`!tax <จำนวน>` - คำนวณ Robux หลังหักภาษี\n\n"
                   "**คำสั่ง Slash Commands (ใช้ / ได้ทั้งเซิร์ฟเวอร์และ DM):**\n"
                   "`/gamepass <จำนวน>` - คำนวณราคา Gamepass\n"
                   "`/group <จำนวน>` - คำนวณราคา Group\n"
                   "`/baht_gamepass <จำนวน>` - คำนวณ Robux จากเงิน (Gamepass)\n"
                   "`/baht_group <จำนวน>` - คำนวณ Robux จากเงิน (Group)\n"
                   "`/tax <จำนวน>` - คำนวณ Robux หลังหักภาษี\n"
                   "**คำสั่งทั่วไป:**\n"
                   "`!level` - เช็คเลเวลและ EXP ของคุณ\n"
                   "`!rate <rate>` - เปลี่ยนเรท Gamepass\n"
                   "`!rate group <low> <high>` - เปลี่ยนเรท Group\n"
                   "**คำสั่งผู้ดูแลระบบเท่านั้น:**\n"
                   "`!stock` - ตรวจสอบ stock\n"
                   "`!sushi` - เปิด/ปิดร้าน\n"
                   "`!group <on/off>` - เปิด/ปิด Group ticket\n"
                   "`!ty` - ส่งของเรียบร้อย (ใช้ในตั๋ว)\n"
                   "`!qr` - แสดง QR Code\n"
                   "`!setup` - ตั้งค่าระบบใหม่\n"
                   "`!restart` - รีสตาร์ทระบบปุ่ม\n"
                   "`!od <จำนวน>` - สั่งซื้อ Gamepass\n"
                   "`!odg <จำนวน>` - สั่งซื้อ Group\n"
                   "`!odl <ชื่อไอเทม> <จำนวน>` - สั่งซื้อ Limited\n"
                   "`!love` - แสดงความรักจากเซิร์ฟ",
        color=0x00FF99
    )
    await ctx.send(embed=help_embed, delete_after=30)

# --------------------------------------------------------------------------------------------------
# คำสั่งจัดการ Stock (แก้ไขข้อ 4)
@bot.command()
@admin_only()
async def stock(ctx, stock_type: str = None, amount: str = None):
    global gamepass_stock, group_stock
    
    try:
        await ctx.message.delete()
    except:
        pass
    
    if stock_type is None:
        embed = discord.Embed(
            title="📊 สต๊อกสินค้า",
            color=0x00FF99,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(
            name="🎮 Gamepass Stock", 
            value=f"**{gamepass_stock:,}**", 
            inline=True
        )
        embed.add_field(
            name="👥 Group Stock", 
            value=f"**{group_stock:,}**", 
            inline=True
        )
        response_msg = await ctx.send(embed=embed)
        await asyncio.sleep(10)
        try:
            await response_msg.delete()
        except:
            pass
        
    elif stock_type.lower() in ["gp", "gamepass", "เกมพาส"]:
        if amount is None:
            embed = discord.Embed(
                title="🎮 Gamepass Stock",
                description=f"**{gamepass_stock:,}**",
                color=0x00FF99
            )
            response_msg = await ctx.send(embed=embed)
            await asyncio.sleep(10)
            try:
                await response_msg.delete()
            except:
                pass
        else:
            amount_clean = amount.replace(",", "")
            try:
                amount_int = int(amount_clean)
                if amount_int < 0:
                    error_msg = await ctx.send("❌ จำนวน stock ต้องมากกว่าหรือเท่ากับ 0")
                    await asyncio.sleep(5)
                    try:
                        await error_msg.delete()
                    except:
                        pass
                    return
                
                gamepass_stock = amount_int
                
                embed = discord.Embed(
                    title="✅ ตั้งค่า Stock เรียบร้อย",
                    description=f"ตั้งค่า สต๊อกเกมพาส เป็น **{gamepass_stock:,}** เรียบร้อยแล้ว",
                    color=0x00FF00
                )
                
                response_msg = await ctx.send(embed=embed)
                
                # ✅ อัพเดทช่องหลัก (ข้อ 4)
                await update_main_channel()
                
                await asyncio.sleep(5)
                try:
                    await response_msg.delete()
                except:
                    pass
                    
            except ValueError:
                error_msg = await ctx.send("❌ กรุณากรอกจำนวน stock เป็นตัวเลขที่ถูกต้อง")
                await asyncio.sleep(5)
                try:
                    await error_msg.delete()
                except:
                    pass
    
    elif stock_type.lower() in ["g", "group", "กรุ๊ป"]:
        if amount is None:
            embed = discord.Embed(
                title="👥 Group Stock",
                description=f"**{group_stock:,}**",
                color=0x00FF99
            )
            response_msg = await ctx.send(embed=embed)
            await asyncio.sleep(10)
            try:
                await response_msg.delete()
            except:
                pass
        else:
            amount_clean = amount.replace(",", "")
            try:
                amount_int = int(amount_clean)
                if amount_int < 0:
                    error_msg = await ctx.send("❌ จำนวน stock ต้องมากกว่าหรือเท่ากับ 0")
                    await asyncio.sleep(5)
                    try:
                        await error_msg.delete()
                    except:
                        pass
                    return
                
                group_stock = amount_int
                
                embed = discord.Embed(
                    title="✅ ตั้งค่า Stock เรียบร้อย",
                    description=f"ตั้งค่า สต๊อกโรบัคกลุ่ม เป็น **{group_stock:,}** เรียบร้อยแล้ว",
                    color=0x00FF00
                )
                
                response_msg = await ctx.send(embed=embed)
                
                # ✅ อัพเดทช่องหลัก (ข้อ 4)
                await update_main_channel()
                
                await asyncio.sleep(5)
                try:
                    await response_msg.delete()
                except:
                    pass
                    
            except ValueError:
                error_msg = await ctx.send("❌ กรุณากรอกจำนวน stock เป็นตัวเลขที่ถูกต้อง")
                await asyncio.sleep(5)
                try:
                    await error_msg.delete()
                except:
                    pass
    
    else:
        embed = discord.Embed(
            title="❌ การใช้งานไม่ถูกต้อง",
            description=(
                "**การใช้งาน:**\n"
                "`!stock` - เช็ค stock ทั้งหมด\n"
                "`!stock gp <จำนวน>` - ตั้งค่า Gamepass stock\n" 
                "`!stock group <จำนวน>` - ตั้งค่า Group stock"
            ),
            color=0xFF0000
        )
        response_msg = await ctx.send(embed=embed)
        await asyncio.sleep(10)
        try:
            await response_msg.delete()
        except:
            pass

# --------------------------------------------------------------------------------------------------
# คำสั่งเปลี่ยนเรท
@bot.command()
@admin_only()
async def rate(ctx, rate_type: str = None, low_rate: str = None, high_rate: str = None):
    """คำสั่งเปลี่ยนเรท Gamepass หรือ Group"""
    global gamepass_rate, group_rate_low, group_rate_high
    
    try:
        await ctx.message.delete()
    except:
        pass
    
    if rate_type is None:
        embed = discord.Embed(
            title="📊 อัตราแลกเปลี่ยนปัจจุบัน",
            color=0x00FF99,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(
            name="🎮 Gamepass Rate", 
            value=f"**{gamepass_rate}**", 
            inline=True
        )
        embed.add_field(
            name="👥 Group Rate", 
            value=f"**{group_rate_low} - {group_rate_high}**", 
            inline=True
        )
        embed.set_footer(text="ใช้ !rate <rate> หรือ !rate group <low> <high> เพื่อเปลี่ยนเรท")
        response_msg = await ctx.send(embed=embed)
        await asyncio.sleep(10)
        try:
            await response_msg.delete()
        except:
            pass
        
    elif rate_type.lower() == "group":
        if low_rate is None or high_rate is None:
            embed = discord.Embed(
                title="❌ การใช้งานไม่ถูกต้อง",
                description="**การใช้งาน:** `!rate group <low_rate> <high_rate>`",
                color=0xFF0000
            )
            response_msg = await ctx.send(embed=embed)
            await asyncio.sleep(10)
            try:
                await response_msg.delete()
            except:
                pass
            return
        
        try:
            new_low = float(low_rate)
            new_high = float(high_rate)
            
            if new_low <= 0 or new_high <= 0:
                error_msg = await ctx.send("❌ เรทต้องมากกว่า 0")
                await asyncio.sleep(5)
                try:
                    await error_msg.delete()
                except:
                    pass
                return
            
            group_rate_low = new_low
            group_rate_high = new_high
            
            embed = discord.Embed(
                title="✅ เปลี่ยนเรท Group เรียบร้อย",
                description=f"ตั้งค่าเรท Group เป็น **{group_rate_low} - {group_rate_high}** เรียบร้อยแล้ว",
                color=0x00FF00
            )
            response_msg = await ctx.send(embed=embed)
            
            await update_main_channel()
            
            await asyncio.sleep(5)
            try:
                await response_msg.delete()
            except:
                pass
                
        except ValueError:
            error_msg = await ctx.send("❌ กรุณากรอกเรทเป็นตัวเลขที่ถูกต้อง")
            await asyncio.sleep(5)
            try:
                await error_msg.delete()
            except:
                pass
    
    else:
        try:
            new_rate = float(rate_type)
            
            if new_rate <= 0:
                error_msg = await ctx.send("❌ เรทต้องมากกว่า 0")
                await asyncio.sleep(5)
                try:
                    await error_msg.delete()
                except:
                    pass
                return
            
            gamepass_rate = new_rate
            
            embed = discord.Embed(
                title="✅ เปลี่ยนเรท Gamepass เรียบร้อย",
                description=f"ตั้งค่าเรท Gamepass เป็น **{gamepass_rate}** เรียบร้อยแล้ว",
                color=0x00FF00
            )
            response_msg = await ctx.send(embed=embed)
            
            await update_main_channel()
            
            await asyncio.sleep(5)
            try:
                await response_msg.delete()
            except:
                pass
                
        except ValueError:
            embed = discord.Embed(
                title="❌ การใช้งานไม่ถูกต้อง",
                description=(
                    "**การใช้งาน:**\n"
                    "`!rate <rate>` - เปลี่ยนเรท Gamepass\n"
                    "`!rate group <low> <high>` - เปลี่ยนเรท Group"
                ),
                color=0xFF0000
            )
            response_msg = await ctx.send(embed=embed)
            await asyncio.sleep(10)
            try:
                await response_msg.delete()
            except:
                pass

# --------------------------------------------------------------------------------------------------
# คำสั่งเปิดปิดร้าน
@bot.command()
@admin_only()
async def sushi(ctx):
    global shop_open
    shop_open = not shop_open

    try:
        await ctx.message.delete()
    except:
        pass

    status = "✅ ร้านเปิด" if shop_open else "❌ ร้านปิด"
    embed = discord.Embed(
        title="🏪 สถานะร้าน",
        description=f"**{status}**",
        color=0x00FF00 if shop_open else 0xFF0000
    )
    
    status_msg = await ctx.send(embed=embed)
    
    await update_channel_name()
    
    await update_main_channel()
    
    await asyncio.sleep(3)
    try:
        await status_msg.delete()
        print("✅ ลบข้อความสถานะร้านเรียบร้อยแล้ว")
    except:
        print("❌ ไม่สามารถลบข้อความสถานะร้าน")

# --------------------------------------------------------------------------------------------------
# คำสั่งเปิดปิด Group Ticket
@bot.command()
@admin_only()
async def group(ctx, status: str = None):
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
        await ctx.send(embed=embed)
    elif status.lower() in ["on", "enable", "เปิด"]:
        group_ticket_enabled = True
        embed = discord.Embed(
            title="✅ เปิดปุ่ม Group Ticket",
            description="เปิดปุ่ม Group Ticket เรียบร้อยแล้ว",
            color=0x00FF00
        )
        await ctx.send(embed=embed)
    elif status.lower() in ["off", "disable", "ปิด"]:
        group_ticket_enabled = False
        embed = discord.Embed(
            title="❌ ปิดปุ่ม Group Ticket",
            description="ปิดปุ่ม Group Ticket เรียบร้อยแล้ว",
            color=0xFF0000
        )
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="❌ การใช้งานไม่ถูกต้อง",
            description="**การใช้งาน:** !group [on/off] หรือ !group [enable/disable] หรือ !group [เปิด/ปิด]",
            color=0xFF0000
        )
        await ctx.send(embed=embed)
    
    await update_main_channel()

# --------------------------------------------------------------------------------------------------
# คำสั่ง !level
@bot.command()
async def level(ctx, member: discord.Member = None):
    if member is None:
        member = ctx.author
    
    await check_user_level_as_command(ctx, member)

# --------------------------------------------------------------------------------------------------
# คำสั่งอื่นๆ
@bot.command()
async def love(ctx):
    await ctx.send("# LOVE YOU<:sushiheart:1410484970291466300>")

@bot.command()
async def say(ctx, *, message: str):
    formatted_message = f"# {message.upper()} <:sushiheart:1410484970291466300>"
    await ctx.send(formatted_message)

@bot.command()
@admin_only()
async def setup(ctx):
    try:
        await ctx.message.delete()
    except:
        pass
    
    embed = discord.Embed(
        title="✅ ตั้งค่าระบบเรียบร้อยแล้ว",
        color=0x00FF00
    )
    await ctx.send(embed=embed)
    await update_main_channel()

@bot.command()
@admin_only()
async def restart(ctx):
    try:
        await ctx.message.delete()
    except:
        pass
    
    await update_main_channel()
    embed = discord.Embed(
        title="🔄 รีสตาร์ทระบบปุ่มเรียบร้อยแล้ว",
        color=0x00FF00
    )
    await ctx.send(embed=embed)

@bot.command()
@admin_only()
async def sync(ctx):
    """Sync slash commands (สำหรับแอดมิน)"""
    try:
        synced = await bot.tree.sync()
        await ctx.send(f"✅ Sync Slash Commands เรียบร้อย: {len(synced)} commands", delete_after=10)
    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=10)

@bot.command()
@admin_only()
async def test(ctx):
    embed = discord.Embed(
        title="✅ บอททำงานปกติ!",
        description="คำสั่งใช้งานได้",
        color=0x00FF00
    )
    await ctx.send(embed=embed, delete_after=10)

# --------------------------------------------------------------------------------------------------
# คำสั่งสำหรับตรวจสอบ DM
@bot.command()
@admin_only()
async def test_dm(ctx, user_id: str = None):
    """ทดสอบส่งข้อความไปยัง DM (สำหรับแอดมิน)"""
    try:
        if user_id is None:
            user = ctx.author
        else:
            user = await bot.fetch_user(int(user_id))
        
        try:
            embed = discord.Embed(
                title="🍣 ทดสอบ DM จาก Sushi Shop",
                description=(
                    "นี่คือข้อความทดสอบจากบอท!\n\n"
                    "**ถ้าคุณเห็นข้อความนี้ แสดงว่าบอทส่ง DM ได้ปกติ**\n"
                    "แต่ Slash Commands อาจยังไม่แสดงเพราะระบบ Discord กำลังโหลด\n\n"
                    "**วิธีใช้ชั่วคราว:**\n"
                    "• พิมพ์ `/help` ตรงๆ โดยไม่ต้องเลือกจากเมนู\n"
                    "• พิมพ์ `help` เพื่อดูคำสั่งด่วน\n"
                    "• รอ 1-2 ชั่วโมงสำหรับระบบเต็มรูปแบบ"
                ),
                color=0x00FF99
            )
            
            await user.send(embed=embed)
            await ctx.send(f"✅ ส่งข้อความทดสอบไปยัง {user.mention} เรียบร้อยแล้ว", delete_after=10)
            
        except discord.Forbidden:
            await ctx.send(f"❌ ไม่สามารถส่ง DM ไปยัง {user.mention} (ผู้ใช้ปิดรับ DM)", delete_after=10)
            
    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=10)

# --------------------------------------------------------------------------------------------------
# คำสั่งสำหรับ User Install Test
@bot.command()
@commands.is_owner()
async def user_install_test(ctx):
    """ทดสอบการตั้งค่า User Install (สำหรับเจ้าของบอทเท่านั้น)"""
    embed = discord.Embed(
        title="🧪 ทดสอบ User Install",
        description=(
            "**สถานะการตั้งค่า:**\n\n"
            "✅ บอทพร้อมใช้งานใน:\n"
            "• เซิร์ฟเวอร์ทั้งหมด\n"
            "• DM ส่วนตัวกับเพื่อน\n"
            "• Group DMs\n"
            "• DM กับบอทโดยตรง\n\n"
            "**วิธีการทดสอบ:**\n"
            "1. เปิดแชทกับเพื่อน\n"
            "2. พิมพ์ `/` แล้วดูคำสั่ง\n"
            "3. ถ้าไม่เห็น ให้พิมพ์ `/help` ตรงๆ\n\n"
            "**หมายเหตุ:**\n"
            "• อาจใช้เวลา 1-2 ชั่วโมงในการโหลดคำสั่ง\n"
            "• บอทต้องมีสิทธิ์ 'Application Commands'"
        ),
        color=0x00FF99
    )
    await ctx.send(embed=embed)

@bot.command()
@commands.is_owner()
async def force_sync(ctx):
    """บังคับ sync คำสั่งใหม่ (สำหรับเจ้าของบอทเท่านั้น)"""
    try:
        synced = await bot.tree.sync()
        await ctx.send(f"✅ Force Sync เรียบร้อย: {len(synced)} commands", delete_after=10)
        
        command_list = "\n".join([f"• `/{cmd.name}` - {cmd.description}" for cmd in synced])
        embed = discord.Embed(
            title="📋 คำสั่งทั้งหมด",
            description=command_list,
            color=0x00FF00
        )
        await ctx.send(embed=embed, delete_after=30)
        
    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=10)

# =======================================================================================
# ✅ SLASH COMMANDS - OPTIMIZED FOR USER INSTALL (GLOBAL DM)
# =======================================================================================

@bot.tree.command(name="gamepass", description="คำนวณราคา Gamepass")
async def gamepass_cmd(interaction: discord.Interaction, amount: str):
    """คำสั่งคำนวณราคา Gamepass - ใช้ได้ใน DM ทุกที่"""
    try:
        expr = amount.replace(",", "").replace(" ", "").lower().replace("x", "*").replace("÷", "/")

        if not re.match(r"^[\d\s\+\-\*\/\(\)\.]+$", expr):
            await interaction.response.send_message("❌ กรุณาใส่เฉพาะตัวเลข และเครื่องหมาย + - * / x ÷ ()", ephemeral=False)
            return

        robux = int(eval(expr))
        price = robux / gamepass_rate
        price_str = f"{price:,.0f} บาท"

        response_msg = f"🎮 Gamepass {robux:,} Robux = **{price_str}** (เรท {gamepass_rate})"
        await interaction.response.send_message(response_msg, ephemeral=False)

    except Exception as e:
        await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=False)

@bot.tree.command(name="group", description="คำนวณราคา Group")
async def group_cmd(interaction: discord.Interaction, amount: str):
    """คำสั่งคำนวณราคา Group - ใช้ได้ใน DM ทุกที่"""
    try:
        expr = amount.replace(",", "").replace(" ", "").lower().replace("x", "*").replace("÷", "/")

        if not re.match(r"^[\d\s\+\-\*\/\(\)\.]+$", expr):
            await interaction.response.send_message("❌ กรุณาใส่เฉพาะตัวเลข และเครื่องหมาย + - * / x ÷ ()", ephemeral=False)
            return

        robux = int(eval(expr))

        if robux < 2250:
            rate = group_rate_low
        else:
            rate = group_rate_high

        price = robux / rate
        price_str = f"{price:,.0f} บาท"

        response_msg = f"👥 Group {robux:,} Robux = **{price_str}** (เรท {rate})"
        await interaction.response.send_message(response_msg, ephemeral=False)

    except Exception as e:
        await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=False)

@bot.tree.command(name="baht_gamepass", description="คำนวณ Robux จากเงินบาท")
async def baht_gamepass_cmd(interaction: discord.Interaction, amount: str):
    """คำสั่งคำนวณ Robux จากเงินบาท - ใช้ได้ใน DM ทุกที่"""
    try:
        expr = amount.replace(",", "").replace(" ", "").lower().replace("x", "*").replace("÷", "/")

        if not re.match(r"^[\d\s\+\-\*\/\(\)\.]+$", expr):
            await interaction.response.send_message("❌ กรุณาใส่เฉพาะตัวเลข และเครื่องหมาย + - * / x ÷ ()", ephemeral=False)
            return

        baht = eval(expr)
        robux = baht * gamepass_rate

        response_msg = f"🎮 {baht:,.0f} บาท = **{robux:,.0f} Robux** (Gamepass เรท {gamepass_rate})"
        await interaction.response.send_message(response_msg, ephemeral=False)

    except Exception as e:
        await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=False)

@bot.tree.command(name="baht_group", description="คำนวณเงินบาทเป็น Robux")
async def baht_group_cmd(interaction: discord.Interaction, amount: str):
    """คำสั่งคำนวณเงินบาทเป็น Robux - ใช้ได้ใน DM ทุกที่"""
    try:
        expr = amount.replace(",", "").replace(" ", "").lower().replace("x", "*").replace("÷", "/")

        if not re.match(r"^[\d\s\+\-\*\/\(\)\.]+$", expr):
            await interaction.response.send_message("❌ กรุณาใส่เฉพาะตัวเลข และเครื่องหมาย + - * / x ÷ ()", ephemeral=False)
            return

        baht = eval(expr)

        if baht < 500:
            rate = group_rate_low
        else:
            rate = group_rate_high

        robux = baht * rate

        response_msg = f"👥 {baht:,.0f} บาท = **{robux:,.0f} Robux** (Group เรท {rate})"
        await interaction.response.send_message(response_msg, ephemeral=False)

    except Exception as e:
        await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=False)

@bot.tree.command(name="tax", description="คำนวณ Robux หลังหัก 30%")
async def tax_cmd(interaction: discord.Interaction, amount: str):
    """คำสั่งคำนวณ Robux หลังหัก 30% - ใช้ได้ใน DM ทุกที่"""
    try:
        expr = amount.replace(" ", "")
        
        if re.match(r"^\d+$", expr):
            number = int(expr)
            result = number * 0.7
            response_msg = f"💰 {number:,} Robux หลังหัก 30% = **{result:,.0f} Robux**"
            
        elif re.match(r"^\d+-\d+%$", expr):
            parts = expr.split('-')
            number = int(parts[0])
            percent = int(parts[1].replace('%', ''))
            
            if percent < 0 or percent > 100:
                await interaction.response.send_message("❌ เปอร์เซ็นต์ต้องอยู่ระหว่าง 0-100%", ephemeral=False)
                return
            
            result = number * (1 - percent/100)
            response_msg = f"💰 {number:,} Robux หลังหัก {percent}% = **{result:,.0f} Robux**"
            
        else:
            response_msg = (
                "❌ รูปแบบไม่ถูกต้อง\n\n"
                "**การใช้งาน:**\n"
                "`/tax 100` - หัก 30% อัตโนมัติ\n"
                "`/tax 100-30%` - หัก 30%\n"
                "`/tax 100-50%` - หัก 50%"
            )

        await interaction.response.send_message(response_msg, ephemeral=False)

    except Exception as e:
        await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=False)

@bot.tree.command(name="help", description="แสดงคำสั่งทั้งหมดที่ใช้ได้")
async def help_cmd(interaction: discord.Interaction):
    """คำสั่งช่วยเหลือ - แสดงคำสั่งทั้งหมด - ใช้ได้ใน DM ทุกที่"""
    try:
        help_embed = discord.Embed(
            title="🍣 Sushi Shop - คำสั่งทั้งหมด",
            description="**คำสั่ง Slash Commands (ใช้ /):**\n"
                       "`/gamepass <จำนวน>` - คำนวณราคา Gamepass\n"
                       "`/group <จำนวน>` - คำนวณราคา Group\n"
                       "`/baht_gamepass <จำนวน>` - คำนวณ Robux จากจำนวนบาท\n"
                       "`/baht_group <จำนวน>` - คำนวณ Robux จากจำนวนบาท\n"
                       "`/tax <จำนวน>` - คำนวณ Robux หลังหักภาษี\n"
                       "`/help` - แสดงคำสั่งที่ใช้ได้\n\n"
                       "**หมายเหตุ:**\n"
                       "• คำสั่งเหล่านี้ใช้ได้ทั้งในเซิร์ฟเวอร์และ DM\n"
                       "• ในการสั่งซื้อจริง ต้องเปิดตั๋วในเซิร์ฟเวอร์เท่านั้น",
            color=0x00FF99
        )
        
        await interaction.response.send_message(embed=help_embed, ephemeral=False)
        
    except Exception as e:
        await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=False)

# =======================================================================================
# ✅ TEXT COMMANDS - ใช้ในเซิร์ฟเวอร์เท่านั้น
# =======================================================================================

@bot.command()
async def gp(ctx, *, expression: str):
    """คำสั่งคำนวณราคา Gamepass (Text Command)"""
    try:
        expr = expression.replace(",", "").lower().replace("x", "*").replace("÷", "/")

        if not re.match(r"^[\d\s\+\-\*\/\(\)]+$", expr):
            await ctx.send("❌ กรุณาใส่เฉพาะตัวเลข และเครื่องหมาย + - * / x ÷ ()", delete_after=10)
            return

        robux = int(eval(expr))
        price = robux / gamepass_rate
        price_str = f"{price:,.0f} บาท"

        await ctx.send(f"🎮 Gamepass {robux:,} Robux = **{price_str}** (เรท {gamepass_rate})")

    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=10)

@bot.command()
async def g(ctx, *, expression: str):
    """คำสั่งคำนวณราคา Group (Text Command)"""
    try:
        expr = expression.replace(",", "").lower().replace("x", "*").replace("÷", "/")

        if not re.match(r"^[\d\s\+\-\*\/\(\)]+$", expr):
            await ctx.send("❌ กรุณาใส่เฉพาะตัวเลข และเครื่องหมาย + - * / x ÷ ()", delete_after=10)
            return

        robux = int(eval(expr))

        if robux < 2250:
            rate = group_rate_low
        else:
            rate = group_rate_high

        price = robux / rate
        price_str = f"{price:,.0f} บาท"

        await ctx.send(f"👥 Group {robux:,} Robux = **{price_str}** (เรท {rate})")

    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=10)

@bot.command()
async def gpb(ctx, *, expression: str):
    """คำสั่งคำนวณ Robux จากเงินบาท (Gamepass) (Text Command)"""
    try:
        expr = expression.replace(",", "").replace(" ", "")
        baht = eval(expr)

        robux = baht * gamepass_rate
        await ctx.send(f"🎮 {baht:,.0f} บาท = **{robux:,.0f} Robux** (Gamepass เรท {gamepass_rate})")

    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=10)

@bot.command()
async def gb(ctx, *, expression: str):
    """คำสั่งคำนวณ Robux จากเงินบาท (Group) (Text Command)"""
    try:
        expr = expression.replace(",", "").replace(" ", "")
        baht = eval(expr)

        if baht < 500:
            rate = group_rate_low
        else:
            rate = group_rate_high

        robux = baht * rate
        await ctx.send(f"👥 {baht:,.0f} บาท = **{robux:,.0f} Robux** (Group เรท {rate})")

    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=10)

@bot.command()
async def tax(ctx, *, expression: str):
    """คำสั่งคำนวณ Robux หลังหักภาษี (Text Command)"""
    try:
        expr = expression.replace(" ", "")
        
        if re.match(r"^\d+$", expr):
            number = int(expr)
            result = number * 0.7
            await ctx.send(f"💰 {number:,} Robux หลังหัก 30% = **{result:,.0f} Robux**")
            
        elif re.match(r"^\d+-\d+%$", expr):
            parts = expr.split('-')
            number = int(parts[0])
            percent = int(parts[1].replace('%', ''))
            
            if percent < 0 or percent > 100:
                await ctx.send("❌ เปอร์เซ็นต์ต้องอยู่ระหว่าง 0-100%", delete_after=10)
                return
            
            result = number * (1 - percent/100)
            await ctx.send(f"💰 {number:,} Robux หลังหัก {percent}% = **{result:,.0f} Robux**")
            
        else:
            await ctx.send(
                "❌ รูปแบบไม่ถูกต้อง\n\n"
                "**การใช้งาน:**\n"
                "`!tax 100` - หัก 30% อัตโนมัติ\n"
                "`!tax 100-30%` - หัก 30%\n"
                "`!tax 100-50%` - หัก 50%",
                delete_after=15
            )

    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=10)

# =======================================================================================
# ✅ เริ่มต้นบอท
# =======================================================================================

print("🚀 กำลังเริ่มต้นบอทสำหรับ User Install...")
print("📍 บอทจะทำงานใน: เซิร์ฟเวอร์, DM ส่วนตัว, Group DMs")

try:
    server_on()
    bot.run(os.getenv("TOKEN"))
except Exception as e:
    print(f"❌ เกิดข้อผิดพลาดร้ายแรง: {e}")
