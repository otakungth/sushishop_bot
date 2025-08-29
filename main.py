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

# ห้องบันทึกการขาย
SALES_LOG_CHANNEL_ID = 1402993077643120720

# ตรวจสอบว่าบอทกำลังรันอยู่แล้วหรือไม่
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
            
            # ลงทะเบียนคำสั่ง
            await self.register_commands()

    async def register_commands(self):
        """ลงทะเบียนคำสั่งทั้งหมด"""
        # ลบคำสั่งเก่าทั้งหมด (ถ้ามี)
        self.tree.clear_commands(guild=None)
        
        # ลงทะเบียนคำสั่งสแลชใหม่
        try:
            await self.tree.sync()
            print("✅ ซิงค์คำสั่งเสร็จสิ้น")
        except Exception as e:
            print(f"⚠️ ไม่สามารถซิงค์คำสั่ง: {e}")

# สร้างอินสแตนซ์บอท
bot = MyBot()

# --------------------------------------------------------------------------------------------------
# ฟังก์ชันคำนวณราคา (อัปเดตรองรับสัญลักษณ์เพิ่มเติม)
def calculate_price(expression: str) -> tuple:
    """คำนวณราคาจากนิพจน์ทางคณิตศาสตร์"""
    try:
        # แทนที่สัญลักษณ์ต่างๆ ให้เป็นรูปแบบที่ Python เข้าใจ
        expression = expression.replace('×', '*').replace('x', '*').replace('÷', '/')
        
        # ตรวจสอบความปลอดภัยของนิพจน์
        allowed_chars = set('0123456789+-*/. ')
        if not all(c in allowed_chars for c in expression):
            return None, "❌ นิพจน์ไม่ถูกต้อง กรุณาใช้เฉพาะตัวเลขและสัญลักษณ์ทางคณิตศาสตร์"
        
        # คำนวณผลลัพธ์
        result = eval(expression)
        
        # คำนวณราคาตามเรท
        rate = 7
        price = result / rate
        
        return result, f"{price:,.0f} บาท"
    except ZeroDivisionError:
        return None, "❌ ไม่สามารถหารด้วยศูนย์ได้"
    except Exception as e:
        return None, f"❌ เกิดข้อผิดพลาดในการคำนวณ: {str(e)}"

# --------------------------------------------------------------------------------------------------
# คำสั่ง !gp สำหรับคำนวณราคา
@bot.command()
async def gp(ctx, *, expression: str):
    """คำนวณราคา Robux เป็นบาท"""
    # ลบคำสั่งออก
    try:
        await ctx.message.delete()
    except:
        pass
    
    # คำนวณราคา
    robux_amount, price = calculate_price(expression)
    
    if robux_amount is None:
        msg = await ctx.send(price, delete_after=10)
        return
    
    # สร้าง Embed แสดงผล
    embed = discord.Embed(
        title="🧮 ผลการคำนวณ",
        color=0x00FF99,
        timestamp=discord.utils.utcnow()
    )
    
    embed.add_field(name="💸 จำนวน Robux", value=f"{robux_amount:,.0f}", inline=True)
    embed.add_field(name="💰 ราคาตามเรท 7", value=price, inline=True)
    embed.add_field(name="📝 นิพจน์", value=expression, inline=False)
    embed.set_footer(text=f"คำนวณโดย {ctx.author.display_name}")
    
    await ctx.send(embed=embed, delete_after=30)

# --------------------------------------------------------------------------------------------------
# ฟังก์ชันส่งบันทึกการขาย (เวอร์ชั่นอัปเดต)
async def send_sale_log(embed_data: discord.Embed, interaction: discord.Interaction = None, ctx: commands.Context = None, delivered_by: discord.Member = None):
    """ส่ง Embed ไปยังห้องบันทึกการขาย"""
    try:
        channel = bot.get_channel(SALES_LOG_CHANNEL_ID)
        if channel is None:
            print("❌ ไม่พบห้องบันทึกการขาย")
            return

        # หาข้อมูลจาก Embed เดิม
        robux_amount = "ไม่ทราบข้อมูล"
        price = "ไม่ทราบข้อมูล"
        user_name = "ไม่ทราบข้อมูล"

        for field in embed_data.fields:
            if field.name == "💸 จำนวน Robux":
                robux_amount = field.value
            elif field.name in ("💰 ราคาตามเรท", "💰 ราคา"):
                price = field.value
            elif field.name == "🪪 ชื่อในเกม":
                user_name = field.value

        # ตรวจหาประเภทสินค้า
        sale_type = "ไม่ทราบ"
        current_channel = interaction.channel if interaction else ctx.channel
        if current_channel:
            category_name = current_channel.category.name if current_channel.category else ""
            if "gamepass" in category_name.lower() or "Sushi Gamepass" in category_name:
                sale_type = "Robux Gamepass"
            elif "group" in category_name.lower() or "Robux Group" in category_name:
                sale_type = "Robux Group"

        # หาผู้สร้างตั๋ว
        ticket_creator = None
        if current_channel.name.startswith("ticket-"):
            try:
                user_id = int(current_channel.name.split("-")[-1])
                ticket_creator = await current_channel.guild.fetch_member(user_id)
            except (IndexError, ValueError, discord.NotFound):
                print("❌ ไม่สามารถดึงข้อมูลผู้สร้างตั๋วจากชื่อช่อง")

        # สร้าง Embed ใหม่
        log_embed = discord.Embed(
            title="🍣 บันทึกการขายสำเร็จ 🍣",
            color=0x00FF00,
            timestamp=discord.utils.utcnow()
        )

        # ประเภทสินค้า
        log_embed.add_field(name="📦 ประเภทสินค้า", value=sale_type, inline=False)

        # ผู้ซื้อ
        if ticket_creator:
            log_embed.add_field(name="😊 ผู้ซื้อ", value=f"{ticket_creator.mention}", inline=False)
        else:
            log_embed.add_field(name="😊 ผู้ซื้อ", value=user_name, inline=False)

        # จำนวน Robux และราคา
        log_embed.add_field(name="💸 จำนวน Robux", value=robux_amount, inline=True)
        log_embed.add_field(name="💰 ราคาตามเรท", value=price, inline=True)

        # ผู้ส่งสินค้า
        if delivered_by:
            log_embed.add_field(name="🚚 ผู้ส่งสินค้า", value=delivered_by.mention, inline=False)

        log_embed.set_footer(text="การสั่งซื้อสำเร็จ")

        await channel.send(embed=log_embed)

    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการส่งบันทึกการขาย: {e}")

# --------------------------------------------------------------------------------------------------
# คำสั่งต่างๆ
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
# Gamepass
GAMEPASS_CHANNEL_ID = 1361044752975532152

@bot.command()
@commands.has_permissions(administrator=True)
async def sushi(ctx):
    global shop_open
    shop_open = not shop_open
    status = "✅ ร้านเปิด" if shop_open else "❌ ร้านปิด"
    await ctx.send(f"📌 สถานะร้านถูกเปลี่ยนเป็น: **{status}**", delete_after=5)
    if ctx.channel.id == GAMEPASS_CHANNEL_ID:
        await openshop(ctx) 

@bot.command()
@commands.has_permissions(administrator=True)
async def openshop(ctx):
    if ctx.channel.id != GAMEPASS_CHANNEL_ID:
        await ctx.message.delete()
        return

    # ลบข้อความเก่าๆ ของบอทในช่องนี้
    async for msg in ctx.channel.history(limit=20):
        if msg.author == bot.user:
            await msg.delete()

    embed = discord.Embed(
        title="🍣 Sushi Shop 🍣",
        description=(
            "# **กดเกมพาสเรท 7**\n\n"
            "กดปุ่ม 'เปิดตั๋ว' เพื่อกดเกมพาสหรือสอบถามได้เลยครับ\n\n"
            "หากลูกค้ามีปัญหาได้รับของผิดสามารถติดต่อทีมงานได้เลยนะครับ"
        ),
        color=0xFFD700
    )
    embed.set_thumbnail(url="https://media.discordapp.net/attachments/717757556889747657/1403684950770847754/noFilter.png?ex=689872fb&is=6897217b&hm=5e55202bef3413971c139963f7e23834ccd7cbd6528966dcdf6303ddb2c13d22&=&format=webp&quality=lossless")
    await ctx.send(embed=embed, view=OpenTicketView())
    await ctx.message.delete()

# --------------------------------------------------------------------------------------------------

@bot.command()
@commands.has_permissions(administrator=True)
async def ty(ctx):
    if ctx.channel.name.startswith("ticket-"):
        # หา Embed ที่มีข้อมูลการสั่งซื้อ
        sale_embed = None
        async for msg in ctx.channel.history():
            if msg.embeds and "รายละเอียดการสั่งซื้อ" in msg.embeds[0].title:
                sale_embed = msg.embeds[0]
                break

        if sale_embed:
            await send_sale_log(sale_embed, ctx=ctx)

        # ย้าย ticket ไป category "ส่งของแล้ว"
        delivered_category = discord.utils.get(ctx.guild.categories, name="ส่งของแล้ว")
        if delivered_category:
            try:
                await ctx.channel.edit(category=delivered_category)
            except Exception as e:
                print(f"❌ ไม่สามารถย้ายหมวดหมู่: {e}")

        # ส่งข้อความขอบคุณและปุ่มปิดตั๋ว
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
        # หา Embed ที่มีข้อมูลการสั่งซื้อ
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

# --------------------------------------------------------------------------------------------------
# Views และ Modals
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
    gamepass_name = TextInput(label="💸กดเกมพาสอะไร?", placeholder="พิมพ์ชื่อเกมพาส เช่น x3 Speed 3 ชิ้น", required=True)
    robux_amount = TextInput(label="🎟 รวมทั้งหมดกี่ Robux?", placeholder="พิมพ์จำนวนRobux เช่น 995", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            robux = int(self.robux_amount.value)
            rate = 7
            price = robux / rate
            price_str = f"{price:,.0f} บาท"

            customer_embed = discord.Embed(title="📨 รายละเอียดการสั่งซื้อ", color=0x00FF99)
            customer_embed.add_field(name="🗺️ แมพ", value=self.map_name.value, inline=False)
            customer_embed.add_field(name="🎟 เกมพาส", value=self.gamepass_name.value, inline=False)
            customer_embed.add_field(name="💸 จำนวน Robux", value=self.robux_amount.value, inline=True)
            customer_embed.add_field(name="💰 ราคา", value=price_str, inline=True)
            customer_embed.set_footer(text="ทีมงานจะตอบกลับโดยเร็วที่สุดครับ")

            confirm_embed = discord.Embed(title="📨 รายละเอียดการสั่งซื้อ", color=0x00FF99)
            confirm_embed.add_field(name="🪪 ชื่อในเกม", value="N/A", inline=False)
            confirm_embed.add_field(name="🗺️ แมพ", value=self.map_name.value, inline=False)
            confirm_embed.add_field(name="🎟 เกมพาส", value=self.gamepass_name.value, inline=False)
            confirm_embed.add_field(name="💸 จำนวน Robux", value=self.robux_amount.value, inline=True)
            confirm_embed.add_field(name="💰 ราคาตามเรท", value=price_str, inline=True)
            confirm_embed.set_footer(text=f"🧾 ผู้ใช้: {interaction.user}")

            view = ConfirmTicketView(embed_data=confirm_embed)
            await interaction.response.send_message(embed=customer_embed, view=view, ephemeral=False)

        except ValueError:
            await interaction.response.send_message("❌ กรุณากรอกจำนวน Robux เป็นตัวเลข", ephemeral=True)

class ConfirmTicketView(discord.ui.View):
    def __init__(self, embed_data: discord.Embed):
        super().__init__(timeout=None)
        self.embed_data = embed_data.copy()

    @discord.ui.button(label="✅ ยืนยันการสั่งซื้อ", style=discord.ButtonStyle.success, custom_id="confirm_ticket")
    async def confirm_button(self, interaction: discord.Interaction, button: Button):
        if any(field.name == "📋 ยืนยันโดย" for field in self.embed_data.fields):
            await interaction.response.send_message(
                "⚠️ คำสั่งซื้อนี้ได้รับการยืนยันแล้ว", ephemeral=True
            )
            return

        self.embed_data.add_field(name="📋 ยืนยันโดย", value=interaction.user.mention, inline=False)
        await interaction.response.send_message(
            "✅ ยืนยันข้อมูลเรียบร้อย!", ephemeral=True
        )

        # เปลี่ยนปุ่มเป็น "📦 ส่งสินค้าสำเร็จ" ให้กดได้เฉพาะแอดมิน
        new_view = ProductDeliveredView(self.embed_data)
        await interaction.message.edit(embed=self.embed_data, view=new_view)


class ProductDeliveredView(discord.ui.View):
    def __init__(self, embed_data: discord.Embed):
        super().__init__(timeout=None)
        self.embed_data = embed_data

    @discord.ui.button(label="📦 ส่งสินค้าสำเร็จ", style=discord.ButtonStyle.primary, custom_id="deliver_product")
    async def deliver_product(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้ปุ่มนี้", ephemeral=True)
            return

        # ส่ง log พร้อมคนส่งสินค้า
        await send_sale_log(self.embed_data, interaction=interaction, delivered_by=interaction.user)

        # ย้ายไปหมวดหมู่ "ส่งของแล้ว"
        delivered_category = discord.utils.get(interaction.guild.categories, name="ส่งของแล้ว")
        if delivered_category:
            try:
                await interaction.channel.edit(category=delivered_category)
            except Exception as e:
                print(f"❌ ไม่สามารถย้ายหมวดหมู่: {e}")

        # ส่ง embed ขอบคุณ + ปุ่มปิดตั๋ว
        embed = discord.Embed(
            title="✅ สินค้าถูกส่งเรียบร้อยแล้ว",
            description=(
                "ขอบคุณที่ใช้บริการกับเรา หากไม่มีปัญหาเพิ่มเติม "
                "สามารถกดปุ่มด้านล่างเพื่อปิดตั๋วได้เลย\n\n"
                "⏳ **หากไม่ได้กดปิดตั๋ว ตั๋วจะถูกปิดอัตโนมัติใน 1 ชั่วโมง**"
            ),
            color=0x00FF00
        )
        await interaction.channel.send(embed=embed, view=CloseTicketView(interaction.channel))

        # ตั้ง auto close 1 ชั่วโมง
        async def auto_close():
            await discord.utils.sleep_until(discord.utils.utcnow() + datetime.timedelta(hours=1))
            if interaction.channel and interaction.channel.name.startswith("ticket-"):
                try:
                    await interaction.channel.send("⏳ ไม่มีการตอบกลับ ตั๋วนี้จะถูกปิดอัตโนมัติ")
                    await interaction.channel.delete()
                except:
                    pass

        interaction.client.loop.create_task(auto_close())

        await interaction.response.send_message("✅ ทำเครื่องหมายว่าส่งสินค้าสำเร็จแล้ว", ephemeral=True)

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

# --------------------------------------------------------------------------------------------------
async def handle_open_ticket(interaction, category_name, view_class, mention_user):
    """ฟังก์ชันจัดการการเปิดตั๋ว"""
    try:
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name=category_name)
        
        if not category:
            await interaction.response.send_message("❌ ไม่พบหมวดหมู่ที่กำหนด", ephemeral=True)
            return
            
        # สร้างช่องใหม่
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        channel = await category.create_text_channel(
            name=f"ticket-{interaction.user.id}",
            overwrites=overwrites
        )
        
        # ส่งข้อความต้อนรับ
        welcome_msg = f"👋 {interaction.user.mention} ยินดีต้อนรับสู่ตั๋ว支援ของคุณ!" if mention_user else "👋 ยินดีต้อนรับสู่ตั๋ว支援ของคุณ!"
        
        embed = discord.Embed(
            title="🎫 ตั๋ว支援ถูกเปิดแล้ว",
            description="กรุณากรอกข้อมูลด้านล่างเพื่อดำเนินการต่อ",
            color=0x00FF00
        )
        
        await channel.send(welcome_msg, embed=embed, view=view_class(channel, interaction.user))
        await interaction.response.send_message(f"✅ เปิดตั๋ว支援เรียบร้อยแล้ว: {channel.mention}", ephemeral=True)
        
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการเปิดตั๋ว: {e}")
        await interaction.response.send_message("❌ เกิดข้อผิดพลาดในการเปิดตั๋ว", ephemeral=True)

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if not interaction.data:
        return

    custom_id = interaction.data.get("custom_id")

    if custom_id == "open_ticket":
        await handle_open_ticket(
            interaction,
            category_name="🍣Sushi Gamepass 🍣",
            view_class=TicketFullActionView,
            mention_user=True
        )

# --------------------------------------------------------------------------------------------------
# --------------------------------------------------------------------------------------------------
# สถานะร้าน Robux Group
group_open = True
GROUP_CHANNEL_ID = 1361554847526162532

@bot.command()
@commands.has_permissions(administrator=True)
async def rg(ctx):
    global group_open
    group_open = not group_open
    status = "✅ Robux Group เปิด" if group_open else "❌ Robux Group ปิด"
    await ctx.send(f"📌 สถานะ Robux Group ถูกเปลี่ยนเป็น: **{status}**", delete_after=5)
    if ctx.channel.id == GROUP_CHANNEL_ID:
        await opengroup(ctx)

@bot.command()
@commands.has_permissions(administrator=True)
async def opengroup(ctx):
    if ctx.channel.id != GROUP_CHANNEL_ID:
        await ctx.message.delete()
        return

    # ลบข้อความเก่าๆ ของบอทในช่องนี้
    async for msg in ctx.channel.history(limit=20):
        if msg.author == bot.user:
            await msg.delete()

    embed = discord.Embed(
        title="🍣 Sushi Shop 🍣",
        description=(
            "# **🛒โรกลุ่มเรท 4.5 ซื้อมากกว่า 500 บาทเรท 5**\n\n"
            "กดปุ่ม 'เปิดตั๋ว' เพื่อสั่งซื้อได้เลยครับ\n\n"
            "เข้ากลุ่มนี้: https://www.roblox.com/communities/34713179/VALKYs \n\n"
            "⚠️ กรุณาเข้ากลุ่มให้ครบ 15 วัน ⚠️\n\n"
            f"📌 จดวันที่เข้ากลุ่มได้ที่ <#{1387421905941827615}>\n\n"
            "หากลูกค้ามีปัญหาสามารถแจ้งทีมงานได้เลยครับ"
        ),
        color=0x00AAFF
    )
    embed.set_thumbnail(url="https://media.discordapp.net/attachments/717757556889747657/1403684950770847754/noFilter.png?ex=689872fb&is=6897217b&hm=5e55202bef3413971c139963f7e23834ccd7cbd6528966dcdf6303ddb2c13d22&=&format=webp&quality=lossless")
    await ctx.send(embed=embed, view=OpenGroupTicketView())
    await ctx.message.delete()

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
            customer_embed.set_footer(text="ทีมงานจะตอบกลับโดยเร็วที่สุดครับ")

            await interaction.response.send_message(embed=customer_embed, ephemeral=False)

        except ValueError:
            await interaction.response.send_message("❌ กรุณากรอกจำนวน Robux เป็นตัวเลข", ephemeral=True)

class GroupTicketFullActionView(View):
    def __init__(self, channel: discord.TextChannel, owner: discord.Member):
        super().__init__(timeout=None)
        self.channel = channel
        self.owner = owner

    @discord.ui.button(label="📝 กรอกแบบฟอร์ม Group", style=discord.ButtonStyle.primary)
    async def open_form(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(GroupTicketInfoModal())

    @discord.ui.button(label="📤 ช่องทางการโอนเงิน", style=discord.ButtonStyle.success)
    async def payment_info(self, interaction: discord.Interaction, button: Button):
        embed = discord.Emembed(title="📤 ช่องทางการโอนเงิน").set_image(
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

# --------------------------------------------------------------------------------------------------
# เริ่มการทำงานของบอท
if __name__ == "__main__":
    # ตรวจสอบว่ามี TOKEN ใน environment variables หรือไม่
    token = os.environ.get('DISCORD_BOT_TOKEN')
    if not token:
        print("❌ ไม่พบ Discord Bot Token ใน environment variables")
        print("⚠️ กรุณาตั้งค่า DISCORD_BOT_TOKEN ใน environment variables ของ Render")
        exit(1)
    
    # ตรวจสอบว่าบอทกำลังทำงานอยู่แล้วหรือไม่
    if bot_instance is not None:
        print("⚠️ บอทกำลังทำงานอยู่แล้ว")
        exit(0)
        
    bot_instance = bot
    
    try:
        bot.run(token)
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการเริ่มบอท: {e}")
        exit(1)
