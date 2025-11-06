import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

# โหลด token จากไฟล์ .env (ถ้ามี)
load_dotenv()

# ✅ ตั้งค่า intents ให้ครบ (สำคัญสำหรับ slash + DM)
intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True

# =======================================================================================
# ✅ คลาสหลักของบอท
# =======================================================================================
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",  # ใช้ ! ได้ด้วยถ้าอยาก
            intents=intents,
            help_command=None,
            application_id=os.getenv("APPLICATION_ID")
        )

    async def setup_hook(self):
        """ซิงค์ global slash commands"""
        print("🔄 กำลังซิงค์ global slash commands ...")

        # ✅ เปิดให้ทุกคำสั่งใช้ใน DM ได้
        for cmd in self.tree.walk_commands():
            try:
                cmd.dm_permission = True
            except Exception as e:
                print(f"⚠️ ตั้งค่า DM permission ไม่ได้สำหรับ {cmd.name}: {e}")

        try:
            synced = await self.tree.sync()
            print(f"✅ ซิงค์สำเร็จ! ({len(synced)} commands)")
            for c in synced:
                print(f"   - /{c.name}: {c.description}")
        except Exception as e:
            print(f"❌ ซิงค์ล้มเหลว: {e}")

# =======================================================================================
# ✅ สร้าง instance ของบอท
# =======================================================================================
bot = MyBot()

# =======================================================================================
# ✅ ตัวอย่างคำสั่ง Slash (ใช้ได้ทั้งในเซิร์ฟเวอร์และ DM)
# =======================================================================================
@bot.tree.command(name="ping", description="ทดสอบการตอบกลับ", dm_permission=True)
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("🏓 Pong!", ephemeral=False)


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


@bot.tree.command(name="tax", description="คำนวณ Robux หลังหักภาษี", dm_permission=True)
async def tax(interaction: discord.Interaction, robux: int):
    after_tax = robux * 0.7
    await interaction.response.send_message(
        f"💸 {robux:,} Robux หลังหักภาษี 30% = **{after_tax:,.0f} Robux**",
        ephemeral=False
    )


@bot.tree.command(name="help", description="แสดงคำสั่งทั้งหมด", dm_permission=True)
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📜 Sushi Shop Commands",
        description=(
            "ใช้ได้ทั้งในเซิร์ฟเวอร์และ DM\n\n"
            "💬 `/ping` - ทดสอบการตอบกลับ\n"
            "🎮 `/gamepass <จำนวน>` - คำนวณราคา Gamepass\n"
            "👥 `/group <จำนวน>` - คำนวณราคา Group\n"
            "💸 `/tax <จำนวน>` - คำนวณหลังหักภาษี"
        ),
        color=0x00FFAA
    )
    await interaction.response.send_message(embed=embed, ephemeral=False)

# =======================================================================================
# ✅ คำสั่ง prefix (แบบเก่า !hello)
# =======================================================================================
@bot.command()
async def hello(ctx):
    await ctx.send("สวัสดี! 👋")

# =======================================================================================
# ✅ Event เมื่อบอทออนไลน์
# =======================================================================================
@bot.event
async def on_ready():
    print(f"✅ บอทออนไลน์แล้ว: {bot.user}")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="ร้าน Sushi Shop | พิมพ์ /help"
        )
    )

# =======================================================================================
# ✅ เริ่มรันบอท
# =======================================================================================
bot.run(os.getenv("DISCORD_TOKEN"))
