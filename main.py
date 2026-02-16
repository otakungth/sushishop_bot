import os
import sys
import datetime
import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import re
import asyncio
import json
import time
import logging
from typing import Optional, Dict, Any, List, Tuple
from collections import deque
import random

# ตั้งค่า logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# นำเข้า server.py
try:
    from server import server_on
    logger.info("✅ นำเข้า server.py สำเร็จ")
except Exception as e:
    logger.error(f"❌ ไม่สามารถนำเข้า server.py: {e}")
    def server_on():
        from flask import Flask
        import threading
        app = Flask(__name__)
        @app.route('/')
        def home():
            return "Sushi Shop Bot is running!"
        def run():
            app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)
        t = threading.Thread(target=run)
        t.daemon = True
        t.start()
        logger.info("✅ Server started on port 8080 (fallback)")

# =======================================================================================
# ✅ Config Class
# =======================================================================================

class Config:
    """เก็บค่าคงที่และการตั้งค่าทั้งหมด"""
    
    # Channel IDs
    MAIN_CHANNEL_ID = 1361044752975532152
    SALES_LOG_CHANNEL_ID = 1402993077643120720
    CREDIT_CHANNEL_ID = 1363250076549382246
    DELIVERED_CATEGORY_ID = 1419565515088597083
    ARCHIVED_CATEGORY_ID = 1445086228113264650
    
    # Role IDs
    ADMIN_ROLE_ID = 1361016912259055896
    
    # Rate limits
    GAMEPASS_RATE = 6
    GROUP_RATE_LOW = 4
    GROUP_RATE_HIGH = 4.5
    
    # Stock
    GAMEPASS_STOCK = 50000
    GROUP_STOCK = 0
    
    # File paths
    USER_DATA_FILE = "user_data.json"
    TICKET_TRANSCRIPTS_FILE = "ticket_transcripts.json"
    TICKET_COUNTER_FILE = "ticket_counter.json"
    
    # Level thresholds
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

# =======================================================================================
# ✅ Rate Limit Handler
# =======================================================================================

class RateLimitHandler:
    """จัดการ rate limits สำหรับ Discord API"""
    
    def __init__(self):
        self.request_times = deque(maxlen=50)
        self.last_reset = time.time()
        self.min_interval = 1.0  # 1 วินาทีระหว่าง requests
        self.max_requests_per_minute = 30
        
    async def wait_if_needed(self):
        """รอถ้าใกล้ถึง rate limit"""
        now = time.time()
        
        # รีเซ็ตทุกนาที
        if now - self.last_reset >= 60:
            self.request_times.clear()
            self.last_reset = now
            
        # ตรวจสอบจำนวน requests ในนาทีนี้
        self.request_times.append(now)
        
        if len(self.request_times) >= self.max_requests_per_minute:
            wait_time = 60 - (now - self.last_reset)
            if wait_time > 0:
                logger.warning(f"⏳ Rate limit: รอ {wait_time:.1f} วินาที")
                await asyncio.sleep(wait_time)
                self.request_times.clear()
                self.last_reset = time.time()
        
        # รอระหว่าง requests
        if self.request_times and len(self.request_times) > 1:
            last_request = self.request_times[-2]
            time_since_last = now - last_request
            if time_since_last < self.min_interval:
                await asyncio.sleep(self.min_interval - time_since_last)

# =======================================================================================
# ✅ Data Manager
# =======================================================================================

class DataManager:
    """จัดการข้อมูลทั้งหมด แทนการใช้ global"""
    
    def __init__(self):
        self.user_data = {}
        self.ticket_transcripts = {}
        self.ticket_counter = {"counter": 1, "date": datetime.datetime.now().strftime("%d%m%y")}
        self.user_notes = {}
        self.ticket_activity = {}
        
        # Shop status
        self.shop_open = True
        self.group_ticket_enabled = True
        
        # Stock
        self.gamepass_stock = Config.GAMEPASS_STOCK
        self.group_stock = Config.GROUP_STOCK
        
        # Rates
        self.gamepass_rate = Config.GAMEPASS_RATE
        self.group_rate_low = Config.GROUP_RATE_LOW
        self.group_rate_high = Config.GROUP_RATE_HIGH
        
        self.load_all_data()
        
    def load_all_data(self):
        """โหลดข้อมูลทั้งหมด"""
        self.user_data = self._load_json(Config.USER_DATA_FILE, {})
        self.ticket_transcripts = self._load_json(Config.TICKET_TRANSCRIPTS_FILE, {})
        self.ticket_counter = self._load_json(Config.TICKET_COUNTER_FILE, 
                                              {"counter": 1, "date": datetime.datetime.now().strftime("%d%m%y")})
        logger.info(f"✅ โหลดข้อมูล: users={len(self.user_data)}, tickets={len(self.ticket_transcripts)}")
        
    def save_all_data(self):
        """บันทึกข้อมูลทั้งหมด"""
        self._save_json(Config.USER_DATA_FILE, self.user_data)
        self._save_json(Config.TICKET_TRANSCRIPTS_FILE, self.ticket_transcripts)
        self._save_json(Config.TICKET_COUNTER_FILE, self.ticket_counter)
        logger.info("✅ บันทึกข้อมูลทั้งหมดเรียบร้อย")
        
    def _load_json(self, filename, default):
        """โหลด JSON file"""
        try:
            if os.path.exists(filename):
                with open(filename, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return default
        except Exception as e:
            logger.error(f"❌ โหลด {filename} ล้มเหลว: {e}")
            return default
            
    def _save_json(self, filename, data):
        """บันทึก JSON file"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"❌ บันทึก {filename} ล้มเหลว: {e}")
            return False
    
    def get_next_ticket_number(self):
        """สร้างเลขตั๋วถัดไป"""
        current_date = datetime.datetime.now().strftime("%d%m%y")
        
        if self.ticket_counter["date"] != current_date:
            self.ticket_counter = {"counter": 1, "date": current_date}
        else:
            self.ticket_counter["counter"] += 1
            
        self._save_json(Config.TICKET_COUNTER_FILE, self.ticket_counter)
        return self.ticket_counter["counter"]
    
    def add_exp(self, user_id: int, amount: int):
        """เพิ่ม EXP ให้ผู้ใช้"""
        user_id_str = str(user_id)
        
        if user_id_str not in self.user_data:
            self.user_data[user_id_str] = {"exp": 0, "level": 0}
            
        self.user_data[user_id_str]["exp"] += amount
        
        # คำนวณ level ใหม่
        old_level = self.user_data[user_id_str]["level"]
        new_level = 0
        
        for level, data in sorted(Config.LEVELS.items(), reverse=True):
            if self.user_data[user_id_str]["exp"] >= data["exp"]:
                new_level = level
                break
                
        self.user_data[user_id_str]["level"] = new_level
        
        return old_level, new_level

# =======================================================================================
# ✅ Sushi Bot Class
# =======================================================================================

class SushiBot(commands.Bot):
    """Main bot class - ไม่มี global variables"""
    
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=self._get_intents(),
            help_command=None,
            allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False)
        )
        
        # Components
        self.data = DataManager()
        self.rate_handler = RateLimitHandler()
        
        # Update queue
        self.update_queue = asyncio.Queue()
        self.update_task = None
        
        # Last update times
        self.last_main_update = 0
        self.last_credit_update = 0
        
        logger.info("✅ สร้าง SushiBot instance สำเร็จ")
        
    @staticmethod
    def _get_intents():
        """ตั้งค่า intents"""
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True
        intents.messages = True
        intents.dm_messages = True
        return intents
        
    async def setup_hook(self):
        """ตั้งค่าเมื่อ bot เริ่มทำงาน"""
        logger.info("🔄 กำลังตั้งค่า bot...")
        
        # เริ่ม update task
        self.update_task = self.loop.create_task(self._process_updates())
        
        # sync commands แบบหน่วงเวลา
        self.loop.create_task(self._delayed_sync())
        
        logger.info("✅ ตั้งค่า bot เสร็จสิ้น")
        
    async def _delayed_sync(self):
        """sync commands แบบหน่วงเวลา"""
        await asyncio.sleep(10)
        try:
            await self.rate_handler.wait_if_needed()
            synced = await self.tree.sync()
            logger.info(f"✅ Synced {len(synced)} commands")
        except Exception as e:
            logger.error(f"❌ Sync ล้มเหลว: {e}")
            
    async def _process_updates(self):
        """ประมวลผลคิวอัพเดท"""
        while not self.is_closed():
            try:
                update_type = await self.update_queue.get()
                
                if update_type == "main":
                    await self._update_main_channel()
                elif update_type == "credit":
                    await self._update_credit_channel()
                    
                await asyncio.sleep(5)  # รอระหว่างอัพเดท
                
            except Exception as e:
                logger.error(f"❌ Update task error: {e}")
                await asyncio.sleep(30)
                
    async def queue_update(self, update_type: str):
        """เพิ่มงานอัพเดทลงคิว"""
        try:
            if not any(item == update_type for item in self.update_queue._queue):
                await self.update_queue.put(update_type)
        except:
            pass
            
    async def _update_main_channel(self):
        """อัพเดท main channel"""
        now = time.time()
        if now - self.last_main_update < 300:  # 5 นาที
            return
            
        try:
            await self.rate_handler.wait_if_needed()
            
            channel = self.get_channel(Config.MAIN_CHANNEL_ID)
            if not channel:
                return
                
            embed = self._create_main_embed()
            
            # หาข้อความเก่า
            async for msg in channel.history(limit=20):
                if msg.author == self.user and msg.embeds:
                    await msg.edit(embed=embed, view=MainShopView(self))
                    self.last_main_update = now
                    logger.info("✅ อัพเดท main channel")
                    return
                    
            # ส่งใหม่ถ้าไม่พบ
            await channel.send(embed=embed, view=MainShopView(self))
            self.last_main_update = now
            logger.info("✅ สร้าง main channel ใหม่")
            
        except Exception as e:
            logger.error(f"❌ อัพเดท main channel ล้มเหลว: {e}")
            
    async def _update_credit_channel(self):
        """อัพเดท credit channel"""
        now = time.time()
        if now - self.last_credit_update < 600:  # 10 นาที
            return
            
        try:
            await self.rate_handler.wait_if_needed()
            
            channel = self.get_channel(Config.CREDIT_CHANNEL_ID)
            if not channel:
                return
                
            # นับข้อความแบบ抽样
            count = 0
            async for _ in channel.history(limit=50):
                count += 1
                
            count = count + random.randint(0, 5)  # เพิ่ม randomness
            new_name = f"✅credit : {count}"
            
            if channel.name != new_name:
                await channel.edit(name=new_name)
                self.last_credit_update = now
                logger.info(f"✅ อัพเดท credit channel: {new_name}")
                
        except Exception as e:
            logger.error(f"❌ อัพเดท credit channel ล้มเหลว: {e}")
            
    def _create_main_embed(self) -> discord.Embed:
        """สร้าง embed สำหรับ main channel"""
        embed = discord.Embed(
            title="🍣 Sushi Shop 🍣 เปิดให้บริการ",
            color=0xFFA500
        )
        
        gamepass_status = "🟢" if self.data.gamepass_stock > 0 else "🔴"
        group_status = "🟢" if self.data.group_stock > 0 else "🔴"
        shop_status = "🟢 เปิด" if self.data.shop_open else "🔴 ปิดชั่วคราว"
        
        embed.add_field(
            name=f"🎮 กดเกมพาส | 📊 Stock: {self.data.gamepass_stock} {gamepass_status}",
            value=f"```\nเรท: {self.data.gamepass_rate} | โรแท้ยัดกลุ่มได้\nเช็คราคา: !gp <จำนวน>\n```",
            inline=False
        )
        
        embed.add_field(
            name=f"👥 โรบัคกลุ่ม | 📊 Stock: {self.data.group_stock} {group_status}", 
            value=f"```\nเรท: {self.data.group_rate_low} | 500+ บาท เรท {self.data.group_rate_high}\n⚠️ต้องเข้ากลุ่ม 15 วันก่อนซื้อ⚠️\n```",
            inline=False
        )
        
        embed.add_field(
            name="🏪 สถานะร้าน",
            value=f"```\n{shop_status}\n```",
            inline=False
        )
        
        return embed
        
    async def on_ready(self):
        """เมื่อ bot พร้อมทำงาน"""
        logger.info(f"✅ บอทออนไลน์: {self.user} (ID: {self.user.id})")
        
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="ร้าน Sushi Shop | พิมพ์ /help"
            )
        )
        
        # เริ่ม periodic tasks
        self.loop.create_task(self._periodic_tasks())
        
        # อัพเดทครั้งแรก
        await self.queue_update("main")
        
    async def _periodic_tasks(self):
        """งานที่ทำเป็นระยะ"""
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                await asyncio.sleep(600)  # 10 นาที
                await self.queue_update("main")
                await self.queue_update("credit")
            except Exception as e:
                logger.error(f"❌ Periodic task error: {e}")
                
    async def on_disconnect(self):
        """เมื่อตัดการเชื่อมต่อ"""
        logger.info("💾 บันทึกข้อมูล...")
        self.data.save_all_data()

# =======================================================================================
# ✅ Views
# =======================================================================================

class MainShopView(View):
    """Main shop view - รับ bot instance"""
    
    def __init__(self, bot: SushiBot):
        super().__init__(timeout=None)
        self.bot = bot
        
        # Gamepass button
        gamepass_disabled = not (bot.data.shop_open and bot.data.gamepass_stock > 0)
        self._add_button(
            label="เปิดตั๋วกดเกมพาส" if not gamepass_disabled else "ร้านปิด/สินค้าหมด",
            style=discord.ButtonStyle.success if not gamepass_disabled else discord.ButtonStyle.danger,
            custom_id="open_gamepass",
            emoji="🎮",
            disabled=gamepass_disabled,
            callback=self.gamepass_callback
        )
        
        # Group button
        group_disabled = not (bot.data.shop_open and bot.data.group_ticket_enabled and bot.data.group_stock > 0)
        self._add_button(
            label="เปิดตั๋ว Group" if not group_disabled else "บริการปิด/สินค้าหมด",
            style=discord.ButtonStyle.success if not group_disabled else discord.ButtonStyle.danger,
            custom_id="open_group",
            emoji="👥",
            disabled=group_disabled,
            callback=self.group_callback
        )
        
        # Level button
        self._add_button(
            label="ดูเลเวลของคุณ",
            style=discord.ButtonStyle.primary,
            custom_id="check_level",
            emoji="⭐",
            disabled=False,
            callback=self.level_callback
        )
        
    def _add_button(self, label, style, custom_id, emoji, disabled, callback):
        """เพิ่มปุ่ม"""
        button = Button(
            label=label,
            style=style,
            custom_id=custom_id,
            emoji=emoji,
            disabled=disabled
        )
        button.callback = callback
        self.add_item(button)
        
    async def gamepass_callback(self, interaction: discord.Interaction):
        await TicketHandler.open_ticket(interaction, self.bot, "gamepass")
        
    async def group_callback(self, interaction: discord.Interaction):
        await TicketHandler.open_ticket(interaction, self.bot, "group")
        
    async def level_callback(self, interaction: discord.Interaction):
        await LevelHandler.show_level(interaction, self.bot)


class QRView(View):
    """QR code view"""
    def __init__(self):
        super().__init__(timeout=None)
        
    @discord.ui.button(label="คัดลอกเลขบัญชี", style=discord.ButtonStyle.success, emoji="📋", custom_id="copy_bank")
    async def copy_bank(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("```120-239181-3 : ธนาคาร SCB```", ephemeral=True)


class DeliveryView(View):
    """Delivery view"""
    def __init__(self, bot: SushiBot, channel, product_type, robux_amount, price, buyer):
        super().__init__(timeout=None)
        self.bot = bot
        self.channel = channel
        self.product_type = product_type
        self.robux_amount = robux_amount
        self.price = price
        self.buyer = buyer
        self.delivered = False
        
    @discord.ui.button(label="ส่งสินค้าแล้ว ✅", style=discord.ButtonStyle.success, emoji="✅", custom_id="deliver")
    async def deliver(self, interaction: discord.Interaction, button: Button):
        await TicketHandler.handle_delivery(interaction, self)
        
    @discord.ui.button(label="ยกเลิก ❌", style=discord.ButtonStyle.danger, emoji="❌", custom_id="cancel_order")
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("❌ คำสั่งซื้อถูกยกเลิก", ephemeral=True)
        await interaction.message.delete()


class ConfirmDeliveryView(View):
    """Confirm delivery view"""
    def __init__(self, bot: SushiBot, channel, product_type, robux_amount, price, buyer, image_url):
        super().__init__(timeout=300)
        self.bot = bot
        self.channel = channel
        self.product_type = product_type
        self.robux_amount = robux_amount
        self.price = price
        self.buyer = buyer
        self.image_url = image_url
        self.delivered = False
        
    @discord.ui.button(label="ยืนยัน ✅", style=discord.ButtonStyle.success, emoji="✅", custom_id="confirm")
    async def confirm(self, interaction: discord.Interaction, button: Button):
        await TicketHandler.confirm_delivery(interaction, self)


class ConfirmTicketView(View):
    """Confirm ticket view"""
    def __init__(self, embed: discord.Embed):
        super().__init__(timeout=300)
        self.embed = embed
        
    @discord.ui.button(label="❌ ยกเลิก", style=discord.ButtonStyle.danger, custom_id="cancel_ticket")
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("❌ ยกเลิกเรียบร้อย", ephemeral=True)
        await interaction.message.delete()

# =======================================================================================
# ✅ Modals
# =======================================================================================

class GamepassModal(Modal, title="📋 แบบฟอร์มกดเกมพาส"):
    """Gamepass form modal"""
    
    map_name = TextInput(
        label="🗺 ชื่อแมพ",
        placeholder="เช่น Gift Simulator",
        required=True,
        max_length=100
    )
    
    gamepass_name = TextInput(
        label="💸 ชื่อเกมพาส",
        placeholder="เช่น x3 Speed 3 ชิ้น",
        required=True,
        max_length=100
    )
    
    robux_amount = TextInput(
        label="🎟 ราคาโรบัค",
        placeholder="เช่น 300 หรือ 100+100+100",
        required=True,
        max_length=50
    )
    
    def __init__(self, bot: SushiBot):
        super().__init__()
        self.bot = bot
        
    async def on_submit(self, interaction: discord.Interaction):
        await TicketHandler.process_gamepass_modal(interaction, self)


class GroupModal(Modal, title="📋 แบบฟอร์มสั่งซื้อ Robux Group"):
    """Group form modal"""
    
    username = TextInput(
        label="🪪 ชื่อในเกม",
        placeholder="Username",
        required=True,
        max_length=50
    )
    
    robux_amount = TextInput(
        label="💸 จำนวนโรบัค",
        placeholder="เช่น 1000",
        required=True,
        max_length=50
    )
    
    def __init__(self, bot: SushiBot):
        super().__init__()
        self.bot = bot
        
    async def on_submit(self, interaction: discord.Interaction):
        await TicketHandler.process_group_modal(interaction, self)

# =======================================================================================
# ✅ Handlers
# =======================================================================================

class TicketHandler:
    """จัดการ ticket operations"""
    
    @staticmethod
    async def open_ticket(interaction: discord.Interaction, bot: SushiBot, ticket_type: str):
        """เปิดตั๋วใหม่"""
        try:
            guild = interaction.guild
            user = interaction.user
            
            if not guild:
                await interaction.response.send_message("❌ ใช้ได้เฉพาะในเซิร์ฟเวอร์", ephemeral=True)
                return
                
            channel_name = f"ticket-{user.name}-{user.id}"
            
            # ตรวจสอบตั๋วซ้ำ
            existing = discord.utils.get(guild.text_channels, name=channel_name)
            if existing:
                view = discord.ui.View()
                view.add_item(discord.ui.Button(
                    label="📩 ไปที่ตั๋ว",
                    url=f"https://discord.com/channels/{guild.id}/{existing.id}",
                    style=discord.ButtonStyle.link
                ))
                await interaction.response.send_message("📌 คุณมีตั๋วอยู่แล้ว!", view=view, ephemeral=True)
                return
                
            # ตั้งค่าสิทธิ์
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
                user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            
            admin_role = guild.get_role(Config.ADMIN_ROLE_ID)
            if admin_role:
                overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
                
            # หาหรือสร้าง category
            category_name = "🍣Sushi Gamepass 🍣" if ticket_type == "gamepass" else "💰Robux Group💰"
            category = discord.utils.get(guild.categories, name=category_name)
            if not category:
                category = await guild.create_category(category_name)
                
            await interaction.response.send_message("🔄 กำลังเปิดตั๋ว...", ephemeral=True)
            
            # สร้าง channel
            channel = await guild.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
                category=category
            )
            
            # อัพเดท stock
            if ticket_type == "gamepass":
                bot.data.gamepass_stock -= 1
            else:
                bot.data.group_stock -= 1
                
            # บันทึก activity
            bot.data.ticket_activity[channel.id] = {
                'last_activity': datetime.datetime.now(),
                'ty_used': False
            }
            
            # ส่งลิงก์
            view = discord.ui.View()
            view.add_item(discord.ui.Button(
                label="📩 ไปที่ตั๋ว",
                url=f"https://discord.com/channels/{guild.id}/{channel.id}",
                style=discord.ButtonStyle.link
            ))
            await interaction.edit_original_response(content="✅ เปิดตั๋วเรียบร้อย!", view=view)
            
            # ส่งข้อความต้อนรับ
            embed = discord.Embed(title="🍣 Sushi Shop 🍣", color=0x00FF99)
            embed.add_field(name="👤 ผู้ซื้อ", value=user.mention, inline=False)
            if admin_role:
                embed.add_field(name="🛠️ ทีมงาน", value=admin_role.mention, inline=False)
                
            await channel.send(embed=embed)
            
            # ส่ง modal
            if ticket_type == "gamepass":
                await channel.send("📝 **กรุณากรอกแบบฟอร์ม:**")
                await channel.send(view=discord.ui.View().add_item(
                    discord.ui.Button(label="📝 กรอกแบบฟอร์ม", style=discord.ButtonStyle.primary, custom_id="open_modal")
                ))
                
        except Exception as e:
            logger.error(f"❌ เปิดตั๋วล้มเหลว: {e}")
            
    @staticmethod
    async def process_gamepass_modal(interaction: discord.Interaction, modal: GamepassModal):
        """ประมวลผล gamepass modal"""
        try:
            expr = modal.robux_amount.value.lower().replace("x", "*").replace("÷", "/")
            
            if not re.match(r"^[\d\s\+\-\*\/\(\)]+$", expr):
                await interaction.response.send_message("❌ กรุณากรอกตัวเลขให้ถูกต้อง", ephemeral=True)
                return
                
            robux = int(eval(expr))
            price = robux / modal.bot.data.gamepass_rate
            
            embed = discord.Embed(title="📨 รายละเอียดการสั่งซื้อ", color=0x00FF99)
            embed.add_field(name="🗺️ แมพ", value=modal.map_name.value, inline=False)
            embed.add_field(name="🎟 เกมพาส", value=modal.gamepass_name.value, inline=False)
            embed.add_field(name="💸 ราคาโรบัค", value=f"{robux:,}", inline=True)
            embed.add_field(name="💰 ราคา", value=f"{price:,.0f} บาท", inline=True)
            
            await interaction.response.send_message(embed=embed, view=ConfirmTicketView(embed))
            
        except Exception as e:
            await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)
            
    @staticmethod
    async def process_group_modal(interaction: discord.Interaction, modal: GroupModal):
        """ประมวลผล group modal"""
        try:
            robux = int(modal.robux_amount.value)
            rate = modal.bot.data.group_rate_low if robux < 1500 else modal.bot.data.group_rate_high
            price = robux / rate
            
            embed = discord.Embed(title="📨 รายละเอียดคำสั่งซื้อ", color=0x00FF99)
            embed.add_field(name="🪪 ชื่อในเกม", value=modal.username.value, inline=False)
            embed.add_field(name="💸 จำนวนโรบัค", value=f"{robux:,}", inline=True)
            embed.add_field(name="💰 ราคา", value=f"{price:,.0f} บาท", inline=True)
            
            await interaction.response.send_message(embed=embed, view=ConfirmTicketView(embed))
            
        except ValueError:
            await interaction.response.send_message("❌ กรุณากรอกตัวเลข", ephemeral=True)
            
    @staticmethod
    async def handle_delivery(interaction: discord.Interaction, view: DeliveryView):
        """จัดการปุ่มส่งสินค้า"""
        # ตรวจสอบสิทธิ์
        admin_role = interaction.guild.get_role(Config.ADMIN_ROLE_ID)
        if not admin_role or admin_role not in interaction.user.roles:
            await interaction.response.send_message("❌ ไม่มีสิทธิ์", ephemeral=True)
            return
            
        if view.delivered:
            await interaction.response.edit_message(content="✅ ส่งแล้ว", embed=None, view=None)
            return
            
        # หารูป
        image_url = None
        async for msg in view.channel.history(limit=5):
            if msg.author == interaction.user and msg.attachments:
                for att in msg.attachments:
                    if any(att.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif']):
                        image_url = att.url
                        break
                if image_url:
                    break
                    
        if not image_url:
            await interaction.response.send_message("❌ แนบรูปก่อน!", ephemeral=True)
            return
            
        # ยืนยัน
        embed = discord.Embed(title="📦 ยืนยันการส่ง", color=0x00FF00)
        embed.set_image(url=image_url)
        
        confirm_view = ConfirmDeliveryView(
            view.bot, view.channel, view.product_type, 
            view.robux_amount, view.price, view.buyer, image_url
        )
        
        await interaction.response.send_message(embed=embed, view=confirm_view, ephemeral=True)
        
    @staticmethod
    async def confirm_delivery(interaction: discord.Interaction, view: ConfirmDeliveryView):
        """ยืนยันการส่งสินค้า"""
        if view.delivered:
            return
            
        view.delivered = True
        
        # จัดการตั๋ว
        await TicketHandler.after_delivery(view.channel, view.buyer, view.bot)
        
        # สร้างใบเสร็จ
        colors = {"Gamepass": 0xFFA500, "Group": 0x00FFFF, "Limited": 0x00FF00}
        embed = discord.Embed(
            title=f"🍣 ใบเสร็จ ({view.product_type}) 🍣",
            color=colors.get(view.product_type, 0xFFA500)
        )
        embed.add_field(name="😊 ผู้ซื้อ", value=view.buyer.mention if view.buyer else "ไม่ทราบ", inline=False)
        embed.add_field(name="💸 จำนวน", value=f"{view.robux_amount:,}", inline=True)
        embed.add_field(name="💰 ราคา", value=f"{view.price:,.0f} บาท", inline=True)
        
        if view.image_url:
            embed.set_image(url=view.image_url)
            
        # ส่งไป log channel
        log_channel = view.bot.get_channel(Config.SALES_LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(embed=embed)
            
        await view.channel.send(embed=embed)
        await interaction.response.edit_message(content="✅ สำเร็จ", embed=None, view=None)
        
    @staticmethod
    async def after_delivery(channel, buyer, bot: SushiBot):
        """หลังส่งสินค้า"""
        try:
            # ย้ายไป delivered category
            delivered = channel.guild.get_channel(Config.DELIVERED_CATEGORY_ID)
            if delivered:
                # สร้างชื่อใหม่
                now = datetime.datetime.now()
                new_name = f"{now.strftime('%d%m%y%H%M')}{bot.data.get_next_ticket_number()}-1099-wforr"
                
                await bot.rate_handler.wait_if_needed()
                await channel.edit(category=delivered, name=new_name)
                
                # ส่ง embed ให้เครดิต
                embed = discord.Embed(
                    title="✅ ส่งของเรียบร้อย",
                    description="สินค้าถูกจัดส่งเรียบร้อย!\nฝากกดเครดิตด้วยนะคะ ⭐",
                    color=0x00FF00
                )
                await channel.send(embed=embed)
                
                # ตั้งเวลา archive
                bot.loop.create_task(TicketHandler.archive_later(channel, buyer, bot, 1800))
                
        except Exception as e:
            logger.error(f"❌ after_delivery error: {e}")
            
    @staticmethod
    async def archive_later(channel, buyer, bot: SushiBot, delay: int):
        """ย้ายไป archive หลังจากหน่วงเวลา"""
        await asyncio.sleep(delay)
        
        try:
            if not channel or channel not in channel.guild.channels:
                return
                
            # บันทึก transcript
            filename = f"transcript-{channel.name}-{int(time.time())}.json"
            bot.data.ticket_transcripts[str(channel.id)] = {
                "filename": filename,
                "channel": channel.name,
                "time": datetime.datetime.now().isoformat()
            }
            
            # ย้ายไป archive
            archived = channel.guild.get_channel(Config.ARCHIVED_CATEGORY_ID)
            if archived:
                await bot.rate_handler.wait_if_needed()
                await channel.edit(category=archived)
                logger.info(f"✅ Archived {channel.name}")
                
        except Exception as e:
            logger.error(f"❌ Archive error: {e}")


class LevelHandler:
    """จัดการ level และ EXP"""
    
    @staticmethod
    async def show_level(interaction: discord.Interaction, bot: SushiBot):
        """แสดง level ของผู้ใช้"""
        user_id = str(interaction.user.id)
        
        if user_id not in bot.data.user_data:
            bot.data.user_data[user_id] = {"exp": 0, "level": 0}
            
        data = bot.data.user_data[user_id]
        
        embed = discord.Embed(
            title=f"🍣 ระดับของคุณ {interaction.user.display_name}",
            color=0x00FF99
        )
        embed.add_field(name="🎮 ระดับ", value=f"Level {data['level']}", inline=True)
        embed.add_field(name="⭐ EXP", value=f"**{data['exp']:,}**", inline=True)
        
        if data['level'] < 9:
            next_exp = Config.LEVELS[data['level'] + 1]["exp"]
            need = next_exp - data['exp']
            embed.add_field(name="🎯 ต้องใช้อีก", value=f"**{need:,} EXP**", inline=False)
            
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    @staticmethod
    async def add_exp_and_update(ctx, user_id: int, amount: int, bot: SushiBot):
        """เพิ่ม EXP และอัพเดทยศ"""
        old_level, new_level = bot.data.add_exp(user_id, amount)
        
        if new_level != old_level:
            await LevelHandler.update_roles(ctx.guild, user_id, old_level, new_level, bot)
            
    @staticmethod
    async def update_roles(guild, user_id: int, old_level: int, new_level: int, bot: SushiBot):
        """อัพเดทยศผู้ใช้"""
        try:
            member = guild.get_member(user_id)
            if not member:
                return
                
            # ลบ role เก่า
            if old_level > 0 and old_level in Config.LEVELS:
                old_role = guild.get_role(Config.LEVELS[old_level]["role_id"])
                if old_role and old_role in member.roles:
                    await bot.rate_handler.wait_if_needed()
                    await member.remove_roles(old_role)
                    
            # เพิ่ม role ใหม่
            if new_level > 0 and new_level in Config.LEVELS:
                new_role = guild.get_role(Config.LEVELS[new_level]["role_id"])
                if new_role and new_role not in member.roles:
                    await bot.rate_handler.wait_if_needed()
                    await member.add_roles(new_role)
                    logger.info(f"✅ {member.display_name} ได้รับ {Config.LEVELS[new_level]['role_name']}")
                    
        except Exception as e:
            logger.error(f"❌ อัพเดทยศล้มเหลว: {e}")

# =======================================================================================
# ✅ สร้าง bot instance
# =======================================================================================
bot = SushiBot()

# =======================================================================================
# ✅ Commands
# =======================================================================================

def admin_check():
    """Decorator สำหรับตรวจสอบสิทธิ์แอดมิน"""
    async def predicate(ctx):
        if ctx.author.guild_permissions.administrator:
            return True
        admin_role = ctx.guild.get_role(Config.ADMIN_ROLE_ID)
        if admin_role and admin_role in ctx.author.roles:
            return True
        await ctx.send("❌ เฉพาะแอดมิน", delete_after=5)
        return False
    return commands.check(predicate)


@bot.command()
@admin_check()
async def od(ctx, *, expression: str):
    """สั่งซื้อ Gamepass"""
    if not ctx.channel.name.startswith("ticket-"):
        await ctx.send("❌ ใช้ในตั๋วเท่านั้น", delete_after=5)
        return
        
    try:
        expr = expression.replace(",", "").lower().replace("x", "*")
        robux = int(eval(expr))
        price = robux / bot.data.gamepass_rate
        
        # หาผู้ซื้อ
        buyer = None
        parts = ctx.channel.name.split('-')
        if len(parts) >= 3:
            try:
                buyer = ctx.guild.get_member(int(parts[-1]))
            except:
                pass
                
        if buyer:
            await LevelHandler.add_exp_and_update(ctx, buyer.id, robux, bot)
            
        bot.data.gamepass_stock -= robux
        if bot.data.gamepass_stock < 0:
            bot.data.gamepass_stock = 0
            
        embed = discord.Embed(title="🍣คำสั่งซื้อ🍣", color=0xFFA500)
        embed.add_field(name="📦 ประเภท", value="Gamepass", inline=False)
        embed.add_field(name="💸 Robux", value=f"{robux:,}", inline=True)
        embed.add_field(name="💰 ราคา", value=f"{price:,.0f} บาท", inline=True)
        
        ctx.channel.robux_amount = str(robux)
        
        view = DeliveryView(bot, ctx.channel, "Gamepass", robux, price, buyer)
        await ctx.send(embed=embed, view=view)
        
    except Exception as e:
        await ctx.send(f"❌ ผิดพลาด: {e}", delete_after=10)


@bot.command()
@admin_check()
async def odg(ctx, *, expression: str):
    """สั่งซื้อ Group"""
    if not ctx.channel.name.startswith("ticket-"):
        await ctx.send("❌ ใช้ในตั๋วเท่านั้น", delete_after=5)
        return
        
    try:
        expr = expression.replace(",", "").lower().replace("x", "*")
        robux = int(eval(expr))
        rate = bot.data.group_rate_low if robux < 1500 else bot.data.group_rate_high
        price = robux / rate
        
        buyer = None
        parts = ctx.channel.name.split('-')
        if len(parts) >= 3:
            try:
                buyer = ctx.guild.get_member(int(parts[-1]))
            except:
                pass
                
        if buyer:
            await LevelHandler.add_exp_and_update(ctx, buyer.id, robux, bot)
            
        bot.data.group_stock -= robux
        if bot.data.group_stock < 0:
            bot.data.group_stock = 0
            
        embed = discord.Embed(title="🍣คำสั่งซื้อ🍣", color=0x00FFFF)
        embed.add_field(name="📦 ประเภท", value="Group", inline=False)
        embed.add_field(name="💸 Robux", value=f"{robux:,}", inline=True)
        embed.add_field(name="💰 ราคา", value=f"{price:,.0f} บาท", inline=True)
        
        ctx.channel.robux_amount = str(robux)
        
        view = DeliveryView(bot, ctx.channel, "Group", robux, price, buyer)
        await ctx.send(embed=embed, view=view)
        
    except Exception as e:
        await ctx.send(f"❌ ผิดพลาด: {e}", delete_after=10)


@bot.command()
@admin_check()
async def odl(ctx, item_name: str, value: str):
    """สั่งซื้อ Limited"""
    if not ctx.channel.name.startswith("ticket-"):
        await ctx.send("❌ ใช้ในตั๋วเท่านั้น", delete_after=5)
        return
        
    try:
        price = int(value.replace(",", ""))
        
        buyer = None
        parts = ctx.channel.name.split('-')
        if len(parts) >= 3:
            try:
                buyer = ctx.guild.get_member(int(parts[-1]))
            except:
                pass
                
        if buyer:
            await LevelHandler.add_exp_and_update(ctx, buyer.id, price, bot)
            
        embed = discord.Embed(title="🍣คำสั่งซื้อ🍣", color=0x00FF00)
        embed.add_field(name="📦 ประเภท", value="Limited", inline=False)
        embed.add_field(name="🎁 ชื่อ", value=item_name, inline=True)
        embed.add_field(name="💰 ราคา", value=f"{price:,} บาท", inline=True)
        
        ctx.channel.robux_amount = str(price)
        
        view = DeliveryView(bot, ctx.channel, "Limited", 0, price, buyer)
        await ctx.send(embed=embed, view=view)
        
    except Exception as e:
        await ctx.send(f"❌ ผิดพลาด: {e}", delete_after=10)


@bot.command()
@admin_check()
async def qr(ctx):
    """แสดง QR Code"""
    embed = discord.Embed(
        title="⚠️ช่องทางการโอนเงิน⚠️",
        description="**หจก. วอเตอร์ เทค เซลล์ แอนด์ เซอร์วิส**\n**120-239181-3** (SCB)",
        color=0x00CCFF
    )
    embed.set_image(url="https://media.discordapp.net/attachments/1361004239043821610/1444373113319198840/160-1-43871-9_1.png")
    await ctx.send(embed=embed, view=QRView())
    try:
        await ctx.message.delete()
    except:
        pass


@bot.command()
@admin_check()
async def ty(ctx):
    """ยืนยันการส่ง"""
    if ctx.channel.name.startswith("ticket-"):
        # คืน stock
        if ctx.channel.category and "gamepass" in ctx.channel.category.name.lower():
            bot.data.gamepass_stock += 1
        elif ctx.channel.category and "group" in ctx.channel.category.name.lower():
            bot.data.group_stock += 1
            
        # หาผู้ซื้อ
        buyer = None
        parts = ctx.channel.name.split('-')
        if len(parts) >= 3:
            try:
                buyer = ctx.guild.get_member(int(parts[-1]))
            except:
                pass
                
        robux = getattr(ctx.channel, 'robux_amount', None)
        
        await TicketHandler.after_delivery(ctx.channel, buyer, bot)
        await ctx.send("✅ ยืนยันการส่ง")
    else:
        await ctx.send("❌ ใช้ในตั๋วเท่านั้น")


@bot.command()
@admin_check()
async def stock(ctx, stock_type: str = None, amount: str = None):
    """ตรวจสอบ/ตั้งค่า stock"""
    if stock_type is None:
        embed = discord.Embed(title="📊 Stock", color=0x00FF99)
        embed.add_field(name="🎮 Gamepass", value=f"**{bot.data.gamepass_stock:,}**", inline=True)
        embed.add_field(name="👥 Group", value=f"**{bot.data.group_stock:,}**", inline=True)
        await ctx.send(embed=embed)
    elif stock_type.lower() in ["gp", "gamepass"]:
        if amount:
            try:
                bot.data.gamepass_stock = max(0, int(amount.replace(",", "")))
                await ctx.send(f"✅ Gamepass = {bot.data.gamepass_stock}")
                await bot.queue_update("main")
            except:
                await ctx.send("❌ ใส่ตัวเลข")
        else:
            await ctx.send(f"🎮 Gamepass: **{bot.data.gamepass_stock:,}**")
    elif stock_type.lower() in ["g", "group"]:
        if amount:
            try:
                bot.data.group_stock = max(0, int(amount.replace(",", "")))
                await ctx.send(f"✅ Group = {bot.data.group_stock}")
                await bot.queue_update("main")
            except:
                await ctx.send("❌ ใส่ตัวเลข")
        else:
            await ctx.send(f"👥 Group: **{bot.data.group_stock:,}**")


@bot.command()
@admin_check()
async def rate(ctx, rate_type: str = None, low: str = None, high: str = None):
    """เปลี่ยนเรท"""
    if rate_type is None:
        embed = discord.Embed(title="📊 อัตรา", color=0x00FF99)
        embed.add_field(name="🎮 Gamepass", value=f"**{bot.data.gamepass_rate}**", inline=True)
        embed.add_field(name="👥 Group", value=f"**{bot.data.group_rate_low} - {bot.data.group_rate_high}**", inline=True)
        await ctx.send(embed=embed)
    elif rate_type.lower() == "group":
        if low and high:
            try:
                bot.data.group_rate_low = float(low)
                bot.data.group_rate_high = float(high)
                await ctx.send(f"✅ Group = {bot.data.group_rate_low} - {bot.data.group_rate_high}")
                await bot.queue_update("main")
            except:
                await ctx.send("❌ ใส่ตัวเลข")
        else:
            await ctx.send("❌ ใช้: !rate group <low> <high>")
    else:
        try:
            bot.data.gamepass_rate = float(rate_type)
            await ctx.send(f"✅ Gamepass = {bot.data.gamepass_rate}")
            await bot.queue_update("main")
        except:
            await ctx.send("❌ ใส่ตัวเลข")


@bot.command()
@admin_check()
async def sushi(ctx):
    """เปิด/ปิดร้าน"""
    bot.data.shop_open = not bot.data.shop_open
    status = "✅ เปิด" if bot.data.shop_open else "❌ ปิด"
    await ctx.send(f"🏪 **{status}**")
    await bot.queue_update("main")


@bot.command()
@admin_check()
async def group(ctx, status: str = None):
    """เปิด/ปิด Group ticket"""
    if status is None:
        current = "✅ เปิด" if bot.data.group_ticket_enabled else "❌ ปิด"
        await ctx.send(f"👥 **{current}**")
    elif status.lower() in ["on", "enable", "เปิด"]:
        bot.data.group_ticket_enabled = True
        await ctx.send("✅ เปิด Group")
    elif status.lower() in ["off", "disable", "ปิด"]:
        bot.data.group_ticket_enabled = False
        await ctx.send("❌ ปิด Group")
    else:
        await ctx.send("❌ ใช้ on/off")
    await bot.queue_update("main")


@bot.command()
async def level(ctx, member: discord.Member = None):
    """ดูเลเวล"""
    if not member:
        member = ctx.author
        
    user_id = str(member.id)
    if user_id not in bot.data.user_data:
        bot.data.user_data[user_id] = {"exp": 0, "level": 0}
        
    data = bot.data.user_data[user_id]
    
    embed = discord.Embed(title=f"🍣 ระดับ {member.display_name}", color=0x00FF99)
    embed.add_field(name="🎮 ระดับ", value=f"Level {data['level']}", inline=True)
    embed.add_field(name="⭐ EXP", value=f"**{data['exp']:,}**", inline=True)
    
    if data['level'] < 9:
        next_exp = Config.LEVELS[data['level'] + 1]["exp"]
        embed.add_field(name="🎯 ต้องใช้อีก", value=f"**{next_exp - data['exp']:,} EXP**", inline=False)
        
    await ctx.send(embed=embed)


@bot.command()
async def gp(ctx, *, expr: str):
    """คำนวณ Gamepass"""
    try:
        robux = int(eval(expr.replace("x", "*").replace(",", "")))
        price = robux / bot.data.gamepass_rate
        await ctx.send(f"🎮 {robux:,} Robux = **{price:,.0f} บาท**")
    except:
        await ctx.send("❌ ผิดพลาด")


@bot.command()
async def g(ctx, *, expr: str):
    """คำนวณ Group"""
    try:
        robux = int(eval(expr.replace("x", "*").replace(",", "")))
        rate = bot.data.group_rate_low if robux < 1500 else bot.data.group_rate_high
        price = robux / rate
        await ctx.send(f"👥 {robux:,} Robux = **{price:,.0f} บาท**")
    except:
        await ctx.send("❌ ผิดพลาด")


@bot.command()
async def gpb(ctx, *, expr: str):
    """บาท -> Robux (Gamepass)"""
    try:
        baht = float(expr.replace(",", ""))
        robux = baht * bot.data.gamepass_rate
        await ctx.send(f"🎮 {baht:,.0f} บาท = **{robux:,.0f} Robux**")
    except:
        await ctx.send("❌ ผิดพลาด")


@bot.command()
async def gb(ctx, *, expr: str):
    """บาท -> Robux (Group)"""
    try:
        baht = float(expr.replace(",", ""))
        rate = bot.data.group_rate_low if baht < 500 else bot.data.group_rate_high
        robux = baht * rate
        await ctx.send(f"👥 {baht:,.0f} บาท = **{robux:,.0f} Robux**")
    except:
        await ctx.send("❌ ผิดพลาด")


@bot.command()
async def tax(ctx, *, expr: str):
    """คำนวณภาษี"""
    try:
        expr = expr.replace(" ", "")
        if re.match(r"^\d+$", expr):
            num = int(expr)
            await ctx.send(f"💰 {num:,} Robux หลังหัก 30% = **{num * 0.7:,.0f}**")
        elif re.match(r"^\d+-\d+%$", expr):
            parts = expr.split('-')
            num = int(parts[0])
            percent = int(parts[1].replace('%', ''))
            await ctx.send(f"💰 {num:,} Robux หลังหัก {percent}% = **{num * (1 - percent/100):,.0f}**")
        else:
            await ctx.send("❌ ใช้ !tax 100 หรือ !tax 100-30%")
    except:
        await ctx.send("❌ ผิดพลาด")


@bot.command(name='help')
async def help_cmd(ctx):
    """แสดงช่วยเหลือ"""
    embed = discord.Embed(
        title="🍣 Sushi Shop - คำสั่ง",
        description=(
            "**ทั่วไป:**\n"
            "`!gp <จำนวน>` - คำนวณ Gamepass\n"
            "`!g <จำนวน>` - คำนวณ Group\n"
            "`!gpb <บาท>` - บาท -> Robux (Gamepass)\n"
            "`!gb <บาท>` - บาท -> Robux (Group)\n"
            "`!tax <จำนวน>` - คำนวณภาษี\n"
            "`!level` - ดูเลเวล\n\n"
            "**แอดมิน:**\n"
            "`!stock` - ดู stock\n"
            "`!rate` - ดูเรท\n"
            "`!sushi` - เปิด/ปิดร้าน\n"
            "`!group on/off` - เปิด/ปิด Group\n"
            "`!od <จำนวน>` - สั่ง Gamepass\n"
            "`!odg <จำนวน>` - สั่ง Group\n"
            "`!odl <ชื่อ> <ราคา>` - สั่ง Limited\n"
            "`!ty` - ยืนยันส่ง\n"
            "`!qr` - แสดง QR"
        ),
        color=0x00FF99
    )
    await ctx.send(embed=embed, delete_after=60)

# =======================================================================================
# ✅ Slash Commands
# =======================================================================================

@bot.tree.command(name="gamepass", description="คำนวณราคา Gamepass")
async def gamepass_slash(interaction: discord.Interaction, amount: str):
    try:
        robux = int(eval(amount.replace("x", "*").replace(",", "")))
        price = robux / bot.data.gamepass_rate
        await interaction.response.send_message(f"🎮 {robux:,} Robux = **{price:,.0f} บาท**")
    except:
        await interaction.response.send_message("❌ ผิดพลาด")


@bot.tree.command(name="group", description="คำนวณราคา Group")
async def group_slash(interaction: discord.Interaction, amount: str):
    try:
        robux = int(eval(amount.replace("x", "*").replace(",", "")))
        rate = bot.data.group_rate_low if robux < 1500 else bot.data.group_rate_high
        price = robux / rate
        await interaction.response.send_message(f"👥 {robux:,} Robux = **{price:,.0f} บาท**")
    except:
        await interaction.response.send_message("❌ ผิดพลาด")


@bot.tree.command(name="baht_gamepass", description="คำนวณ Robux จากเงินบาท (Gamepass)")
async def baht_gamepass_slash(interaction: discord.Interaction, amount: str):
    try:
        baht = float(amount.replace(",", ""))
        robux = baht * bot.data.gamepass_rate
        await interaction.response.send_message(f"🎮 {baht:,.0f} บาท = **{robux:,.0f} Robux**")
    except:
        await interaction.response.send_message("❌ ผิดพลาด")


@bot.tree.command(name="baht_group", description="คำนวณ Robux จากเงินบาท (Group)")
async def baht_group_slash(interaction: discord.Interaction, amount: str):
    try:
        baht = float(amount.replace(",", ""))
        rate = bot.data.group_rate_low if baht < 500 else bot.data.group_rate_high
        robux = baht * rate
        await interaction.response.send_message(f"👥 {baht:,.0f} บาท = **{robux:,.0f} Robux**")
    except:
        await interaction.response.send_message("❌ ผิดพลาด")


@bot.tree.command(name="tax", description="คำนวณ Robux หลังหักภาษี")
async def tax_slash(interaction: discord.Interaction, amount: str):
    try:
        amount = amount.replace(" ", "")
        if re.match(r"^\d+$", amount):
            num = int(amount)
            await interaction.response.send_message(f"💰 {num:,} Robux หลังหัก 30% = **{num * 0.7:,.0f}**")
        elif re.match(r"^\d+-\d+%$", amount):
            parts = amount.split('-')
            num = int(parts[0])
            percent = int(parts[1].replace('%', ''))
            await interaction.response.send_message(f"💰 {num:,} Robux หลังหัก {percent}% = **{num * (1 - percent/100):,.0f}**")
        else:
            await interaction.response.send_message("❌ ใช้ 100 หรือ 100-30%")
    except:
        await interaction.response.send_message("❌ ผิดพลาด")


@bot.tree.command(name="help", description="แสดงคำสั่งทั้งหมด")
async def help_slash(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🍣 Sushi Shop - คำสั่ง",
        description=(
            "**Slash Commands:**\n"
            "`/gamepass <จำนวน>`\n"
            "`/group <จำนวน>`\n"
            "`/baht_gamepass <บาท>`\n"
            "`/baht_group <บาท>`\n"
            "`/tax <จำนวน>`\n"
            "`/help`\n\n"
            "**Text Commands ในเซิร์ฟเวอร์:**\n"
            "`!gp`, `!g`, `!gpb`, `!gb`, `!tax`, `!level`"
        ),
        color=0x00FF99
    )
    await interaction.response.send_message(embed=embed)

# =======================================================================================
# ✅ Events
# =======================================================================================

@bot.event
async def on_message(message):
    if message.author.bot:
        return
        
    if message.channel.id == Config.CREDIT_CHANNEL_ID:
        await bot.queue_update("credit")
        
    await bot.process_commands(message)


@bot.event
async def on_command_completion(ctx):
    if ctx.channel.name.startswith("ticket-"):
        bot.data.ticket_activity[ctx.channel.id] = {
            'last_activity': datetime.datetime.now(),
            'ty_used': ctx.command.name == 'ty'
        }

# =======================================================================================
# ✅ Main
# =======================================================================================

if __name__ == "__main__":
    logger.info("🚀 เริ่มต้นบอท...")
    
    # เริ่ม web server
    try:
        server_on()
        logger.info("✅ Web server started")
    except Exception as e:
        logger.error(f"❌ Web server error: {e}")
    
    # รันบอท
    token = os.getenv("TOKEN")
    if not token:
        logger.error("❌ ไม่มี TOKEN")
        sys.exit(1)
        
    try:
        bot.run(token, log_handler=None)
    except Exception as e:
        logger.error(f"❌  fatal: {e}")
        sys.exit(1)
