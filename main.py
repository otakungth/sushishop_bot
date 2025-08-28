import os
import datetime
import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import re
import ast

from server import server_on

# ตั้งค่าพื้นฐาน
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
shop_open = True

# ห้องบันทึกการขาย
SALES_LOG_CHANNEL_ID = 1402993077643120720

bot = commands.Bot(command_prefix="!", intents=intents)

# --------------------------------------------------------------------------------------------------
# ฟังก์ชัน parse สูตรคำนวณ robux
def parse_robux(expr: str) -> int:
    expr = expr.lower().replace("x", "*")
    # อนุญาตเฉพาะตัวเลขและเครื่องหมายคำนวณ
    if not re.match(r"^[0-9+\-*/ ().]+$", expr):
        raise ValueError("Invalid expression")
    try:
        value = eval(expr, {"__builtins__": None}, {})
    except Exception:
        raise ValueError("Invalid expression")
    return int(value)

# --------------------------------------------------------------------------------------------------
# ฟังก์ชันส่งบันทึกการขาย
async def send_sale_log(embed_data: discord.Embed, interaction: discord.Interaction = None, ctx: commands.Context = None, delivered_by: discord.Member = None):
    try:
        channel = bot.get_channel(SALES_LOG_CHANNEL_ID)
        if channel is None:
            print("❌ ไม่พบห้องบันทึกการขาย")
            return

        robux_amount = "ไม่ทราบข้อมูล"
        price = "ไม่ทราบข้อมูล"
        user_name = "ไม่ทราบข้อมูล"

        for field in embed_data.fields:
            if field.name == "💸 จำนวน Robux":
                robux_amount = field.value
            elif field.name in ("💰 ราคาตามเรท", "💰 ราคา"):
                price = field.value

        sale_type = "ไม่ทราบ"
        current_channel = interaction.channel if interaction else ctx.channel
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
        log_embed.add_field(name="💰 ราคาตามเรท", value=price, inline=True)
        if delivered_by:
            log_embed.add_field(name="🚚 ผู้ส่งสินค้า", value=delivered_by.mention, inline=False)
        log_embed.set_footer(text="การสั่งซื้อสำเร็จ")

        await channel.send(embed=log_embed)

    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการส่งบันทึกการขาย: {e}")

# --------------------------------------------------------------------------------------------------
# คำสั่ง QR
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
    shop_open = not shop_open  # toggle เปิด/ปิดร้าน

    status = "✅ ร้านเปิด" if shop_open else "❌ ร้านปิด"
    await ctx.send(f"📌 สถานะร้านถูกเปลี่ยนเป็น: **{status}**", delete_after=5)

    # เปลี่ยนชื่อช่องตามสถานะ
    new_name = "🟢เกมพาสเรท 7" if shop_open else "🔴เกมพาสเรท 7"
    await ctx.channel.edit(name=new_name)

    # ลบข้อความเก่าของบอท
    async for msg in ctx.channel.history(limit=20):
        if msg.author == bot.user:
            await msg.delete()

    # ถ้าร้านเปิด ให้ส่งหน้า openshop ทันที
    if shop_open and ctx.channel.id == GAMEPASS_CHANNEL_ID:
        await openshop.callback(ctx)  # เรียก callback ของ command ตรง ๆ

@bot.command()
@commands.has_permissions(administrator=True)
async def openshop(ctx):
    if ctx.channel.id != GAMEPASS_CHANNEL_ID:
        await ctx.message.delete()
        return
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
    embed.set_thumbnail(url="https://media.discordapp.net/attachments/717757556889747657/1403684950770847754/noFilter.png")
    await ctx.send(embed=embed, view=OpenTicketView())
    await ctx.message.delete()

# --------------------------------------------------------------------------------------------------
# Modal Gamepass
class TicketInfoModal(Modal, title="📋 แบบฟอร์มสั่งสินค้า"):
    map_name = TextInput(label="🗺 ชื่อแมพที่จะกด?", placeholder="พิมพ์ชื่อแมพ เช่น All Star Tower Defense X", required=True)
    gamepass_name = TextInput(label="💸 กดเกมพาสอะไร?", placeholder="พิมพ์ชื่อเกมพาส เช่น x3 Speed 3 ชิ้น", required=True)
    robux_amount = TextInput(label="🎟 รวมทั้งหมดกี่ Robux?", placeholder="สามารถใช้สูตร เช่น 100+200 หรือ 70x10", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            robux = parse_robux(self.robux_amount.value)
            rate = 7
            price = robux / rate
            price_str = f"{price:,.0f} บาท"

            customer_embed = discord.Embed(title="📨 รายละเอียดการสั่งซื้อ", color=0x00FF99)
            customer_embed.add_field(name="🗺️ แมพ", value=self.map_name.value, inline=False)
            customer_embed.add_field(name="🎟 เกมพาส", value=self.gamepass_name.value, inline=False)
            customer_embed.add_field(name="💸 จำนวน Robux", value=str(robux), inline=True)
            customer_embed.add_field(name="💰 ราคา", value=price_str, inline=True)
            customer_embed.set_footer(text="ทีมงานจะตอบกลับโดยเร็วที่สุดครับ")

            confirm_embed = customer_embed.copy()
            confirm_embed.set_footer(text=f"🧾 ผู้ใช้: {interaction.user}")

            view = ConfirmTicketView(embed_data=confirm_embed)
            await interaction.response.send_message(embed=customer_embed, view=view, ephemeral=False)

        except ValueError:
            await interaction.response.send_message("❌ กรุณากรอกจำนวน Robux เป็นสูตรเลขที่ถูกต้อง", ephemeral=True)

# --------------------------------------------------------------------------------------------------
# Group
group_open = True
GROUP_CHANNEL_ID = 1361554847526162532

@bot.command()
@commands.has_permissions(administrator=True)
async def rg(ctx):
    global group_open
    group_open = not group_open
    status = "✅ Robux Group เปิด" if group_open else "❌ Robux Group ปิด"
    await ctx.send(f"📌 สถานะ Robux Group ถูกเปลี่ยนเป็น: **{status}**", delete_after=5)

    channel = ctx.guild.get_channel(GROUP_CHANNEL_ID)
    if channel:
        new_name = "🟢โรบัคกลุ่มเรท 4.5 ซื้อมากกว่า 500 บาทเรท 5" if group_open else "🔴โรบัคกลุ่มเรท 4.5 ซื้อมากกว่า 500 บาทเรท 5"
        await channel.edit(name=new_name)

    if ctx.channel.id == GROUP_CHANNEL_ID:
        await opengroup(ctx)

class GroupTicketInfoModal(Modal, title="📋 แบบฟอร์ม Robux Group"):
    robux_amount = TextInput(label="💸 ต้องการกดทั้งหมดกี่ Robux?", placeholder="เช่น 1000+500 หรือ 200x3", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            robux = parse_robux(self.robux_amount.value)
            rate = 4.5 if robux < 1500 else 5
            price = robux / rate
            price_str = f"{price:,.0f} บาท"

            customer_embed = discord.Embed(title="📨 รายละเอียดการสั่งซื้อ Robux Group", color=0x00FF99)
            customer_embed.add_field(name="💸 จำนวน Robux", value=str(robux), inline=True)
            customer_embed.add_field(name="💰 ราคาตามเรท", value=price_str, inline=True)
            customer_embed.set_footer(text="ทีมงานจะตรวจสอบและตอบกลับโดยเร็วที่สุดครับ")

            confirm_embed = customer_embed.copy()
            confirm_embed.set_footer(text=f"🧾 ผู้ใช้: {interaction.user}")

            view = ConfirmTicketView(embed_data=confirm_embed)
            await interaction.response.send_message(embed=customer_embed, view=view, ephemeral=False)

        except ValueError:
            await interaction.response.send_message("❌ กรุณากรอกจำนวน Robux เป็นสูตรเลขที่ถูกต้อง", ephemeral=True)

# --------------------------------------------------------------------------------------------------
# คิดเลขเรทของ Gamepass / Group
@bot.command()
async def gp(ctx, *, expr: str):
    try:
        robux = parse_robux(expr)
        rate = 7
        price = robux / rate
        price_str = f"{price:,.0f} บาท"
        await ctx.send(f"🎮 Gamepass {robux:,} Robux = **{price_str}** (เรท {rate})")
    except Exception:
        await ctx.send("❌ กรุณาใส่จำนวน Robux หรือสูตรเลขให้ถูกต้อง")

@bot.command()
async def g(ctx, *, expr: str):
    try:
        robux = parse_robux(expr)
        rate = 4.5 if robux < 1500 else 5
        price = robux / rate
        price_str = f"{price:,.0f} บาท"
        await ctx.send(f"👥 Group {robux:,} Robux = **{price_str}** (เรท {rate})")
    except Exception:
        await ctx.send("❌ กรุณาใส่จำนวน Robux หรือสูตรเลขให้ถูกต้อง")

# --------------------------------------------------------------------------------------------------
#ปิด bot
@bot.command()
@commands.is_owner()
async def shutdown(ctx):
    await ctx.send("🛑 Bot ถูกสั่งปิด")
    await bot.close()
# --------------------------------------------------------------------------------------------------
server_on()
bot.run(os.getenv("TOKEN"))





