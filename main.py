import os
import datetime
import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import re
import asyncio
import json
import traceback
import time

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
DELIVERED_CHANNEL_ID = 1419565515088597083  # ✅ ห้อง "ส่งของแล้ว"
ARCHIVED_CATEGORY_ID = 1445086228113264650  # ✅ Category สำหรับย้ายตั๋วหลัง 10 นาที
gamepass_stock = 100  # ตั้งค่าเริ่มต้น
group_stock = 100     # ตั้งค่าเริ่มต้น

# เก็บข้อมูลโน้ตส่วนตัว
user_notes = {}

# ระบบติดตามกิจกรรมในตั๋ว
ticket_activity = {}

# ระบบเก็บเลเวลและ EXP
user_data_file = "user_data.json"
ticket_transcripts_file = "ticket_transcripts.json"
ticket_counter_file = "ticket_counter.json"  # ✅ ไฟล์เก็บตัวนับตั๋ว

# =======================================================================================
# ✅ ฟังก์ชันจัดการไฟล์ข้อมูล
# =======================================================================================

def load_user_data():
    """โหลดข้อมูลผู้ใช้จากไฟล์"""
    try:
        if os.path.exists(user_data_file):
            with open(user_data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                print(f"✅ โหลดข้อมูลผู้ใช้: {len(data)} users")
                return data
        return {}
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการโหลด user_data: {e}")
        return {}

def save_user_data():
    """บันทึกข้อมูลผู้ใช้ลงไฟล์ (เวอร์ชันปลอดภัย)"""
    try:
        with open(user_data_file, 'w', encoding='utf-8') as f:
            json.dump(user_data, f, ensure_ascii=False, indent=2)
        print("💾 บันทึกข้อมูลผู้ใช้เรียบร้อยแล้ว")
        return True
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการบันทึก user_data: {e}")
        return False

def load_ticket_transcripts():
    """โหลดประวัติตั๋วจากไฟล์"""
    try:
        if os.path.exists(ticket_transcripts_file):
            with open(ticket_transcripts_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                print(f"✅ โหลดประวัติตั๋ว: {len(data)} tickets")
                return data
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
        return True
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการบันทึก ticket_transcripts: {e}")
        return False

# ✅ ระบบตัวนับตั๋วใหม่
def load_ticket_counter():
    """โหลดตัวนับตั๋วจากไฟล์"""
    try:
        if os.path.exists(ticket_counter_file):
            with open(ticket_counter_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                print(f"✅ โหลดตัวนับตั๋ว: {data}")
                return data
        return {"counter": 1, "date": datetime.datetime.now().strftime("%d%m%y")}
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการโหลด ticket_counter: {e}")
        return {"counter": 1, "date": datetime.datetime.now().strftime("%d%m%y")}

def save_ticket_counter(counter_data):
    """บันทึกตัวนับตั๋วลงไฟล์"""
    try:
        with open(ticket_counter_file, 'w', encoding='utf-8') as f:
            json.dump(counter_data, f, ensure_ascii=False, indent=2)
        print(f"💾 บันทึกตัวนับตั๋วเรียบร้อย: {counter_data}")
        return True
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการบันทึก ticket_counter: {e}")
        return False

# =======================================================================================
# ✅ คลาสหลักของบอท
# =======================================================================================

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
            allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False)
        )
        self.last_update_time = 0
        self.ticket_counter = load_ticket_counter()  # ✅ โหลดตัวนับตั๋ว

    async def setup_hook(self):
        """ตั้งค่าและ sync คำสั่ง"""
        print("🔄 กำลังตั้งค่า slash commands...")
        
        # ✅ โหลดข้อมูลทั้งหมด
        global user_data, ticket_transcripts
        user_data = load_user_data()
        ticket_transcripts = load_ticket_transcripts()
        
        print(f"✅ โหลดข้อมูลผู้ใช้: {len(user_data)} users")
        print(f"✅ โหลดประวัติตั๋ว: {len(ticket_transcripts)} tickets")
        print(f"✅ โหลดตัวนับตั๋ว: {self.ticket_counter}")
        
        try:
            synced = await self.tree.sync()
            print(f"✅ Sync Global Commands เรียบร้อย: {len(synced)} commands")
        except Exception as e:
            print(f"❌ เกิดข้อผิดพลาดในการ sync: {e}")

# =======================================================================================
# ✅ สร้าง instance ของบอท
# =======================================================================================
bot = MyBot()

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
# ✅ Decorator สำหรับตรวจสอบสิทธิ์แอดมิน - ย้ายมาไว้ก่อนใช้งาน
# =======================================================================================

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

# =======================================================================================
# ✅ ระบบนับเครดิต
# =======================================================================================

async def update_credit_channel():
    """อัพเดทชื่อช่องเครดิตตามจำนวนข้อความ"""
    try:
        channel = bot.get_channel(CREDIT_CHANNEL_ID)
        if not channel:
            print("❌ ไม่พบช่องเครดิต")
            return
        
        message_count = 0
        async for _ in channel.history(limit=None):
            message_count += 1
        
        new_name = f"✅credit : {message_count}"
        if channel.name != new_name:
            await channel.edit(name=new_name)
            print(f"✅ อัพเดทชื่อช่องเครดิตเป็น: {new_name}")
            
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการอัพเดทช่องเครดิต: {e}")

# =======================================================================================
# ✅ ฟังก์ชันสร้างเลขตั๋วใหม่
# =======================================================================================

def get_next_ticket_number():
    """สร้างเลขตั๋วถัดไป"""
    try:
        current_date = datetime.datetime.now().strftime("%d%m%y")
        
        # ตรวจสอบว่าวันนี้เป็นวันใหม่หรือไม่
        if bot.ticket_counter["date"] != current_date:
            bot.ticket_counter = {"counter": 1, "date": current_date}
            print(f"🔄 รีเซ็ตตัวนับเป็นวันใหม่: {current_date}")
        else:
            # เพิ่มตัวนับทีละ 1
            bot.ticket_counter["counter"] += 1
        
        # บันทึกตัวนับลงไฟล์
        save_ticket_counter(bot.ticket_counter)
        
        ticket_number = bot.ticket_counter["counter"]
        print(f"✅ สร้างเลขตั๋วใหม่: {ticket_number} (วันที่: {current_date})")
        return ticket_number
        
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการสร้างเลขตั๋ว: {e}")
        return 1

# =======================================================================================
# ✅ ฟังก์ชันบันทึกประวัติแชทในตั๋ว
# =======================================================================================

async def save_ticket_transcript(channel, action_by=None, robux_amount=None):
    """บันทึกประวัติแชทในตั๋ว"""
    try:
        print(f"📝 กำลังบันทึกประวัติตั๋ว: {channel.name}")
        
        # ✅ ใช้ระบบตัวนับตั๋วใหม่
        ticket_number = get_next_ticket_number()
        
        # ✅ สร้าง timestamp แบบใหม่ (ddmmyytime)
        now = datetime.datetime.now()
        date_str = now.strftime("%d%m%y")
        time_str = now.strftime("%H%M")  # เวลาแบบ 24 ชั่วโมง
        timestamp_str = f"{date_str}{time_str}"
        
        # ✅ ดึงชื่อผู้ใช้จากชื่อห้อง
        username = "unknown"
        if channel.name.startswith("ticket-"):
            parts = channel.name.split('-')
            if len(parts) >= 2:
                username = parts[1]  # ใช้ส่วนที่สองเป็นชื่อผู้ใช้
        
        # ✅ ตรวจสอบจำนวน robux
        robux_info = ""
        if robux_amount and robux_amount != "unknown":
            robux_info = f"-{robux_amount}"
        
        # ✅ สร้างชื่อไฟล์ใหม่ตามรูปแบบ: ticketnumber-timestamp-robux-username
        filename = f"{ticket_number}-{timestamp_str}{robux_info}-{username}"
        
        # เก็บข้อมูลตั๋ว
        transcript_data = {
            "filename": filename,
            "channel_name": channel.name,
            "channel_id": channel.id,
            "ticket_number": ticket_number,
            "timestamp": timestamp_str,
            "username": username,
            "robux_amount": robux_amount,
            "category": channel.category.name if channel.category else "ไม่มีหมวดหมู่",
            "created_at": now.isoformat(),
            "closed_by": str(action_by) if action_by else "ระบบอัตโนมัติ",
            "messages_count": 0
        }
        
        # นับข้อความ
        message_count = 0
        try:
            async for message in channel.history(limit=None):
                message_count += 1
        except:
            pass
        
        transcript_data["messages_count"] = message_count
        
        # บันทึกลงไฟล์
        ticket_transcripts[str(channel.id)] = transcript_data
        
        # บันทึกไฟล์
        if save_ticket_transcripts():
            print(f"✅ บันทึกประวัติตั๋วเรียบร้อย: {filename}")
            return True, filename, ticket_number
        else:
            print(f"⚠️ บันทึกประวัติตั๋วไม่สำเร็จ: {channel.name}")
            return False, "บันทึกไม่สำเร็จ", 0
        
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการบันทึกประวัติตั๋ว: {e}")
        return False, str(e), 0

# =======================================================================================
# ✅ ฟังก์ชันจัดการตั๋วหลัง !ty - แก้ไขใหม่
# =======================================================================================

async def archive_ticket_after_ty(channel, user, robux_amount=None):
    """ย้ายและเปลี่ยนชื่อตั๋วหลังใช้ !ty (รอ 10 นาทีก่อนย้ายจริง)"""
    try:
        guild = channel.guild
        
        # ✅ 1. ย้ายตั๋วไปห้อง "ส่งของแล้ว" ก่อน
        delivered_channel = guild.get_channel(DELIVERED_CHANNEL_ID)
        
        if not delivered_channel:
            print(f"❌ ไม่พบห้องส่งของแล้ว ID: {DELIVERED_CHANNEL_ID}")
            return False
        
        # ✅ สร้างชื่อใหม่สำหรับห้องส่งของแล้ว
        now = datetime.datetime.now()
        date_str = now.strftime("%d%m%y")
        time_str = now.strftime("%H%M")
        
        # หาตัวนับ transcript สูงสุดในหมวดหมู่
        if 'transcript_counter' not in globals():
            global transcript_counter
            transcript_counter = {}
        
        if guild.id not in transcript_counter:
            transcript_counter[guild.id] = 0
        
        # เพิ่มตัวนับ
        transcript_counter[guild.id] += 1
        counter = transcript_counter[guild.id]
        
        # ✅ รูปแบบใหม่: ddmmyytime-robux-ticketnumber-username
        username = user.name if user else "unknown"
        if len(username) > 15:
            username = username[:15]
        
        # ใช้ robux_amount จากพารามิเตอร์หรือจากข้อมูลตั๋ว
        robux_display = robux_amount if robux_amount else "unknown"
        
        # ✅ สร้างชื่อใหม่ตามรูปแบบที่ต้องการ
        new_name = f"{date_str}{time_str}-{robux_display}-{counter}-{username}"
        
        print(f"📁 กำลังย้ายตั๋วไปห้องส่งของแล้ว: {new_name}")
        
        # ✅ ย้ายตั๋วไปยังห้องส่งของแล้ว
        await channel.edit(
            category=delivered_channel.category,
            name=new_name,
            reason=f"ส่งของแล้ว โดย {user.name if user else 'ระบบ'}"
        )
        
        print(f"✅ ย้ายตั๋วไปห้องส่งของแล้วเรียบร้อย: {new_name}")
        
        # ✅ เริ่มนับถอยหลัง 10 นาทีเพื่อย้ายไป transcript
        await start_transcript_countdown(channel, user, robux_amount, counter)
        
        return True
        
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการย้ายตั๋ว: {e}")
        traceback.print_exc()
        return False

async def start_transcript_countdown(channel, user, robux_amount, counter):
    """เริ่มนับถอยหลัง 10 นาทีก่อนย้ายไป transcript"""
    print(f"⏰ เริ่มนับถอยหลัง 10 นาทีสำหรับตั๋ว: {channel.name}")
    
    # ✅ ส่งข้อความแจ้งผู้ซื้อ
    try:
        embed = discord.Embed(
            title="⏳ ตั๋วถูกย้ายไปห้องส่งของแล้ว",
            description="คุณสามารถตรวจสอบรายละเอียดการส่งสินค้าได้ในอีก 10 นาที\nหลังจากนั้นตั๋วจะถูกย้ายไปเก็บในระบบ transcript",
            color=0xFFA500
        )
        embed.set_footer(text="ระบบจะลบสิทธ์การเข้าดูหลัง 10 นาที")
        
        await channel.send(embed=embed)
    except Exception as e:
        print(f"⚠️ ไม่สามารถส่งข้อความแจ้ง: {e}")
    
    # ✅ รอ 10 นาที
    await asyncio.sleep(600)  # 10 นาที
    
    try:
        # ตรวจสอบว่าตั๋วยังมีอยู่
        if not channel or channel not in channel.guild.channels:
            print(f"❌ ตั๋ว {channel.name} ไม่มีอยู่แล้ว")
            return
        
        # ✅ ย้ายไปยังหมวดหมู่เก็บข้อมูล
        await move_to_transcript_category(channel, user, robux_amount, counter)
        
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดใน transcript countdown: {e}")

async def move_to_transcript_category(channel, user, robux_amount, counter):
    """ย้ายตั๋วไปยังหมวดหมู่ transcript และลบสิทธ์ view"""
    try:
        guild = channel.guild
        
        # ✅ หา category สำหรับเก็บ transcript
        archive_category = guild.get_channel(ARCHIVED_CATEGORY_ID)
        
        if not archive_category:
            print(f"❌ ไม่พบ category ID: {ARCHIVED_CATEGORY_ID}")
            return False
        
        # ✅ สร้างชื่อตามรูปแบบใหม่: ddmmyytime-robux-ticketnumber-username
        now = datetime.datetime.now()
        date_str = now.strftime("%d%m%y")
        time_str = "0800"  # ใช้เวลา 08:00 ตามที่ต้องการ
        
        username = user.name if user else "unknown"
        if len(username) > 15:
            username = username[:15]
        
        robux_display = robux_amount if robux_amount else "unknown"
        new_name = f"{date_str}{time_str}-{robux_display}-{counter}-{username}"
        
        # ✅ สร้าง overwrites ใหม่ - ลบสิทธิ์ view ของผู้ซื้อ
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True)
        }
        
        # ✅ ลบสิทธิ์ view ของผู้ซื้อ
        if user:
            overwrites[user] = discord.PermissionOverwrite(read_messages=False)
        
        # ✅ เพิ่มสิทธิ์ให้แอดมิน
        admin_role = guild.get_role(1361016912259055896)
        if admin_role:
            overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True)
        
        # ✅ ย้ายไปยังหมวดหมู่ transcript
        await channel.edit(
            category=archive_category,
            name=new_name,
            overwrites=overwrites,
            reason=f"ย้ายไป transcript หลัง 10 นาที"
        )
        
        # ✅ ส่งข้อความแจ้ง
        embed = discord.Embed(
            title="📁 ตั๋วถูกย้ายไปเก็บแล้ว",
            description="ตั๋วนี้ถูกย้ายไปยังระบบเก็บข้อมูลเรียบร้อยแล้ว\n*10 นาทีผ่านไปหลังจากส่งของเรียบร้อย*",
            color=0x808080
        )
        
        try:
            await channel.send(embed=embed)
        except:
            pass
        
        print(f"✅ ย้ายตั๋วไป transcript เรียบร้อย: {new_name}")
        
        # ✅ ลบออกจากระบบ tracking
        if channel.id in ticket_activity:
            del ticket_activity[channel.id]
        
        return True
        
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการย้ายไป transcript: {e}")
        traceback.print_exc()
        return False

# =======================================================================================
# ✅ View สำหรับส่งสินค้า - แก้ไขใหม่
# =======================================================================================

class DeliveryView(View):
    def __init__(self, channel, product_type, robux_amount, price, buyer, ticket_number=None):
        super().__init__(timeout=None)
        self.channel = channel
        self.product_type = product_type
        self.robux_amount = robux_amount
        self.price = price
        self.buyer = buyer
        self.ticket_number = ticket_number  # ✅ เพิ่ม ticket number
        self.delivered = False

    @discord.ui.button(label="ส่งสินค้าแล้ว ✅", style=discord.ButtonStyle.success, emoji="✅", custom_id="deliver_product_btn")
    async def deliver_product(self, interaction: discord.Interaction, button: Button):
        """ปุ่มส่งสินค้า (เฉพาะแอดมิน)"""
        try:
            # ✅ ตรวจสอบสิทธิ์แอดมิน
            admin_role = interaction.guild.get_role(1361016912259055896)
            if not admin_role or admin_role not in interaction.user.roles:
                await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้ปุ่มนี้", ephemeral=True)
                return

            # ✅ ตรวจสอบไฟล์รูปภาพ
            delivery_image = None
            
            # 1. ตรวจสอบว่ามีไฟล์ใหม่จาก modal แก้ไขหรือไม่
            if self.channel.id in ticket_activity and 'new_delivery_image' in ticket_activity[self.channel.id]:
                delivery_image = ticket_activity[self.channel.id]['new_delivery_image']
            
            # 2. ถ้าไม่มีไฟล์ใหม่ ให้ตรวจสอบไฟล์ล่าสุดในแชท
            if not delivery_image:
                async for message in self.channel.history(limit=10):
                    if message.author == interaction.user and message.attachments:
                        for attachment in message.attachments:
                            if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
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
                self.buyer, delivery_image, self.ticket_number
            )
            
            await interaction.response.send_message(embed=confirm_embed, view=confirm_view, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

    @discord.ui.button(label="ยกเลิก ❌", style=discord.ButtonStyle.danger, emoji="❌", custom_id="cancel_order_btn")
    async def cancel_order(self, interaction: discord.Interaction, button: Button):
        """ปุ่มยกเลิกคำสั่งซื้อ"""
        try:
            await interaction.response.send_message("❌ คำสั่งซื้อถูกยกเลิก", ephemeral=True)
            await interaction.message.delete()
        except Exception as e:
            await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

class ConfirmDeliveryView(View):
    def __init__(self, channel, product_type, robux_amount, price, buyer, delivery_image, ticket_number=None):
        super().__init__(timeout=300)
        self.channel = channel
        self.product_type = product_type
        self.robux_amount = robux_amount
        self.price = price
        self.buyer = buyer
        self.delivery_image = delivery_image
        self.ticket_number = ticket_number
        self.delivered = False

    @discord.ui.button(label="ยืนยัน ✅", style=discord.ButtonStyle.success, emoji="✅", custom_id="confirm_delivery_btn")
    async def confirm_delivery(self, interaction: discord.Interaction, button: Button):
        """ยืนยันการส่งสินค้า"""
        try:
            if self.delivered:
                await interaction.response.edit_message(
                    content="✅ สินค้าถูกส่งเรียบร้อยแล้ว",
                    embed=None,
                    view=None
                )
                return
                
            self.delivered = True
            
            # ✅ บันทึก transcript (เก็บ ticket number สำหรับใช้ใน embed)
            save_success, filename, ticket_num = await save_ticket_transcript(
                self.channel, 
                interaction.user, 
                str(self.robux_amount) if self.robux_amount > 0 else "0"
            )
            
            # ✅ ใช้ ticket number จากระบบบันทึก
            if save_success and ticket_num > 0:
                self.ticket_number = ticket_num
            
            # ✅ สร้าง embed ใบเสร็จการสั่งซื้อ (เพิ่ม ticket number)
            receipt_color = 0xFFA500  # สีส้มสำหรับ Gamepass
            if self.product_type == "Group":
                receipt_color = 0x00FFFF  # สีฟ้าแบบ Cyan
            elif self.product_type == "Limited":
                receipt_color = 0x00FF00  # สีเขียว
            
            current_time = datetime.datetime.now()
            
            # ✅ เพิ่ม ticket number ใน title
            ticket_display = f" #{self.ticket_number}" if self.ticket_number else ""
            receipt_title = f"🍣 ใบเสร็จการสั่งซื้อ ({self.product_type}) 🍣{ticket_display}"
            
            receipt_embed = discord.Embed(
                title=receipt_title,
                color=receipt_color
            )
            
            receipt_embed.add_field(name="😊 ผู้ซื้อ", value=self.buyer.mention if self.buyer else "ไม่ทราบ", inline=False)
            
            if self.product_type == "Limited":
                receipt_embed.add_field(name="🎁 สินค้า", value="ไอเทม Limited", inline=True)
                receipt_embed.add_field(name="💰 ราคา", value=f"{self.price:,.0f} บาท", inline=True)
            else:
                receipt_embed.add_field(name="💸 จำนวน Robux", value=f"{self.robux_amount:,}", inline=True)
                receipt_embed.add_field(name="💰 ราคาตามเรท", value=f"{self.price:,.0f} บาท", inline=True)
            
            if self.delivery_image:
                receipt_embed.set_image(url=self.delivery_image)
            
            receipt_embed.set_footer(text=f"จัดส่งสินค้าสำเร็จ 🤗 • {current_time.strftime('%d/%m/%y, %H:%M')}")
            
            # ✅ ส่งไปยังห้องบันทึกการขาย
            log_channel = bot.get_channel(SALES_LOG_CHANNEL_ID)
            if log_channel:
                try:
                    await log_channel.send(embed=receipt_embed)
                    print(f"✅ บันทึกใบเสร็จการสั่งซื้อในห้องบันทึกการขาย: {self.product_type}")
                except:
                    print(f"⚠️ ไม่สามารถส่งใบเสร็จไปยังห้องบันทึกการขาย")
            
            # ✅ ส่งใบเสร็จในตั๋ว
            await self.channel.send(embed=receipt_embed)
            
            # ✅ แก้ไขข้อความเดิม
            await interaction.response.edit_message(
                content="✅ บันทึกการส่งสินค้าเรียบร้อยแล้ว",
                embed=None,
                view=None
            )
            
            # ✅ เริ่มกระบวนการ !ty (ย้ายไปห้องส่งของแล้ว)
            # เรียกใช้ !ty ผ่าน context
            ctx = await bot.get_context(interaction.message)
            ctx.channel = self.channel
            ctx.author = interaction.user
            
            # เรียกคำสั่ง !ty
            await ty_command(ctx)
            
        except Exception as e:
            print(f"❌ เกิดข้อผิดพลาดในการยืนยันการส่งสินค้า: {e}")
            traceback.print_exc()
            try:
                await interaction.response.edit_message(
                    content="✅ ส่งสินค้าเรียบร้อยแล้ว (บันทึกบางส่วนไม่สมบูรณ์)",
                    embed=None,
                    view=None
                )
            except:
                pass

    @discord.ui.button(label="แก้ไข", style=discord.ButtonStyle.secondary, emoji="✏️", custom_id="edit_delivery_btn")
    async def edit_delivery(self, interaction: discord.Interaction, button: Button):
        """แก้ไขหลักฐานการส่งสินค้า"""
        try:
            modal = EditDeliveryModal(self.channel)
            await interaction.response.send_modal(modal)
            
        except Exception as e:
            await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

class EditDeliveryModal(Modal, title="✏️ แก้ไขหลักฐานการส่งสินค้า"):
    def __init__(self, channel):
        super().__init__(timeout=300)
        self.channel = channel
    
    new_image = TextInput(
        label="🔗 URL หลักฐานใหม่ (หรือแนบไฟล์ในแชทก่อน แล้วคัดลอก URL)",
        placeholder="https://example.com/image.png",
        required=False,
        max_length=1000
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            new_image_url = None
            
            if self.new_image.value.strip():
                if self.new_image.value.startswith(('http://', 'https://')):
                    new_image_url = self.new_image.value
                else:
                    await interaction.response.send_message("❌ URL ไม่ถูกต้อง กรุณากรอก URL ที่ขึ้นต้นด้วย http:// หรือ https://", ephemeral=True)
                    return
            
            if not new_image_url:
                async for message in self.channel.history(limit=10):
                    if message.author == interaction.user and message.attachments:
                        for attachment in message.attachments:
                            if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                                new_image_url = attachment.url
                                break
                        if new_image_url:
                            break
            
            if not new_image_url:
                await interaction.response.send_message(
                    "❌ ไม่พบหลักฐานใหม่ กรุณา:\n1. แนบไฟล์รูปในแชท\nหรือ\n2. กรอก URL หลักฐานในช่องด้านบน",
                    ephemeral=True
                )
                return
            
            await interaction.response.send_message(
                f"✅ อัพเดทหลักฐานใหม่เรียบร้อยแล้ว!\n"
                f"กดปุ่ม 'ส่งสินค้าแล้ว ✅' อีกครั้งเพื่อยืนยันด้วยหลักฐานใหม่",
                ephemeral=True
            )
            
            if self.channel.id in ticket_activity:
                ticket_activity[self.channel.id]['new_delivery_image'] = new_image_url
            
        except Exception as e:
            print(f"❌ เกิดข้อผิดพลาดในแก้ไขหลักฐาน: {e}")
            await interaction.response.send_message("❌ เกิดข้อผิดพลาดในการแก้ไขหลักฐาน", ephemeral=True)

# =======================================================================================
# ✅ คำสั่ง !ty - แก้ไขใหม่
# =======================================================================================

async def ty_command(ctx):
    """คำสั่ง !ty - ย้ายตั๋วไปห้องส่งของแล้ว"""
    try:
        if ctx.channel.name.startswith("ticket-"):
            global gamepass_stock, group_stock
            
            # ✅ อัพเดท stock
            if ctx.channel.category and "gamepass" in ctx.channel.category.name.lower():
                gamepass_stock += 1
            elif ctx.channel.category and "group" in ctx.channel.category.name.lower():
                group_stock += 1

            # ✅ ดึงข้อมูลผู้ซื้อ
            buyer = None
            channel_name = ctx.channel.name
            if channel_name.startswith("ticket-"):
                parts = channel_name.split('-')
                if len(parts) >= 3:
                    try:
                        user_id = int(parts[-1])
                        buyer = ctx.guild.get_member(user_id)
                    except:
                        pass
            
            # ✅ ดึงจำนวน robux จากข้อมูลตั๋ว
            robux_amount = None
            if hasattr(ctx.channel, 'robux_amount'):
                robux_amount = ctx.channel.robux_amount
            else:
                # ค้นหาในประวัติข้อความ
                try:
                    async for message in ctx.channel.history(limit=20):
                        if message.content.startswith('!od ') or message.content.startswith('!odg '):
                            try:
                                parts = message.content.split()
                                if len(parts) >= 2:
                                    expr = parts[1].replace(",", "").lower().replace("x", "*").replace("÷", "/")
                                    if re.match(r"^[\d\s\+\-\*\/\(\)]+$", expr):
                                        robux_amount = str(int(eval(expr)))
                                        break
                            except:
                                continue
                except:
                    pass
            
            # ✅ ย้ายตั๋วไปห้องส่งของแล้ว
            archive_success = await archive_ticket_after_ty(ctx.channel, buyer, robux_amount)
            
            if not archive_success:
                await ctx.send("⚠️ ไม่สามารถย้ายตั๋วไปห้องส่งของแล้วได้", delete_after=5)
                return
            
            # ✅ ส่ง embed ให้เครดิต
            credit_embed = discord.Embed(
                title="⭐ กรุณาให้เครดิต",
                description="หากคุณพอใจกับการบริการ กรุณาให้เครดิตที่ช่องด้านล่าง\n\n[กดที่นี่เพื่อให้เครดิต](https://discord.com/channels/1360990259311018077/1363250076549382246)",
                color=0xFFD700
            )
            
            credit_view = discord.ui.View(timeout=None)
            credit_view.add_item(
                discord.ui.Button(
                    label="⭐ ให้เครดิตที่นี่",
                    url="https://discord.com/channels/1360990259311018077/1363250076549382246",
                    style=discord.ButtonStyle.link,
                    emoji="⭐"
                )
            )
            
            await ctx.send(embed=credit_embed, view=credit_view)
            
            # ✅ อัพเดทช่องหลัก
            await update_main_channel()
            
            print(f"✅ ใช้ !ty สำเร็จ: {ctx.channel.name}")
            
        else:
            await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะในตั๋วเท่านั้น", delete_after=5)
            
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดใน !ty: {e}")
        traceback.print_exc()
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=10)

@bot.command()
@admin_only()
async def ty(ctx):
    """คำสั่ง !ty - ส่งของเรียบร้อยแล้ว"""
    await ty_command(ctx)

# =======================================================================================
# ✅ View ต่างๆ - ตามโค้ดเดิม
# =======================================================================================

# --------------------------------------------------------------------------------------------------
# ✅ View สำหรับ QR Code
class QRView(View):
    def __init__(self):
        super().__init__(timeout=None)
        
    @discord.ui.button(label="คัดลอกเลขบัญชี", style=discord.ButtonStyle.success, emoji="📋", custom_id="copy_bank_account_btn")
    async def copy_bank_account(self, interaction: discord.Interaction, button: Button):
        """ปุ่มคัดลอกเลขบัญชี SCB"""
        try:
            bank_info = "120-239181-3 : ธนาคาร SCB"
            await interaction.response.send_message(f"```{bank_info}```", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

# --------------------------------------------------------------------------------------------------
# View สำหรับการดำเนินการในตั๋ว
class TicketActionView(View):
    def __init__(self, channel, user, modal_class):
        super().__init__(timeout=None)
        self.channel = channel
        self.user = user
        self.modal_class = modal_class

    @discord.ui.button(label="📝 กรอกแบบฟอร์มใหม่", style=discord.ButtonStyle.primary, emoji="📝", custom_id="refill_form_btn")
    async def refill_form(self, interaction: discord.Interaction, button: Button):
        try:
            modal = self.modal_class()
            await interaction.response.send_modal(modal)
        except Exception as e:
            await interaction.response.send_message("❌ เกิดข้อผิดพลาดในการเปิดแบบฟอร์ม", ephemeral=True)

    @discord.ui.button(label="🔒 ปิดตั๋ว", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="close_ticket_btn")
    async def close_ticket(self, interaction: discord.Interaction, button: Button):
        try:
            admin_role = interaction.guild.get_role(1361016912259055896)
            if admin_role and admin_role in interaction.user.roles:
                save_success, _, _ = await save_ticket_transcript(self.channel, interaction.user)
                
                if save_success:
                    await interaction.response.send_message("📪 กำลังปิดตั๋ว...")
                    await asyncio.sleep(2)
                    await self.channel.delete()
                else:
                    await interaction.response.send_message("⚠️ บันทึกประวัติตั๋วไม่สมบูรณ์ แต่จะปิดตั๋วต่อไป", ephemeral=True)
                    await asyncio.sleep(2)
                    await self.channel.delete()
            else:
                await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ปิดตั๋วนี้", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message("❌ เกิดข้อผิดพลาดในการปิดตั๋ว", ephemeral=True)

# --------------------------------------------------------------------------------------------------
# View สำหรับให้เครดิต
class GiveCreditView(discord.ui.View):
    def __init__(self, channel):
        super().__init__(timeout=None)
        self.channel = channel
        
        self.add_item(
            discord.ui.Button(
                label="ให้เครดิตที่นี่", 
                url="https://discord.com/channels/1360990259311018077/1363250076549382246", 
                style=discord.ButtonStyle.link,
                emoji="⭐"
            )
        )
        
        close_button = Button(
            label="🔒 ปิดตั๋ว", 
            style=discord.ButtonStyle.danger, 
            emoji="🔒",
            custom_id="user_close_ticket"
        )
        close_button.callback = self.user_close_ticket
        self.add_item(close_button)

    async def user_close_ticket(self, interaction: discord.Interaction):
        try:
            save_success, _, _ = await save_ticket_transcript(self.channel, interaction.user)
            
            if save_success:
                await interaction.response.send_message("📪 กำลังปิดตั๋ว... ขอบคุณที่ใช้บริการ!")
                await asyncio.sleep(3)
                await self.channel.delete()
            else:
                await interaction.response.send_message("⚠️ บันทึกประวัติตั๋วไม่สมบูรณ์ แต่จะปิดตั๋วต่อไป", ephemeral=True)
                await asyncio.sleep(3)
                await self.channel.delete()
            
        except Exception as e:
            await interaction.response.send_message("❌ เกิดข้อผิดพลาดในการปิดตั๋ว", ephemeral=True)

# --------------------------------------------------------------------------------------------------
# ฟังก์ชันจัดการเลเวลและ EXP
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
    
    save_user_data()
    
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
        current_time = time.time()
        if current_time - bot.last_update_time < 60:
            print(f"⏳ รอเพื่อป้องกัน rate limit... (เหลืออีก {60 - (current_time - bot.last_update_time):.0f} วินาที)")
            return
            
        channel = bot.get_channel(MAIN_CHANNEL_ID)
        if channel:
            if shop_open:
                new_name = "〔🟢เปิด〕กดสั่งซื้อที่นี่"
            else:
                new_name = "〔🔴〕ปิดชั่วคราว"
            
            if channel.name != new_name:
                try:
                    await channel.edit(name=new_name)
                    bot.last_update_time = current_time
                    print(f"✅ เปลี่ยนชื่อช่องเป็น: {new_name}")
                except discord.HTTPException as e:
                    if e.status == 429:
                        print(f"⏳ Discord rate limit: {e}")
                        bot.last_update_time = current_time
                        return
                    else:
                        raise
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
            placeholder="พิมพ์ชื่อแมพ เช่น Gift Simulator",
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
            placeholder="เช่น 300 หรือ 100+100+100 หรือ 100x3",
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
                color=0x00FF99
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
                color=0x00FF99
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

    @discord.ui.button(label="❌ ยกเลิกสินค้า", style=discord.ButtonStyle.danger, custom_id="cancel_ticket_btn")
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
async def handle_open_ticket(interaction: discord.Interaction, ticket_title: str, modal_class, ticket_type: str):
    """จัดการการเปิดตั๋ว"""
    try:
        # ตรวจสอบว่าเปิดตั๋วอยู่แล้วหรือไม่
        guild = interaction.guild
        user = interaction.user
        
        for channel in guild.channels:
            if channel.name.startswith(f"ticket-{user.name.lower()}") and isinstance(channel, discord.TextChannel):
                embed = discord.Embed(
                    title="❌ คุณมีตั๋วเปิดอยู่แล้ว",
                    description=f"คุณมีตั๋วเปิดอยู่แล้วที่ {channel.mention}\nกรุณาใช้ตั๋วที่มีอยู่ก่อนเปิดตั๋วใหม่",
                    color=0xFF0000
                )
                view = GoToTicketView(channel)
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
                return
        
        # สร้างห้องตั๋วใหม่
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True)
        }
        
        admin_role = guild.get_role(1361016912259055896)
        if admin_role:
            overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True)
        
        category_name = "🍣gamepass" if ticket_type == "gamepass" else "💰group"
        category = discord.utils.get(guild.categories, name=category_name)
        
        if not category:
            category = await guild.create_category(category_name)
        
        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{user.name}-{user.id}",
            category=category,
            overwrites=overwrites,
            reason=f"ตั๋วใหม่จาก {user.name}"
        )
        
        # สร้าง embed ต้อนรับ
        welcome_embed = discord.Embed(
            title=ticket_title,
            description=f"สวัสดีค่ะ {user.mention} ยินดีต้อนรับสู่ร้านซูชิ\nกรุณากรอกแบบฟอร์มด้านล่างเพื่อทำการสั่งซื้อค่ะ",
            color=0x00FF99
        )
        welcome_embed.add_field(name="📝 วิธีการสั่งซื้อ", value="1. กดปุ่ม 'กรอกแบบฟอร์มใหม่' เพื่อกรอกข้อมูล\n2. รอการตอบกลับจากทีมงาน", inline=False)
        welcome_embed.set_footer(text="ร้านซูชิ | เราคือความอร่อยของทุกคน")
        
        view = TicketActionView(ticket_channel, user, modal_class)
        await ticket_channel.send(embed=welcome_embed, view=view)
        
        # ส่งข้อความยืนยันให้ผู้ใช้
        success_embed = discord.Embed(
            title="✅ เปิดตั๋วสำเร็จ",
            description=f"เปิดตั๋วสำเร็จแล้ว! กรุณาไปที่ {ticket_channel.mention}",
            color=0x00FF00
        )
        view = GoToTicketView(ticket_channel)
        await interaction.response.send_message(embed=success_embed, view=view, ephemeral=True)
        
        print(f"✅ เปิดตั๋วใหม่: {ticket_channel.name} โดย {user.name}")
        
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการเปิดตั๋ว: {e}")
        await interaction.response.send_message("❌ เกิดข้อผิดพลาดในการเปิดตั๋ว", ephemeral=True)

# =======================================================================================
# ✅ คำสั่ง !od, !odg, !odl - แก้ไขเพิ่ม ticket number
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
        
        current_time = datetime.datetime.now()
        
        # ✅ ดึง ticket number จากระบบ
        ticket_number = get_next_ticket_number()
        
        order_embed = discord.Embed(
            title="🍣คำสั่งซื้อสินค้า🍣",
            color=0xFFA500
        )
        order_embed.add_field(name="📦 ประเภทสินค้า", value="Gamepass", inline=False)
        order_embed.add_field(name="💸 จำนวน Robux", value=f"{robux:,}", inline=True)
        order_embed.add_field(name="💰 ราคาตามเรท", value=f"{price:,.0f} บาท", inline=True)
        order_embed.set_footer(text=f"รับออร์เดอร์แล้ว 🤗 • {current_time.strftime('%d/%m/%y, %H:%M')}")
        
        # ✅ เก็บข้อมูล robux_amount และ ticket_number
        ctx.channel.robux_amount = str(robux)
        ctx.channel.ticket_number = ticket_number
        
        delivery_view = DeliveryView(ctx.channel, "Gamepass", robux, price, buyer, ticket_number)
        await ctx.send(embed=order_embed, view=delivery_view)

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
        
        current_time = datetime.datetime.now()
        
        # ✅ ดึง ticket number จากระบบ
        ticket_number = get_next_ticket_number()
        
        order_embed = discord.Embed(
            title="🍣คำสั่งซื้อสินค้า🍣",
            color=0x00FFFF
        )
        order_embed.add_field(name="📦 ประเภทสินค้า", value="Group", inline=False)
        order_embed.add_field(name="💸 จำนวน Robux", value=f"{robux:,}", inline=True)
        order_embed.add_field(name="💰 ราคาตามเรท", value=f"{price:,.0f} บาท", inline=True)
        order_embed.set_footer(text=f"รับออร์เดอร์แล้ว 🤗 • {current_time.strftime('%d/%m/%y, %H:%M')}")
        
        # ✅ เก็บข้อมูล robux_amount และ ticket_number
        ctx.channel.robux_amount = str(robux)
        ctx.channel.ticket_number = ticket_number
        
        delivery_view = DeliveryView(ctx.channel, "Group", robux, price, buyer, ticket_number)
        await ctx.send(embed=order_embed, view=delivery_view)

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

        current_time = datetime.datetime.now()
        
        # ✅ ดึง ticket number จากระบบ
        ticket_number = get_next_ticket_number()
        
        order_embed = discord.Embed(
            title="🍣คำสั่งซื้อสินค้า🍣",
            color=0x00FF00
        )
        order_embed.add_field(name="📦 ประเภทสินค้า", value="Limited", inline=False)
        order_embed.add_field(name="🎁 ชื่อไอเทม", value=item_name, inline=True)
        order_embed.add_field(name="💰 ราคา", value=f"{item_value:,} บาท", inline=True)
        order_embed.set_footer(text=f"รับออร์เดอร์แล้ว 🤗 • {current_time.strftime('%d/%m/%y, %H:%M')}")
        
        # ✅ เก็บข้อมูล item_value และ ticket_number
        ctx.channel.robux_amount = str(item_value)
        ctx.channel.ticket_number = ticket_number
        
        delivery_view = DeliveryView(ctx.channel, "Limited", 0, item_value, buyer, ticket_number)
        await ctx.send(embed=order_embed, view=delivery_view)

    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=10)

# =======================================================================================
# ✅ คำสั่ง !qr
# =======================================================================================

@bot.command()
@admin_only()
async def qr(ctx):
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
    
    qr_url = "https://media.discordapp.net/attachments/1361004239043821610/1444373113319198840/160-1-43871-9_1.png?ex=692d2189&is=692bd009&hm=dd539f3a1acd87cb62430c3b7e13fe44c03cec7b86087ad84397a874b5ee0c8b&=&format=webp&quality=lossless&width=1161&height=1058"
    embed.set_image(url=qr_url)
    
    qr_view = QRView()
    await ctx.send(embed=embed, view=qr_view)
    
# =======================================================================================
# ✅ อัพเดทช่องหลัก
# =======================================================================================

async def update_main_channel():
    """อัพเดทข้อความในช่องหลักโดยการ edit ข้อความเดิม"""
    try:
        current_time = time.time()
        if current_time - bot.last_update_time < 30:
            print(f"⏳ รอเพื่อป้องกัน rate limit ใน update_main_channel...")
            return
            
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
            color=0xFFA500
        )
        
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
                bot.last_update_time = current_time
                print(f"✅ อัพเดท embed หลักเรียบร้อยแล้ว (แก้ไขข้อความ ID: {target_message.id})")
            except discord.NotFound:
                print("❌ ไม่พบข้อความเดิม ส่งข้อความใหม่")
                try:
                    await channel.send(embed=embed, view=MainShopView())
                    bot.last_update_time = current_time
                except Exception as e:
                    print(f"❌ ไม่สามารถส่งข้อความใหม่: {e}")
            except discord.HTTPException as e:
                if e.status == 429:
                    print(f"⏳ Discord rate limit ใน edit: {e}")
                    bot.last_update_time = current_time
                else:
                    print(f"❌ ไม่สามารถ edit ข้อความ: {e}")
                    try:
                        await channel.send(embed=embed, view=MainShopView())
                        bot.last_update_time = current_time
                    except:
                        pass
            except Exception as e:
                print(f"❌ ไม่สามารถ edit ข้อความ: {e}")
                try:
                    await channel.send(embed=embed, view=MainShopView())
                    bot.last_update_time = current_time
                except:
                    pass
        else:
            try:
                await channel.send(embed=embed, view=MainShopView())
                bot.last_update_time = current_time
                print("✅ สร้าง embed หลักใหม่เรียบร้อยแล้ว")
            except Exception as e:
                print(f"❌ ไม่สามารถส่ง embed หลักใหม่: {e}")
        
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการอัปเดตช่องหลัก: {e}")

# =======================================================================================
# ✅ Main Shop View
# =======================================================================================

class MainShopView(View):
    def __init__(self):
        super().__init__(timeout=None)
        
        if shop_open and gamepass_stock > 0:
            gamepass_label = "เปิดตั๋วกดเกมพาส"
            gamepass_style = discord.ButtonStyle.success
            gamepass_disabled = False
        else:
            if not shop_open:
                gamepass_label = "ร้านปิดชั่วคราว"
            else:
                gamepass_label = "สินค้าหมด"
            gamepass_style = discord.ButtonStyle.danger
            gamepass_disabled = True
            
        gamepass_button = Button(
            label=gamepass_label,
            style=gamepass_style,
            custom_id="open_gamepass_ticket",
            emoji="🎮",
            disabled=gamepass_disabled
        )
        gamepass_button.callback = self.gamepass_ticket
        self.add_item(gamepass_button)
        
        if shop_open and group_ticket_enabled and group_stock > 0:
            group_label = "เปิดตั๋ว Group"
            group_style = discord.ButtonStyle.success
            group_disabled = False
        else:
            if not shop_open:
                group_label = "ร้านปิดชั่วคราว"
            elif not group_ticket_enabled:
                group_label = "บริการปิดชั่วคราว"
            else:
                group_label = "สินค้าหมด"
            group_style = discord.ButtonStyle.danger
            group_disabled = True
            
        group_button = Button(
            label=group_label,
            style=group_style,
            custom_id="open_group_ticket", 
            emoji="👥",
            disabled=group_disabled
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
            label="ดูเลเวลของคุณ",
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
# ✅ Events
# =======================================================================================

@bot.event
async def on_message(message):
    if message.channel.id == CREDIT_CHANNEL_ID and not message.author.bot:
        await update_credit_channel()
    
    if isinstance(message.channel, discord.DMChannel) and message.author != bot.user:
        print(f"📨 DM จาก {message.author.name} ({message.author.id}): {message.content}")
        
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
async def on_ready():
    print(f"✅ บอทออนไลน์แล้ว: {bot.user} (ID: {bot.user.id})")
    print(f"🌍 บอทพร้อมใช้งานใน: เซิร์ฟเวอร์, DM ส่วนตัว, และ Group DMs")
    
    # ✅ โหลดข้อมูลทั้งหมดเมื่อบอทเริ่มทำงาน
    global user_data, ticket_transcripts, transcript_counter
    user_data = load_user_data()
    ticket_transcripts = load_ticket_transcripts()
    
    # ✅ ตรวจสอบ transcript_counter
    if 'transcript_counter' not in globals():
        transcript_counter = {}
    
    # ✅ อัพเดทตัวนับจากห้องที่มีอยู่
    for guild in bot.guilds:
        archive_category = guild.get_channel(ARCHIVED_CATEGORY_ID)
        if archive_category:
            highest_number = 0
            for ch in archive_category.text_channels:
                if ch.name.startswith("transcript") or re.match(r"\d{10}-\d+-", ch.name):
                    try:
                        # ดึงหมายเลขจากรูปแบบใหม่ ddmmyytime-robux-ticketnumber-user
                        if re.match(r"\d{10}-\d+-", ch.name):
                            parts = ch.name.split('-')
                            if len(parts) >= 3 and parts[2].isdigit():
                                num = int(parts[2])
                                if num > highest_number:
                                    highest_number = num
                        # ดึงหมายเลขจากรูปแบบเก่า transcriptX-...
                        elif ch.name.startswith("transcript"):
                            num_str = ch.name.replace("transcript", "").split('-')[0]
                            if num_str.isdigit():
                                num = int(num_str)
                                if num > highest_number:
                                    highest_number = num
                    except:
                        continue
            
            transcript_counter[guild.id] = highest_number
            print(f"✅ ตั้งค่า transcript_counter สำหรับ {guild.name}: {highest_number}")
    
    print(f"✅ โหลดข้อมูลผู้ใช้: {len(user_data)} users")
    print(f"✅ โหลดประวัติตั๋ว: {len(ticket_transcripts)} tickets")
    print(f"✅ Transcript counter initialized")
    
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
    
    # ลงทะเบียน Views ด้วย custom_id
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
    
    # ✅ อัพเดทช่องเครดิตเมื่อบอทเริ่มทำงาน
    await update_credit_channel()
    
    print("\n🎯 บอทพร้อมใช้งานเต็มที่!")
    print("📨 ทดสอบใน DM เพื่อนโดย:")
    print("   1. เปิดแชทกับเพื่อน")
    print("   2. พิมพ์ '/' แล้วดูมีคำสั่งหรือไม่")
    print("   3. พิมพ์ '/help' ตรงๆ")

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
# ✅ ระบบติดตามกิจกรรมในตั๋ว
# =======================================================================================

async def check_stale_tickets():
    """ตรวจสอบตั๋วค้างที่ต้องย้าย"""
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
                        print(f"🔍 พบตั๋วค้างต้องย้าย: {channel.name} (ผ่านไป {time_since_activity.total_seconds()/60:.1f} นาที)")
                    channels_to_remove.append(channel_id)
        
        for channel_id in channels_to_remove:
            if channel_id in ticket_activity:
                del ticket_activity[channel_id]

# =======================================================================================
# ✅ คำสั่งจัดการข้อมูล
# =======================================================================================

@bot.command()
@admin_only()
async def backup_data(ctx):
    """สร้าง backup ข้อมูล"""
    try:
        save_user_data()
        save_ticket_transcripts()
        
        user_file_exists = os.path.exists(user_data_file)
        ticket_file_exists = os.path.exists(ticket_transcripts_file)
        
        embed = discord.Embed(
            title="✅ สร้าง backup ข้อมูลเรียบร้อยแล้ว",
            color=0x00FF00
        )
        embed.add_field(name="👥 ข้อมูลผู้ใช้", value="✅ บันทึกแล้ว" if user_file_exists else "❌ ไม่พบไฟล์", inline=True)
        embed.add_field(name="📝 ประวัติตั๋ว", value="✅ บันทึกแล้ว" if ticket_file_exists else "❌ ไม่พบไฟล์", inline=True)
        embed.add_field(name="📁 ไฟล์ backup", value="สร้างไฟล์ .backup แล้ว", inline=False)
        
        await ctx.send(embed=embed, delete_after=15)
    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=10)

@bot.command()
@admin_only()
async def data_status(ctx):
    """ตรวจสอบสถานะข้อมูล"""
    try:
        user_count = len(user_data)
        ticket_count = len(ticket_transcripts)
        
        user_file_size = os.path.getsize(user_data_file) if os.path.exists(user_data_file) else 0
        ticket_file_size = os.path.getsize(ticket_transcripts_file) if os.path.exists(ticket_transcripts_file) else 0
        
        user_file_exists = os.path.exists(user_data_file)
        ticket_file_exists = os.path.exists(ticket_transcripts_file)
        
        embed = discord.Embed(
            title="📊 สถานะข้อมูล",
            color=0x00FF99
        )
        embed.add_field(name="👥 จำนวนผู้ใช้", value=f"{user_count} users", inline=True)
        embed.add_field(name="📝 จำนวนตั๋วที่บันทึก", value=f"{ticket_count} tickets", inline=True)
        embed.add_field(name="💾 ไฟล์ข้อมูลผู้ใช้", 
                       value=f"✅ {user_file_size:,} bytes" if user_file_exists else "❌ ไม่พบไฟล์", 
                       inline=False)
        embed.add_field(name="📋 ไฟล์ประวัติตั๋ว", 
                       value=f"✅ {ticket_file_size:,} bytes" if ticket_file_exists else "❌ ไม่พบไฟล์", 
                       inline=False)
        embed.add_field(name="🕒 อัพเดทล่าสุด", 
                       value=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
                       inline=False)
        
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=10)

@bot.command()
@admin_only()
async def restore_backup(ctx, data_type: str = "all"):
    """กู้คืนข้อมูลจาก backup (all, user, ticket)"""
    try:
        user_msg = ""
        ticket_msg = ""
        
        if data_type.lower() in ["all", "user"]:
            backup_file = f"{user_data_file}.backup"
            if os.path.exists(backup_file):
                with open(backup_file, 'r', encoding='utf-8') as f:
                    global user_data
                    user_data = json.load(f)
                save_user_data()
                user_msg = "✅ กู้คืนข้อมูลผู้ใช้เรียบร้อย"
            else:
                user_msg = "❌ ไม่พบไฟล์ backup ข้อมูลผู้ใช้"
        
        if data_type.lower() in ["all", "ticket"]:
            backup_file = f"{ticket_transcripts_file}.backup"
            if os.path.exists(backup_file):
                with open(backup_file, 'r', encoding='utf-8') as f:
                    global ticket_transcripts
                    ticket_transcripts = json.load(f)
                save_ticket_transcripts()
                ticket_msg = "✅ กู้คืนประวัติตั๋วเรียบร้อย"
            else:
                ticket_msg = "❌ ไม่พบไฟล์ backup ประวัติตั๋ว"
        
        embed = discord.Embed(
            title="🔄 ผลการกู้คืนข้อมูล",
            color=0x00FF00
        )
        
        if data_type.lower() in ["all", "user"]:
            embed.add_field(name="👥 ข้อมูลผู้ใช้", value=user_msg, inline=False)
        if data_type.lower() in ["all", "ticket"]:
            embed.add_field(name="📝 ประวัติตั๋ว", value=ticket_msg, inline=False)
            
        await ctx.send(embed=embed, delete_after=15)
        
    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาดในการกู้คืน: {e}", delete_after=10)

# =======================================================================================
# ✅ คำสั่งอื่นๆ ที่เหลือ
# =======================================================================================

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
                   "`/tax <จำนวน>` - คำนวณ Robux หลังหักภาษี\n\n"
                   "**คำสั่งทั่วไป:**\n"
                   "`!level` - เช็คเลเวลและ EXP ของคุณ\n"
                   "`!rate <rate>` - เปลี่ยนเรท Gamepass\n"
                   "`!rate group <low> <high>` - เปลี่ยนเรท Group\n\n"
                   "**คำสั่งจัดการข้อมูล:**\n"
                   "`!backup_data` - สร้าง backup ข้อมูล\n"
                   "`!data_status` - ตรวจสอบสถานะข้อมูล\n"
                   "`!restore_backup <all/user/ticket>` - กู้คืนข้อมูลจาก backup\n\n"
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
# คำสั่งจัดการ Stock
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
            color=0x00FF99
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
            color=0x00FF99
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
    except Exception as e:
        print(f"⚠️ ไม่สามารถเปลี่ยนชื่อช่อง: {e}")
    
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
# ✅ SLASH COMMANDS
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

print("🚀 กำลังเริ่มต้นบอท...")

try:
    server_on()
    bot.run(os.getenv("TOKEN"))
except Exception as e:
    print(f"❌ เกิดข้อผิดพลาดร้ายแรง: {e}")
