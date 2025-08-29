import os
import datetime
import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput

# ตั้งค่าพื้นฐาน
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
shop_open = True
group_open = True

# ห้องบันทึกการขาย
SALES_LOG_CHANNEL_ID = 1402993077643120720
GAMEPASS_CHANNEL_ID = 1361044752975532152
GROUP_CHANNEL_ID = 1361554847526162532

bot_instance = None

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.has_started = False

    async def on_ready(self):
        if not self.has_started:
            self.has_started = True
            print(f"✅ บอทออนไลน์แล้ว: {self.user}")
            await self.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="ร้าน Sushi Shop"))
            await self.register_commands()

    async def register_commands(self):
        self.tree.clear_commands(guild=None)
        try:
            await self.tree.sync()
            print("✅ ซิงค์คำสั่งเสร็จสิ้น")
        except Exception as e:
            print(f"⚠️ ไม่สามารถซิงค์คำสั่ง: {e}")

bot = MyBot()

# --------------------------------------------------------------------------------------------------
# ฟังก์ชันคำนวณราคา
def calculate_price(expression: str) -> tuple:
    try:
        expression = expression.replace('×', '*').replace('x', '*').replace('÷', '/')
        allowed_chars = set('0123456789+-*/. ')
        if not all(c in allowed_chars for c in expression):
            return None, "❌ นิพจน์ไม่ถูกต้อง กรุณาใช้เฉพาะตัวเลขและสัญลักษณ์ทางคณิตศาสตร์"
        result = eval(expression)
        price = result / 7
        return result, f"{price:,.0f} บาท"
    except ZeroDivisionError:
        return None, "❌ ไม่สามารถหารด้วยศูนย์ได้"
    except Exception as e:
        return None, f"❌ เกิดข้อผิดพลาดในการคำนวณ: {str(e)}"

# --------------------------------------------------------------------------------------------------
@bot.command()
async def gp(ctx, *, expression: str):
    try:
        await ctx.message.delete()
    except:
        pass
    robux_amount, price = calculate_price(expression)
    if robux_amount is None:
        await ctx.send(price, delete_after=10)
        return
    embed = discord.Embed(title="🧮 ผลการคำนวณ", color=0x00FF99, timestamp=discord.utils.utcnow())
    embed.add_field(name="💸 จำนวน Robux", value=f"{robux_amount:,.0f}", inline=True)
    embed.add_field(name="💰 ราคาตามเรท 7", value=price, inline=True)
    embed.add_field(name="📝 นิพจน์", value=expression, inline=False)
    embed.set_footer(text=f"คำนวณโดย {ctx.author.display_name}")
    await ctx.send(embed=embed, delete_after=30)

# --------------------------------------------------------------------------------------------------
async def send_sale_log(embed_data: discord.Embed, interaction: discord.Interaction = None, ctx: commands.Context = None, delivered_by: discord.Member = None):
    try:
        channel = bot.get_channel(SALES_LOG_CHANNEL_ID)
        if channel is None:
            print("❌ ไม่พบห้องบันทึกการขาย")
            return

        robux_amount = next((f.value for f in embed_data.fields if "Robux" in f.name), "ไม่ทราบข้อมูล")
        price = next((f.value for f in embed_data.fields if "ราคา" in f.name), "ไม่ทราบข้อมูล")

        sale_type = "ไม่ทราบ"
        current_channel = interaction.channel if interaction else ctx.channel
        if current_channel and current_channel.category:
            cname = current_channel.category.name.lower()
            if "gamepass" in cname:
                sale_type = "Robux Gamepass"
            elif "group" in cname:
                sale_type = "Robux Group"

        ticket_creator = None
        if current_channel.name.startswith("ticket-"):
            try:
                user_id = int(current_channel.name.split("-")[-1])
                ticket_creator = await current_channel.guild.fetch_member(user_id)
            except:
                pass

        log_embed = discord.Embed(title="🍣 บันทึกการขายสำเร็จ 🍣", color=0x00FF00, timestamp=discord.utils.utcnow())
        log_embed.add_field(name="📦 ประเภทสินค้า", value=sale_type, inline=False)
        log_embed.add_field(name="😊 ผู้ซื้อ", value=ticket_creator.mention if ticket_creator else "ไม่ทราบ", inline=False)
        log_embed.add_field(name="💸 จำนวน Robux", value=robux_amount, inline=True)
        log_embed.add_field(name="💰 ราคา", value=price, inline=True)
        if delivered_by:
            log_embed.add_field(name="🚚 ผู้ส่งสินค้า", value=delivered_by.mention, inline=False)
        log_embed.set_footer(text="การสั่งซื้อสำเร็จ")
        await channel.send(embed=log_embed)
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการส่งบันทึกการขาย: {e}")

# --------------------------------------------------------------------------------------------------
class OpenTicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.update_button()

    def update_button(self):
        self.clear_items()
        if shop_open:
            self.add_item(Button(label="เปิดตั๋ว Robux Gamepass", style=discord.ButtonStyle.success, custom_id="open_ticket"))
        else:
            self.add_item(Button(label="❌ ร้านปิดชั่วคราว", style=discord.ButtonStyle.danger, disabled=True))

class TicketInfoModal(Modal, title="📋 แบบฟอร์มสั่งสินค้า"):
    map_name = TextInput(label="🗺 ชื่อแมพที่จะกด?", placeholder="พิมพ์ชื่อแมพ เช่น All Star Tower Defense X", required=True)
    gamepass_name = TextInput(label="💸 กดเกมพาสอะไร?", placeholder="พิมพ์ชื่อเกมพาส เช่น x3 Speed 3 ชิ้น", required=True)
    robux_amount = TextInput(label="🎟 รวมทั้งหมดกี่ Robux?", placeholder="พิมพ์จำนวนRobux เช่น 995", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            robux = int(self.robux_amount.value)
            price = robux / 7
            price_str = f"{price:,.0f} บาท"
            customer_embed = discord.Embed(title="📨 รายละเอียดการสั่งซื้อ", color=0x00FF99)
            customer_embed.add_field(name="🗺️ แมพ", value=self.map_name.value, inline=False)
            customer_embed.add_field(name="🎟 เกมพาส", value=self.gamepass_name.value, inline=False)
            customer_embed.add_field(name="💸 จำนวน Robux", value=self.robux_amount.value, inline=True)
            customer_embed.add_field(name="💰 ราคา", value=price_str, inline=True)
            customer_embed.set_footer(text=f"🧾 ผู้ใช้: {interaction.user}")
            await interaction.response.send_message(embed=customer_embed, ephemeral=False)
        except ValueError:
            await interaction.response.send_message("❌ กรุณากรอกจำนวน Robux เป็นตัวเลข", ephemeral=True)

class TicketFullActionView(View):
    def __init__(self, channel: discord.TextChannel, owner: discord.Member):
        super().__init__(timeout=None)
        self.channel = channel
        self.owner = owner

    @discord.ui.button(label="📝 กรอกแบบฟอร์ม", style=discord.ButtonStyle.primary)
    async def open_form(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(TicketInfoModal())

# --------------------------------------------------------------------------------------------------
# ฟังก์ชันเปิดตั๋ว
async def handle_open_ticket(interaction, category_name, view_class, mention_user):
    try:
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name=category_name)
        if not category:
            await interaction.response.send_message("❌ ไม่พบหมวดหมู่ที่กำหนด", ephemeral=True)
            return
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        channel = await category.create_text_channel(name=f"ticket-{interaction.user.id}", overwrites=overwrites)
        welcome_msg = f"👋 {interaction.user.mention} ยินดีต้อนรับสู่ตั๋วของคุณ!" if mention_user else "👋 ยินดีต้อนรับสู่ตั๋วของคุณ!"
        embed = discord.Embed(title="🎫 ตั๋วถูกเปิดแล้ว", description="กรุณากรอกข้อมูลด้านล่างเพื่อดำเนินการต่อ", color=0x00FF00)
        await channel.send(welcome_msg, embed=embed, view=view_class(channel, interaction.user))
        await interaction.response.send_message(f"✅ เปิดตั๋วเรียบร้อยแล้ว: {channel.mention}", ephemeral=True)
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการเปิดตั๋ว: {e}")
        await interaction.response.send_message("❌ เกิดข้อผิดพลาดในการเปิดตั๋ว", ephemeral=True)

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if not interaction.data:
        return
    custom_id = interaction.data.get("custom_id")
    if custom_id == "open_ticket":
        await handle_open_ticket(interaction, "🍣Sushi Gamepass 🍣", TicketFullActionView, True)
    elif custom_id == "open_group_ticket":
        await handle_open_ticket(interaction, "Robux Group", GroupTicketFullActionView, True)

# --------------------------------------------------------------------------------------------------
# View และ Modal สำหรับ Robux Group
class OpenGroupTicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.update_button()

    def update_button(self):
        self.clear_items()
        if group_open:
            self.add_item(Button(label="เปิดตั๋ว Robux Group", style=discord.ButtonStyle.success, custom_id="open_group_ticket"))
        else:
            self.add_item(Button(label="❌ ร้านปิดชั่วคราว", style=discord.ButtonStyle.danger, disabled=True))

class GroupTicketFullActionView(View):
    def __init__(self, channel: discord.TextChannel, owner: discord.Member):
        super().__init__(timeout=None)
        self.channel = channel
        self.owner = owner

    @discord.ui.button(label="📝 กรอกแบบฟอร์ม Group", style=discord.ButtonStyle.primary)
    async def open_form(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(GroupTicketInfoModal())

class GroupTicketInfoModal(Modal, title="📋 แบบฟอร์ม Robux Group"):
    user_name = TextInput(label="🪪 ชื่อในเกม", placeholder="พิมพ์ชื่อในเกมของคุณ", required=True)
    group_name = TextInput(label="👥 ชื่อกลุ่ม", placeholder="พิมพ์ชื่อกลุ่มที่ต้องการซื้อ", required=True)
    robux_amount = TextInput(label="🎟 จำนวน Robux", placeholder="พิมพ์จำนวน Robux ที่ต้องการ", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            robux = int(self.robux_amount.value)
            rate = 4.5 if robux < 500 else 5
            price = robux / rate
            price_str = f"{price:,.0f} บาท"
            customer_embed = discord.Embed(title="📨 รายละเอียดการสั่งซื้อ Group", color=0x00AAFF)
            customer_embed.add_field(name="🪪 ชื่อในเกม", value=self.user_name.value, inline=False)
            customer_embed.add_field(name="👥 ชื่อกลุ่ม", value=self.group_name.value, inline=False)
            customer_embed.add_field(name="💸 จำนวน Robux", value=self.robux_amount.value, inline=True)
            customer_embed.add_field(name="💰 ราคา", value=price_str, inline=True)
            customer_embed.set_footer(text=f"🧾 ผู้ใช้: {interaction.user}")
            await interaction.response.send_message(embed=customer_embed, ephemeral=False)
        except ValueError:
            await interaction.response.send_message("❌ กรุณากรอกจำนวน Robux เป็นตัวเลข", ephemeral=True)

# --------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    token = os.environ.get('DISCORD_BOT_TOKEN')
    if not token:
        print("❌ ไม่พบ Discord Bot Token")
        exit(1)
    if bot_instance is not None:
        print("⚠️ บอทกำลังทำงานอยู่แล้ว")
        exit(0)
    bot_instance = bot
    try:
        bot.run(token)
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการเริ่มบอท: {e}")
        exit(1)
