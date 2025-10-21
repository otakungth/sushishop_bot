import os
import datetime
import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, Select
import re
import json
import asyncio

from server import server_on

# ตั้งค่า Intents ให้ครบถ้วน
intents = discord.Intents.all()
intents.message_content = True

# ตั้งค่าเรท
gamepass_rate = 6
group_rate_low = 4
group_rate_high = 4.5

# ตั้งค่าพื้นฐาน
shop_open = True
group_ticket_enabled = True

# ตั้งค่าห้องหลักและ stock
MAIN_CHANNEL_ID = 1361044752975532152
SALES_LOG_CHANNEL_ID = 1402993077643120720
gamepass_stock = 67
group_stock = 67

# เก็บข้อมูลโน้ตส่วนตัว
user_notes = {}

# สร้างบอทด้วย intents ที่ถูกต้อง
bot = commands.Bot(
    command_prefix="!", 
    intents=intents,
    help_command=None
)

# --------------------------------------------------------------------------------------------------
# Events หลัก
@bot.event
async def on_connect():
    print("🔗 บอทเชื่อมต่อกับ Discord แล้ว")

@bot.event
async def on_ready():
    print(f"✅ บอทออนไลน์แล้ว: {bot.user.name}")
    print(f"🆔 ID: {bot.user.id}")
    print(f"🔗 เชื่อมต่อกับ {len(bot.guilds)} เซิร์ฟเวอร์")
    
    # ตรวจสอบว่าเห็นช่อง text หรือไม่
    for guild in bot.guilds:
        print(f"🏠 เซิร์ฟเวอร์: {guild.name}")
        for channel in guild.text_channels:
            print(f"   📁 {channel.name} ({channel.id})")
    
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="ร้าน Sushi Shop"))
    
    # ลงทะเบียน Persistent View
    bot.add_view(MainShopView())
    print("✅ ลงทะเบียน MainShopView เรียบร้อย")
    
    await update_main_channel()

@bot.event
async def on_message(message):
    # ตรวจสอบว่าบอทเป็นผู้ส่งข้อความหรือไม่
    if message.author == bot.user:
        return
    
    # ตรวจสอบว่าเป็นคำสั่งหรือไม่
    if message.content.startswith('!'):
        print(f"📨 รับคำสั่ง: {message.content} จาก {message.author} ใน #{message.channel.name}")
    
    # ต้องมีบรรทัดนี้เพื่อให้คำสั่งทำงาน
    await bot.process_commands(message)

@bot.event
async def on_command_error(ctx, error):
    """จัดการข้อผิดพลาดของคำสั่ง"""
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("❌ ไม่พบคำสั่งนี้ กรุณาพิมพ์ `!help` เพื่อดูคำสั่งทั้งหมด", delete_after=10)
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", delete_after=10)
    else:
        print(f"❌ ข้อผิดพลาดในคำสั่ง {ctx.command}: {error}")
        await ctx.send("❌ เกิดข้อผิดพลาดในการประมวลผลคำสั่ง", delete_after=10)

# --------------------------------------------------------------------------------------------------
# คำสั่งทดสอบ
@bot.command()
async def test(ctx):
    """ทดสอบว่าคำสั่งทำงานได้"""
    try:
        await ctx.send("✅ บอททำงานปกติ! คำสั่งใช้งานได้")
        print(f"✅ ทดสอบคำสั่งสำเร็จโดย {ctx.author}")
    except Exception as e:
        print(f"❌ ข้อผิดพลาดในคำสั่ง test: {e}")

@bot.command()
async def ping(ctx):
    """ตรวจสอบ latency ของบอท"""
    latency = round(bot.latency * 1000)
    await ctx.send(f"🏓 Pong! {latency}ms")

@bot.command()
async def help(ctx):
    """แสดงคำสั่งทั้งหมด"""
    embed = discord.Embed(
        title="🍣 Sushi Shop - คำสั่งทั้งหมด",
        description="รายการคำสั่งที่สามารถใช้งานได้",
        color=0x00FF99
    )
    
    embed.add_field(
        name="🎮 คำสั่งคำนวณราคา",
        value=(
            "`!gp <จำนวน>` - คำนวณราคา Gamepass\n"
            "`!g <จำนวน>` - คำนวณราคา Group\n"
            "`!gpb <จำนวน>` - คำนวณ Robux จากเงิน (Gamepass)\n"
            "`!gb <จำนวน>` - คำนวณ Robux จากเงิน (Group)\n"
            "`!tax <จำนวน>` - คำนวณ Robux หลังหักภาษี"
        ),
        inline=False
    )
    
    embed.add_field(
        name="⚙️ คำสั่งผู้ดูแล",
        value=(
            "`!stock` - ตรวจสอบ stock\n"
            "`!stock gp <จำนวน>` - ตั้งค่า Gamepass stock\n"
            "`!stock group <จำนวน>` - ตั้งค่า Group stock\n"
            "`!sushi` - เปิด/ปิดร้าน\n"
            "`!group <on/off>` - เปิด/ปิด Group ticket\n"
            "`!restart` - รีสตาร์ทระบบปุ่ม"
        ),
        inline=False
    )
    
    await ctx.send(embed=embed)

# --------------------------------------------------------------------------------------------------
# คำสั่งเดิมทั้งหมด (เหลือไว้เหมือนเดิม)
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
                await ctx.send("❌ จำนวน stock ต้องมากกว่าหรือเท่ากับ 0")
                return
            
            gamepass_stock = amount
            await ctx.send(f"✅ ตั้งค่า สต๊อกเกมพาส เป็น **{gamepass_stock}** เรียบร้อยแล้ว")
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
                await ctx.send("❌ จำนวน stock ต้องมากกว่าหรือเท่ากับ 0")
                return
            
            group_stock = amount
            await ctx.send(f"✅ ตั้งค่า สต๊อกโรบัคกลุ่ม เป็น **{group_stock}** เรียบร้อยแล้ว")
            await update_main_channel()
    
    else:
        message = await ctx.send(
            "❌ การใช้งาน:\n"
            "`!stock` - เช็ค stock ทั้งหมด\n"
            "`!stock gp <จำนวน>` - ตั้งค่า Gamepass stock\n" 
            "`!stock group <จำนวน>` - ตั้งค่า Group stock"
        )
        await asyncio.sleep(5)
        try:
            await message.delete()
        except:
            pass

# ... (คำสั่งอื่นๆ เหมือนเดิม)

# --------------------------------------------------------------------------------------------------
# เริ่มต้นบอท
print("🚀 กำลังเริ่มต้นบอท...")
server_on()
try:
    bot.run(os.getenv("TOKEN"))
except Exception as e:
    print(f"❌ เกิดข้อผิดพลาดในการเริ่มต้นบอท: {e}")

