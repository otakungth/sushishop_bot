import os
import datetime
import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import re
import asyncio
import json

# ตั้งค่าเรท (ค่าเริ่มต้น)
gamepass_rate = 6
group_rate_low = 4
group_rate_high = 4.5

# ตั้งค่าพื้นฐาน - แก้ไข Intents
intents = discord.Intents.all()
intents.message_content = True
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

# โหลดข้อมูลผู้ใช้จากไฟล์
def load_user_data():
    try:
        with open(user_data_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

# บันทึกข้อมูลผู้ใช้ลงไฟล์
def save_user_data():
    with open(user_data_file, 'w', encoding='utf-8') as f:
        json.dump(user_data, f, ensure_ascii=False, indent=2)

# โหลดข้อมูลผู้ใช้
user_data = load_user_data()

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

# สร้างบอทด้วยการตั้งค่าเพิ่มเติมสำหรับ User Install
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
            application_id=os.getenv("APPLICATION_ID")
        )

    async def setup_hook(self):
        """ตั้งค่าและซิงค์ global slash commands"""
        print("🔄 เริ่ม sync global slash commands ...")

        # ✅ เปิดให้ทุกคำสั่งใช้ใน DM ได้
        for cmd in self.tree.walk_commands():
            try:
                cmd.dm_permission = True
            except Exception as e:
                print(f"⚠️ ตั้งค่า DM permission ไม่ได้สำหรับ {cmd.name}: {e}")

        try:
            synced = await self.tree.sync()
            print(f"✅ Sync Global Commands สำเร็จ ({len(synced)} commands)")
            for c in synced:
                print(f"   - /{c.name}: {c.description}")
        except Exception as e:
            print(f"❌ Sync ล้มเหลว: {e}")

bot = MyBot()

print("🔄 กำลังเริ่มต้นบอท...")

# --------------------------------------------------------------------------------------------------
# Decorator สำหรับตรวจสอบสิทธิ์แอดมิน
def admin_only():
    async def predicate(ctx):
        # ถ้าเป็น DM ให้ปฏิเสธคำสั่งแอดมิน
        if isinstance(ctx.channel, discord.DMChannel):
            await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะในเซิร์ฟเวอร์เท่านั้น", delete_after=5)
            return False
            
        if ctx.author.guild_permissions.administrator:
            return True
        
        admin_role = ctx.guild.get_role(1361016912259055896)
        if admin_role and admin_role in ctx.author.roles:
            return True
            
        await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะผู้ดูแลระบบเท่านั้น", delete_after=5)
        return False
    return commands.check(predicate)

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
        channel = bot.get_channel(MAIN_CHANNEL_ID)
        if channel:
            if shop_open:
                new_name = "〔🟢เปิด〕กดสั่งซื้อที่นี่"
            else:
                new_name = "〔🔴〕ปิดชั่วคราว"
            
            # ตรวจสอบว่าชื่อช่องปัจจุบันต่างจากที่ต้องการหรือไม่
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
# ฟังก์ชันลบข้อความอัตโนมัติ
async def auto_delete_messages(ctx, bot_message, delay=60):
    """ลบข้อความผู้ใช้และบอทหลังจากเวลาที่กำหนด"""
    try:
        await asyncio.sleep(delay)
        
        try:
            await bot_message.delete()
        except:
            pass
            
        try:
            await ctx.message.delete()
        except:
            pass
            
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการลบข้อความ: {e}")

# --------------------------------------------------------------------------------------------------
# ฟังก์ชันส่งบันทึกการขาย
async def send_sale_log(embed_data: discord.Embed, interaction: discord.Interaction = None, ctx: commands.Context = None, delivered_by: discord.Member = None):
    """ส่ง Embed ไปยังห้องบันทึกการขาย"""
    try:
        channel = bot.get_channel(SALES_LOG_CHANNEL_ID)
        if channel is None:
            print("❌ ไม่พบห้องบันทึกการขาย")
            return

        # ดึงข้อมูลจาก embed
        robux_amount = "ไม่ทราบ"
        price = "ไม่ทราบ"
        
        for field in embed_data.fields:
            if field.name == "💸 จำนวนโรบัค":
                robux_amount = field.value
            elif field.name == "💰 ราคาตามเรท":
                price = field.value
            elif field.name == "💸 จำนวน Robux":
                robux_amount = field.value
            elif field.name == "💰 ราคา":
                price = field.value

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
        log_embed.add_field(name="💸 จำนวน Robux", value=robux_amount, inline=True)
        log_embed.add_field(name="💰 ราคา", value=price, inline=True)
        log_embed.set_footer(text="การสั่งซื้อสำเร็จ")

        await channel.send(embed=log_embed)
        print(f"✅ ส่งบันทึกการขาย: {sale_type} - {robux_amount} Robux - {price}")

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
# View สำหรับการดำเนินการในตั๋ว
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
# ฟังก์ชันจัดการการเปิดตั๋ว
async def handle_open_ticket(interaction, category_name, modal_class, stock_type):
    global gamepass_stock, group_stock
    
    try:
        # ตรวจสอบว่าเป็น DM หรือไม่
        if isinstance(interaction.channel, discord.DMChannel):
            await interaction.response.send_message("❌ การเปิดตั๋วต้องทำในเซิร์ฟเวอร์เท่านั้น กรุณาไปที่เซิร์ฟเวอร์ของเราเพื่อเปิดตั๋ว", ephemeral=True)
            return
            
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

        # ส่งข้อความแจ้ง admin ก่อน
        if admin_role:
            await channel.send(content=f"{admin_role.mention} มีตั๋วใหม่!")

        # แล้วค่อยส่ง embed ต้อนรับ
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

# --------------------------------------------------------------------------------------------------
# View สำหรับให้เครดิต
class GiveCreditView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(
                label="ให้เครดิตที่นี่⭐", 
                url="https://discord.com/channels/1360990259311018077/1363250076549382246", 
                style=discord.ButtonStyle.link,
                emoji="⭐"
            )
        )

# --------------------------------------------------------------------------------------------------
# View สำหรับ QR Code
class QRView(View):
    def __init__(self):
        super().__init__(timeout=None)
        
    @discord.ui.button(label="คัดลอกเลขบัญชี", style=discord.ButtonStyle.success, emoji="📋")
    async def copy_kbank(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("160-1-43871-9 (กสิกร)", ephemeral=True)
        
    @discord.ui.button(label="คัดลอกเบอร์ทรูมันนี่", style=discord.ButtonStyle.success, emoji="📋")
    async def copy_truemoney(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("065-506-0702", ephemeral=True)

# --------------------------------------------------------------------------------------------------
# ฟังก์ชันเช็คเลเวลผู้ใช้
async def check_user_level(interaction: discord.Interaction):
    """แสดงเลเวลและ EXP ของผู้ใช้"""
    try:
        user_id = str(interaction.user.id)
        
        if user_id not in user_data:
            user_data[user_id] = {"exp": 0, "level": 0}
            save_user_data()
        
        user_exp = user_data[user_id]["exp"]
        user_level = user_data[user_id]["level"]
        
        # ระดับปัจจุบัน
        if user_level == 0:
            current_display = "Level 0"
        else:
            current_role_id = LEVELS[user_level]["role_id"]
            current_display = f"<@&{current_role_id}>"
        
        # ระดับถัดไป
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
        
        # แสดงความคืบหน้า
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
        
        # ระดับปัจจุบัน
        if user_level == 0:
            current_display = "Level 0"
        else:
            current_role_id = LEVELS[user_level]["role_id"]
            current_display = f"<@&{current_role_id}>"
        
        # ระดับถัดไป
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
        
        # แสดงความคืบหน้า
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
# Main Shop View
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

# --------------------------------------------------------------------------------------------------
# ระบบติดตามกิจกรรมในตั๋ว
@bot.event
async def on_message(message):
    # ตรวจสอบว่าเป็น DM และไม่ใช่ข้อความจากบอทตัวเอง
    if isinstance(message.channel, discord.DMChannel) and message.author != bot.user:
        print(f"📨 DM จาก {message.author.name}: {message.content}")
        
        # ถ้าผู้ใช้พิมพ์ "/help" ใน DM
        if message.content.lower() in ["/help", "help", "คำสั่ง"]:
            help_embed = discord.Embed(
                title="🍣 Sushi Shop - คำสั่งใน DM",
                description=(
                    "**ขณะนี้ระบบ Slash Commands กำลังโหลด...**\n\n"
                    "**คำสั่งที่ใช้ได้:**\n"
                    "`/gamepass <จำนวน>` - คำนวณราคา Gamepass\n"
                    "`/group <จำนวน>` - คำนวณราคา Group\n"
                    "`/baht_gamepass <จำนวน>` - คำนวณ Robux จากเงินบาท\n"
                    "`/baht_group <จำนวน>` - คำนวณ Robux จากเงินบาท (Group)\n"
                    "`/tax <จำนวน>` - คำนวณ Robux หลังหักภาษี\n"
                    "`/exch <จำนวน>` - คำนวณอัตราแลกเปลี่ยน\n\n"
                    "**หมายเหตุ:**\n"
                    "• ถ้าไม่เห็นคำสั่งเมื่อพิมพ์ `/` ให้พิมพ์คำสั่งตรงๆ ได้เลย\n"
                    "• ระบบอาจใช้เวลา 1-2 ชั่วโมงในการโหลดคำสั่งเต็มที่\n"
                    "• การสั่งซื้อจริงต้องทำในเซิร์ฟเวอร์เท่านั้น"
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

# --------------------------------------------------------------------------------------------------
# ฟังก์ชันตรวจสอบตั๋วที่ค้าง
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

# --------------------------------------------------------------------------------------------------
# อัปเดตช่องหลัก
async def update_main_channel():
    """อัปเดตข้อความในช่องหลักโดยการ edit ข้อความเดิม"""
    try:
        channel = bot.get_channel(MAIN_CHANNEL_ID)
        if not channel:
            print("❌ ไม่พบช่องหลัก")
            return

        # หา embed ล่าสุดของบอทในช่องนี้
        target_message = None
        async for msg in channel.history(limit=100):
            if msg.author == bot.user and msg.embeds:
                if msg.embeds and len(msg.embeds) > 0:
                    embed_title = msg.embeds[0].title or ""
                    if "Sushi Shop" in embed_title:
                        target_message = msg
                        break
        
        # สร้าง embed ใหม่ด้วยสีส้ม (0xFFA500)
        embed = discord.Embed(
            title="🍣 Sushi Shop 🍣 เปิดให้บริการ",
            color=0xFFA500,  # สีส้ม
            timestamp=discord.utils.utcnow()
        )
        
        # ส่วน Gamepass
        gamepass_stock_status = "🟢 พร้อมให้บริการ" if gamepass_stock > 0 else "🔴 สินค้าหมด"
        embed.add_field(
            name="🎮 **บริการกดเกมพาส**",
            value=(
                "```\n"
                f"เรท: {gamepass_rate} | โรแท้ซื้อยัดกลุ่มได้\n"
                "พิมพ์ !gp ตามด้วยจำนวนเพื่อเช็คราคาได้\n"
                "```\n"
                f"📊 Stock: **{gamepass_stock}** ({gamepass_stock_status})\n"
            ),
            inline=False
        )
        
        # ส่วน Group
        group_stock_status = "🟢 พร้อมให้บริการ" if group_stock > 0 else "🔴 สินค้าหมด"
        
        group_value = (
            "```\n"
            f"เรท: {group_rate_low}-{group_rate_high} | 500 บาทขึ้นไปเรท 4.5 \n"
            "⚠️ต้องเข้ากลุ่ม 15 วันก่อนซื้อ⚠️\n"
            "```\n"
            f"📌 กดเข้ากลุ่มนี้ : :point_right: [VALKYs](https://www.roblox.com/communities/34713179/VALKYs) :point_left: \n"
            "📝เข้ากลุ่มแล้วจดวันที่เข้ากลุ่มด้วย\n"
            f"📊 Stock: **{group_stock}** ({group_stock_status})\n"
        )
        
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

# --------------------------------------------------------------------------------------------------
# SLASH COMMANDS - สำหรับ User Install (ใช้ใน DM ได้)
# --------------------------------------------------------------------------------------------------

@bot.tree.command(name="gamepass", description="คำนวณราคา Gamepass", dm_permission=True)
async def gamepass(interaction: discord.Interaction, amount: int):
    rate = 6
    price = amount / rate
    await interaction.response.send_message(
        f"🎮 {amount:,} Robux = **{price:,.0f} บาท** (เรท {rate})",
        ephemeral=False
    )

@bot.tree.command(name="group", description="คำนวณราคา Group", dm_permission=True)
async def group(interaction: discord.Interaction, amount: int):
    rate = 4.5 if amount >= 1500 else 4
    price = amount / rate
    await interaction.response.send_message(
        f"👥 {amount:,} Robux = **{price:,.0f} บาท** (เรท {rate})",
        ephemeral=False
    )

@bot.tree.command(name="baht_gamepass", description="คำนวณ Robux จากเงินบาท (Gamepass)", dm_permission=True)
async def baht_gamepass(interaction: discord.Interaction, baht: float):
    rate = 6
    robux = baht * rate
    await interaction.response.send_message(
        f"💰 {baht:,.0f} บาท = **{robux:,.0f} Robux** (Gamepass เรท {rate})",
        ephemeral=False
    )

@bot.tree.command(name="baht_group", description="คำนวณ Robux จากเงินบาท (Group)", dm_permission=True)
async def baht_group(interaction: discord.Interaction, baht: float):
    rate = 4.5 if baht >= 500 else 4
    robux = baht * rate
    await interaction.response.send_message(
        f"💰 {baht:,.0f} บาท = **{robux:,.0f} Robux** (Group เรท {rate})",
        ephemeral=False
    )

@bot.tree.command(name="tax", description="คำนวณ Robux หลังหักภาษี", dm_permission=True)
async def tax(interaction: discord.Interaction, robux: int):
    after_tax = robux * 0.7
    await interaction.response.send_message(
        f"💸 {robux:,} Robux หลังหักภาษี 30% = **{after_tax:,.0f} Robux**",
        ephemeral=False
    )

@bot.tree.command(name="exch", description="คำนวณอัตราแลกเปลี่ยน (เรท 34)")
async def exch_slash(interaction: discord.Interaction, amount: str):
    """คำสั่งคำนวณอัตราแลกเปลี่ยน เรท 34"""
    try:
        is_dm = isinstance(interaction.channel, discord.DMChannel)
        
        expr = amount.replace(",", "").replace(" ", "").lower().replace("x", "*").replace("÷", "/")

        if not re.match(r"^[\d\s\+\-\*\/\(\)\.]+$", expr):
            await interaction.response.send_message("❌ กรุณาใส่เฉพาะตัวเลข และเครื่องหมาย + - * / x ÷ () และจุดทศนิยม", ephemeral=not is_dm)
            return

        baht = float(eval(expr))
        exchange_rate = 34
        result = baht * exchange_rate

        response_msg = f"💱 {baht:,.2f} บาท × {exchange_rate} = **{result:,.2f}**"
        await interaction.response.send_message(response_msg, ephemeral=not is_dm)

    except ZeroDivisionError:
        await interaction.response.send_message("❌ ไม่สามารถหารด้วยศูนย์ได้", ephemeral=True)
    except ValueError:
        await interaction.response.send_message("❌ กรุณากรอกตัวเลขที่ถูกต้อง", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {str(e)}", ephemeral=True)

@bot.tree.command(name="exch_custom", description="คำนวณอัตราแลกเปลี่ยนแบบกำหนดเรทเอง")
async def exch_custom_slash(interaction: discord.Interaction, amount: str, rate: str):
    """คำสั่งคำนวณอัตราแลกเปลี่ยนแบบกำหนดเรทเอง"""
    try:
        is_dm = isinstance(interaction.channel, discord.DMChannel)
        
        amount_expr = amount.replace(",", "").replace(" ", "").lower().replace("x", "*").replace("÷", "/")
        rate_expr = rate.replace(",", "").replace(" ", "").lower().replace("x", "*").replace("÷", "/")

        if not re.match(r"^[\d\s\+\-\*\/\(\)\.]+$", amount_expr) or not re.match(r"^[\d\s\+\-\*\/\(\)\.]+$", rate_expr):
            await interaction.response.send_message("❌ กรุณาใส่เฉพาะตัวเลข และเครื่องหมาย + - * / x ÷ () และจุดทศนิยม", ephemeral=not is_dm)
            return

        baht = float(eval(amount_expr))
        exchange_rate = float(eval(rate_expr))
        result = baht * exchange_rate

        response_msg = f"💱 {baht:,.2f} บาท × {exchange_rate} = **{result:,.2f}**"
        await interaction.response.send_message(response_msg, ephemeral=not is_dm)

    except ZeroDivisionError:
        await interaction.response.send_message("❌ ไม่สามารถหารด้วยศูนย์ได้", ephemeral=True)
    except ValueError:
        await interaction.response.send_message("❌ กรุณากรอกตัวเลขที่ถูกต้อง", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {str(e)}", ephemeral=True)

# เพิ่มคำสั่ง help สำหรับ slash command
@bot.tree.command(name="help", description="แสดงคำสั่งทั้งหมดที่ใช้ได้", dm_permission=True)
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🍣 Sushi Shop - คำสั่งทั้งหมด",
        description=(
            "ใช้ได้ทั้งในเซิร์ฟเวอร์และ DM\n\n"
            "`/gamepass <จำนวน>` - คำนวณราคา Gamepass\n"
            "`/group <จำนวน>` - คำนวณราคา Group\n"
            "`/baht_gamepass <จำนวน>` - คำนวณ Robux จากเงินบาท (Gamepass)\n"
            "`/baht_group <จำนวน>` - คำนวณ Robux จากเงินบาท (Group)\n"
            "`/tax <จำนวน>` - คำนวณ Robux หลังหักภาษี\n"
        ),
        color=0x00FF99
    )
    await interaction.response.send_message(embed=embed, ephemeral=False)

# เพิ่มคำสั่งตรวจสอบการติดตั้ง
@bot.tree.command(name="install_info", description="ตรวจสอบการติดตั้งบอท")
async def install_info(interaction: discord.Interaction):
    """ตรวจสอบว่าบอทติดตั้งแบบ User Install หรือไม่"""
    is_dm = isinstance(interaction.channel, discord.DMChannel)
    
    embed = discord.Embed(
        title="🔧 ข้อมูลการติดตั้งบอท",
        color=0x00FF99
    )
    
    embed.add_field(
        name="ช่องทาง", 
        value="DM" if is_dm else "เซิร์ฟเวอร์", 
        inline=True
    )
    
    embed.add_field(
        name="ผู้ใช้", 
        value=interaction.user.display_name, 
        inline=True
    )
    
    embed.add_field(
        name="สถานะ", 
        value="✅ User Install ทำงานได้" if is_dm else "🔄 Guild Install", 
        inline=False
    )
    
    if is_dm:
        embed.add_field(
            name="คำแนะนำ",
            value="คุณสามารถใช้คำสั่ง slash (/) ทั้งหมดได้ใน DM นี้!",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=not is_dm)

# --------------------------------------------------------------------------------------------------
# Events
async def on_ready():
    print(f"✅ บอทออนไลน์แล้ว: {bot.user} (ID: {bot.user.id})")
    print(f"✅ Prefix: {bot.command_prefix}")
    print(f"✅ Guilds: {len(bot.guilds)}")

    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="ร้าน Sushi Shop | พิมพ์ /help"
        )
    )

    print("✅ ตั้งค่าสถานะเรียบร้อย")
    print("🎯 บอทพร้อมใช้งานแล้ว! ทดสอบใน DM โดยพิมพ์ /help")
    
# --------------------------------------------------------------------------------------------------
# TEXT COMMANDS - ใช้ในเซิร์ฟเวอร์เท่านั้น
# --------------------------------------------------------------------------------------------------

@bot.command()
async def gp(ctx, *, expression: str):
    """คำสั่งคำนวณราคา Gamepass (Text Command)"""
    try:
        # ตรวจสอบว่าเป็น DM หรือไม่
        if isinstance(ctx.channel, discord.DMChannel):
            await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะในเซิร์ฟเวอร์เท่านั้น ใช้ `/gamepass` แทน", delete_after=10)
            return
            
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
        # ตรวจสอบว่าเป็น DM หรือไม่
        if isinstance(ctx.channel, discord.DMChannel):
            await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะในเซิร์ฟเวอร์เท่านั้น ใช้ `/group` แทน", delete_after=10)
            return
            
        expr = expression.replace(",", "").lower().replace("x", "*").replace("÷", "/")

        if not re.match(r"^[\d\s\+\-\*\/\(\)]+$", expr):
            await ctx.send("❌ กรุณาใส่เฉพาะตัวเลข และเครื่องหมาย + - * / x ÷ ()", delete_after=10)
            return

        robux = int(eval(expr))

        if robux < 1500:
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
        # ตรวจสอบว่าเป็น DM หรือไม่
        if isinstance(ctx.channel, discord.DMChannel):
            await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะในเซิร์ฟเวอร์เท่านั้น ใช้ `/baht_gamepass` แทน", delete_after=10)
            return
            
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
        # ตรวจสอบว่าเป็น DM หรือไม่
        if isinstance(ctx.channel, discord.DMChannel):
            await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะในเซิร์ฟเวอร์เท่านั้น ใช้ `/baht_group` แทน", delete_after=10)
            return
            
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
        # ตรวจสอบว่าเป็น DM หรือไม่
        if isinstance(ctx.channel, discord.DMChannel):
            await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะในเซิร์ฟเวอร์เท่านั้น ใช้ `/tax` แทน", delete_after=10)
            return
            
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

# --------------------------------------------------------------------------------------------------
# Events
@bot.event
async def on_ready():
    print(f"✅ บอทออนไลน์แล้ว: {bot.user} (ID: {bot.user.id})")
    print(f"✅ Prefix: {bot.command_prefix}")
    print(f"✅ Guilds: {len(bot.guilds)}")
    
    # ตรวจสอบว่าเป็นบอทที่ถูกต้อง
    print(f"✅ Bot Name: {bot.user.name}")
    print(f"✅ Bot Discriminator: {bot.user.discriminator}")
    
    # Force global sync
    try:
        print("🔄 Force syncing global commands...")
        await bot.tree.sync()
        print("✅ Global commands synced!")
    except Exception as e:
        print(f"❌ Sync error: {e}")
    
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
    
    print("\n🎯 บอทพร้อมใช้งานเต็มที่!")
    print("📨 ทดสอบใน DM โดย:")
    print("   1. พิมพ์ '/' แล้วดูมีคำสั่งหรือไม่")
    print("   2. พิมพ์ '/help' ตรงๆ")
    print("   3. พิมพ์ 'help' เพื่อดูคำสั่งแบบด่วน")

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
                   "`/exch <จำนวน>` - คำนวณอัตราแลกเปลี่ยน (เรท 33.5)\n"
                   "`/exch_custom <จำนวน> <เรท>` - คำนวณอัตราแลกเปลี่ยนแบบกำหนดเรท\n"
                   "`/install_info` - ตรวจสอบการติดตั้งบอท\n\n"
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
        # ส่ง embed แสดง stock ปัจจุบัน
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
        # ลบหลังจาก 10 วินาที
        await asyncio.sleep(10)
        try:
            await response_msg.delete()
        except:
            pass
        
    elif stock_type.lower() in ["gp", "gamepass", "เกมพาส"]:
        if amount is None:
            # ส่ง embed แสดง stock ปัจจุบัน
            embed = discord.Embed(
                title="🎮 Gamepass Stock",
                description=f"**{gamepass_stock:,}**",
                color=0x00FF99
            )
            response_msg = await ctx.send(embed=embed)
            # ลบหลังจาก 10 วินาที
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
                
                # ส่งข้อความตอบกลับชั่วคราว
                embed = discord.Embed(
                    title="✅ ตั้งค่า Stock เรียบร้อย",
                    description=f"ตั้งค่า สต๊อกเกมพาส เป็น **{gamepass_stock:,}** เรียบร้อยแล้ว",
                    color=0x00FF00
                )
                
                response_msg = await ctx.send(embed=embed)
                
                # อัปเดตช่องหลักแบบไม่แจ้งเตือน
                await update_main_channel()
                
                # ลบข้อความตอบกลับหลังจาก 5 วินาที
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
            # ส่ง embed แสดง stock ปัจจุบัน
            embed = discord.Embed(
                title="👥 Group Stock",
                description=f"**{group_stock:,}**",
                color=0x00FF99
            )
            response_msg = await ctx.send(embed=embed)
            # ลบหลังจาก 10 วินาที
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
                
                # ส่งข้อความตอบกลับชั่วคราว
                embed = discord.Embed(
                    title="✅ ตั้งค่า Stock เรียบร้อย",
                    description=f"ตั้งค่า สต๊อกโรบัคกลุ่ม เป็น **{group_stock:,}** เรียบร้อยแล้ว",
                    color=0x00FF00
                )
                
                response_msg = await ctx.send(embed=embed)
                
                # อัปเดตช่องหลักแบบไม่แจ้งเตือน
                await update_main_channel()
                
                # ลบข้อความตอบกลับหลังจาก 5 วินาที
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
        # ลบหลังจาก 10 วินาที
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
        # แสดงเรทปัจจุบัน
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
            
            # อัปเดตช่องหลัก
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
        # เปลี่ยนเรท Gamepass
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
            
            # อัปเดตช่องหลัก
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
    
    # ส่งข้อความและบันทึก reference เพื่อลบภายหลัง
    status_msg = await ctx.send(embed=embed)
    
    # อัปเดตชื่อช่องหลัก
    await update_channel_name()
    
    # อัปเดต embed หลัก
    await update_main_channel()
    
    # ลบข้อความสถานะหลังจาก 5 วินาที
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
# คำสั่ง !od - Gamepass
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

        # เพิ่ม EXP ให้ผู้ซื้อ (1 Robux = 1 EXP)
        exp_to_add = robux
        if buyer:
            new_level, total_exp = await add_exp(buyer.id, exp_to_add, ctx.guild)
            print(f"✅ เพิ่ม {exp_to_add} EXP ให้ {buyer.display_name} (เลเวล {new_level}, รวม {total_exp} EXP)")
        else:
            print("⚠️ ไม่พบผู้ซื้อในการเพิ่ม EXP")

        gamepass_stock -= robux
        if gamepass_stock < 0:
            gamepass_stock = 0
        
        # ใบเสร็จที่ไม่แสดงชื่อผู้ซื้อและผู้ส่ง แต่แสดง EXP
        embed = discord.Embed(
            title="🍣 ใบเสร็จคำสั่งซื้อ Gamepass 🍣",
            color=0x00FF99,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="💸 จำนวนโรบัค", value=f"{robux:,}", inline=True)
        embed.add_field(name="💰 ราคาตามเรท", value=price_str, inline=True)
        
        if buyer:
            embed.add_field(name="⭐ ได้รับ EXP", value=f"{exp_to_add:,} EXP", inline=True)
        
        embed.set_footer(text="การสั่งซื้อสำเร็จ")

        await ctx.send(embed=embed)

        # ส่งบันทึกการขาย (ไม่แสดงชื่อ)
        await send_sale_log(embed, ctx=ctx)

        await update_main_channel()

    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=10)

# --------------------------------------------------------------------------------------------------
# คำสั่ง !odg - Group
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

        # เพิ่ม EXP ให้ผู้ซื้อ (1 Robux = 1 EXP)
        exp_to_add = robux
        if buyer:
            new_level, total_exp = await add_exp(buyer.id, exp_to_add, ctx.guild)
            print(f"✅ เพิ่ม {exp_to_add} EXP ให้ {buyer.display_name} (เลเวล {new_level}, รวม {total_exp} EXP)")
        else:
            print("⚠️ ไม่พบผู้ซื้อในการเพิ่ม EXP")

        group_stock -= robux
        if group_stock < 0:
            group_stock = 0
        
        # ใบเสร็จที่ไม่แสดงชื่อผู้ซื้อและผู้ส่ง แต่แสดง EXP
        embed = discord.Embed(
            title="🍣 ใบเสร็จคำสั่งซื้อโรบัคกลุ่ม 🍣",
            color=0x00AAFF,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="💸 จำนวนโรบัค", value=f"{robux:,}", inline=True)
        embed.add_field(name="💰 ราคาตามเรท", value=price_str, inline=True)
        
        if buyer:
            embed.add_field(name="⭐ ได้รับ EXP", value=f"{exp_to_add:,} EXP", inline=True)
        
        embed.set_footer(text="การสั่งซื้อสำเร็จ • Robux Group")

        await ctx.send(embed=embed)

        # ส่งบันทึกการขาย (ไม่แสดงชื่อ)
        await send_sale_log(embed, ctx=ctx)

        await update_main_channel()

    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=10)
        
# --------------------------------------------------------------------------------------------------
# คำสั่ง !odl - Limited
@bot.command()
@admin_only()
async def odl(ctx, item_name: str, value: str):
    try:
        value_clean = value.replace(",", "")
        
        if not re.match(r"^\d+$", value_clean):
            await ctx.send("❌ กรุณากรอกราคาเป็นตัวเลขที่ถูกต้อง", delete_after=10)
            return

        item_value = int(value_clean)

        # หาผู้ซื้อจากชื่อตั๋ว
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

        # เพิ่ม EXP ให้ผู้ซื้อ (1 บาท = 1 EXP)
        exp_to_add = item_value
        if buyer:
            new_level, total_exp = await add_exp(buyer.id, exp_to_add, ctx.guild)
            print(f"✅ เพิ่ม {exp_to_add} EXP ให้ {buyer.display_name} (เลเวล {new_level}, รวม {total_exp} EXP)")
        else:
            print("⚠️ ไม่พบผู้ซื้อในการเพิ่ม EXP")

        # ใบเสร็จที่ไม่แสดงชื่อผู้ซื้อและผู้ส่ง
        embed = discord.Embed(
            title="🍣 ใบเสร็จคำสั่งซื้อ Limited 🍣",
            color=0xFF69B4,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="🎁 ชื่อไอเทม", value=item_name, inline=True)
        embed.add_field(name="💰 ราคา (บาท)", value=f"{item_value:,}", inline=True)
        
        if buyer:
            embed.add_field(name="⭐ ได้รับ EXP", value=f"{exp_to_add:,} EXP", inline=True)
        
        embed.set_footer(text="การสั่งซื้อสำเร็จ • Limited")

        await ctx.send(embed=embed)

        # ส่งบันทึกการขาย (ไม่แสดงชื่อ)
        await send_sale_log(embed, ctx=ctx)

    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=10)

# --------------------------------------------------------------------------------------------------
# คำสั่ง !level
@bot.command()
async def level(ctx, member: discord.Member = None):
    if member is None:
        member = ctx.author
    
    await check_user_level_as_command(ctx, member)

# --------------------------------------------------------------------------------------------------
# คำสั่ง !qr
@bot.command()
@admin_only()
async def qr(ctx):
    try:
        await ctx.message.delete()
    except:
        pass
    
    embed = discord.Embed(
        title="📱 สแกน QR เพื่อชำระเงิน",
        color=0x00CCFF
    )
    embed.set_image(url="https://media.discordapp.net/attachments/722832040860319835/1402994996600111114/186-8-06559-8.png")
    
    await ctx.send(embed=embed, view=QRView())

# --------------------------------------------------------------------------------------------------
# คำสั่ง !ty
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
                    
                await interaction.response.send_message("📪 กำลังปิดตั๋ว...", ephemeral=True)
                try:
                    await self.channel.delete()
                except:
                    pass

        credit_view = GiveCreditView()
        
        embed = discord.Embed(
            title="✅ สินค้าถูกส่งเรียบร้อยแล้ว",
            description=(
                "ขอบคุณที่ใช้บริการกับเรา หากไม่มีปัญหาเพิ่มเติมสามารถกดปุ่มปิดตั๋วได้เลย\n\n"
                "⏳ หากไม่ได้กดปิดตั๋วเอง ตั๋วจะถูกปิดอัตโนมัติใน 10 นาที"
            ),
            color=0x00FF00
        )
        
        await ctx.send(embed=embed, view=TempCloseView(ctx.channel))
        await ctx.send("กดปุ่มด้านล่างเพื่อให้เครดิตกับผู้ส่งสินค้า:", view=credit_view)

        ticket_activity[ctx.channel.id] = {
            'last_activity': datetime.datetime.now(),
            'ty_used': True,
            'ty_time': datetime.datetime.now()
        }
        
        await start_auto_close_countdown(ctx.channel)
        
    else:
        await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะในตั๋วเท่านั้น", delete_after=5)

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
async def resync(ctx):
    """รี sync คำสั่งทั้งหมดใหม่"""
    try:
        # Sync ใหม่
        await bot.tree.sync()
        global_synced = await bot.tree.sync(guild=None)
        
        await ctx.send(f"✅ รี sync คำสั่งเรียบร้อย! Global: {len(global_synced)} commands")
    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")

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
            # ทดสอบส่งให้ตัวเอง
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
# เริ่มต้นบอท
print("🚀 กำลังเริ่มต้นบอท...")
try:
    # เรียกใช้ฟังก์ชัน server_on ถ้ามี
    try:
        from server import server_on
        server_on()
    except ImportError:
        print("ℹ️ ไม่พบ server_on function, ข้ามไป...")
    
    # ดึง token จาก environment variable
    bot.run(os.getenv("DISCORD_TOKEN"))
    if not token:
        print("❌ ไม่พบ TOKEN ใน environment variables")
        exit(1)
    
    bot.run(token)
except Exception as e:
    print(f"❌ เกิดข้อผิดพลาดร้ายแรง: {e}")
    





