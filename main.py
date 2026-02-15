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
from typing import Optional, Dict, Any, List
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
            app.run(host='0.0.0.0', port=8080)
        t = threading.Thread(target=run)
        t.daemon = True
        t.start()
        logger.info("✅ Server started on port 8080 (fallback)")

# ตั้งค่าเรท (ค่าเริ่มต้น)
gamepass_rate = 6
group_rate_low = 4
group_rate_high = 4.5

# ตั้งค่าพื้นฐาน
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.messages = True
intents.dm_messages = True

shop_open = True
group_ticket_enabled = True

# ตั้งค่าห้องหลักและ stock
MAIN_CHANNEL_ID = 1361044752975532152
SALES_LOG_CHANNEL_ID = 1402993077643120720
CREDIT_CHANNEL_ID = 1363250076549382246
DELIVERED_CATEGORY_ID = 1419565515088597083
ARCHIVED_CATEGORY_ID = 1445086228113264650

gamepass_stock = 50000
group_stock = 0

# เก็บข้อมูลโน้ตส่วนตัว
user_notes = {}

# ระบบติดตามกิจกรรมในตั๋ว
ticket_activity = {}

# ระบบเก็บเลเวลและ EXP
user_data_file = "user_data.json"
ticket_transcripts_file = "ticket_transcripts.json"
ticket_counter_file = "ticket_counter.json"

# =======================================================================================
# ✅ Rate limiting handler - IMPROVED VERSION
# =======================================================================================

class RateLimitHandler:
    def __init__(self):
        self.request_times = deque(maxlen=100)
        self.last_reset = time.time()
        self.min_interval = 1.2  # Increased from 1.0 to 1.2 seconds
        self.max_requests_per_minute = 25  # Reduced from 30 to 25
        self.consecutive_429s = 0
        self.last_429_time = 0
        
    async def wait_if_needed(self):
        """รอถ้าใกล้ถึง rate limit"""
        now = time.time()
        
        # รีเซ็ตทุกนาที
        if now - self.last_reset >= 60:
            self.request_times.clear()
            self.last_reset = now
            self.consecutive_429s = 0
            
        # ตรวจสอบจำนวน requests ในนาทีนี้
        self.request_times.append(now)
        
        if len(self.request_times) >= self.max_requests_per_minute:
            # รอจนครบนาที
            wait_time = 60 - (now - self.last_reset)
            if wait_time > 0:
                logger.warning(f"⏳ Rate limit: รอ {wait_time:.1f} วินาที")
                await asyncio.sleep(wait_time)
                self.request_times.clear()
                self.last_reset = time.time()
        
        # รอระหว่าง requests - เพิ่มเวลารอ
        if self.request_times and len(self.request_times) > 1:
            last_request = self.request_times[-2]
            time_since_last = now - last_request
            if time_since_last < self.min_interval:
                wait_time = self.min_interval - time_since_last
                await asyncio.sleep(wait_time)
                
    def handle_429(self):
        """จัดการเมื่อเจอ 429 error"""
        now = time.time()
        self.consecutive_429s += 1
        self.last_429_time = now
        
        # Exponential backoff
        wait_time = min(60 * self.consecutive_429s, 300)  # Max 5 minutes
        logger.error(f"🚨 พบ 429 error ครั้งที่ {self.consecutive_429s} จะรอ {wait_time} วินาที")
        return wait_time

rate_handler = RateLimitHandler()

# =======================================================================================
# ✅ ฟังก์ชันจัดการไฟล์ข้อมูล
# =======================================================================================

def load_json_file(filename, default=None):
    """โหลดข้อมูลจากไฟล์ JSON"""
    if default is None:
        default = {}
    try:
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info(f"✅ โหลด {filename}: {len(data)} รายการ")
                return data
        return default
    except Exception as e:
        logger.error(f"❌ เกิดข้อผิดพลาดในการโหลด {filename}: {e}")
        return default

def save_json_file(filename, data):
    """บันทึกข้อมูลลงไฟล์ JSON"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"💾 บันทึก {filename} เรียบร้อยแล้ว")
        return True
    except Exception as e:
        logger.error(f"❌ เกิดข้อผิดพลาดในการบันทึก {filename}: {e}")
        return False

# =======================================================================================
# ✅ คลาสหลักของบอท
# =======================================================================================

class SushiBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
            allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False)
        )
        self.last_update_time = 0
        self.last_channel_update = 0
        self.ticket_counter = self.load_ticket_counter()
        self.user_data = load_json_file(user_data_file, {})
        self.ticket_transcripts = load_json_file(ticket_transcripts_file, {})
        self.update_queue = asyncio.Queue()
        self.update_task = None
        self.initialized = False
        
    def load_ticket_counter(self):
        """โหลดตัวนับตั๋ว"""
        try:
            data = load_json_file(ticket_counter_file, {"counter": 1, "date": datetime.datetime.now().strftime("%d%m%y")})
            return data
        except:
            return {"counter": 1, "date": datetime.datetime.now().strftime("%d%m%y")}
    
    def save_ticket_counter(self):
        """บันทึกตัวนับตั๋ว"""
        save_json_file(ticket_counter_file, self.ticket_counter)
    
    def save_all_data(self):
        """บันทึกข้อมูลทั้งหมด"""
        save_json_file(user_data_file, self.user_data)
        save_json_file(ticket_transcripts_file, self.ticket_transcripts)
        self.save_ticket_counter()
        
    async def setup_hook(self):
        """ตั้งค่าและ sync คำสั่ง"""
        logger.info("🔄 กำลังตั้งค่า slash commands...")
        
        # ไม่ sync ทันที รอให้พร้อม
        self.loop.create_task(self.delayed_sync())
        
        # เริ่ม task สำหรับอัพเดทช่อง
        self.update_task = self.loop.create_task(self.process_updates())
        
        self.initialized = True
        
    async def delayed_sync(self):
        """sync commands แบบหน่วงเวลา"""
        await asyncio.sleep(5)  # รอ 5 วินาทีก่อน sync
        try:
            await rate_handler.wait_if_needed()
            synced = await self.tree.sync()
            logger.info(f"✅ Sync Global Commands เรียบร้อย: {len(synced)} commands")
        except Exception as e:
            logger.error(f"❌ เกิดข้อผิดพลาดในการ sync: {e}")
            
    async def process_updates(self):
        """ประมวลผลการอัพเดทช่องแบบคิว"""
        while not self.is_closed():
            try:
                # รอรับงานจากคิว
                update_type = await self.update_queue.get()
                
                if update_type == "main_channel":
                    await self._update_main_channel()
                elif update_type == "credit_channel":
                    await self._update_credit_channel()
                    
                # รอระหว่างการอัพเดท - เพิ่มเวลารอ
                await asyncio.sleep(15)  # Increased from 10 to 15 seconds
                
            except Exception as e:
                logger.error(f"❌ เกิดข้อผิดพลาดในการ process_updates: {e}")
                await asyncio.sleep(30)
        
    async def queue_update(self, update_type):
        """เพิ่มงานอัพเดทลงคิว"""
        try:
            # ตรวจสอบว่ามีงานซ้ำในคิวหรือไม่
            if not any(item == update_type for item in self.update_queue._queue):
                await self.update_queue.put(update_type)
                logger.info(f"📋 เพิ่ม {update_type} ในคิวอัพเดท")
        except:
            pass
        
    async def on_ready(self):
        logger.info(f"✅ บอทออนไลน์แล้ว: {self.user} (ID: {self.user.id})")
        
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching, 
                name="ร้าน Sushi Shop | พิมพ์ /help"
            )
        )
        
        # เริ่มงานพื้นหลังแบบจำกัด rate
        self.loop.create_task(self.periodic_updates())
        self.loop.create_task(self.check_stale_tickets())
        
        # อัพเดทช่องหลักครั้งแรก
        await self.queue_update("main_channel")
        
        logger.info("🎯 บอทพร้อมใช้งานเต็มที่!")
        
    async def on_disconnect(self):
        logger.info("💾 กำลังบันทึกข้อมูลก่อนปิดบอท...")
        self.save_all_data()
        
    async def periodic_updates(self):
        """ทำงานพื้นหลังที่ต้องทำเป็นระยะ (ช้าลง)"""
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                # อัพเดททุก 15 นาทีแทน 10 นาที
                await asyncio.sleep(900)  # 15 minutes
                
                # Don't update both at once - stagger them
                await self.queue_update("main_channel")
                await asyncio.sleep(30)  # Wait 30 seconds between updates
                await self.queue_update("credit_channel")
                
            except Exception as e:
                logger.error(f"❌ เกิดข้อผิดพลาดใน periodic_updates: {e}")
                await asyncio.sleep(300)
                
    async def _update_main_channel(self):
        """อัพเดทข้อความในช่องหลัก (private)"""
        try:
            await rate_handler.wait_if_needed()
            
            channel = self.get_channel(MAIN_CHANNEL_ID)
            if not channel:
                logger.error("❌ ไม่พบช่องหลัก")
                return

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
                    f"```\n"
                    f"เรท: {gamepass_rate} | โรแท้ยัดกลุ่มได้\n"
                    f"เช็คราคา: !gp <จำนวน>\n"
                    f"```"
                ),
                inline=False
            )
            
            embed.add_field(
                name=f"👥 โรบัคกลุ่ม | 📊 Stock: {group_stock} {group_status}", 
                value=(
                    f"```\n"
                    f"เรท: {group_rate_low} | 500+ บาท เรท {group_rate_high}\n"
                    f"⚠️ต้องเข้ากลุ่ม 15 วันก่อนซื้อ⚠️\n"
                    f"```"
                ),
                inline=False
            )
            
            embed.add_field(
                name="🏪 สถานะร้าน",
                value=f"```\n{shop_status}\n```",
                inline=False
            )
            
            # ค้นหาข้อความเก่า (จำกัด history)
            try:
                await rate_handler.wait_if_needed()
                async for msg in channel.history(limit=20):
                    if msg.author == self.user and msg.embeds:
                        await msg.edit(embed=embed, view=MainShopView())
                        logger.info("✅ อัพเดท embed หลักเรียบร้อยแล้ว")
                        return
                    await asyncio.sleep(0.1)  # Small delay between messages
            except Exception as e:
                logger.error(f"❌ ไม่สามารถค้นหาข้อความเก่า: {e}")
            
            # ถ้าไม่พบ ให้ส่งใหม่
            await rate_handler.wait_if_needed()
            await channel.send(embed=embed, view=MainShopView())
            logger.info("✅ สร้าง embed หลักใหม่เรียบร้อยแล้ว")
            
        except Exception as e:
            logger.error(f"❌ เกิดข้อผิดพลาดในการอัปเดตช่องหลัก: {e}")
    
    async def _update_credit_channel(self):
        """อัพเดทชื่อช่องเครดิต (private) - FIXED VERSION"""
        try:
            await rate_handler.wait_if_needed()
            
            channel = self.get_channel(CREDIT_CHANNEL_ID)
            if not channel:
                logger.error("❌ ไม่พบช่องเครดิต")
                return
            
            # นับข้อความแบบจำกัด - WITH RATE LIMITING
            message_count = 0
            try:
                # Add rate limiting before history scan
                await rate_handler.wait_if_needed()
                
                # Use a more efficient approach - just count messages in cache
                async for msg in channel.history(limit=100):
                    message_count += 1
                    if message_count >= 100:
                        break
                    # Add small delay between message fetches
                    await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"❌ Error counting messages: {e}")
                message_count = random.randint(50, 100)  # Fallback to random
            
            # เพิ่มจำนวนคร่าวๆ
            message_count = message_count + random.randint(0, 5)
            
            new_name = f"✅credit : {message_count}"
            if channel.name != new_name:
                # Add rate limiting before channel edit
                await rate_handler.wait_if_needed()
                await channel.edit(name=new_name)
                logger.info(f"✅ อัพเดทชื่อช่องเครดิตเป็น: {new_name}")
                
        except Exception as e:
            logger.error(f"❌ เกิดข้อผิดพลาดในการอัพเดทช่องเครดิต: {e}")
    
    def get_next_ticket_number(self):
        """สร้างเลขตั๋วถัดไป"""
        try:
            current_date = datetime.datetime.now().strftime("%d%m%y")
            
            if self.ticket_counter["date"] != current_date:
                self.ticket_counter = {"counter": 1, "date": current_date}
                logger.info(f"🔄 รีเซ็ตตัวนับเป็นวันใหม่: {current_date}")
            else:
                self.ticket_counter["counter"] += 1
            
            self.save_ticket_counter()
            return self.ticket_counter["counter"]
            
        except Exception as e:
            logger.error(f"❌ เกิดข้อผิดพลาดในการสร้างเลขตั๋ว: {e}")
            return 1
            
    async def save_ticket_transcript(self, channel, action_by=None, robux_amount=None):
        """บันทึกประวัติแชทในตั๋ว - FIXED VERSION"""
        try:
            logger.info(f"📝 กำลังบันทึกประวัติตั๋ว: {channel.name}")
            
            ticket_number = self.get_next_ticket_number()
            
            now = datetime.datetime.now()
            date_str = now.strftime("%d%m%y")
            time_str = now.strftime("%H%M")
            timestamp_str = f"{date_str}{time_str}"
            
            username = "unknown"
            if channel.name.startswith("ticket-"):
                parts = channel.name.split('-')
                if len(parts) >= 2:
                    username = parts[1]
            
            filename = f"{timestamp_str}{ticket_number}-1099-wforr"
            
            # นับข้อความแบบจำกัด - WITH RATE LIMITING
            message_count = 0
            try:
                # Add rate limiting
                await rate_handler.wait_if_needed()
                
                # Get just the count without iterating through all messages if possible
                async for _ in channel.history(limit=200):
                    message_count += 1
                    if message_count >= 200:
                        break
                    await asyncio.sleep(0.05)  # Small delay
                    
            except Exception as e:
                logger.error(f"❌ Error counting messages: {e}")
                message_count = 50  # Fallback value
            
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
                "messages_count": message_count
            }
            
            self.ticket_transcripts[str(channel.id)] = transcript_data
            
            save_json_file(ticket_transcripts_file, self.ticket_transcripts)
            logger.info(f"✅ บันทึกประวัติตั๋วเรียบร้อย: {filename}")
            return filename
            
        except Exception as e:
            logger.error(f"❌ เกิดข้อผิดพลาดในการบันทึกประวัติตั๋ว: {e}")
            return None
    
    async def check_stale_tickets(self):
        """ตรวจสอบตั๋วค้างที่ต้องย้าย (ช้าลง)"""
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                await asyncio.sleep(600)  # ตรวจสอบทุก 10 นาที
                
                current_time = datetime.datetime.now()
                channels_to_remove = []
                
                for channel_id, activity_data in list(ticket_activity.items()):
                    if activity_data.get('ty_used', False):
                        last_activity = activity_data.get('last_activity')
                        if last_activity:
                            time_since_activity = current_time - last_activity
                            
                            if time_since_activity.total_seconds() >= 1800:  # 30 นาที
                                channel = self.get_channel(channel_id)
                                if channel:
                                    logger.info(f"🔍 พบตั๋วค้างต้องย้าย: {channel.name}")
                                    await self.archive_ticket_automatically(channel)
                                channels_to_remove.append(channel_id)
                
                for channel_id in channels_to_remove:
                    ticket_activity.pop(channel_id, None)
                    
            except Exception as e:
                logger.error(f"❌ เกิดข้อผิดพลาดในการตรวจสอบตั๋วค้าง: {e}")
                await asyncio.sleep(300)
                
    async def archive_ticket_automatically(self, channel):
        """ย้ายตั๋วไปยัง archive category อัตโนมัติ"""
        try:
            if not channel or channel not in channel.guild.channels:
                return
            
            # บันทึก transcript
            filename = await self.save_ticket_transcript(channel)
            
            # ย้ายไป archive category
            archived_category = channel.guild.get_channel(ARCHIVED_CATEGORY_ID)
            if archived_category:
                try:
                    await rate_handler.wait_if_needed()
                    await channel.edit(
                        category=archived_category,
                        reason="Archived automatically after timeout"
                    )
                    logger.info(f"✅ ย้ายตั๋วอัตโนมัติเรียบร้อย: {channel.name}")
                except Exception as e:
                    logger.error(f"❌ ไม่สามารถย้ายตั๋วอัตโนมัติ: {e}")
                    
        except Exception as e:
            logger.error(f"❌ เกิดข้อผิดพลาดในการย้ายตั๋วอัตโนมัติ: {e}")

# =======================================================================================
# ✅ สร้าง instance ของบอท
# =======================================================================================
bot = SushiBot()

# =======================================================================================
# ✅ Views
# =======================================================================================

class QRView(View):
    def __init__(self):
        super().__init__(timeout=None)
        
    @discord.ui.button(label="คัดลอกเลขบัญชี", style=discord.ButtonStyle.success, emoji="📋", custom_id="copy_bank_account_btn")
    async def copy_bank_account(self, interaction: discord.Interaction, button: Button):
        try:
            bank_info = "120-239181-3 : ธนาคาร SCB"
            await interaction.response.send_message(f"```{bank_info}```", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

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

class DeliveryView(View):
    def __init__(self, channel, product_type, robux_amount, price, buyer):
        super().__init__(timeout=None)
        self.channel = channel
        self.product_type = product_type
        self.robux_amount = robux_amount
        self.price = price
        self.buyer = buyer
        self.delivered = False

    @discord.ui.button(label="ส่งสินค้าแล้ว ✅", style=discord.ButtonStyle.success, emoji="✅", custom_id="deliver_product_btn")
    async def deliver_product(self, interaction: discord.Interaction, button: Button):
        try:
            admin_role = interaction.guild.get_role(1361016912259055896)
            if not admin_role or admin_role not in interaction.user.roles:
                await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้ปุ่มนี้", ephemeral=True)
                return

            if self.delivered:
                await interaction.response.edit_message(
                    content="✅ สินค้าถูกส่งเรียบร้อยแล้ว",
                    embed=None,
                    view=None
                )
                return

            delivery_image = None
            async for message in self.channel.history(limit=5):
                if message.author == interaction.user and message.attachments:
                    for attachment in message.attachments:
                        if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif']):
                            delivery_image = attachment.url
                            break
                    if delivery_image:
                        break
                await asyncio.sleep(0.1)  # Small delay

            if not delivery_image:
                await interaction.response.send_message(
                    "❌ ผู้ส่งสินค้าต้องแนบไฟล์หลักฐานการส่งสินค้าก่อน !",
                    ephemeral=True
                )
                return

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

    @discord.ui.button(label="ยกเลิก ❌", style=discord.ButtonStyle.danger, emoji="❌", custom_id="cancel_order_btn")
    async def cancel_order(self, interaction: discord.Interaction, button: Button):
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
        self.delivered = False

    @discord.ui.button(label="ยืนยัน ✅", style=discord.ButtonStyle.success, emoji="✅", custom_id="confirm_delivery_btn")
    async def confirm_delivery(self, interaction: discord.Interaction, button: Button):
        try:
            if self.delivered:
                await interaction.response.edit_message(
                    content="✅ สินค้าถูกส่งเรียบร้อยแล้ว",
                    embed=None,
                    view=None
                )
                return
                
            self.delivered = True
            
            # จัดการตั๋วหลังส่งของ
            await handle_ticket_after_ty(self.channel, self.buyer, str(self.robux_amount))
            
            receipt_color = 0xFFA500
            if self.product_type == "Group":
                receipt_color = 0x00FFFF
            elif self.product_type == "Limited":
                receipt_color = 0x00FF00
            
            current_time = datetime.datetime.now()
            
            receipt_embed = discord.Embed(
                title=f"🍣 ใบเสร็จการสั่งซื้อ ({self.product_type}) 🍣",
                color=receipt_color
            )
            
            receipt_embed.add_field(name="😊 ผู้ซื้อ", value=self.buyer.mention if self.buyer else "ไม่ทราบ", inline=False)
            receipt_embed.add_field(name="💸 จำนวน Robux", value=f"{self.robux_amount:,}", inline=True)
            receipt_embed.add_field(name="💰 ราคาตามเรท", value=f"{self.price:,.0f} บาท", inline=True)
            
            if self.delivery_image:
                receipt_embed.set_image(url=self.delivery_image)
            
            receipt_embed.set_footer(text=f"จัดส่งสินค้าสำเร็จ 🤗 • {current_time.strftime('%d/%m/%y, %H:%M')}")
            
            log_channel = bot.get_channel(SALES_LOG_CHANNEL_ID)
            if log_channel:
                try:
                    await rate_handler.wait_if_needed()
                    await log_channel.send(embed=receipt_embed)
                except:
                    pass
            
            await rate_handler.wait_if_needed()
            await self.channel.send(embed=receipt_embed)
            
            await interaction.response.edit_message(
                content="✅ บันทึกการส่งสินค้าเรียบร้อยแล้ว",
                embed=None,
                view=None
            )
            
            ticket_activity[self.channel.id] = {
                'last_activity': datetime.datetime.now(),
                'ty_used': True,
                'ty_time': datetime.datetime.now(),
                'buyer_id': self.buyer.id if self.buyer else None
            }
            
        except Exception as e:
            logger.error(f"❌ เกิดข้อผิดพลาดในการยืนยันการส่งสินค้า: {e}")
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
        try:
            await interaction.response.send_message(
                "📝 กรุณาแนบไฟล์หลักฐานการส่งสินค้าใหม่ แล้วกดปุ่ม 'ส่งสินค้าแล้ว ✅' อีกครั้ง",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

class MainShopView(View):
    def __init__(self):
        super().__init__(timeout=None)
        
        # Gamepass button
        if shop_open and gamepass_stock > 0:
            gamepass_label = "เปิดตั๋วกดเกมพาส"
            gamepass_style = discord.ButtonStyle.success
            gamepass_disabled = False
        else:
            gamepass_label = "ร้านปิด/สินค้าหมด"
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
        
        # Group button
        if shop_open and group_ticket_enabled and group_stock > 0:
            group_label = "เปิดตั๋ว Group"
            group_style = discord.ButtonStyle.success
            group_disabled = False
        else:
            group_label = "บริการปิด/สินค้าหมด"
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
        
        # Level button
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
            
            await handle_open_ticket(interaction, "🍣Sushi Gamepass 🍣", "gamepass")
        except Exception as e:
            logger.error(f"❌ ข้อผิดพลาดใน gamepass_ticket: {e}")
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
                
            await handle_open_ticket(interaction, "💰Robux Group💰", "group")
        except Exception as e:
            logger.error(f"❌ ข้อผิดพลาดใน group_ticket: {e}")
            await interaction.response.send_message("❌ เกิดข้อผิดพลาด", ephemeral=True)

    async def check_level(self, interaction: discord.Interaction):
        await check_user_level(interaction)

# =======================================================================================
# ✅ Modals
# =======================================================================================

class GamepassTicketModal(Modal, title="📋 แบบฟอร์มกดเกมพาส"):
    map_name = TextInput(
        label="🗺 ชื่อแมพที่จะกด?",
        placeholder="พิมพ์ชื่อแมพ เช่น Gift Simulator",
        required=True,
        max_length=100
    )
    
    gamepass_name = TextInput(
        label="💸 กดเกมพาสอะไร?",
        placeholder="พิมพ์ชื่อเกมพาส เช่น x3 Speed 3 ชิ้น",
        required=True,
        max_length=100
    )
    
    robux_amount = TextInput(
        label="🎟 ราคาของเกมพาสเท่าไหร่บ้าง?",
        placeholder="เช่น 300 หรือ 100+100+100 หรือ 100x3",
        required=True,
        max_length=50
    )

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

class GroupTicketModal(Modal, title="📋 แบบฟอร์มสั่งซื้อ Robux Group"):
    user_name = TextInput(
        label="🪪 ชื่อในเกม", 
        placeholder="Username",
        required=True,
        max_length=50
    )
    
    robux_amount = TextInput(
        label="💸 ต้องการซื้อกี่โรบัค?", 
        placeholder="กรอกจำนวนโรบัคที่ต้องการ",
        required=True,
        max_length=50
    )

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

# =======================================================================================
# ✅ ฟังก์ชันจัดการตั๋ว
# =======================================================================================

async def handle_open_ticket(interaction, category_name, stock_type):
    global gamepass_stock, group_stock
    
    try:
        guild = interaction.guild
        user = interaction.user

        if guild is None:
            await interaction.response.send_message("❌ คำสั่งนี้ใช้ได้เฉพาะในเซิร์ฟเวอร์", ephemeral=True)
            return

        channel_name = f"ticket-{user.name}-{user.id}"
        
        # ตรวจสอบว่ามีตั๋วอยู่แล้วหรือไม่
        existing_channel = discord.utils.get(guild.text_channels, name=channel_name)
        if existing_channel:
            view = discord.ui.View()
            view.add_item(discord.ui.Button(
                label="📩 ไปที่ตั๋ว", 
                url=f"https://discord.com/channels/{guild.id}/{existing_channel.id}", 
                style=discord.ButtonStyle.link
            ))
            await interaction.response.send_message(
                "📌 คุณมีตั๋วเปิดอยู่แล้ว! กดปุ่มด้านล่างเพื่อไปที่ตั๋ว",
                view=view,
                ephemeral=True
            )
            return

        # ตั้งค่าสิทธิ์
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        admin_role = guild.get_role(1361016912259055896)
        if admin_role:
            overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        # หาหมวดหมู่
        category = discord.utils.get(guild.categories, name=category_name)
        if category is None:
            await rate_handler.wait_if_needed()
            category = await guild.create_category(category_name)
            logger.info(f"✅ สร้างหมวดหมู่ใหม่: {category_name}")

        await interaction.response.send_message("🔄 กำลังเปิดตั๋ว...", ephemeral=True)

        # สร้าง channel
        await rate_handler.wait_if_needed()
        channel = await guild.create_text_channel(
            name=channel_name,
            overwrites=overwrites,
            reason="New ticket",
            category=category
        )
        
        # บันทึกกิจกรรม
        ticket_activity[channel.id] = {
            'last_activity': datetime.datetime.now(),
            'ty_used': False
        }
        
        # ลด stock
        if stock_type == "gamepass":
            gamepass_stock -= 1
        else:
            group_stock -= 1
        
        # ส่งลิงก์ไปที่ตั๋ว
        view = discord.ui.View()
        view.add_item(discord.ui.Button(
            label="📩 ไปที่ตั๋ว", 
            url=f"https://discord.com/channels/{guild.id}/{channel.id}", 
            style=discord.ButtonStyle.link
        ))
        await interaction.edit_original_response(
            content="✅ เปิดตั๋วเรียบร้อย!",
            view=view
        )

        # ส่งข้อความต้อนรับ
        if admin_role:
            await rate_handler.wait_if_needed()
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
        else:
            welcome_embed.add_field(
                name="บริการโรบัคกลุ่ม",
                value=f"📦 Stock: **{group_stock}**",
                inline=False
            )
            
        welcome_embed.set_footer(text="Sushi Shop บริการรับกดเกมพาส")
        await rate_handler.wait_if_needed()
        await channel.send(embed=welcome_embed)

        # ส่ง modal ตามประเภท
        if stock_type == "gamepass":
            modal = GamepassTicketModal()
            await rate_handler.wait_if_needed()
            await channel.send("📝 **กรุณากรอกแบบฟอร์มด้านล่าง:**", view=discord.ui.View().add_item(
                discord.ui.Button(label="📝 กรอกแบบฟอร์ม", style=discord.ButtonStyle.primary, custom_id="open_modal_btn")
            ))

    except Exception as e:
        logger.error(f"❌ เกิดข้อผิดพลาดในการเปิดตั๋ว: {e}")
        try:
            await interaction.edit_original_response(content="❌ เกิดข้อผิดพลาดในการเปิดตั๋ว")
        except:
            pass

async def handle_ticket_after_ty(channel, user, robux_amount=None):
    """จัดการตั๋วหลังใช้ !ty"""
    try:
        guild = channel.guild
        
        now = datetime.datetime.now()
        date_str = now.strftime("%d%m%y")
        time_str = now.strftime("%H%M")
        timestamp_str = f"{date_str}{time_str}"
        
        ticket_number = bot.get_next_ticket_number()
        new_name = f"{timestamp_str}{ticket_number}-1099-wforr"
        
        delivered_category = guild.get_channel(DELIVERED_CATEGORY_ID)
        if not delivered_category:
            logger.error(f"❌ ไม่พบ category ส่งของแล้ว ID: {DELIVERED_CATEGORY_ID}")
            return False
        
        try:
            await rate_handler.wait_if_needed()
            await channel.edit(
                category=delivered_category,
                name=new_name,
                reason=f"ย้ายไปห้องส่งของแล้วโดย {user.name if user else 'ระบบ'}"
            )
            logger.info(f"✅ ย้ายตั๋วไปยัง category ส่งของแล้วและเปลี่ยนชื่อเป็น: {new_name}")
            
            credit_embed = discord.Embed(
                title="✅ ส่งของเรียบร้อยแล้ว",
                description="สินค้าถูกจัดส่งเรียบร้อยแล้ว!\n\n" +
                           "**ขอบคุณที่ใช้บริการร้าน Sushi Shop 🍣**\n" +
                           "ฝากกดเครดิตให้ด้วยนะคะ ⭐\n\n" +
                           "⚠️ **หมายเหตุ:** ตั๋วนี้จะถูกย้ายไปเก็บถาวรใน 30 นาที",
                color=0x00FF00
            )
            credit_embed.set_footer(text="Sushi Shop • ขอบคุณที่ใช้บริการ")
            
            await rate_handler.wait_if_needed()
            await channel.send(embed=credit_embed)
            
            # เริ่มนับถอยหลัง 30 นาที
            bot.loop.create_task(move_to_transcript_after_delay(channel, user, robux_amount, 1800))
            
            return True
            
        except Exception as e:
            logger.error(f"❌ ไม่สามารถย้ายตั๋ว: {e}")
            return False
        
    except Exception as e:
        logger.error(f"❌ เกิดข้อผิดพลาดในการจัดการตั๋วหลัง !ty: {e}")
        return False

async def move_to_transcript_after_delay(channel, user, robux_amount, delay_seconds):
    """รอ delay แล้วย้ายตั๋วไป transcript"""
    try:
        logger.info(f"⏳ กำลังรอ {delay_seconds} วินาทีก่อนย้ายตั๋ว {channel.name} ไป transcript")
        await asyncio.sleep(delay_seconds)
        
        if not channel or channel not in channel.guild.channels:
            return
        
        filename = await bot.save_ticket_transcript(channel, user, robux_amount)
        
        if filename:
            logger.info(f"✅ บันทึก transcript: {filename}")
        
        guild = channel.guild
        archived_category = guild.get_channel(ARCHIVED_CATEGORY_ID)
        
        if archived_category:
            try:
                if user:
                    try:
                        overwrites = channel.overwrites
                        if user in overwrites:
                            overwrites[user].update(read_messages=False)
                            await rate_handler.wait_if_needed()
                            await channel.edit(overwrites=overwrites)
                    except:
                        pass
                
                await rate_handler.wait_if_needed()
                await channel.edit(
                    category=archived_category,
                    reason="ย้ายไปเก็บถาวรหลังจาก 30 นาที"
                )
                logger.info(f"✅ ย้ายตั๋ว {channel.name} ไปเก็บถาวรเรียบร้อยแล้ว")
                    
            except Exception as e:
                logger.error(f"❌ ไม่สามารถย้ายตั๋วไปเก็บถาวร: {e}")
            
    except Exception as e:
        logger.error(f"❌ เกิดข้อผิดพลาดในการย้ายตั๋วหลังจาก delay: {e}")

# =======================================================================================
# ✅ ฟังก์ชันจัดการเลเวลและ EXP
# =======================================================================================

async def add_exp(user_id, exp_amount, guild):
    """เพิ่ม EXP ให้ผู้ใช้และอัพเดทเลเวล"""
    user_id_str = str(user_id)
    
    if user_id_str not in bot.user_data:
        bot.user_data[user_id_str] = {"exp": 0, "level": 0}
    
    bot.user_data[user_id_str]["exp"] += exp_amount
    
    old_level = bot.user_data[user_id_str]["level"]
    
    new_level = 0
    for level, data in sorted(LEVELS.items(), reverse=True):
        if bot.user_data[user_id_str]["exp"] >= data["exp"]:
            new_level = level
            break
    
    bot.user_data[user_id_str]["level"] = new_level
    
    save_json_file(user_data_file, bot.user_data)
    
    if new_level != old_level:
        await update_user_roles(user_id, guild, old_level, new_level)
    
    return new_level, bot.user_data[user_id_str]["exp"]

async def update_user_roles(user_id, guild, old_level, new_level):
    """อัพเดทยศผู้ใช้ตามเลเวล - FIXED VERSION"""
    try:
        member = guild.get_member(user_id)
        if not member:
            return
        
        if old_level > 0 and old_level in LEVELS:
            old_role_id = LEVELS[old_level]["role_id"]
            old_role = guild.get_role(old_role_id)
            if old_role and old_role in member.roles:
                await rate_handler.wait_if_needed()
                await member.remove_roles(old_role)
                await asyncio.sleep(0.5)  # Small delay
        
        if new_level > 0 and new_level in LEVELS:
            new_role_id = LEVELS[new_level]["role_id"]
            new_role = guild.get_role(new_role_id)
            if new_role and new_role not in member.roles:
                await rate_handler.wait_if_needed()
                await member.add_roles(new_role)
                logger.info(f"✅ เพิ่มยศ {LEVELS[new_level]['role_name']} ให้ {member.display_name}")
                
    except Exception as e:
        logger.error(f"❌ เกิดข้อผิดพลาดในการอัพเดทยศ: {e}")

async def check_user_level(interaction: discord.Interaction):
    """แสดงเลเวลและ EXP ของผู้ใช้"""
    try:
        user_id = str(interaction.user.id)
        
        if user_id not in bot.user_data:
            bot.user_data[user_id] = {"exp": 0, "level": 0}
            save_json_file(user_data_file, bot.user_data)
        
        user_exp = bot.user_data[user_id]["exp"]
        user_level = bot.user_data[user_id]["level"]
        
        embed = discord.Embed(
            title=f"🍣 ระดับของคุณ {interaction.user.display_name}",
            color=0x00FF99
        )
        embed.add_field(name="🎮 ระดับ", value=f"Level {user_level}", inline=True)
        embed.add_field(name="⭐ EXP", value=f"**{user_exp:,}**", inline=True)
        
        if user_level < 9:
            next_exp = LEVELS[user_level + 1]["exp"]
            need = next_exp - user_exp
            embed.add_field(name="🎯 EXP ที่ต้องใช้ถึง Level ถัดไป", value=f"**{need:,}**", inline=False)
        
        embed.set_footer(text="ได้รับ EXP จากการซื้อสินค้าในร้าน")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        logger.error(f"❌ เกิดข้อผิดพลาดในการเช็คเลเวล: {e}")
        await interaction.response.send_message("❌ เกิดข้อผิดพลาดในการเช็คเลเวล", ephemeral=True)

# =======================================================================================
# ✅ ระดับและ EXP
# =======================================================================================

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
# ✅ Decorator สำหรับตรวจสอบสิทธิ์แอดมิน
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
# ✅ TEXT COMMANDS
# =======================================================================================

@bot.command()
@admin_only()
async def od(ctx, *, expression: str):
    """สั่งซื้อ Gamepass"""
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

        # หาผู้ซื้อ
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

        # เพิ่ม EXP
        if buyer:
            await add_exp(buyer.id, robux, ctx.guild)

        # อัพเดท stock
        gamepass_stock -= robux
        if gamepass_stock < 0:
            gamepass_stock = 0
        
        current_time = datetime.datetime.now()
        
        order_embed = discord.Embed(
            title="🍣คำสั่งซื้อสินค้า🍣",
            color=0xFFA500
        )
        order_embed.add_field(name="📦 ประเภทสินค้า", value="Gamepass", inline=False)
        order_embed.add_field(name="💸 จำนวน Robux", value=f"{robux:,}", inline=True)
        order_embed.add_field(name="💰 ราคาตามเรท", value=f"{price:,.0f} บาท", inline=True)
        order_embed.set_footer(text=f"รับออร์เดอร์แล้ว 🤗 • {current_time.strftime('%d/%m/%y, %H:%M')}")
        
        # เก็บข้อมูล robux_amount สำหรับใช้ใน transcript
        ctx.channel.robux_amount = str(robux)
        
        delivery_view = DeliveryView(ctx.channel, "Gamepass", robux, price, buyer)
        await ctx.send(embed=order_embed, view=delivery_view)

    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=10)

@bot.command()
@admin_only()
async def odg(ctx, *, expression: str):
    """สั่งซื้อ Group"""
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
                try:
                    user_id = int(parts[-1])
                    buyer = ctx.guild.get_member(user_id)
                except:
                    pass

        if buyer:
            await add_exp(buyer.id, robux, ctx.guild)

        group_stock -= robux
        if group_stock < 0:
            group_stock = 0
        
        current_time = datetime.datetime.now()
        
        order_embed = discord.Embed(
            title="🍣คำสั่งซื้อสินค้า🍣",
            color=0x00FFFF
        )
        order_embed.add_field(name="📦 ประเภทสินค้า", value="Group", inline=False)
        order_embed.add_field(name="💸 จำนวน Robux", value=f"{robux:,}", inline=True)
        order_embed.add_field(name="💰 ราคาตามเรท", value=f"{price:,.0f} บาท", inline=True)
        order_embed.set_footer(text=f"รับออร์เดอร์แล้ว 🤗 • {current_time.strftime('%d/%m/%y, %H:%M')}")
        
        ctx.channel.robux_amount = str(robux)
        
        delivery_view = DeliveryView(ctx.channel, "Group", robux, price, buyer)
        await ctx.send(embed=order_embed, view=delivery_view)

    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=10)

@bot.command()
@admin_only()
async def odl(ctx, item_name: str, value: str):
    """สั่งซื้อ Limited"""
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
                try:
                    user_id = int(parts[-1])
                    buyer = ctx.guild.get_member(user_id)
                except:
                    pass

        if buyer:
            await add_exp(buyer.id, item_value, ctx.guild)

        current_time = datetime.datetime.now()
        
        order_embed = discord.Embed(
            title="🍣คำสั่งซื้อสินค้า🍣",
            color=0x00FF00
        )
        order_embed.add_field(name="📦 ประเภทสินค้า", value="Limited", inline=False)
        order_embed.add_field(name="🎁 ชื่อไอเทม", value=item_name, inline=True)
        order_embed.add_field(name="💰 ราคา", value=f"{item_value:,} บาท", inline=True)
        order_embed.set_footer(text=f"รับออร์เดอร์แล้ว 🤗 • {current_time.strftime('%d/%m/%y, %H:%M')}")
        
        ctx.channel.robux_amount = str(item_value)
        
        delivery_view = DeliveryView(ctx.channel, "Limited", 0, item_value, buyer)
        await ctx.send(embed=order_embed, view=delivery_view)

    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}", delete_after=10)

@bot.command()
@admin_only()
async def qr(ctx):
    """แสดง QR Code"""
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
    
    qr_url = "https://media.discordapp.net/attachments/1361004239043821610/1444373113319198840/160-1-43871-9_1.png"
    embed.set_image(url=qr_url)
    
    await ctx.send(embed=embed, view=QRView())

@bot.command()
@admin_only()
async def ty(ctx):
    """ยืนยันการส่งสินค้า"""
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
        
        robux_amount = getattr(ctx.channel, 'robux_amount', None)
        
        await handle_ticket_after_ty(ctx.channel, buyer, robux_amount)
        await ctx.send("✅ ยืนยันการส่งสินค้าเรียบร้อยแล้ว")
        
    else:
        await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะในตั๋วเท่านั้น", delete_after=5)

@bot.command()
@admin_only()
async def stock(ctx, stock_type: str = None, amount: str = None):
    """ตรวจสอบ/ตั้งค่า stock"""
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
        embed.add_field(name="🎮 Gamepass Stock", value=f"**{gamepass_stock:,}**", inline=True)
        embed.add_field(name="👥 Group Stock", value=f"**{group_stock:,}**", inline=True)
        await ctx.send(embed=embed, delete_after=30)
        
    elif stock_type.lower() in ["gp", "gamepass"]:
        if amount is None:
            await ctx.send(f"🎮 Gamepass Stock: **{gamepass_stock:,}**", delete_after=30)
        else:
            try:
                amount_int = int(amount.replace(",", ""))
                if amount_int < 0:
                    await ctx.send("❌ จำนวนต้องมากกว่าหรือเท่ากับ 0")
                    return
                gamepass_stock = amount_int
                await ctx.send(f"✅ ตั้งค่า Gamepass Stock เป็น **{gamepass_stock:,}** เรียบร้อย")
                await bot.queue_update("main_channel")
            except ValueError:
                await ctx.send("❌ กรุณากรอกตัวเลข")
    
    elif stock_type.lower() in ["g", "group"]:
        if amount is None:
            await ctx.send(f"👥 Group Stock: **{group_stock:,}**", delete_after=30)
        else:
            try:
                amount_int = int(amount.replace(",", ""))
                if amount_int < 0:
                    await ctx.send("❌ จำนวนต้องมากกว่าหรือเท่ากับ 0")
                    return
                group_stock = amount_int
                await ctx.send(f"✅ ตั้งค่า Group Stock เป็น **{group_stock:,}** เรียบร้อย")
                await bot.queue_update("main_channel")
            except ValueError:
                await ctx.send("❌ กรุณากรอกตัวเลข")
    else:
        await ctx.send("❌ ใช้ !stock, !stock gp <จำนวน>, !stock group <จำนวน>")

@bot.command()
@admin_only()
async def rate(ctx, rate_type: str = None, low_rate: str = None, high_rate: str = None):
    """เปลี่ยนเรท"""
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
        embed.add_field(name="🎮 Gamepass Rate", value=f"**{gamepass_rate}**", inline=True)
        embed.add_field(name="👥 Group Rate", value=f"**{group_rate_low} - {group_rate_high}**", inline=True)
        await ctx.send(embed=embed, delete_after=30)
        
    elif rate_type.lower() == "group":
        if low_rate is None or high_rate is None:
            await ctx.send("❌ ใช้: !rate group <low> <high>")
            return
        
        try:
            group_rate_low = float(low_rate)
            group_rate_high = float(high_rate)
            await ctx.send(f"✅ ตั้งค่า Group Rate เป็น **{group_rate_low} - {group_rate_high}**")
            await bot.queue_update("main_channel")
        except ValueError:
            await ctx.send("❌ กรุณากรอกตัวเลข")
    
    else:
        try:
            gamepass_rate = float(rate_type)
            await ctx.send(f"✅ ตั้งค่า Gamepass Rate เป็น **{gamepass_rate}**")
            await bot.queue_update("main_channel")
        except ValueError:
            await ctx.send("❌ กรุณากรอกตัวเลข")

@bot.command()
@admin_only()
async def sushi(ctx):
    """เปิด/ปิดร้าน"""
    global shop_open
    shop_open = not shop_open
    status = "✅ ร้านเปิด" if shop_open else "❌ ร้านปิด"
    await ctx.send(f"🏪 **{status}**")
    await bot.queue_update("main_channel")

@bot.command()
@admin_only()
async def group(ctx, status: str = None):
    """เปิด/ปิด Group ticket"""
    global group_ticket_enabled
    
    if status is None:
        current = "✅ เปิด" if group_ticket_enabled else "❌ ปิด"
        await ctx.send(f"👥 สถานะ Group Ticket: **{current}**")
    elif status.lower() in ["on", "enable", "เปิด"]:
        group_ticket_enabled = True
        await ctx.send("✅ เปิด Group Ticket เรียบร้อย")
    elif status.lower() in ["off", "disable", "ปิด"]:
        group_ticket_enabled = False
        await ctx.send("❌ ปิด Group Ticket เรียบร้อย")
    else:
        await ctx.send("❌ ใช้ !group [on/off]")
    
    await bot.queue_update("main_channel")

@bot.command()
async def level(ctx, member: discord.Member = None):
    """เช็คเลเวล"""
    if member is None:
        member = ctx.author
    
    user_id = str(member.id)
    
    if user_id not in bot.user_data:
        bot.user_data[user_id] = {"exp": 0, "level": 0}
        save_json_file(user_data_file, bot.user_data)
    
    user_exp = bot.user_data[user_id]["exp"]
    user_level = bot.user_data[user_id]["level"]
    
    embed = discord.Embed(
        title=f"🍣 ระดับของคุณ {member.display_name}",
        color=0x00FF99
    )
    embed.add_field(name="🎮 ระดับ", value=f"Level {user_level}", inline=True)
    embed.add_field(name="⭐ EXP", value=f"**{user_exp:,}**", inline=True)
    
    if user_level < 9:
        next_exp = LEVELS[user_level + 1]["exp"]
        need = next_exp - user_exp
        embed.add_field(name="🎯 EXP ที่ต้องใช้ถึง Level ถัดไป", value=f"**{need:,}**", inline=False)
    
    await ctx.send(embed=embed)

@bot.command()
async def gp(ctx, *, expression: str):
    """คำนวณราคา Gamepass"""
    try:
        expr = expression.replace(",", "").lower().replace("x", "*").replace("÷", "/")
        robux = int(eval(expr))
        price = robux / gamepass_rate
        await ctx.send(f"🎮 Gamepass {robux:,} Robux = **{price:,.0f} บาท** (เรท {gamepass_rate})")
    except:
        await ctx.send("❌ เกิดข้อผิดพลาด")

@bot.command()
async def g(ctx, *, expression: str):
    """คำนวณราคา Group"""
    try:
        expr = expression.replace(",", "").lower().replace("x", "*").replace("÷", "/")
        robux = int(eval(expr))
        rate = group_rate_low if robux < 1500 else group_rate_high
        price = robux / rate
        await ctx.send(f"👥 Group {robux:,} Robux = **{price:,.0f} บาท** (เรท {rate})")
    except:
        await ctx.send("❌ เกิดข้อผิดพลาด")

@bot.command()
async def gpb(ctx, *, expression: str):
    """คำนวณเงินบาท -> Robux (Gamepass)"""
    try:
        baht = float(expression.replace(",", ""))
        robux = baht * gamepass_rate
        await ctx.send(f"🎮 {baht:,.0f} บาท = **{robux:,.0f} Robux** (เรท {gamepass_rate})")
    except:
        await ctx.send("❌ เกิดข้อผิดพลาด")

@bot.command()
async def gb(ctx, *, expression: str):
    """คำนวณเงินบาท -> Robux (Group)"""
    try:
        baht = float(expression.replace(",", ""))
        rate = group_rate_low if baht < 500 else group_rate_high
        robux = baht * rate
        await ctx.send(f"👥 {baht:,.0f} บาท = **{robux:,.0f} Robux** (เรท {rate})")
    except:
        await ctx.send("❌ เกิดข้อผิดพลาด")

@bot.command()
async def tax(ctx, *, expression: str):
    """คำนวณหลังหักภาษี"""
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
            result = number * (1 - percent/100)
            await ctx.send(f"💰 {number:,} Robux หลังหัก {percent}% = **{result:,.0f} Robux**")
        else:
            await ctx.send("❌ รูปแบบไม่ถูกต้อง ใช้ !tax 100 หรือ !tax 100-30%")
    except:
        await ctx.send("❌ เกิดข้อผิดพลาด")

@bot.command(name='help')
async def help_command(ctx):
    """แสดงคำสั่งทั้งหมด"""
    embed = discord.Embed(
        title="🍣 Sushi Shop - คำสั่งทั้งหมด",
        description=(
            "**คำสั่งทั่วไป:**\n"
            "`!gp <จำนวน>` - คำนวณราคา Gamepass\n"
            "`!g <จำนวน>` - คำนวณราคา Group\n"
            "`!gpb <จำนวน>` - คำนวณ Robux จากเงิน (Gamepass)\n"
            "`!gb <จำนวน>` - คำนวณ Robux จากเงิน (Group)\n"
            "`!tax <จำนวน>` - คำนวณ Robux หลังหักภาษี\n"
            "`!level` - เช็คเลเวลของคุณ\n\n"
            "**คำสั่ง Slash Commands:**\n"
            "`/gamepass`, `/group`, `/baht_gamepass`, `/baht_group`, `/tax`, `/help`\n\n"
            "**คำสั่งแอดมิน:**\n"
            "`!stock`, `!rate`, `!sushi`, `!group`, `!ty`, `!qr`, `!od`, `!odg`, `!odl`"
        ),
        color=0x00FF99
    )
    await ctx.send(embed=embed, delete_after=60)

# =======================================================================================
# ✅ SLASH COMMANDS
# =======================================================================================

@bot.tree.command(name="gamepass", description="คำนวณราคา Gamepass")
async def gamepass_slash(interaction: discord.Interaction, amount: str):
    try:
        expr = amount.replace(",", "").replace(" ", "").lower().replace("x", "*")
        robux = int(eval(expr))
        price = robux / gamepass_rate
        await interaction.response.send_message(f"🎮 Gamepass {robux:,} Robux = **{price:,.0f} บาท** (เรท {gamepass_rate})")
    except:
        await interaction.response.send_message("❌ เกิดข้อผิดพลาด กรุณากรอกตัวเลข")

@bot.tree.command(name="group", description="คำนวณราคา Group")
async def group_slash(interaction: discord.Interaction, amount: str):
    try:
        expr = amount.replace(",", "").replace(" ", "").lower().replace("x", "*")
        robux = int(eval(expr))
        rate = group_rate_low if robux < 1500 else group_rate_high
        price = robux / rate
        await interaction.response.send_message(f"👥 Group {robux:,} Robux = **{price:,.0f} บาท** (เรท {rate})")
    except:
        await interaction.response.send_message("❌ เกิดข้อผิดพลาด กรุณากรอกตัวเลข")

@bot.tree.command(name="baht_gamepass", description="คำนวณ Robux จากเงินบาท (Gamepass)")
async def baht_gamepass_slash(interaction: discord.Interaction, amount: str):
    try:
        baht = float(amount.replace(",", ""))
        robux = baht * gamepass_rate
        await interaction.response.send_message(f"🎮 {baht:,.0f} บาท = **{robux:,.0f} Robux** (เรท {gamepass_rate})")
    except:
        await interaction.response.send_message("❌ เกิดข้อผิดพลาด กรุณากรอกตัวเลข")

@bot.tree.command(name="baht_group", description="คำนวณ Robux จากเงินบาท (Group)")
async def baht_group_slash(interaction: discord.Interaction, amount: str):
    try:
        baht = float(amount.replace(",", ""))
        rate = group_rate_low if baht < 500 else group_rate_high
        robux = baht * rate
        await interaction.response.send_message(f"👥 {baht:,.0f} บาท = **{robux:,.0f} Robux** (เรท {rate})")
    except:
        await interaction.response.send_message("❌ เกิดข้อผิดพลาด กรุณากรอกตัวเลข")

@bot.tree.command(name="tax", description="คำนวณ Robux หลังหักภาษี")
async def tax_slash(interaction: discord.Interaction, amount: str):
    try:
        expr = amount.replace(" ", "")
        if re.match(r"^\d+$", expr):
            number = int(expr)
            result = number * 0.7
            await interaction.response.send_message(f"💰 {number:,} Robux หลังหัก 30% = **{result:,.0f} Robux**")
        elif re.match(r"^\d+-\d+%$", expr):
            parts = expr.split('-')
            number = int(parts[0])
            percent = int(parts[1].replace('%', ''))
            result = number * (1 - percent/100)
            await interaction.response.send_message(f"💰 {number:,} Robux หลังหัก {percent}% = **{result:,.0f} Robux**")
        else:
            await interaction.response.send_message("❌ รูปแบบไม่ถูกต้อง ใช้ 100 หรือ 100-30%")
    except:
        await interaction.response.send_message("❌ เกิดข้อผิดพลาด กรุณากรอกตัวเลข")

@bot.tree.command(name="help", description="แสดงคำสั่งทั้งหมด")
async def help_slash(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🍣 Sushi Shop - คำสั่งทั้งหมด",
        description=(
            "**คำสั่ง Slash Commands:**\n"
            "`/gamepass <จำนวน>` - คำนวณราคา Gamepass\n"
            "`/group <จำนวน>` - คำนวณราคา Group\n"
            "`/baht_gamepass <จำนวน>` - คำนวณ Robux จากบาท\n"
            "`/baht_group <จำนวน>` - คำนวณ Robux จากบาท (Group)\n"
            "`/tax <จำนวน>` - คำนวณหลังหักภาษี\n"
            "`/help` - แสดงคำสั่งนี้\n\n"
            "**คำสั่ง Text ในเซิร์ฟเวอร์:**\n"
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
        return await bot.process_commands(message)
    
    if message.channel.id == CREDIT_CHANNEL_ID:
        await bot.queue_update("credit_channel")
    
    await bot.process_commands(message)

# =======================================================================================
# ✅ Global Error Handler
# =======================================================================================

@bot.event
async def on_error(event, *args, **kwargs):
    """Handle errors globally"""
    import traceback
    error = traceback.format_exc()
    
    if "429" in error:
        logger.error("🚨 พบ 429 Rate Limit Error!")
        
        # Get wait time from rate handler
        wait_time = rate_handler.handle_429()
        
        # Cancel all pending tasks and wait
        logger.info(f"⏸️ หยุดการทำงานทั้งหมด {wait_time} วินาที...")
        await asyncio.sleep(wait_time)
        
        # Clear queues
        while not bot.update_queue.empty():
            try:
                bot.update_queue.get_nowait()
            except:
                pass
                
        logger.info("✅ เริ่มการทำงานใหม่...")

# =======================================================================================
# ✅ เริ่มต้นบอท
# =======================================================================================

if __name__ == "__main__":
    logger.info("🚀 กำลังเริ่มต้นบอท...")
    
    # เริ่ม web server
    try:
        server_on()
        logger.info("✅ Web server started on port 8080")
    except Exception as e:
        logger.error(f"❌ ไม่สามารถเริ่ม web server: {e}")
    
    # รันบอท
    token = os.getenv("TOKEN")
    if not token:
        logger.error("❌ ไม่พบ TOKEN ใน environment variables")
        sys.exit(1)
    
    # Add reconnect logic with exponential backoff
    max_retries = 5
    retry_count = 0
    base_delay = 5
    
    while retry_count < max_retries:
        try:
            # รันบอทโดยไม่ใช้ shard และจำกัด rate
            bot.run(token, log_handler=None, reconnect=True)
            break  # If successful, exit loop
        except discord.HTTPException as e:
            if e.status == 429:  # Rate limit
                retry_count += 1
                wait_time = base_delay * (2 ** retry_count)  # Exponential backoff
                logger.error(f"🚨 Rate limited! Retry {retry_count}/{max_retries} in {wait_time}s")
                time.sleep(wait_time)
            else:
                logger.error(f"❌ HTTP Exception: {e}")
                break
        except discord.PrivilegedIntentsRequired:
            logger.error("❌ ต้องเปิด Privileged Intents ใน Discord Developer Portal")
            break
        except discord.LoginFailure:
            logger.error("❌ TOKEN ไม่ถูกต้อง")
            break
        except Exception as e:
            logger.error(f"❌ เกิดข้อผิดพลาดร้ายแรง: {e}")
            break
