import os, discord, random, math, json, asyncio, time, re
from datetime import datetime
from discord.ext import commands, tasks
from discord.ui import View, Button, Modal, TextInput, Select
from flask import Flask, jsonify
from threading import Thread
from typing import Dict, List, Optional, Tuple

# ==================== CONFIG ====================
app = Flask(__name__)
start_time = time.time()
def keep_alive(): Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.getenv("PORT", 8080)), debug=False, use_reloader=False), daemon=True).start()

@app.route('/')
def home(): return f"Bot alive! Uptime: {int((time.time()-start_time)/3600)}h"

def get_thailand_time():
    try:
        import pytz
        return datetime.now(pytz.timezone('Asia/Bangkok'))
    except:
        return datetime.utcnow() + timedelta(hours=7)

intents = discord.Intents.all()
intents.message_content = True

# ==================== CONSTANTS ====================
GAMEPASS_RATE = 6.5
GROUP_RATE_LOW = 4
GROUP_RATE_HIGH = 4.5
MAIN_CHANNEL_ID = 1361044752975532152
CREDIT_CHANNEL_ID = 1363250076549382246
DELIVERED_CATEGORY_ID = 1419565515088597083
ARCHIVED_CATEGORY_ID = 1445086228113264650
ADMIN_ROLE_ID = 1361016912259055896

FILES = {
    'user': 'user_data.json',
    'ticket': 'ticket_transcripts.json',
    'counter': 'ticket_counter.json',
    'robux': 'ticket_robux_data.json',
    'customer': 'ticket_customer_data.json',
    'inventory': 'rng_inventory.json',
    'balance': 'rng_balance.json'
}

LEVELS = {
    1: {"exp": 1, "role": 1361555369825927249},
    2: {"exp": 5000, "role": 1432070662977093703},
    3: {"exp": 10000, "role": 1361555364776247297},
    4: {"exp": 20000, "role": 1432075600746643537},
    5: {"exp": 50000, "role": 1432075369179254804},
    6: {"exp": 100000, "role": 1361554929017294949},
    7: {"exp": 250000, "role": 1432077732862492722},
    8: {"exp": 500000, "role": 1363882685260365894},
    9: {"exp": 1000000, "role": 1406309272786047106}
}

# ==================== GLOBALS ====================
shop_open = True
group_enabled = True
gp_stock, group_stock = 50000, 0
user_data, tickets, robux_data, cust_data, notes = {}, {}, {}, {}, {}
credit_queue = asyncio.Queue()

def load_json(f, d): 
    try:
        if os.path.exists(f):
            with open(f, 'r', encoding='utf-8') as file: return json.load(file)
    except: pass
    return d

def save_json(f, d):
    try:
        with open(f, 'w', encoding='utf-8') as file: json.dump(d, file, ensure_ascii=False, indent=2)
        return True
    except: return False

# ==================== BOT ====================
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        self.synced = False
        self.stock_lock = asyncio.Lock()
        self.counter = load_json(FILES['counter'], {"counter": 1, "date": get_thailand_time().strftime("%d%m%y")})
        self.main_msg, self.pawn_data = None, {}
    
    async def setup_hook(self):
        global user_data, tickets, robux_data, cust_data
        user_data = load_json(FILES['user'], {})
        tickets = load_json(FILES['ticket'], {})
        robux_data = load_json(FILES['robux'], {})
        cust_data = load_json(FILES['customer'], {})

bot = MyBot()

# ==================== UTILS ====================
def admin_check():
    async def pred(ctx):
        if ctx.author.guild_permissions.administrator: return True
        role = ctx.guild.get_role(ADMIN_ROLE_ID)
        return role and role in ctx.author.roles or await ctx.send("❌ แอดมินเท่านั้น", delete_after=5) or False
    return commands.check(pred)

def next_ticket():
    d = get_thailand_time().strftime("%d%m%y")
    if bot.counter["date"] != d: bot.counter = {"counter": 1, "date": d}
    else: bot.counter["counter"] += 1
    save_json(FILES['counter'], bot.counter)
    return bot.counter["counter"]

async def add_exp(uid, amt, guild):
    uid = str(uid)
    if uid not in user_data: user_data[uid] = {"exp": 0, "level": 0}
    user_data[uid]["exp"] += amt
    old = user_data[uid]["level"]
    new = max([l for l, d in LEVELS.items() if user_data[uid]["exp"] >= d["exp"]] or [0])
    user_data[uid]["level"] = new
    save_json(FILES['user'], user_data)
    if new != old and (m := guild.get_member(int(uid))):
        if old and (r := guild.get_role(LEVELS[old]["role"])) and r in m.roles: await m.remove_roles(r)
        if new and (r := guild.get_role(LEVELS[new]["role"])) and r not in m.roles: await m.add_roles(r)
    return new, user_data[uid]["exp"]

# ==================== SHOP ====================
async def update_shop():
    ch = bot.get_channel(MAIN_CHANNEL_ID)
    if not ch: return
    e = discord.Embed(title="🍣 Sushi Shop 🍣", color=0xFFA500)
    e.add_field(name=f"🎮 Gamepass: {gp_stock:,}", value=f"เรท {GAMEPASS_RATE}\n!gp <จำนวน>", inline=False)
    e.add_field(name=f"👥 Group: {group_stock:,}", value=f"เรท {GROUP_RATE_LOW}-{GROUP_RATE_HIGH}", inline=False)
    e.add_field(name="🏪 สถานะ", value="🟢 เปิด" if shop_open else "🔴 ปิด", inline=False)
    e.set_footer(text=f"อัปเดต {get_thailand_time().strftime('%d/%m/%y %H:%M')}")
    
    v = View(timeout=None)
    gp_btn = Button(label="กดเกมพาส" if gp_stock>0 and shop_open else "ปิด", emoji="🎮", style=discord.ButtonStyle.success if gp_stock>0 and shop_open else discord.ButtonStyle.danger, disabled=not (gp_stock>0 and shop_open))
    gr_btn = Button(label="เติมโรกลุ่ม" if group_stock>0 and shop_open and group_enabled else "ปิด", emoji="👥", style=discord.ButtonStyle.success if group_stock>0 and shop_open and group_enabled else discord.ButtonStyle.danger, disabled=not (group_stock>0 and shop_open and group_enabled))
    
    async def gp_cb(i): await open_ticket(i, "🍣Sushi Gamepass 🍣", "gp")
    async def gr_cb(i): await open_ticket(i, "💰Robux Group💰", "gr")
    gp_btn.callback, gr_btn.callback = gp_cb, gr_cb
    
    v.add_item(gp_btn).add_item(gr_btn).add_item(Button(label="📝 โน้ต", emoji="📝", style=discord.ButtonStyle.secondary, custom_id="notes"))
    v.add_item(Button(label="⭐ เลเวล", emoji="⭐", style=discord.ButtonStyle.primary, custom_id="level"))
    
    if bot.main_msg:
        try: await bot.main_msg.edit(embed=e, view=v); return
        except: bot.main_msg = None
    async for m in ch.history(limit=10):
        if m.author == bot.user and m.embeds and "Sushi" in m.embeds[0].title:
            bot.main_msg = m; await m.edit(embed=e, view=v); return
    bot.main_msg = await ch.send(embed=e, view=v)

async def open_ticket(i, cat, typ):
    global gp_stock, group_stock
    if (typ=="gp" and gp_stock<=0) or (typ=="gr" and group_stock<=0) or not shop_open:
        return await i.response.send_message("❌ ปิด/หมด", ephemeral=True)
    if discord.utils.get(i.guild.text_channels, name=f"ticket-{i.user.name}-{i.user.id}".lower()):
        return await i.response.send_message("📌 มีตั๋วแล้ว", ephemeral=True)
    
    await i.response.defer(ephemeral=True)
    overwrites = {i.guild.default_role: discord.PermissionOverwrite(read_messages=False), i.guild.me: discord.PermissionOverwrite(read_messages=True), i.user: discord.PermissionOverwrite(read_messages=True)}
    if admin_role := i.guild.get_role(ADMIN_ROLE_ID): overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True)
    
    cat = discord.utils.get(i.guild.categories, name=cat)
    ch = await i.guild.create_text_channel(f"ticket-{i.user.name}-{i.user.id}".lower(), overwrites=overwrites, category=cat)
    cust_data[str(ch.id)] = i.user.name; save_json(FILES['customer'], cust_data)
    
    if typ=="gp": gp_stock -= 1
    else: group_stock -= 1
    await update_shop()
    
    v = View()
    v.add_item(Button(label="📩 ไปที่ตั๋ว", url=f"https://discord.com/channels/{ch.guild.id}/{ch.id}", style=discord.ButtonStyle.link))
    await i.followup.send("✅ เปิดตั๋ว", view=v, ephemeral=True)
    
    e = discord.Embed(title="🍣 Sushi Shop", description="กรอกแบบฟอร์ม", color=0x00FF99)
    e.add_field(name="👤 ผู้ซื้อ", value=i.user.mention)
    tv = View(timeout=None)
    fb = Button(label="📝 กรอกแบบฟอร์ม", style=discord.ButtonStyle.primary, emoji="📝")
    fb.callback = lambda x: x.response.send_modal(GamepassModal() if typ=="gp" else GroupModal())
    cb = Button(label="🔒 ปิด", style=discord.ButtonStyle.danger, emoji="🔒")
    async def close_cb(x):
        if admin_role and admin_role in x.user.roles:
            await save_transcript(ch, x.user)
            await x.response.send_message("📪 ปิดตั๋ว"); await asyncio.sleep(2); await ch.delete()
    cb.callback = close_cb
    tv.add_item(fb).add_item(cb)
    await ch.send(content=f"{admin_role.mention}" if admin_role else "", embed=e, view=tv)

async def save_transcript(ch, user, robux=None, name=None):
    num = next_ticket()
    now = get_thailand_time()
    d, t = now.strftime("%d%m%y"), now.strftime("%H%M")
    robux = robux or robux_data.get(str(ch.id), "1099")
    name = name or cust_data.get(str(ch.id), ch.name.split('-')[1] if ch.name.startswith("ticket-") else "wforr")
    fn = f"{d}{t}-{robux}-{name}"
    tickets[str(ch.id)] = {"filename": fn, "channel": ch.name, "id": ch.id, "num": num, "date": d, "time": t, "robux": str(robux), "customer": name, "closed_by": str(user) if user else "auto"}
    save_json(FILES['ticket'], tickets)
    return fn

# ==================== MODALS ====================
class GamepassModal(Modal, title="📋 แบบฟอร์มเกมพาส"):
    map = TextInput(label="🗺 ชื่อแมพ", placeholder="Gift Simulator")
    gp = TextInput(label="💸 ชื่อเกมพาส", placeholder="x3 Speed")
    amt = TextInput(label="🎟 ราคา", placeholder="300 หรือ 100+100+100")
    async def on_submit(self, i):
        try:
            robux = int(eval(self.amt.value.lower().replace("x","*").replace("÷","/").replace(",","")))
            e = discord.Embed(title="📨 รายละเอียด", color=0x00FF99)
            e.add_field(name="🗺️ แมพ", value=self.map.value).add_field(name="🎟 เกมพาส", value=self.gp.value).add_field(name="💸 โรบัค", value=f"{robux:,}").add_field(name="💰 ราคา", value=f"{robux/GAMEPASS_RATE:,.0f} บาท")
            await i.response.send_message(embed=e)
        except: await i.response.send_message("❌ ผิดพลาด", ephemeral=True)

class GroupModal(Modal, title="📋 แบบฟอร์มโรบัคกลุ่ม"):
    user = TextInput(label="🪪 ชื่อในเกม", placeholder="Username")
    amt = TextInput(label="💸 จำนวน", placeholder="1500")
    async def on_submit(self, i):
        try:
            robux = int(self.amt.value)
            rate = GROUP_RATE_LOW if robux<1500 else GROUP_RATE_HIGH
            e = discord.Embed(title="📨 รายละเอียด", color=0x00FF99)
            e.add_field(name="🪪 ชื่อ", value=self.user.value).add_field(name="💸 โรบัค", value=f"{robux:,}").add_field(name="💰 ราคา", value=f"{robux/rate:,.0f} บาท")
            await i.response.send_message(embed=e)
        except: await i.response.send_message("❌ ผิดพลาด", ephemeral=True)

class NoteModal(Modal, title="📝 จดวันที่"):
    note = TextInput(label="วันที่เข้ากลุ่ม", placeholder="20/10", style=discord.TextStyle.paragraph, required=False)
    async def on_submit(self, i):
        if self.note.value.strip():
            notes[str(i.user.id)] = {"note": self.note.value, "time": datetime.now().isoformat()}
            await i.response.send_message("✅ บันทึกแล้ว", ephemeral=True)
        else:
            notes.pop(str(i.user.id), None)
            await i.response.send_message("🗑️ ลบแล้ว", ephemeral=True)

# ==================== RNG SYSTEM ====================
ITEMS = {
    **{f"c{i}": {"name": n, "rarity":"common", "emoji":e, "value":1} for i,(n,e) in enumerate([
        ("🍎 แอปเปิล","🍎"), ("🍌 กล้วย","🍌"), ("🍒 เชอร์รี่","🍒"), ("🥕 แครอท","🥕"), ("🍞 ขนมปัง","🍞"),
        ("🥚 ไข่","🥚"), ("🥛 นม","🥛"), ("🍗 ไก่ทอด","🍗"), ("🍔 แฮมเบอร์เกอร์","🍔"), ("🍟 เฟรนช์ฟรายส์","🍟"),
        ("🍕 พิซซ่า","🍕"), ("🍣 ซูชิ","🍣"), ("🍜 ราเมน","🍜"), ("🍛 แกงกะหรี่","🍛"), ("🍚 ข้าวสวย","🍚")
    ])},
    **{f"r{i}": {"name": n, "rarity":"rare", "emoji":e, "value":5} for i,(n,e) in enumerate([
        ("⚔️ ดาบไม้","⚔️"), ("🛡️ โล่ไม้","🛡️"), ("🏹 ธนู","🏹"), ("🔮 ลูกแก้ว","🔮"), ("📜 ม้วนคัมภีร์","📜"),
        ("👑 มงกุฎทอง","👑"), ("🔑 กุญแจทอง","🔑"), ("💎 เพชร","💎"), ("⏳ นาฬิกาทราย","⏳"), ("🧭 เข็มทิศ","🧭")
    ])},
    **{f"l{i}": {"name": n, "rarity":"legendary", "emoji":e, "value":50} for i,(n,e) in enumerate([
        ("🐉 มังกร","🐉"), ("🦄 ยูนิคอร์น","🦄"), ("🧝 เอลฟ์","🧝"), ("🧙 พ่อมด","🧙"), ("🧚 นางฟ้า","🧚"),
        ("🧛 แวมไพร์","🧛"), ("🧟 ซอมบี้","🧟"), ("👽 เอเลี่ยน","👽")
    ])}
}

COMMON = {k:v for k,v in ITEMS.items() if v["rarity"]=="common"}
RARE = {k:v for k,v in ITEMS.items() if v["rarity"]=="rare"}
LEGEND = {k:v for k,v in ITEMS.items() if v["rarity"]=="legendary"}

def load_inv(): return load_json(FILES['inventory'], {})
def save_inv(d): save_json(FILES['inventory'], d)
def load_bal(): return load_json(FILES['balance'], {})
def save_bal(d): save_json(FILES['balance'], d)

def get_bal(uid): return load_bal().get(uid, 0)
def add_bal(uid, amt):
    b = load_bal()
    b[uid] = b.get(uid, 0) + amt
    save_bal(b)
    return b[uid]
def rem_bal(uid, amt):
    b = load_bal()
    if b.get(uid, 0) < amt: return False
    b[uid] -= amt
    if b[uid] <= 0: del b[uid]
    save_bal(b)
    return True

def get_inv(uid): return load_inv().get(uid, {})
def add_item(uid, iid, amt=1):
    inv = load_inv()
    if uid not in inv: inv[uid] = {}
    inv[uid][iid] = inv[uid].get(iid, 0) + amt
    save_inv(inv)
    return True
def rem_item(uid, iid, amt=1):
    inv = load_inv()
    if uid not in inv or inv[uid].get(iid, 0) < amt: return False
    inv[uid][iid] -= amt
    if inv[uid][iid] <= 0: del inv[uid][iid]
    if not inv[uid]: del inv[uid]
    save_inv(inv)
    return True

def random_item():
    r = random.random() * 100
    if r < 50: return random.choice(list(COMMON.items()))
    if r < 95: return random.choice(list(RARE.items()))
    return random.choice(list(LEGEND.items()))

# ==================== PAWN SHOP ====================
CUSTOMERS = ["คุณสมชาย", "คุณสมหญิง", "คุณอนันต์", "คุณประภาพร", "Mike", "John", "Sarah", "Emma"]
AVATARS = ["👨", "👩", "🧔", "👵", "👴"]

def get_price(item):
    if item["rarity"]=="common": return random.randint(1, 1000)
    if item["rarity"]=="rare": return random.randint(1001, 10000)
    return random.randint(10001, 100000)

class PawnCustomer:
    def __init__(self):
        self.name = random.choice(CUSTOMERS)
        self.avatar = random.choice(AVATARS)
        self.sat = random.randint(30, 100)
        self.pat = random.randint(2, 5)
        self.type = random.choice(["buy", "sell"])
    def calc(self, offer, base):
        diff = ((offer - base) / base) * 100
        new = self.sat + (-diff*0.5 if self.type=="buy" else diff*0.5)
        new = max(0, min(100, new))
        emoji = "😄" if new>=70 else "😐" if new>=40 else "😡"
        return int(new), emoji

# ==================== VIEWS ====================
class RNGMainView(View):
    def __init__(self, user):
        super().__init__(timeout=60)
        self.user = user
    
    @discord.ui.button(label="🎲 สุ่ม", style=discord.ButtonStyle.success, emoji="🎲", row=0)
    async def roll(self, i, b):
        if i.user != self.user: return await i.response.send_message("❌ ไม่ใช่เกมคุณ", ephemeral=True)
        iid, item = random_item()
        add_item(str(i.user.id), iid)
        inv = get_inv(str(i.user.id))
        e = discord.Embed(title="🎲 ผลสุ่ม", description=f"ได้: {item['emoji']} **{item['name']}**", color={"common":0x808080, "rare":0x00AAFF, "legendary":0xFFD700}[item["rarity"]])
        e.set_footer(text=f"{item['rarity'].upper()} | รวม {sum(inv.values())} ชิ้น | 🪙 {get_bal(str(i.user.id))}")
        await i.response.send_message(embed=e, ephemeral=True)
    
    @discord.ui.button(label="📦 Inventory", style=discord.ButtonStyle.primary, emoji="📦", row=0)
    async def inv(self, i, b):
        if i.user != self.user: return await i.response.send_message("❌ ไม่ใช่เกมคุณ", ephemeral=True)
        uid = str(i.user.id)
        inv = get_inv(uid)
        bal = get_bal(uid)
        if not inv:
            return await i.response.send_message(embed=discord.Embed(title="📦 Inventory", description=f"ยังไม่มีไอเทม\n💰 {bal} 🪙", color=0x808080), ephemeral=True)
        items = []
        for iid, amt in list(inv.items())[:10]:
            it = ITEMS[iid]
            e = {"common":"🟤", "rare":"🔵", "legendary":"🟡"}[it["rarity"]]
            items.append(f"{e} {it['emoji']} **{it['name']}** x{amt}")
        e = discord.Embed(title="📦 Inventory", color=0x00AAFF)
        e.add_field(name="📊 สถิติ", value=f"🟤 {sum(1 for k in inv if k in COMMON)} | 🔵 {sum(1 for k in inv if k in RARE)} | 🟡 {sum(1 for k in inv if k in LEGEND)}")
        e.add_field(name="📋 รายการ", value="\n".join(items))
        e.set_footer(text=f"💰 {bal} 🪙")
        await i.response.send_message(embed=e, ephemeral=True)
    
    @discord.ui.button(label="🏪 Pawn Shop", style=discord.ButtonStyle.secondary, emoji="🏪", row=1)
    async def pawn(self, i, b):
        if i.user != self.user: return await i.response.send_message("❌ ไม่ใช่เกมคุณ", ephemeral=True)
        uid = str(i.user.id)
        inv = get_inv(uid)
        bal = get_bal(uid)
        if not inv:
            return await i.response.send_message(embed=discord.Embed(title="🏪 Pawn Shop", description=f"ไม่มีไอเทม\n💰 {bal} 🪙", color=0x808080), ephemeral=True)
        
        opts = []
        for iid, amt in list(inv.items())[:10]:
            it = ITEMS[iid]
            price = "1-1k" if it["rarity"]=="common" else "1k-10k" if it["rarity"]=="rare" else "10k-100k"
            opts.append(discord.SelectOption(label=f"{it['name']} x{amt}", description=f"{it['rarity']} {price} 🪙", emoji=it['emoji'], value=iid))
        
        select = Select(placeholder="เลือกไอเทม...", options=opts)
        async def select_cb(si):
            if si.user != self.user: return await si.response.send_message("❌ ไม่ใช่เกมคุณ", ephemeral=True)
            iid = si.data["values"][0]
            it = ITEMS[iid]
            cust = PawnCustomer()
            price = get_price(it)
            e = discord.Embed(title=f"🏪 {it['emoji']} {it['name']}", description=f"{cust.avatar} **{cust.name}**\nสนใจ{cust.type} {it['emoji']} **{it['name']}**\nราคาพื้นฐาน {price:,} 🪙", color=0x00AAFF)
            e.add_field(name="📊 ลูกค้า", value=f"พอใจ {cust.sat}% | อดทน {cust.pat} ครั้ง | {'💰 ซื้อ' if cust.type=='buy' else '💸 ขาย'}")
            e.add_field(name="💰 ยอดคุณ", value=f"{bal} 🪙")
            bot.pawn_data[uid] = {"iid": iid, "it": it, "cust": cust, "base": price, "cur": price}
            await si.response.send_message(embed=e, view=PawnView(self.user, iid, it, cust, price, bal), ephemeral=True)
        
        select.callback = select_cb
        v = View(timeout=60)
        v.add_item(select)
        e = discord.Embed(title="🏪 Pawn Shop", description=f"💰 {bal} 🪙", color=0x00AAFF)
        e.add_field(name="💰 ระบบราคา", value="🟤 1-1k | 🔵 1k-10k | 🟡 10k-100k")
        await i.response.send_message(embed=e, view=v, ephemeral=True)
    
    @discord.ui.button(label="💰 เช็คเงิน", style=discord.ButtonStyle.success, emoji="🪙", row=1)
    async def bal(self, i, b):
        if i.user != self.user: return await i.response.send_message("❌ ไม่ใช่เกมคุณ", ephemeral=True)
        await i.response.send_message(embed=discord.Embed(title="💰 ยอดเงิน", description=f"**{get_bal(str(i.user.id))}** 🪙", color=0xFFD700), ephemeral=True)

class PawnView(View):
    def __init__(self, user, iid, it, cust, base, bal):
        super().__init__(timeout=120)
        self.user, self.iid, self.it, self.cust, self.base, self.cur, self.bal = user, iid, it, cust, base, base, bal
    
    @discord.ui.button(label="✅ ตกลง", style=discord.ButtonStyle.success, row=0)
    async def accept(self, i, b):
        if i.user != self.user: return await i.response.send_message("❌ ไม่ใช่เกมคุณ", ephemeral=True)
        uid = str(i.user.id)
        new_sat, emoji = self.cust.calc(self.cur, self.base)
        
        if new_sat >= 50:
            if self.cust.type == "buy":
                if rem_item(uid, self.iid):
                    nb = add_bal(uid, self.cur)
                    msg = f"✅ ขาย {self.it['emoji']} **{self.it['name']}** {self.cur:,} 🪙\n💰 {nb} 🪙"
                else: msg = "❌ ไม่พบไอเทม"
            else:
                if rem_bal(uid, self.cur):
                    add_item(uid, self.iid)
                    nb = get_bal(uid)
                    msg = f"✅ ซื้อ {self.it['emoji']} **{self.it['name']}** {self.cur:,} 🪙\n💰 {nb} 🪙"
                else: msg = f"❌ เงินไม่พอ ({self.bal}/{self.cur})"
        else: msg = f"{emoji} {self.cust.name}: ไม่เอาแล้ว!"
        
        e = discord.Embed(title=f"🤝 {emoji}" if new_sat>=50 else "❌ ล้มเหลว", description=msg, color=0x00FF00 if new_sat>=50 else 0xFF0000)
        bot.pawn_data.pop(uid, None)
        
        cv = View(timeout=60)
        cb = Button(label="เล่นต่อ", emoji="🎮", style=discord.ButtonStyle.primary)
        async def cont_cb(ci):
            if ci.user != self.user: return
            await ci.response.defer(ephemeral=True)
            inv = get_inv(uid)
            bal = get_bal(uid)
            if not inv:
                return await ci.followup.send(embed=discord.Embed(title="🏪 Pawn Shop", description=f"ไม่มีไอเทม\n💰 {bal} 🪙", color=0x808080), ephemeral=True)
            items = []
            for iid2, amt2 in list(inv.items())[:10]:
                it2 = ITEMS[iid2]
                e2 = {"common":"🟤", "rare":"🔵", "legendary":"🟡"}[it2["rarity"]]
                price = "1-1k" if it2["rarity"]=="common" else "1k-10k" if it2["rarity"]=="rare" else "10k-100k"
                items.append(f"`{len(items)+1}.` {e2} {it2['emoji']} **{it2['name']}** x{amt2} ({price})")
            e2 = discord.Embed(title="🏪 Pawn Shop", description=f"💰 {bal} 🪙\n\n" + "\n".join(items), color=0x00AAFF)
            e2.add_field(name="💰 วิธีใช้", value="พิมพ์ `!pselect <เลข>`")
            await ci.followup.send(embed=e2, ephemeral=True)
        cb.callback = cont_cb
        cv.add_item(cb)
        
        for child in self.children: child.disabled = True
        await i.response.edit_message(embed=e, view=cv)
    
    @discord.ui.button(label="❌ ปฏิเสธ", style=discord.ButtonStyle.danger, row=0)
    async def reject(self, i, b):
        if i.user != self.user: return
        e = discord.Embed(title="🚫 ปฏิเสธ", description=f"{self.cust.avatar} **{self.cust.name}**: ไว้คราวหน้า", color=0x808080)
        bot.pawn_data.pop(str(i.user.id), None)
        cv = View(timeout=60)
        cb = Button(label="เล่นต่อ", emoji="🎮", style=discord.ButtonStyle.primary)
        async def cont_cb(ci):
            if ci.user != self.user: return
            await ci.response.defer(ephemeral=True)
            uid = str(ci.user.id)
            inv = get_inv(uid)
            bal = get_bal(uid)
            if not inv:
                return await ci.followup.send(embed=discord.Embed(title="🏪 Pawn Shop", description=f"ไม่มีไอเทม\n💰 {bal} 🪙", color=0x808080), ephemeral=True)
            items = []
            for iid2, amt2 in list(inv.items())[:10]:
                it2 = ITEMS[iid2]
                e2 = {"common":"🟤", "rare":"🔵", "legendary":"🟡"}[it2["rarity"]]
                price = "1-1k" if it2["rarity"]=="common" else "1k-10k" if it2["rarity"]=="rare" else "10k-100k"
                items.append(f"`{len(items)+1}.` {e2} {it2['emoji']} **{it2['name']}** x{amt2} ({price})")
            e2 = discord.Embed(title="🏪 Pawn Shop", description=f"💰 {bal} 🪙\n\n" + "\n".join(items), color=0x00AAFF)
            e2.add_field(name="💰 วิธีใช้", value="พิมพ์ `!pselect <เลข>`")
            await ci.followup.send(embed=e2, ephemeral=True)
        cb.callback = cont_cb
        cv.add_item(cb)
        for child in self.children: child.disabled = True
        await i.response.edit_message(embed=e, view=cv)
    
    @discord.ui.button(label="💰 +5%", style=discord.ButtonStyle.primary, row=1)
    async def inc(self, i, b):
        if i.user != self.user or not self.cust.can_negotiate(): return await i.response.send_message("❌ หมดความอดทน", ephemeral=True)
        self.cur = math.ceil(self.cur * 1.05)
        self.cust.use_patience()
        new_sat, emoji = self.cust.calc(self.cur, self.base)
        self.cust.sat = new_sat
        e = discord.Embed(title="🤔 ต่อรอง", description=f"{self.cust.avatar} **{self.cust.name}**\n💰 {self.cur:,} 🪙\n😊 {new_sat}% {emoji}\n⏱️ {self.cust.pat} ครั้ง", color=0x00AAFF)
        await i.response.edit_message(embed=e, view=self)
    
    @discord.ui.button(label="💸 -5%", style=discord.ButtonStyle.primary, row=1)
    async def dec(self, i, b):
        if i.user != self.user or not self.cust.can_negotiate(): return await i.response.send_message("❌ หมดความอดทน", ephemeral=True)
        self.cur = max(1, math.floor(self.cur * 0.95))
        self.cust.use_patience()
        new_sat, emoji = self.cust.calc(self.cur, self.base)
        self.cust.sat = new_sat
        e = discord.Embed(title="🤔 ต่อรอง", description=f"{self.cust.avatar} **{self.cust.name}**\n💰 {self.cur:,} 🪙\n😊 {new_sat}% {emoji}\n⏱️ {self.cust.pat} ครั้ง", color=0x00AAFF)
        await i.response.edit_message(embed=e, view=self)

# ==================== PREFIX COMMANDS ====================
@bot.command(name="shop_open")
@admin_check()
async def shop_open(ctx):
    global shop_open
    shop_open = True
    await ctx.message.delete()
    await update_shop()
    await ctx.send(embed=discord.Embed(title="✅ เปิดร้าน", color=0x00FF00))

@bot.command(name="shop_close")
@admin_check()
async def shop_close(ctx):
    global shop_open
    shop_open = False
    await ctx.message.delete()
    await update_shop()
    await ctx.send(embed=discord.Embed(title="🔴 ปิดร้าน", color=0xFF0000))

@bot.command()
async def link(ctx):
    await ctx.send(embed=discord.Embed(title="🔗 ลิงก์กลุ่ม", description="https://www.roblox.com/communities/34713179/VALKYs", color=0x00FF00))

@bot.command()
@admin_check()
async def stock(ctx, typ=None, amt=None):
    global gp_stock, group_stock
    await ctx.message.delete()
    if not typ:
        e = discord.Embed(title="📊 สต๊อก", color=0x00FF99)
        e.add_field(name="🎮 Gamepass", value=f"{gp_stock:,}").add_field(name="👥 Group", value=f"{group_stock:,}")
        return await ctx.send(embed=e)
    if typ.lower() in ["gp","gamepass"]:
        if amt:
            gp_stock = int(amt.replace(",",""))
            await ctx.send(embed=discord.Embed(title="✅ ตั้งค่า", description=f"Gamepass = {gp_stock:,}", color=0x00FF00))
            await update_shop()
        else: await ctx.send(embed=discord.Embed(title="🎮 Gamepass", description=f"{gp_stock:,}", color=0x00FF99))
    elif typ.lower() in ["g","group"]:
        if amt:
            group_stock = int(amt.replace(",",""))
            await ctx.send(embed=discord.Embed(title="✅ ตั้งค่า", description=f"Group = {group_stock:,}", color=0x00FF00))
            await update_shop()
        else: await ctx.send(embed=discord.Embed(title="👥 Group", description=f"{group_stock:,}", color=0x00FF99))

@bot.command()
@admin_check()
async def group(ctx, status=None):
    global group_enabled
    await ctx.message.delete()
    if not status: return await ctx.send(embed=discord.Embed(title="👥 สถานะ", description="✅ เปิด" if group_enabled else "❌ ปิด", color=0x00FF00 if group_enabled else 0xFF0000))
    group_enabled = status.lower() in ["on","enable","เปิด"]
    await ctx.send(embed=discord.Embed(title="✅ เปิด" if group_enabled else "❌ ปิด", color=0x00FF00 if group_enabled else 0xFF0000))
    await update_shop()

@bot.command()
async def gp(ctx, *, expr):
    try: await ctx.send(f"🎮 {int(eval(expr.replace(',',''))):,} = **{int(eval(expr.replace(',','')))/GAMEPASS_RATE:,.0f}** บาท")
    except: await ctx.send("❌ ผิดพลาด")

@bot.command()
async def g(ctx, *, expr):
    try:
        r = int(eval(expr.replace(',','')))
        rate = GROUP_RATE_LOW if r<2250 else GROUP_RATE_HIGH
        await ctx.send(f"👥 {r:,} = **{r/rate:,.0f}** บาท")
    except: await ctx.send("❌ ผิดพลาด")

@bot.command(name="rng")
async def rng_cmd(ctx):
    e = discord.Embed(title="🎲 RNG Gacha", description="กดปุ่มด้านล่าง", color=0x00AAFF)
    e.add_field(name="📊 อัตรา", value="🟤 50% | 🔵 45% | 🟡 5%")
    await ctx.send(embed=e, view=RNGMainView(ctx.author))

@bot.command(name="roll")
async def roll_cmd(ctx):
    iid, it = random_item()
    add_item(str(ctx.author.id), iid)
    e = discord.Embed(title="🎲 ผลสุ่ม", description=f"ได้: {it['emoji']} **{it['name']}**", color={"common":0x808080, "rare":0x00AAFF, "legendary":0xFFD700}[it["rarity"]])
    e.set_footer(text=f"{it['rarity'].upper()} | 🪙 {get_bal(str(ctx.author.id))}")
    await ctx.send(embed=e)

@bot.command(name="inv", aliases=["inventory"])
async def inv_cmd(ctx):
    uid = str(ctx.author.id)
    inv = get_inv(uid)
    bal = get_bal(uid)
    if not inv:
        return await ctx.send(embed=discord.Embed(title="📦 Inventory", description=f"ไม่มีไอเทม\n💰 {bal} 🪙", color=0x808080))
    items = []
    for iid, amt in list(inv.items())[:10]:
        it = ITEMS[iid]
        e = {"common":"🟤", "rare":"🔵", "legendary":"🟡"}[it["rarity"]]
        items.append(f"{e} {it['emoji']} **{it['name']}** x{amt}")
    e = discord.Embed(title="📦 Inventory", color=0x00AAFF)
    e.add_field(name="📊 สถิติ", value=f"🟤 {sum(1 for k in inv if k in COMMON)} | 🔵 {sum(1 for k in inv if k in RARE)} | 🟡 {sum(1 for k in inv if k in LEGEND)}")
    e.add_field(name="📋 รายการ", value="\n".join(items))
    e.set_footer(text=f"💰 {bal} 🪙")
    await ctx.send(embed=e)

@bot.command(name="pawnshop", aliases=["pshop"])
async def pawn_cmd(ctx):
    uid = str(ctx.author.id)
    inv = get_inv(uid)
    bal = get_bal(uid)
    if not inv:
        return await ctx.send(embed=discord.Embed(title="🏪 Pawn Shop", description=f"ไม่มีไอเทม\n💰 {bal} 🪙", color=0x808080))
    items = []
    for i, (iid, amt) in enumerate(list(inv.items())[:10], 1):
        it = ITEMS[iid]
        e = {"common":"🟤", "rare":"🔵", "legendary":"🟡"}[it["rarity"]]
        price = "1-1k" if it["rarity"]=="common" else "1k-10k" if it["rarity"]=="rare" else "10k-100k"
        items.append(f"`{i}.` {e} {it['emoji']} **{it['name']}** x{amt} ({price})")
    e = discord.Embed(title="🏪 Pawn Shop", description=f"💰 {bal} 🪙\n\n" + "\n".join(items), color=0x00AAFF)
    e.add_field(name="💰 วิธีใช้", value="พิมพ์ `!pselect <เลข>`")
    await ctx.send(embed=e)

@bot.command(name="pselect")
async def pselect_cmd(ctx, num: int):
    uid = str(ctx.author.id)
    inv = get_inv(uid)
    bal = get_bal(uid)
    if not inv: return await ctx.send("❌ ไม่มีไอเทม")
    items = list(inv.items())
    if num < 1 or num > len(items): return await ctx.send(f"❌ เลือก 1-{len(items)}")
    iid, amt = items[num-1]
    it = ITEMS[iid]
    cust = PawnCustomer()
    price = get_price(it)
    e = discord.Embed(title=f"🏪 {it['emoji']} {it['name']}", description=f"{cust.avatar} **{cust.name}**\nสนใจ{cust.type} {it['emoji']} **{it['name']}**\nราคาพื้นฐาน {price:,} 🪙", color=0x00AAFF)
    e.add_field(name="📊 ลูกค้า", value=f"พอใจ {cust.sat}% | อดทน {cust.pat} ครั้ง | {'💰 ซื้อ' if cust.type=='buy' else '💸 ขาย'}")
    e.add_field(name="💰 ยอดคุณ", value=f"{bal} 🪙")
    bot.pawn_data[uid] = {"iid": iid, "it": it, "cust": cust, "base": price, "cur": price}
    await ctx.send(embed=e, view=PawnView(ctx.author, iid, it, cust, price, bal))

@bot.command()
@admin_check()
async def sync(ctx):
    try:
        s = await bot.tree.sync()
        await ctx.send(f"✅ Synced {len(s)} commands")
    except Exception as e: await ctx.send(f"❌ {e}")

# ==================== SLASH COMMANDS ====================
@bot.tree.command(name="rng", description="เล่นเกม RNG Gacha")
async def rng_slash(i: discord.Interaction):
    e = discord.Embed(title="🎲 RNG Gacha", description="กดปุ่มด้านล่าง", color=0x00AAFF)
    e.add_field(name="📊 อัตรา", value="🟤 50% | 🔵 45% | 🟡 5%")
    await i.response.send_message(embed=e, view=RNGMainView(i.user))

# ==================== TASKS ====================
@tasks.loop(minutes=1)
async def presence():
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=f"Sushi | GP:{gp_stock:,} G:{group_stock:,}"))

@tasks.loop(minutes=5)
async def save_all():
    save_json(FILES['user'], user_data)
    save_json(FILES['ticket'], tickets)
    save_json(FILES['robux'], robux_data)
    save_json(FILES['customer'], cust_data)

# ==================== EVENTS ====================
@bot.event
async def on_ready():
    print(f"✅ {bot.user}")
    try:
        s = await bot.tree.sync()
        print(f"✅ Synced {len(s)} commands")
        for cmd in s: print(f"   - /{cmd.name}")
    except Exception as e: print(f"❌ {e}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Sushi Shop"))
    presence.start()
    save_all.start()
    await update_shop()

@bot.event
async def on_message(m):
    if m.channel.id == CREDIT_CHANNEL_ID and m.author != bot.user:
        await asyncio.sleep(1)
        for e in ["❤️", "🍣"]:
            try: await m.add_reaction(e); await asyncio.sleep(0.5)
            except: pass
        await credit_queue.put("new")
    await bot.process_commands(m)

# ==================== START ====================
if __name__ == "__main__":
    keep_alive()
    time.sleep(3)
    token = os.getenv("TOKEN")
    if not token: exit("❌ No TOKEN")
    try: bot.run(token)
    except Exception as e: print(f"❌ {e}")
