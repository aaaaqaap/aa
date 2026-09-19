# -*- coding: utf-8 -*-
"""
بوت موحد: أرقام + منتجات + آسيا سيل + نجوم
المالك: 7380333343 | الأدمن: 8514663363
"""

import os
import json
import asyncio
import re
import time
import threading
import datetime
import random
import string
import traceback

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError, FloodWaitError
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetParticipantRequest

import telebot
import telebot.apihelper
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==========================================================
#                     الإعدادات
# ==========================================================
API_ID = 22651991
API_HASH = 'ecad214ecff6a5cd90fc141d4e32f597'
BOT_TOKEN = "8528362160:AAEjqI4JEfSCe5RRnNzDrwoAkak46pFheYc"

REG_ID = 1724716
REG_HASH = '00b2d8f59c12c1b9a4bc63b70b461b2f'

OWNER_ID = 7380333343
ADMIN2_ID = 8514663363

ACC_FILE = 'registered_accounts.json'
NUM_FILE = 'numbers_for_sale.json'
USER_FILE = 'user_data.json'
CONF_FILE = 'bot_settings.json'
PROD_FILE = 'products_data.json'
RECEIPT_FILE = 'star_receipts.json'
SESSION_FILE = 'BotSession'

telebot.apihelper.CONNECT_TIMEOUT = 30
telebot.apihelper.READ_TIMEOUT = 90

_retry = Retry(total=5, backoff_factor=2,
               status_forcelist=[429, 500, 502, 503, 504],
               allowed_methods=["GET", "POST"])
_adapter = HTTPAdapter(max_retries=_retry, pool_connections=20, pool_maxsize=20)
telebot.apihelper._get_req_session().mount("https://", _adapter)
telebot.apihelper._get_req_session().mount("http://", _adapter)

# ==========================================================
#                     ASIACELL
# ==========================================================
ASIA_BASE_URL = "https://odpapp.asiacell.com/api/v1/"
ASIA_DEVICE_ID = "5f4c8a3e-1234-5678-9abc-def012345678"
ASIA_API_KEY = "a1b2c3d4e5f67890abcdef1234567890"

def asia_headers(access_token=None):
    h = {
        'User-Agent': "okhttp/5.0.0-alpha.2",
        'Connection': "Keep-Alive",
        'Accept-Encoding': "gzip",
        'X-ODP-API-KEY': ASIA_API_KEY,
        'Cache-Control': "no-cache",
        'DeviceID': ASIA_DEVICE_ID,
        'X-OS-Version': "11",
        'X-Device-Type': "[Android][realme][RMX3834 11][TIRAMISU][HMS][4.3.7:90000325]",
        'X-ODP-APP-VERSION': "4.3.7",
        'X-FROM-APP': "odp",
        'X-ODP-CHANNEL': "mobile",
        'X-SCREEN-TYPE': "false",
        'Content-Type': "application/json; charset=UTF-8"
    }
    if access_token:
        h['Authorization'] = f"Bearer {access_token}"
    return h

def _safe_json(r):
    if r.status_code != 200:
        return {"success": False, "message": f"HTTP {r.status_code}"}
    try:
        return r.json()
    except Exception:
        return {"success": False, "message": "invalid"}

def asia_login(phone):
    try:
        r = requests.post(f"{ASIA_BASE_URL}login?lang=en",
                          data=json.dumps({"captchaCode": "", "username": phone}),
                          headers=asia_headers(), timeout=30)
        return _safe_json(r)
    except Exception as e:
        return {"success": False, "message": str(e)}

def asia_verify(pid, code):
    try:
        r = requests.post(f"{ASIA_BASE_URL}smsvalidation?lang=en",
                          data=json.dumps({"PID": pid, "passcode": code, "token": ""}),
                          headers=asia_headers(), timeout=30)
        return _safe_json(r)
    except Exception as e:
        return {"success": False, "message": str(e)}

def asia_start_transfer(amount, receiver, token):
    try:
        r = requests.post(f"{ASIA_BASE_URL}credit-transfer/start?lang=ar",
                          data=json.dumps({"amount": amount, "receiverMsisdn": receiver}),
                          headers=asia_headers(token), timeout=30)
        return _safe_json(r)
    except Exception as e:
        return {"success": False, "message": str(e)}

def asia_confirm_transfer(pid, code, token):
    try:
        r = requests.post(f"{ASIA_BASE_URL}credit-transfer/do-transfer?lang=ar",
                          data=json.dumps({"PID": pid, "passcode": code}),
                          headers=asia_headers(token), timeout=30)
        print(f"[ASIA CONFIRM] HTTP={r.status_code} RAW={r.text[:400]}")
        if r.status_code in (401, 403):
            return {"success": False, "expired": True}
        if r.status_code != 200:
            return {"success": False}
        try:
            data = r.json()
        except Exception:
            return {"success": False}
        if data.get('success') is True:
            return {"success": True}
        if data.get('error') is False or data.get('error') == 0:
            return {"success": True}
        status = str(data.get('status', '')).lower()
        if status in ('success', '1', '200', 'ok', 'true'):
            return {"success": True}
        result = data.get('result')
        if isinstance(result, dict) and result.get('success') is True:
            return {"success": True}
        msg = str(data.get('message', '')).lower()
        if 'success' in msg or 'نجاح' in msg or 'تم' in msg:
            return {"success": True}
        return {"success": False}
    except Exception:
        return {"success": False}

def _clean_session():
    for f in [f"{SESSION_FILE}.session", f"{SESSION_FILE}.session-journal"]:
        if os.path.exists(f):
            try:
                os.remove(f)
                print(f"[session] حُذف: {f}")
            except Exception as e:
                print(f"[session] فشل: {e}")

# ==========================================================
#                     كائنات
# ==========================================================
client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML', threaded=False)

state_lock = threading.RLock()
MAIN_LOOP = None

# ==========================================================
#                     المتغيرات
# ==========================================================
u_clients = {}
code_reqs = {}
res_timers = {}
u_sessions = {}
avail_nums = {}
syyad_users = {}
conv_state = {}
star_receipts = {}

syyad_conf = {
    'admin_ids': [str(OWNER_ID), str(ADMIN2_ID)],
    'dailyGiftPoints': 0,
    'referralPoints': 0,
    'reservationTimeoutMinutes': 60,
    'publish_channel_id': None,
    'force_channels': [],
    'asia_phone': None,
    'asia_token': None,
    'asia_pid': None,
    'asia_points_per_dollar': 1000,
    'asia_max_dollars': 10,
    'asia_min_dollars': 1,
    'stars_receiver_id': ADMIN2_ID,
    'stats': {
        'total_users': 0, 'total_sales_all': 0,
        'sales_by_day': {}, 'users_seen': [],
    },
    'sales_channel_id': None,
}

products_data = {
    'categories': [], 'products': [],
    'pending_transfers': {},
}

# ==========================================================
#                     Helpers
# ==========================================================
def run_async(coro):
    if MAIN_LOOP is None or MAIN_LOOP.is_closed():
        try: coro.close()
        except: pass
        return None
    try:
        return asyncio.run_coroutine_threadsafe(coro, MAIN_LOOP)
    except Exception:
        try: coro.close()
        except: pass
        return None

def load(fpath, d):
    if os.path.exists(fpath):
        with open(fpath, 'r', encoding='utf-8') as f:
            try: return json.load(f)
            except: return d
    return d

def save(fpath, data):
    try:
        tmp = fpath + ".tmp"
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(tmp, fpath)
    except Exception as e:
        print(f"[save] {fpath}: {e}")

def load_all():
    global u_sessions, avail_nums, syyad_users, syyad_conf, products_data, star_receipts
    u_sessions = load(ACC_FILE, {})
    avail_nums = load(NUM_FILE, {})
    syyad_users = load(USER_FILE, {})
    loaded = load(CONF_FILE, {})
    syyad_conf.update(loaded)
    products_data = load(PROD_FILE, products_data)
    star_receipts = load(RECEIPT_FILE, {})

    syyad_conf.setdefault('force_channels', [])
    syyad_conf.setdefault('admin_ids', [])
    syyad_conf.setdefault('stats', {})
    syyad_conf['stats'].setdefault('total_users', 0)
    syyad_conf['stats'].setdefault('total_sales_all', 0)
    syyad_conf['stats'].setdefault('sales_by_day', {})
    syyad_conf['stats'].setdefault('users_seen', [])
    syyad_conf.setdefault('asia_points_per_dollar', 1000)
    syyad_conf.setdefault('asia_max_dollars', 10)
    syyad_conf.setdefault('asia_min_dollars', 1)
    syyad_conf.setdefault('stars_receiver_id', ADMIN2_ID)
    syyad_conf.setdefault('reservationTimeoutMinutes', 60)

    if str(OWNER_ID) not in syyad_conf['admin_ids']:
        syyad_conf['admin_ids'].insert(0, str(OWNER_ID))
    if str(ADMIN2_ID) not in syyad_conf['admin_ids']:
        syyad_conf['admin_ids'].append(str(ADMIN2_ID))

def save_all():
    save(ACC_FILE, u_sessions)
    save(NUM_FILE, avail_nums)
    save(CONF_FILE, syyad_conf)
    save(USER_FILE, syyad_users)
    save(PROD_FILE, products_data)
    save(RECEIPT_FILE, star_receipts)

def save_products(): save(PROD_FILE, products_data)
def save_conf(): save(CONF_FILE, syyad_conf)
def save_receipts(): save(RECEIPT_FILE, star_receipts)
def save_users(): save(USER_FILE, syyad_users)

def get_bal(uid):
    uid = str(uid)
    if uid not in syyad_users:
        syyad_users[uid] = {}
    syyad_users[uid].setdefault('points', 0)
    syyad_users[uid].setdefault('lastDailyGiftClaim', None)
    syyad_users[uid].setdefault('verified_asia_phone', None)
    syyad_users[uid].setdefault('asia_token', None)
    save_users()
    return syyad_users[uid]

def register_user(uid):
    uid = str(uid)
    if uid not in syyad_users:
        syyad_users[uid] = {
            'points': 0,
            'lastDailyGiftClaim': None,
            'verified_asia_phone': None,
            'asia_token': None
        }
        save_users()
    if uid not in syyad_conf['stats']['users_seen']:
        syyad_conf['stats']['users_seen'].append(uid)
        syyad_conf['stats']['total_users'] = len(syyad_conf['stats']['users_seen'])
        save_conf()

def is_adm(uid): return str(uid) in syyad_conf['admin_ids']
def is_owner(uid): return str(uid) == str(OWNER_ID)
def get_stars_receiver(): return int(syyad_conf.get('stars_receiver_id', ADMIN2_ID))

def record_sale(sale_type, uid, amount, details=""):
    today = datetime.date.today().isoformat()
    stats = syyad_conf['stats']
    stats['total_sales_all'] += 1
    stats['sales_by_day'][today] = stats['sales_by_day'].get(today, 0) + 1
    save_conf()

def notify_sales_channel(text):
    ch = syyad_conf.get('sales_channel_id')
    if not ch: return
    try: bot.send_message(ch, text, parse_mode='HTML')
    except: pass

def _normalize_asia_phone(phone):
    if not phone: return None
    cleaned = str(phone).strip().replace('+', '').replace(' ', '').replace('-', '')
    if not cleaned.isdigit(): return None
    if cleaned.startswith('00'): cleaned = cleaned[2:]
    if cleaned.startswith('964'): rest = cleaned[3:]
    elif cleaned.startswith('0'): rest = cleaned[1:]
    else: rest = cleaned
    if len(rest) != 10: return None
    if not rest.startswith('7'): return None
    return f"964{rest}"

def safe_edit(chat_id, msg_id, text, kb=None):
    try:
        bot.edit_message_text(text, chat_id, msg_id,
                              parse_mode='HTML', reply_markup=kb)
    except Exception as e:
        if 'message is not modified' in str(e).lower(): return
        try:
            bot.send_message(chat_id, text, parse_mode='HTML', reply_markup=kb)
        except: pass

def safe_send(chat_id, text, kb=None, photo=None):
    try:
        if photo:
            bot.send_photo(chat_id, photo, caption=text,
                           parse_mode='HTML', reply_markup=kb)
        else:
            bot.send_message(chat_id, text, parse_mode='HTML', reply_markup=kb)
    except Exception as e:
        print(f"[safe_send] {e}")

# ==========================================================
#              الاشتراك الإجباري
# ==========================================================
async def check_membership(user_id):
    if not syyad_conf.get('force_channels'):
        return True, []
    missing = []
    for ch in syyad_conf['force_channels']:
        try:
            target = ch['id']
            if str(target).lstrip('-').isdigit():
                target = int(target)
            await client(GetParticipantRequest(channel=target, participant=user_id))
        except Exception:
            missing.append(ch)
    return (len(missing) == 0), missing

# ==========================================================
#              الحجز
# ==========================================================
async def run_timer(phone, uid, expiry):
    rem = expiry - time.time()
    if rem <= 0:
        await end_resv(phone, notify=False); return
    task = asyncio.create_task(asyncio.sleep(rem))
    res_timers[phone] = task
    try: await task; await end_resv(phone)
    except asyncio.CancelledError: pass
    finally: res_timers.pop(phone, None)

async def end_resv(phone, notify=True):
    if phone in avail_nums and avail_nums[phone]['status'] == 'booked':
        booked_by = avail_nums[phone]['booked_by']
        avail_nums[phone].update({
            'status': 'available', 'booked_by': None,
            'booking_time': None, 'expiry_time': None, 'deposit_paid_stars': None
        })
        save_all()
        if notify and booked_by:
            try: await client.send_message(int(booked_by),
                f"🚨 انتهى حجز <code>{phone}</code>.", parse_mode='html')
            except: pass
    if phone in res_timers:
        res_timers[phone].cancel(); del res_timers[phone]

async def init_resv():
    for phone, d in list(avail_nums.items()):
        if d.get('status') == 'booked' and d.get('expiry_time'):
            exp = d['expiry_time']
            if exp > time.time():
                asyncio.create_task(run_timer(phone, d['booked_by'], exp))
            else: await end_resv(phone, notify=False)

# ==========================================================
#              تهيئة عملاء الأرقام
# ==========================================================
async def init_acc(phone, api_id, api_hash, sess_str):
    if phone in u_clients and u_clients[phone].is_connected(): return
    uc = TelegramClient(StringSession(sess_str), api_id, api_hash)

    @uc.on(events.NewMessage(incoming=True, from_users=777000))
    async def proc_code(event):
        text = event.message.text or ""
        m = re.search(r'Login code:\s*(\d+)', text) or re.search(r'\b(\d{4,7})\b', text)
        if not m: return
        code = m.group(1)
        buyer = code_reqs.get(phone)
        if buyer:
            acc = u_sessions.get(phone, {})
            two = acc.get('two_factor_password', 'لا يوجد')
            msg = (f"✅ <b>كود التحقق</b>\n\n"
                   f"📞 <code>{phone}</code>\n🔑 <code>{code}</code>\n")
            if two and two != "لا يوجد":
                msg += f"🔒 2FA: <code>{two}</code>\n"
            try: await client.send_message(int(buyer), msg, parse_mode='html')
            except: pass
            code_reqs.pop(phone, None)
        raise events.StopPropagation

    try:
        await uc.connect()
        if not await uc.is_user_authorized():
            u_clients.pop(phone, None); return
        u_clients[phone] = uc
    except Exception as e:
        print(f"[init_acc] {phone}: {e}")
        u_clients.pop(phone, None)

async def run_accs():
    for phone, d in u_sessions.items():
        if d.get('api_id') and d.get('api_hash') and d.get('session_str'):
            asyncio.create_task(init_acc(phone, d['api_id'], d['api_hash'], d['session_str']))

# ==========================================================
#              التسليم
# ==========================================================
async def deliver_number(phone, buyer_id):
    acc = u_sessions.get(phone, {})
    info = avail_nums.get(phone, {})
    code_reqs[phone] = int(buyer_id)
    msg = (f"🎉 <b>تم تسليم الرقم!</b>\n\n"
           f"📞 <code>{phone}</code>\n"
           f"🌍 {info.get('country', 'غير محدد')}\n\n"
           f"1️⃣ افتح تيليجرام\n2️⃣ سجّل بالرقم\n3️⃣ سيصلك الكود هنا\n")
    if acc.get('two_factor_password') and acc['two_factor_password'] != "لا يوجد":
        msg += f"\n🔒 2FA: <code>{acc['two_factor_password']}</code>\n"
    try: await client.send_message(int(buyer_id), msg, parse_mode='html')
    except: pass
    notify_sales_channel(f"🛒 شراء رقم: <code>{phone}</code>")

async def edit_post_sold(phone):
    ch = syyad_conf.get('publish_channel_id')
    if ch and phone in avail_nums:
        mid = avail_nums[phone].get('publish_message_id')
        if mid:
            try:
                orig = await client.get_messages(ch, ids=mid)
                if orig:
                    await client.edit_message(ch, mid, f"#تم_البيع\n\n{orig.text}")
            except: pass

# ==========================================================
#              /start
# ==========================================================
@bot.message_handler(commands=['start'])
def cmd_start(m):
    try:
        uid = str(m.chat.id)
        is_new = uid not in syyad_users
        get_bal(uid)
        register_user(uid)

        # إحالة
        text = m.text or ""
        parts = text.split()
        ref_id = None
        if len(parts) > 1 and parts[1].startswith('ref_'):
            ref_id = parts[1][4:]

        if is_new and ref_id and ref_id != uid and 'referred_by' not in syyad_users[uid]:
            syyad_users[uid]['referred_by'] = ref_id
            rp = syyad_conf.get('referralPoints', 0)
            if rp > 0:
                get_bal(ref_id)['points'] += rp
                save_users()
                try: bot.send_message(int(ref_id), f"🎉 +{rp}")
                except: pass

        # أدمن
        if is_adm(uid):
            send_admin_main(m.chat.id)
            return

        # فحص الاشتراك
        try:
            fut = asyncio.run_coroutine_threadsafe(
                check_membership(m.chat.id), MAIN_LOOP)
            ok, missing = fut.result(timeout=10)
        except Exception:
            ok = True
            missing = []

        if not ok:
            kb = InlineKeyboardMarkup()
            for c in missing:
                url = (c.get('url') or '').strip()
                if url and not url.startswith(('https://', 'tg://')):
                    if url.startswith('@'): url = f"https://t.me/{url[1:]}"
                    elif url.startswith('t.me/'): url = f"https://{url}"
                    else: url = f"https://t.me/{url}"
                if url and url.startswith(('https://', 'tg://')):
                    kb.add(InlineKeyboardButton(f"📢 {c.get('title', 'قناة')}", url=url))
                else:
                    kb.add(InlineKeyboardButton(f"📢 {c.get('title', 'قناة')}",
                                                 callback_data='dummy_sep'))
            kb.add(InlineKeyboardButton("✅ تحققت", callback_data='check_subs'))
            safe_send(m.chat.id, "🚫 <b>اشترك أولاً:</b>", kb)
            return

        send_user_main(m.chat.id)
    except Exception as e:
        print(f"[cmd_start] {e}")
        traceback.print_exc()

# ==========================================================
#              قوائم
# ==========================================================
def send_admin_main(chat_id, msg_id=None):
    receiver = get_stars_receiver()
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton('📱 الأرقام', callback_data='admin_numbers_section'),
        InlineKeyboardButton('🛍️ المتجر', callback_data='admin_store_section')
    )
    kb.row(
        InlineKeyboardButton('📊 الإحصائيات', callback_data='admin_stats'),
        InlineKeyboardButton('💳 الرصيد', callback_data='admin_balance_section')
    )
    kb.row(
        InlineKeyboardButton('⚙️ الإعدادات', callback_data='admin_settings_section'),
        InlineKeyboardButton('🔗 قناة المبيعات', callback_data='admin_set_sales_ch')
    )
    kb.row(
        InlineKeyboardButton('📢 الاشتراك', callback_data='admin_force_subs'),
        InlineKeyboardButton('📱 آسيا سيل', callback_data='admin_asia_section')
    )
    kb.row(InlineKeyboardButton('⭐ النجوم', callback_data='admin_stars_section'))
    text = f'🛠️ <b>لوحة الأدمن</b>\n⭐ النجوم: <code>{receiver}</code>'
    if msg_id:
        safe_edit(chat_id, msg_id, text, kb)
    else:
        safe_send(chat_id, text, kb)


def send_user_main(chat_id, msg_id=None):
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton('📱 شراء رقم', callback_data='user_buy_number_menu'),
        InlineKeyboardButton('🛍️ المتجر', callback_data='store_main')
    )
    kb.row(
        InlineKeyboardButton('💰 شحن نقاط (آسيا سيل)', callback_data='user_asia_main'),
        InlineKeyboardButton('🎁 الهدية اليومية', callback_data='user_daily_gift')
    )
    kb.row(InlineKeyboardButton('💳 رصيدي', callback_data='user_balance'))
    text = '👋 <b>أهلاً بك</b>'
    if msg_id:
        safe_edit(chat_id, msg_id, text, kb)
    else:
        safe_send(chat_id, text, kb)

# ==========================================================
#              /cancel
# ==========================================================
@bot.message_handler(commands=['cancel'])
def cmd_cancel(m):
    with state_lock:
        conv_state.pop(m.chat.id, None)
    try: bot.send_message(m.chat.id, "❌ تم الإلغاء.")
    except: pass

# ==========================================================
#              callbacks
# ==========================================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    try:
        uid = str(call.from_user.id)
        data = call.data
        chat_id = call.message.chat.id
        msg_id = call.message.message_id
        register_user(uid)

        if data == 'dummy_sep':
            try: bot.answer_callback_query(call.id)
            except: pass
            return

        if data == 'check_subs':
            try:
                fut = asyncio.run_coroutine_threadsafe(
                    check_membership(call.from_user.id), MAIN_LOOP)
                ok, missing = fut.result(timeout=10)
            except Exception:
                ok = True
            if ok:
                try: bot.answer_callback_query(call.id, "✅", show_alert=True)
                except: pass
                send_user_main(chat_id, msg_id)
            else:
                try: bot.answer_callback_query(call.id, "❌ اشترك أولاً.", show_alert=True)
                except: pass
            return

        if is_adm(uid):
            handle_admin_callback(call, data)
            return

        try:
            fut = asyncio.run_coroutine_threadsafe(
                check_membership(call.from_user.id), MAIN_LOOP)
            ok, missing = fut.result(timeout=10)
        except Exception:
            ok = True
        if not ok:
            try: bot.answer_callback_query(call.id, "🚫 اشترك.", show_alert=True)
            except: pass
            return

        handle_user_callback(call, data)
    except Exception as e:
        print(f"[callback ERROR] {e}")
        traceback.print_exc()
        try:
            bot.answer_callback_query(call.id, f"❌ {str(e)[:100]}", show_alert=True)
        except: pass

# ==========================================================
#              admin callbacks
# ==========================================================
def handle_admin_callback(call, data):
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    uid = str(call.from_user.id)
    try:
        bot.answer_callback_query(call.id)
    except: pass

    if data == 'main_admin_menu':
        send_admin_main(chat_id, msg_id); return

    if data == 'admin_stats':
        stats = syyad_conf['stats']
        today = datetime.date.today().isoformat()
        today_count = stats['sales_by_day'].get(today, 0)
        last7 = ""
        for i in range(6, -1, -1):
            d = (datetime.date.today() - datetime.timedelta(days=i)).isoformat()
            cnt = stats['sales_by_day'].get(d, 0)
            last7 += f"<code>{d}</code> → <b>{cnt}</b>\n"
        msg = (f"📊 <b>الإحصائيات</b>\n\n"
               f"👥 {stats['total_users']}\n"
               f"💰 اليوم: {today_count}\n"
               f"📈 الإجمالي: {stats['total_sales_all']}\n\n{last7}")
        kb = InlineKeyboardMarkup()
        kb.row(
            InlineKeyboardButton("🔄", callback_data='admin_stats'),
            InlineKeyboardButton("العودة", callback_data='main_admin_menu')
        )
        safe_edit(chat_id, msg_id, msg, kb)
        return

    if data == 'admin_stars_section':
        receiver = get_stars_receiver()
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("✏️ تغيير", callback_data='admin_change_stars_id'))
        kb.add(InlineKeyboardButton("العودة", callback_data='main_admin_menu'))
        safe_edit(chat_id, msg_id,
                  f"⭐ <b>النجوم</b>\n\n👤 حساب: <code>{receiver}</code>", kb)
        return

    if data == 'admin_change_stars_id':
        with state_lock:
            conv_state[chat_id] = {'step': 'change_stars_id', 'data': {}}
        bot.send_message(chat_id, "✏️ أرسل ID:")
        return

    if data == 'admin_asia_section':
        phone = syyad_conf.get('asia_phone')
        token_set = bool(syyad_conf.get('asia_token'))
        rate = syyad_conf.get('asia_points_per_dollar', 1000)
        min_d = syyad_conf.get('asia_min_dollars', 1)
        max_d = syyad_conf.get('asia_max_dollars', 10)
        kb = InlineKeyboardMarkup()
        if phone and token_set:
            status = f"✅ <code>{phone}</code>"
            kb.add(InlineKeyboardButton("🗑️ حذف", callback_data='admin_asia_delete'))
        else:
            status = "❌ غير مربوط"
            kb.add(InlineKeyboardButton("📱 ربط رقم", callback_data='admin_asia_setup'))
        kb.row(
            InlineKeyboardButton(f"✏️ النسبة ({rate})", callback_data='admin_change_asia_rate'),
            InlineKeyboardButton("📊 النطاق", callback_data='admin_change_asia_minmax')
        )
        kb.add(InlineKeyboardButton("العودة", callback_data='main_admin_menu'))
        safe_edit(chat_id, msg_id,
                  f"📱 <b>آسيا سيل (المالك)</b>\n\n"
                  f"الحالة: {status}\n💱 1$ = {rate}\n📊 {min_d}$ إلى {max_d}$", kb)
        return

    if data == 'admin_asia_setup':
        with state_lock:
            conv_state[chat_id] = {'step': 'asia_setup_phone', 'data': {}}
        bot.send_message(chat_id, "📱 أرسل رقم المالك:")
        return

    if data == 'admin_asia_delete':
        syyad_conf['asia_phone'] = None
        syyad_conf['asia_token'] = None
        syyad_conf['asia_pid'] = None
        save_conf()
        try: bot.answer_callback_query(call.id, "🗑️", show_alert=True)
        except: pass
        handle_admin_callback(call, 'admin_asia_section')
        return

    if data == 'admin_asia_confirm':
        if syyad_conf.get('asia_phone') and syyad_conf.get('asia_token'):
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("العودة", callback_data='admin_asia_section'))
            safe_edit(chat_id, msg_id,
                      f"✅ <code>{syyad_conf['asia_phone']}</code>", kb)
        return

    if data == 'admin_change_asia_rate':
        with state_lock:
            conv_state[chat_id] = {'step': 'admin_change_asia_rate', 'data': {}}
        bot.send_message(chat_id, "💱 أرسل النسبة:")
        return

    if data == 'admin_change_asia_minmax':
        with state_lock:
            conv_state[chat_id] = {'step': 'admin_change_asia_minmax', 'data': {}}
        bot.send_message(chat_id, "📊 أرسل min max (مثال: 1 10):")
        return

    if data == 'admin_numbers_section':
        kb = InlineKeyboardMarkup()
        kb.row(
            InlineKeyboardButton('➕ إضافة', callback_data='add_new_number'),
            InlineKeyboardButton('📋 عرض', callback_data='view_added_numbers')
        )
        kb.add(InlineKeyboardButton('🗑️ حذف', callback_data='delete_displayed_numbers'))
        kb.add(InlineKeyboardButton('العودة', callback_data='main_admin_menu'))
        safe_edit(chat_id, msg_id, '📱 <b>الأرقام</b>', kb)
        return

    if data == 'add_new_number':
        start_add_number(chat_id)
        return

    if data == 'view_added_numbers':
        if not avail_nums:
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("العودة", callback_data='admin_numbers_section'))
            safe_edit(chat_id, msg_id, "لا توجد أرقام.", kb)
            return
        kb = InlineKeyboardMarkup()
        for p, d in list(avail_nums.items())[:20]:
            st = d.get('status', 'N/A')
            emoji = "🟢" if st == 'available' else ("🟡" if st == 'booked' else "🔴")
            kb.add(InlineKeyboardButton(f"{emoji} {p}",
                                         callback_data=f"view_specific_number:{p}"))
        kb.add(InlineKeyboardButton("العودة", callback_data='admin_numbers_section'))
        safe_edit(chat_id, msg_id, f"📋 <b>الأرقام ({len(avail_nums)}):</b>", kb)
        return

    if data.startswith('view_specific_number:'):
        phone = data.split(':', 1)[1]
        if phone not in avail_nums:
            return
        d = avail_nums[phone]
        st = d.get('status')
        txt = {'available': "🟢 متاح", 'booked': "🟡 محجوز", 'sold': "🔴 مباع"}.get(st, st)
        msg = (f"📞 <code>{phone}</code>\n🌍 {d.get('country')}\n"
               f"💰 {d.get('price_points',0)}\n🌟 {d.get('price_stars',0)}\n{txt}")
        kb = InlineKeyboardMarkup()
        if st == 'booked':
            kb.add(InlineKeyboardButton("إلغاء", callback_data=f"admin_cancel_booking:{phone}"))
        kb.add(InlineKeyboardButton("العودة", callback_data='view_added_numbers'))
        safe_edit(chat_id, msg_id, msg, kb)
        return

    if data.startswith('admin_cancel_booking:'):
        phone = data.split(':', 1)[1]
        run_async(end_resv(phone))
        try: bot.answer_callback_query(call.id, "✅", show_alert=True)
        except: pass
        handle_admin_callback(call, 'view_added_numbers')
        return

    if data == 'delete_displayed_numbers':
        if not avail_nums:
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("العودة", callback_data='admin_numbers_section'))
            safe_edit(chat_id, msg_id, "لا توجد.", kb)
            return
        kb = InlineKeyboardMarkup()
        for p in list(avail_nums.keys())[:20]:
            kb.add(InlineKeyboardButton(f"❌ {p}",
                                         callback_data=f"delete_number_confirm:{p}"))
        kb.add(InlineKeyboardButton("العودة", callback_data='admin_numbers_section'))
        safe_edit(chat_id, msg_id, "اختر:", kb)
        return

    if data.startswith('delete_number_confirm:'):
        phone = data.split(':', 1)[1]
        kb = InlineKeyboardMarkup()
        kb.row(
            InlineKeyboardButton("✅", callback_data=f"delete_number_execute:{phone}"),
            InlineKeyboardButton("❌", callback_data='delete_displayed_numbers')
        )
        safe_edit(chat_id, msg_id, f"حذف <code>{phone}</code>؟", kb)
        return

    if data.startswith('delete_number_execute:'):
        phone = data.split(':', 1)[1]
        if phone in avail_nums:
            if phone in u_clients:
                try: run_async(u_clients[phone].disconnect())
                except: pass
                del u_clients[phone]
            if phone in res_timers:
                res_timers[phone].cancel(); del res_timers[phone]
            del avail_nums[phone]
            u_sessions.pop(phone, None)
            save_all()
        try: bot.answer_callback_query(call.id, "✅", show_alert=True)
        except: pass
        handle_admin_callback(call, 'delete_displayed_numbers')
        return

    if data == 'admin_balance_section':
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton('العودة', callback_data='main_admin_menu'))
        safe_edit(chat_id, msg_id, '💳 الأوامر:\n/addpoints uid عدد\n/forcepoints uid عدد', kb)
        return

    if data == 'admin_settings_section':
        kb = InlineKeyboardMarkup()
        kb.row(
            InlineKeyboardButton("⭐ النجوم", callback_data='admin_stars_section'),
            InlineKeyboardButton("📱 آسيا", callback_data='admin_asia_section')
        )
        kb.add(InlineKeyboardButton('العودة', callback_data='main_admin_menu'))
        safe_edit(chat_id, msg_id, '⚙️', kb)
        return

    if data == 'admin_set_sales_ch':
        with state_lock:
            conv_state[chat_id] = {'step': 'set_sales_ch', 'data': {}}
        bot.send_message(chat_id, "🔗 أرسل معرف قناة المبيعات (أو 'حذف'):")
        return

    if data == 'admin_force_subs':
        chans = syyad_conf.get('force_channels', [])
        lines = [f"{i+1}. {c.get('title','?')}" for i, c in enumerate(chans)] or ["لا توجد."]
        kb = InlineKeyboardMarkup()
        for i, c in enumerate(chans):
            kb.add(InlineKeyboardButton(f"🗑️ {c.get('title','?')}",
                                         callback_data=f"del_force_sub:{i}"))
        kb.add(InlineKeyboardButton("➕", callback_data='add_force_sub'))
        kb.add(InlineKeyboardButton("العودة", callback_data='main_admin_menu'))
        safe_edit(chat_id, msg_id, "📢 <b>الاشتراك:</b>\n\n" + "\n".join(lines), kb)
        return

    if data == 'add_force_sub':
        with state_lock:
            conv_state[chat_id] = {'step': 'fs_title', 'data': {}}
        bot.send_message(chat_id, "📢 العنوان:")
        return

    if data.startswith('del_force_sub:'):
        idx = int(data.split(':', 1)[1])
        chans = syyad_conf.get('force_channels', [])
        if 0 <= idx < len(chans):
            chans.pop(idx); save_conf()
            try: bot.answer_callback_query(call.id, "✅", show_alert=True)
            except: pass
        handle_admin_callback(call, 'admin_force_subs')
        return

    if data == 'admin_store_section':
        lines = [f"📁 {c['name']}" for c in products_data['categories']] or ["لا توجد."]
        kb = InlineKeyboardMarkup()
        kb.row(
            InlineKeyboardButton("➕ قسم", callback_data='store_add_cat'),
            InlineKeyboardButton("➕ منتج", callback_data='store_add_prod')
        )
        kb.add(InlineKeyboardButton("🗑️ حذف", callback_data='store_del_cat'))
        kb.add(InlineKeyboardButton("العودة", callback_data='main_admin_menu'))
        safe_edit(chat_id, msg_id, "🛍️ <b>المتجر</b>\n\n" + "\n".join(lines), kb)
        return

    if data == 'store_add_cat':
        with state_lock:
            conv_state[chat_id] = {'step': 'store_cat_name', 'data': {}}
        bot.send_message(chat_id, "📝 اسم القسم:")
        return

    if data == 'store_add_prod':
        if not products_data['categories']:
            try: bot.answer_callback_query(call.id, "❌ أضف قسم.", show_alert=True)
            except: pass
            return
        with state_lock:
            conv_state[chat_id] = {'step': 'store_prod_cat', 'data': {}}
        cats = "\n".join(f"<code>{c['id']}</code> → {c['name']}"
                         for c in products_data['categories'])
        bot.send_message(chat_id, f"🆔 أرسل ID القسم:\n\n{cats}", parse_mode='HTML')
        return

    if data == 'store_del_cat':
        if not products_data['categories']:
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("العودة", callback_data='admin_store_section'))
            safe_edit(chat_id, msg_id, "لا توجد.", kb)
            return
        kb = InlineKeyboardMarkup()
        for c in products_data['categories']:
            kb.add(InlineKeyboardButton(f"🗑️ {c['name']}",
                                         callback_data=f"store_del_cat_exec:{c['id']}"))
        kb.add(InlineKeyboardButton("العودة", callback_data='admin_store_section'))
        safe_edit(chat_id, msg_id, "اختر:", kb)
        return

    if data.startswith('store_del_cat_exec:'):
        cid = data.split(':', 1)[1]
        products_data['categories'] = [c for c in products_data['categories'] if c['id'] != cid]
        products_data['products'] = [p for p in products_data['products'] if p['category_id'] != cid]
        save_products()
        try: bot.answer_callback_query(call.id, "✅", show_alert=True)
        except: pass
        handle_admin_callback(call, 'store_del_cat')
        return

    if data.startswith('star_approve:'):
        rid = data.split(':', 1)[1]
        run_async(process_star_approve(rid))
        try: bot.answer_callback_query(call.id, "✅", show_alert=True)
        except: pass
        return

    if data.startswith('star_reject:'):
        rid = data.split(':', 1)[1]
        if rid in star_receipts:
            star_receipts[rid]['status'] = 'rejected'
            save_receipts()
        try: bot.answer_callback_query(call.id, "❌", show_alert=True)
        except: pass
        return

# ==========================================================
#              user callbacks
# ==========================================================
def handle_user_callback(call, data):
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    uid = str(call.from_user.id)
    try:
        bot.answer_callback_query(call.id)
    except: pass

    if data == 'user_main_menu':
        send_user_main(chat_id, msg_id); return

    if data == 'user_balance':
        ub = get_bal(uid)
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("العودة", callback_data='user_main_menu'))
        safe_edit(chat_id, msg_id,
                  f"💳 <b>رصيدك:</b>\n\n"
                  f"💰 نقاط: <code>{ub['points']}</code>\n"
                  f"📱 رقم آسيا: <code>{ub.get('verified_asia_phone') or 'غير مرتبط'}</code>",
                  kb)
        return

    if data == 'user_buy_number_menu':
        countries = sorted({d['country'] for d in avail_nums.values()
                            if d.get('status') in ('available', 'booked')})
        if not countries:
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("العودة", callback_data='user_main_menu'))
            safe_edit(chat_id, msg_id, "❌ لا توجد أرقام.", kb)
            return
        kb = InlineKeyboardMarkup()
        row = []
        for c in countries:
            row.append(InlineKeyboardButton(c, callback_data=f"show_country_numbers:{c}"))
            if len(row) == 2:
                kb.row(*row); row = []
        if row: kb.row(*row)
        kb.add(InlineKeyboardButton("العودة", callback_data='user_main_menu'))
        safe_edit(chat_id, msg_id, "🌍 اختر الدولة:", kb)
        return

    if data.startswith('show_country_numbers:'):
        ctry = data.split(':', 1)[1]
        nums = {p: d for p, d in avail_nums.items()
                if d.get('country') == ctry and d.get('status') in ('available', 'booked')}
        kb = InlineKeyboardMarkup()
        added = False
        for p, d in nums.items():
            if d['status'] == 'available':
                kb.add(InlineKeyboardButton(f"📞 {p}",
                                             callback_data=f"view_number_details:{p}"))
                added = True
            elif str(d.get('booked_by')) == uid:
                kb.add(InlineKeyboardButton(f"🔔 {p}",
                                             callback_data=f"view_number_details:{p}"))
                added = True
        if not added:
            kb.add(InlineKeyboardButton("العودة", callback_data='user_buy_number_menu'))
            safe_edit(chat_id, msg_id, "❌ لا أرقام.", kb)
            return
        kb.add(InlineKeyboardButton("العودة", callback_data='user_buy_number_menu'))
        safe_edit(chat_id, msg_id, f"📋 أرقام {ctry}:", kb)
        return

    if data.startswith('view_number_details:'):
        phone = data.split(':', 1)[1]
        if phone not in avail_nums:
            return
        d = avail_nums[phone]
        st = d.get('status')
        pp = d.get('price_points', 0)
        sp = d.get('price_stars', 0)
        msg = f"📞 <code>{phone}</code>\n🌍 {d['country']}\n"
        if pp > 0: msg += f"💰 {pp} نقطة\n"
        if sp > 0: msg += f"🌟 {sp} نجمة\n"
        kb = InlineKeyboardMarkup()
        if st == 'available':
            row = []
            if sp > 0 and syyad_conf.get('reservationTimeoutMinutes', 0) > 0:
                row.append(InlineKeyboardButton(f"حجز {max(1, sp//2)}🌟",
                                                 callback_data=f"book_number:{phone}"))
            if pp > 0 or sp > 0:
                row.append(InlineKeyboardButton("💳 شراء",
                                                 callback_data=f"choose_payment_method:{phone}:full"))
            if row: kb.row(*row)
        elif st == 'booked' and str(d.get('booked_by')) == uid:
            kb.add(InlineKeyboardButton("❌ إلغاء الحجز",
                                         callback_data=f"user_cancel_booking:{phone}"))
        kb.add(InlineKeyboardButton("العودة", callback_data='user_buy_number_menu'))
        safe_edit(chat_id, msg_id, msg, kb)
        return

    if data.startswith('book_number:'):
        phone = data.split(':', 1)[1]
        if phone not in avail_nums or avail_nums[phone]['status'] != 'available':
            return
        full = avail_nums[phone].get('price_stars', 0)
        if full == 0: return
        dep = max(1, full // 2)
        show_star_payment_tb(chat_id, msg_id, phone, 'booking', dep)
        return

    if data.startswith('choose_payment_method:'):
        parts = data.split(':', 2)
        phone = parts[1]; pay_type = parts[2]
        show_payment_methods_tb(chat_id, msg_id, phone, pay_type, uid)
        return

    if data.startswith('pay_with_points:'):
        parts = data.split(':', 2)
        phone = parts[1]; pay_type = parts[2]
        process_pay_points_tb(chat_id, msg_id, phone, pay_type, uid)
        return

    if data.startswith('pay_with_stars:'):
        parts = data.split(':', 3)
        phone = parts[1]; amount = int(parts[2]); pay_type = parts[3]
        show_star_payment_tb(chat_id, msg_id, phone, pay_type, amount)
        return

    if data.startswith('star_receipt:'):
        parts = data.split(':', 3)
        phone = parts[1]; pay_type = parts[2]; amount = int(parts[3])
        with state_lock:
            conv_state[chat_id] = {
                'step': 'star_receipt',
                'data': {'phone': phone, 'pay_type': pay_type, 'amount': amount}
            }
        bot.send_message(chat_id, "📸 أرسل لقطة شاشة للإيصال:")
        return

    if data.startswith('user_cancel_booking:'):
        phone = data.split(':', 1)[1]
        if phone in avail_nums and avail_nums[phone]['status'] == 'booked' \
           and str(avail_nums[phone]['booked_by']) == uid:
            kb = InlineKeyboardMarkup()
            kb.row(
                InlineKeyboardButton("✅", callback_data=f"execute_user_cancel_booking:{phone}"),
                InlineKeyboardButton("❌", callback_data=f"view_number_details:{phone}")
            )
            safe_edit(chat_id, msg_id, "إلغاء؟", kb)
        return

    if data.startswith('execute_user_cancel_booking:'):
        phone = data.split(':', 1)[1]
        if phone in avail_nums and avail_nums[phone]['status'] == 'booked' \
           and str(avail_nums[phone]['booked_by']) == uid:
            run_async(end_resv(phone))
            try: bot.answer_callback_query(call.id, "✅", show_alert=True)
            except: pass
            handle_user_callback(call, 'user_buy_number_menu')
        return

    if data == 'user_asia_main':
        ub = get_bal(uid)
        verified = ub.get('verified_asia_phone')
        user_token = ub.get('asia_token')
        rate = syyad_conf.get('asia_points_per_dollar', 1000)
        min_d = syyad_conf.get('asia_min_dollars', 1)
        max_d = syyad_conf.get('asia_max_dollars', 10)
        kb = InlineKeyboardMarkup()
        if not verified or not user_token:
            kb.add(InlineKeyboardButton("📱 تأكيد الرقم", callback_data='asia_login_start'))
            kb.add(InlineKeyboardButton("العودة", callback_data='user_main_menu'))
            safe_edit(chat_id, msg_id,
                      f"📱 <b>شحن رصيد آسيا سيل</b>\n\n"
                      f"سعر الصرف: <b>1$ = {rate} نقطة</b>\n"
                      f"الحد الأدنى: {min_d}$ — الأقصى: {max_d}$\n\n"
                      f"⚠️ يجب تأكيد رقم آسيا سيل أولاً.", kb)
            return
        kb.add(InlineKeyboardButton("💰 شحن الآن", callback_data='asia_enter_amount'))
        kb.row(
            InlineKeyboardButton("🗑️ حذف الرقم", callback_data='asia_delete_phone'),
            InlineKeyboardButton("🔄 تغيير الرقم", callback_data='asia_login_start')
        )
        kb.add(InlineKeyboardButton("العودة", callback_data='user_main_menu'))
        safe_edit(chat_id, msg_id,
                  f"📱 <b>شحن رصيد آسيا سيل</b>\n\n"
                  f"✅ <b>رقمك:</b> <code>{verified}</code>\n\n"
                  f"💱 <b>1$ = {rate} نقطة</b>\n"
                  f"📊 النطاق: <b>{min_d*rate}</b> إلى <b>{max_d*rate}</b>\n"
                  f"💳 رصيدك: <b>{ub['points']}</b> نقطة", kb)
        return

    if data == 'asia_login_start':
        with state_lock:
            conv_state[chat_id] = {'step': 'asia_phone', 'data': {}}
        bot.send_message(chat_id,
            "📱 <b>الخطوة 1:</b> أرسل رقم آسيا سيل\n"
            "مثال: <code>07701234567</code>\n\n"
            "/cancel للإلغاء.",
            parse_mode='HTML')
        return

    if data == 'asia_delete_phone':
        ub = get_bal(uid)
        ub['verified_asia_phone'] = None
        ub['asia_token'] = None
        save_users()
        try: bot.answer_callback_query(call.id, "🗑️", show_alert=True)
        except: pass
        handle_user_callback(call, 'user_asia_main')
        return

    if data == 'asia_enter_amount':
        with state_lock:
            conv_state[chat_id] = {'step': 'asia_user_amount', 'data': {}}
        rate = syyad_conf.get('asia_points_per_dollar', 1000)
        max_d = syyad_conf.get('asia_max_dollars', 10)
        min_d = syyad_conf.get('asia_min_dollars', 1)
        bot.send_message(chat_id,
            f"💰 <b>الخطوة 2:</b> أدخل عدد النقاط\n\n"
            f"📊 النطاق: <b>{min_d*rate}</b> إلى <b>{max_d*rate}</b>\n"
            f"💱 كل {rate} = 1$\n\n"
            f"مثال: <code>{rate}</code> = 1$",
            parse_mode='HTML')
        return

    if data == 'user_daily_gift':
        ub = get_bal(uid)
        now = time.time()
        last = ub.get('lastDailyGiftClaim')
        pts = syyad_conf.get('dailyGiftPoints', 0)
        if pts == 0:
            try: bot.answer_callback_query(call.id, "❌", show_alert=True)
            except: pass
            return
        if last and (now - last) < 86400:
            rem = int(last + 86400 - now)
            h, rem = divmod(rem, 3600); mm, ss = divmod(rem, 60)
            try: bot.answer_callback_query(call.id,
                f"⏳ {h:02d}:{mm:02d}:{ss:02d}", show_alert=True)
            except: pass
        else:
            ub['points'] += pts
            ub['lastDailyGiftClaim'] = now
            save_users()
            try: bot.answer_callback_query(call.id, f"🎉 +{pts}", show_alert=True)
            except: pass
        return

    if data == 'store_main':
        if not products_data['categories']:
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("العودة", callback_data='user_main_menu'))
            safe_edit(chat_id, msg_id, "🛍️ المتجر فارغ.", kb)
            return
        kb = InlineKeyboardMarkup()
        for c in products_data['categories'][:8]:
            count = len([p for p in products_data['products'] if p['category_id'] == c['id']])
            kb.add(InlineKeyboardButton(f"{c['name']} ({count})",
                                         callback_data=f"store_cat:{c['id']}"))
        kb.add(InlineKeyboardButton("العودة", callback_data='user_main_menu'))
        safe_edit(chat_id, msg_id, "🛍️ <b>اختر القسم:</b>", kb)
        return

    if data.startswith('store_cat:'):
        cat_id = data.split(':', 1)[1]
        cat = next((c for c in products_data['categories'] if c['id'] == cat_id), None)
        if not cat: return
        prods = [p for p in products_data['products'] if p['category_id'] == cat_id]
        if not prods:
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("العودة", callback_data='store_main'))
            safe_edit(chat_id, msg_id, "لا توجد منتجات.", kb)
            return
        kb = InlineKeyboardMarkup()
        for p in prods[:10]:
            kb.add(InlineKeyboardButton(f"{p['name']} | {p['points']}",
                                         callback_data=f"store_prod:{p['id']}"))
        kb.add(InlineKeyboardButton("العودة", callback_data='store_main'))
        safe_edit(chat_id, msg_id, f"📁 <b>{cat['name']}</b>", kb)
        return

    if data.startswith('store_prod:'):
        prod_id = data.split(':', 1)[1]
        p = next((p for p in products_data['products'] if p['id'] == prod_id), None)
        if not p: return
        ub = get_bal(uid)
        msg = (f"🛍️ <b>{p['name']}</b>\n\n"
               f"📝 {p.get('description', '')}\n\n"
               f"💰 <b>{p['points']}</b> نقطة\n"
               f"💳 رصيدك: <b>{ub['points']}</b>")
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🛒 شراء", callback_data=f"store_buy:{p['id']}"))
        kb.add(InlineKeyboardButton("العودة", callback_data=f"store_cat:{p['category_id']}"))
        safe_edit(chat_id, msg_id, msg, kb)
        return

    if data.startswith('store_buy:'):
        prod_id = data.split(':', 1)[1]
        p = next((p for p in products_data['products'] if p['id'] == prod_id), None)
        if not p: return
        ub = get_bal(uid)
        if ub['points'] < p['points']:
            try: bot.answer_callback_query(call.id, "❌ رصيدك غير كافٍ.", show_alert=True)
            except: pass
            return
        ub['points'] -= p['points']
        save_users()
        try:
            if p.get('delivery_type') == 'text':
                bot.send_message(chat_id,
                    f"✅ <b>تم الشراء!</b>\n\n"
                    f"🛍️ {p['name']}\n\n📦 {p.get('delivery_content', '')}",
                    parse_mode='HTML')
            elif p.get('delivery_type') == 'photo':
                bot.send_photo(chat_id, p.get('delivery_file_id'),
                               caption=f"✅ {p['name']}")
            elif p.get('delivery_type') == 'document':
                bot.send_document(chat_id, p.get('delivery_file_id'),
                                  caption=f"✅ {p['name']}")
        except: pass
        products_data['products'] = [x for x in products_data['products'] if x['id'] != prod_id]
        save_products()
        record_sale('product', uid, p['points'], p['name'])
        try: bot.answer_callback_query(call.id, "✅", show_alert=True)
        except: pass
        handle_user_callback(call, 'store_main')
        return

# ==========================================================
#              نجوم - شحن
# ==========================================================
def show_star_payment_tb(chat_id, msg_id, phone, pay_type, amount):
    receiver = get_stars_receiver()
    target_link = f"tg://openmessage?user_id={receiver}"
    msg = (f"🌟 <b>الدفع بالنجوم</b>\n\n"
           f"📞 <code>{phone}</code>\n"
           f"⭐ <b>{amount}</b> نجمة\n\n"
           f"1️⃣ اضغط <b>📩 راسل المالك</b>\n"
           f"2️⃣ أرسل <b>{amount}</b> نجمة\n"
           f"3️⃣ ارجع واضغط <b>📸 إرسال الإيصال</b>")
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📩 راسل المالك", url=target_link))
    kb.add(InlineKeyboardButton("📸 إرسال الإيصال",
                                 callback_data=f"star_receipt:{phone}:{pay_type}:{amount}"))
    kb.add(InlineKeyboardButton("❌ إلغاء", callback_data=f"view_number_details:{phone}"))
    safe_edit(chat_id, msg_id, msg, kb)


def show_payment_methods_tb(chat_id, msg_id, phone, pay_type, uid):
    if phone not in avail_nums: return
    d = avail_nums[phone]
    ub = get_bal(uid)
    pp, sp = d.get('price_points', 0), d.get('price_stars', 0)
    star_to_pay, pts_to_pay = 0, 0
    if pay_type == 'remaining':
        star_to_pay = sp - d.get('deposit_paid_stars', 0)
        pts_to_pay = pp
    elif pay_type == 'full':
        star_to_pay, pts_to_pay = sp, pp
    elif pay_type == 'points_only':
        star_to_pay, pts_to_pay = 0, pp
    msg = f"💳 <code>{phone}</code>\n\n"
    kb = InlineKeyboardMarkup()
    if pts_to_pay > 0:
        msg += f"💰 {pts_to_pay} (رصيدك {ub['points']})\n"
        kb.add(InlineKeyboardButton(f"{pts_to_pay} نقطة",
                                     callback_data=f"pay_with_points:{phone}:{pay_type}"))
    if star_to_pay > 0:
        msg += f"🌟 {star_to_pay}\n"
        kb.add(InlineKeyboardButton(f"{star_to_pay} نجمة",
                                     callback_data=f"pay_with_stars:{phone}:{star_to_pay}:{pay_type}"))
    kb.add(InlineKeyboardButton("إلغاء", callback_data=f"view_number_details:{phone}"))
    safe_edit(chat_id, msg_id, msg, kb)


def process_pay_points_tb(chat_id, msg_id, phone, pay_type, uid):
    if phone not in avail_nums: return
    d = avail_nums[phone]
    ub = get_bal(uid)
    pts = d.get('price_points', 0)
    if pts <= 0 or ub['points'] < pts:
        try: bot.send_message(chat_id, "❌ رصيدك غير كافٍ.")
        except: pass
        return
    is_booked = pay_type in ('remaining', 'points_only')
    is_full = pay_type == 'full'
    if (is_booked and d.get('status') == 'booked' and str(d.get('booked_by')) == uid) or \
       (is_full and d.get('status') == 'available'):
        ub['points'] -= pts
        avail_nums[phone]['status'] = 'sold'
        avail_nums[phone]['buyer_id'] = uid
        if is_booked: run_async(end_resv(phone, notify=False))
        save_users(); save_all()
        record_sale('number', uid, pts, phone)
        run_async(edit_post_sold(phone))
        run_async(deliver_number(phone, uid))
        safe_edit(chat_id, msg_id, f"✅ <code>{phone}</code>")


async def process_star_approve(rid):
    if rid not in star_receipts: return
    r = star_receipts[rid]
    if r['status'] != 'pending': return
    phone = r['phone']
    uid = str(r['user_id'])
    amount = r['amount']
    if phone not in avail_nums or avail_nums[phone].get('status') == 'sold':
        r['status'] = 'rejected'; save_receipts(); return
    was_booked = avail_nums[phone].get('status') == 'booked'
    avail_nums[phone]['status'] = 'sold'
    avail_nums[phone]['buyer_id'] = uid
    avail_nums[phone]['booked_by'] = None
    save_all()
    if was_booked and phone in res_timers:
        try: res_timers[phone].cancel(); del res_timers[phone]
        except: pass
    record_sale('number', uid, amount, phone)
    await edit_post_sold(phone)
    await deliver_number(phone, uid)
    r['status'] = 'approved'; save_receipts()

# ==========================================================
#              آسيا سيل (المستخدم)
# ==========================================================
def start_add_number(chat_id):
    with state_lock:
        conv_state[chat_id] = {'step': 'phone', 'data': {}}
    try: bot.send_message(chat_id, "📱 أرسل الرقم (+964...):")
    except: pass

# ==========================================================
#              محادثات
# ==========================================================
@bot.message_handler(func=lambda m: m.chat.id in conv_state, content_types=['text'])
def handle_conv(m):
    chat_id = m.chat.id
    with state_lock:
        state = conv_state.get(chat_id)
    if not state: return
    step = state['step']
    text = m.text.strip()

    if step == 'phone':
        if not text.startswith('+') or not text[1:].isdigit():
            bot.send_message(chat_id, "❌ صيغة خاطئة."); return
        if text in u_sessions:
            bot.send_message(chat_id, "❌ مسجل.")
            with state_lock: conv_state.pop(chat_id, None); return
        state['data']['phone'] = text
        state['step'] = 'country'
        bot.send_message(chat_id, "🌍 الدولة:")

    elif step == 'country':
        state['data']['country'] = text
        state['step'] = 'pts_price'
        bot.send_message(chat_id, "💰 نقاط:")

    elif step == 'pts_price':
        try: state['data']['pts_price'] = int(text)
        except: bot.send_message(chat_id, "❌"); return
        state['step'] = 'star_price'
        bot.send_message(chat_id, "🌟 نجوم:")

    elif step == 'star_price':
        try: state['data']['star_price'] = int(text)
        except: bot.send_message(chat_id, "❌"); return
        state['step'] = '2fa'
        bot.send_message(chat_id, "🔒 2FA (أو 'لا يوجد'):")

    elif step == '2fa':
        state['data']['two_fa'] = text
        state['step'] = 'waiting_code'
        phone = state['data']['phone']
        bot.send_message(chat_id, "⏳...")
        run_async(request_code_and_prompt(chat_id, phone))

    elif step == 'code':
        state['data']['code'] = text
        run_async(try_sign_in(chat_id))

    elif step == '2fa_signin':
        state['data']['2fa_signin'] = text
        run_async(try_sign_in_with_2fa(chat_id))

    elif step == 'fs_title':
        state['data']['title'] = text
        state['step'] = 'fs_url'
        bot.send_message(chat_id, "🔗 الرابط:")

    elif step == 'fs_url':
        state['data']['url'] = text
        state['step'] = 'fs_id'
        bot.send_message(chat_id, "🆔 المعرف (@xxx أو -100xxx):")

    elif step == 'fs_id':
        state['data']['id'] = text
        syyad_conf['force_channels'].append({
            'title': state['data']['title'],
            'url': state['data']['url'],
            'id': state['data']['id']
        })
        save_conf()
        with state_lock: conv_state.pop(chat_id, None)
        bot.send_message(chat_id, "✅")

    elif step == 'asia_phone':
        run_async(process_asia_phone(chat_id, text))

    elif step == 'asia_code':
        run_async(process_asia_code(chat_id, text))

    elif step == 'asia_user_amount':
        run_async(process_asia_user_amount(chat_id, text))

    elif step == 'asia_user_code':
        run_async(process_asia_user_code(chat_id, text))

    elif step == 'asia_setup_phone':
        state['data']['phone'] = text
        bot.send_message(chat_id, "⏳...")
        run_async(admin_asia_login(chat_id, text))

    elif step == 'asia_setup_code':
        run_async(admin_asia_verify(chat_id, text))

    elif step == 'change_stars_id':
        if not text.isdigit():
            bot.send_message(chat_id, "❌ رقم فقط."); return
        syyad_conf['stars_receiver_id'] = int(text)
        save_conf()
        with state_lock: conv_state.pop(chat_id, None)
        bot.send_message(chat_id, f"✅ {text}")

    elif step == 'admin_change_asia_rate':
        try: r = int(text)
        except: bot.send_message(chat_id, "❌"); return
        syyad_conf['asia_points_per_dollar'] = r
        save_conf()
        with state_lock: conv_state.pop(chat_id, None)
        bot.send_message(chat_id, f"✅ {r}")

    elif step == 'admin_change_asia_minmax':
        parts = text.split()
        if len(parts) != 2:
            bot.send_message(chat_id, "❌"); return
        try: mn, mx = int(parts[0]), int(parts[1])
        except: bot.send_message(chat_id, "❌"); return
        syyad_conf['asia_min_dollars'] = mn
        syyad_conf['asia_max_dollars'] = mx
        save_conf()
        with state_lock: conv_state.pop(chat_id, None)
        bot.send_message(chat_id, f"✅ {mn}-{mx}")

    elif step == 'store_cat_name':
        cid = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        products_data['categories'].append({'id': cid, 'name': text})
        save_products()
        with state_lock: conv_state.pop(chat_id, None)
        bot.send_message(chat_id, f"✅ {text}")

    elif step == 'store_prod_cat':
        cat = next((c for c in products_data['categories'] if c['id'] == text), None)
        if not cat:
            bot.send_message(chat_id, "❌ القسم غير موجود."); return
        state['data']['cat_id'] = text
        state['step'] = 'store_prod_name'
        bot.send_message(chat_id, "📝 اسم المنتج:")

    elif step == 'store_prod_name':
        state['data']['name'] = text
        state['step'] = 'store_prod_desc'
        bot.send_message(chat_id, "📄 الوصف:")

    elif step == 'store_prod_desc':
        state['data']['desc'] = text
        state['step'] = 'store_prod_price'
        bot.send_message(chat_id, "💰 السعر:")

    elif step == 'store_prod_price':
        try: state['data']['price'] = int(text)
        except: bot.send_message(chat_id, "❌"); return
        state['step'] = 'store_prod_content'
        bot.send_message(chat_id, "📦 المحتوى (نص/صورة/ملف):")

    elif step == 'store_prod_content':
        pid = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        products_data['products'].append({
            'id': pid,
            'category_id': state['data']['cat_id'],
            'name': state['data']['name'],
            'description': state['data']['desc'],
            'points': state['data']['price'],
            'delivery_type': 'text',
            'delivery_content': text,
            'delivery_file_id': None,
        })
        save_products()
        with state_lock: conv_state.pop(chat_id, None)
        bot.send_message(chat_id, "✅")

    elif step == 'set_sales_ch':
        ch = text.strip()
        syyad_conf['sales_channel_id'] = None if ch == 'حذف' else ch
        save_conf()
        with state_lock: conv_state.pop(chat_id, None)
        bot.send_message(chat_id, f"✅ {ch}")

# ==========================================================
#              media
# ==========================================================
@bot.message_handler(content_types=['photo', 'document'],
                     func=lambda m: m.chat.id in conv_state
                     and conv_state[m.chat.id].get('step') in ('store_prod_content', 'star_receipt'))
def handle_media(m):
    chat_id = m.chat.id
    with state_lock:
        state = conv_state.get(chat_id)
    if not state: return
    if state['step'] == 'star_receipt':
        run_async(process_star_receipt(chat_id, m))
        return
    if state['step'] == 'store_prod_content':
        dtype = 'text'
        content = None
        fid = None
        if m.content_type == 'photo':
            dtype = 'photo'; fid = m.photo[-1].file_id
        elif m.content_type == 'document':
            dtype = 'document'; fid = m.document.file_id
        pid = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        products_data['products'].append({
            'id': pid,
            'category_id': state['data']['cat_id'],
            'name': state['data']['name'],
            'description': state['data']['desc'],
            'points': state['data']['price'],
            'delivery_type': dtype,
            'delivery_content': content,
            'delivery_file_id': fid,
        })
        save_products()
        with state_lock: conv_state.pop(chat_id, None)
        bot.send_message(chat_id, "✅")

# ==========================================================
#       Async: إضافة رقم + آسيا + نجوم
# ==========================================================
async def request_code_and_prompt(chat_id, phone):
    try:
        c = TelegramClient(StringSession(), REG_ID, REG_HASH)
        await c.connect()
        ci = await c.send_code_request(phone)
        with state_lock:
            if chat_id not in conv_state:
                await c.disconnect(); return
            conv_state[chat_id]['data']['_client'] = c
            conv_state[chat_id]['data']['_code_info'] = ci
            conv_state[chat_id]['step'] = 'code'
        try: bot.send_message(chat_id, "📨 أرسل الكود:")
        except: pass
    except FloodWaitError as e:
        try: bot.send_message(chat_id, f"⏳ {e.seconds}s")
        except: pass
        with state_lock: conv_state.pop(chat_id, None)
    except Exception as e:
        try: bot.send_message(chat_id, f"❌ {e}")
        except: pass
        with state_lock: conv_state.pop(chat_id, None)

async def try_sign_in(chat_id):
    with state_lock:
        state = conv_state.get(chat_id)
    if not state: return
    d = state['data']
    try:
        await d['_client'].sign_in(phone=d['phone'], code=d['code'],
                                    phone_code_hash=d['_code_info'].phone_code_hash)
        await finalize_add(chat_id)
    except SessionPasswordNeededError:
        with state_lock:
            if chat_id in conv_state:
                conv_state[chat_id]['step'] = '2fa_signin'
        try: bot.send_message(chat_id, "🔒 2FA:")
        except: pass
    except Exception as e:
        try: bot.send_message(chat_id, f"❌ {e}")
        except: pass
        with state_lock: conv_state.pop(chat_id, None)

async def try_sign_in_with_2fa(chat_id):
    with state_lock:
        state = conv_state.get(chat_id)
    if not state: return
    try:
        await state['data']['_client'].sign_in(password=state['data']['2fa_signin'])
        await finalize_add(chat_id)
    except Exception as e:
        try: bot.send_message(chat_id, f"❌ {e}")
        except: pass
        with state_lock: conv_state.pop(chat_id, None)

async def finalize_add(chat_id):
    with state_lock:
        state = conv_state.pop(chat_id, None)
    if not state: return
    d = state['data']
    c = d['_client']
    phone = d['phone']
    sess = c.session.save()
    try: await c.disconnect()
    except: pass
    u_sessions[phone] = {
        'api_id': REG_ID, 'api_hash': REG_HASH,
        'session_str': sess,
        'two_factor_password': d.get('two_fa', 'لا يوجد')
    }
    avail_nums[phone] = {
        'price_points': d['pts_price'], 'price_stars': d['star_price'],
        'country': d['country'], 'status': 'available',
        'added_by': str(OWNER_ID), 'buyer_id': None, 'booked_by': None,
        'booking_time': None, 'expiry_time': None,
        'deposit_paid_stars': None, 'publish_message_id': None
    }
    save_all()
    try: bot.send_message(chat_id, f"✅ {phone}")
    except: pass
    asyncio.create_task(init_acc(phone, REG_ID, REG_HASH, sess))

# آسيا
async def admin_asia_login(chat_id, phone):
    normalized = _normalize_asia_phone(phone)
    if not normalized:
        try: bot.send_message(chat_id, "❌ رقم غير صالح.")
        except: pass
        with state_lock: conv_state.pop(chat_id, None); return
    data = asia_login(normalized)
    if data.get('success') and 'nextUrl' in data:
        m = re.search(r'PID=([a-f0-9\-]+)', data['nextUrl'])
        if m:
            with state_lock:
                if chat_id in conv_state:
                    conv_state[chat_id]['data']['asia_phone'] = normalized
                    conv_state[chat_id]['data']['asia_pid'] = m.group(1)
                    conv_state[chat_id]['step'] = 'asia_setup_code'
            try: bot.send_message(chat_id, "📨 رمز SMS:")
            except: pass
            return
    try: bot.send_message(chat_id, "❌ فشل.")
    except: pass
    with state_lock: conv_state.pop(chat_id, None)

async def admin_asia_verify(chat_id, code):
    with state_lock:
        state = conv_state.get(chat_id)
    if not state: return
    data = asia_verify(state['data']['asia_pid'], code)
    if data.get('success'):
        normalized = _normalize_asia_phone(state['data']['asia_phone'])
        syyad_conf['asia_phone'] = normalized or state['data']['asia_phone']
        syyad_conf['asia_token'] = data['access_token']
        save_conf()
        try:
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("✅ تأكيد", callback_data="admin_asia_confirm"))
            bot.send_message(chat_id,
                f"✅ رقم المالك: <code>{syyad_conf['asia_phone']}</code>\nاضغط تأكيد:",
                parse_mode='HTML', reply_markup=kb)
        except: pass
    else:
        try: bot.send_message(chat_id, "❌ كود خاطئ.")
        except: pass
    with state_lock: conv_state.pop(chat_id, None)

async def process_asia_phone(chat_id, phone):
    normalized = _normalize_asia_phone(phone)
    if not normalized:
        try: bot.send_message(chat_id, "❌ رقم غير صالح.\nمثال: <code>07701234567</code>", parse_mode='HTML')
        except: pass
        with state_lock: conv_state.pop(chat_id, None); return
    data = asia_login(normalized)
    if data.get('success') and 'nextUrl' in data:
        m = re.search(r'PID=([a-f0-9\-]+)', data['nextUrl'])
        if m:
            pid = m.group(1)
            with state_lock:
                conv_state[chat_id] = {
                    'step': 'asia_code',
                    'data': {'asia_phone': normalized, 'asia_pid': pid}
                }
            try: bot.send_message(chat_id, "📨 أرسل كود SMS:")
            except: pass
            return
    try: bot.send_message(chat_id, "❌ فشل.")
    except: pass
    with state_lock: conv_state.pop(chat_id, None)

async def process_asia_code(chat_id, code):
    with state_lock:
        state = conv_state.get(chat_id)
    if not state or state.get('step') != 'asia_code': return
    pid = state['data'].get('asia_pid')
    phone = state['data'].get('asia_phone')
    data = asia_verify(pid, code)
    if data.get('success'):
        uid = str(chat_id)
        ub = get_bal(uid)
        ub['verified_asia_phone'] = phone
        ub['asia_token'] = data.get('access_token')
        save_users()
        try:
            bot.send_message(chat_id,
                f"✅ <b>تم تأكيد رقمك!</b>\n\n📱 <code>{phone}</code>",
                parse_mode='HTML')
        except: pass
        with state_lock: conv_state.pop(chat_id, None)
    else:
        try: bot.send_message(chat_id, "❌ كود خاطئ. أعد المحاولة:")
        except: pass

async def process_asia_user_amount(chat_id, text):
    uid = str(chat_id)
    ub = get_bal(uid)
    rate = syyad_conf.get('asia_points_per_dollar', 1000)
    max_d = syyad_conf.get('asia_max_dollars', 10)
    min_d = syyad_conf.get('asia_min_dollars', 1)
    try:
        points = int(text.strip())
    except ValueError:
        try: bot.send_message(chat_id, "❌ رقم صحيح.")
        except: pass
        with state_lock: conv_state.pop(chat_id, None); return
    if points < min_d * rate:
        bot.send_message(chat_id, f"❌ الأدنى {min_d*rate}"); 
        with state_lock: conv_state.pop(chat_id, None); return
    if points > max_d * rate:
        bot.send_message(chat_id, f"❌ الأقصى {max_d*rate}")
        with state_lock: conv_state.pop(chat_id, None); return
    if points % rate != 0:
        bot.send_message(chat_id, f"❌ مضاعفات {rate}")
        with state_lock: conv_state.pop(chat_id, None); return
    amount_dollars = points // rate
    user_phone = ub.get('verified_asia_phone')
    user_token = ub.get('asia_token')
    owner_phone = syyad_conf.get('asia_phone')
    if not user_phone or not user_token:
        bot.send_message(chat_id, "❌ أعد الربط.")
        with state_lock: conv_state.pop(chat_id, None); return
    if not owner_phone:
        bot.send_message(chat_id, "⚠️ غير متاح.")
        with state_lock: conv_state.pop(chat_id, None); return
    owner_phone_norm = _normalize_asia_phone(owner_phone) or owner_phone
    data = asia_start_transfer(amount_dollars, owner_phone_norm, user_token)
    print(f"[ASIA START] {uid} {amount_dollars}$ data={data}")
    if not (data.get('success') or 'PID' in data):
        err = str(data.get('message', ''))
        if '403' in err:
            ub['asia_token'] = None
            ub['verified_asia_phone'] = None
            save_users()
            try: bot.send_message(chat_id, "⚠️ انتهت الجلسة. أعد الربط.")
            except: pass
        else:
            try: bot.send_message(chat_id, "❌ تعذر بدء التحويل.")
            except: pass
        with state_lock: conv_state.pop(chat_id, None); return
    pid = data.get('PID')
    if not pid and data.get('nextUrl'):
        m = re.search(r'PID=([a-f0-9\-]+)', data['nextUrl'])
        if m: pid = m.group(1)
    if not pid:
        bot.send_message(chat_id, "❌ لا يمكن.")
        with state_lock: conv_state.pop(chat_id, None); return
    products_data['pending_transfers'][uid] = {
        'amount': amount_dollars, 'points': int(points),
        'user_phone': user_phone, 'owner_phone': owner_phone_norm,
        'transfer_pid': pid,
        'timestamp': datetime.datetime.now().isoformat(),
    }
    save_products()
    with state_lock:
        conv_state[chat_id] = {'step': 'asia_user_code', 'data': {}}
    try:
        bot.send_message(chat_id,
            f"📨 <b>وصل كود SMS</b>\n\n"
            f"📞 <code>{user_phone}</code>\n"
            f"💰 {amount_dollars}$\n"
            f"⭐ {points}\n\nأرسل الكود:",
            parse_mode='HTML')
    except: pass

async def process_asia_user_code(chat_id, code):
    uid = str(chat_id)
    if uid not in products_data['pending_transfers']:
        try: bot.send_message(chat_id, "❌ الطلب غير موجود.")
        except: pass
        with state_lock: conv_state.pop(chat_id, None); return
    transfer = products_data['pending_transfers'][uid]
    ub = get_bal(uid)
    user_token = ub.get('asia_token')
    if not user_token:
        try: bot.send_message(chat_id, "❌ انتهت الجلسة.")
        except: pass
        del products_data['pending_transfers'][uid]
        save_products()
        with state_lock: conv_state.pop(chat_id, None); return
    data = asia_confirm_transfer(transfer['transfer_pid'], code, user_token)
    print(f"[ASIA USER CONFIRM] {uid} → {data}")
    if data.get('expired'):
        ub['asia_token'] = None; ub['verified_asia_phone'] = None
        save_users()
        try: bot.send_message(chat_id, "⚠️ انتهت الجلسة.")
        except: pass
        del products_data['pending_transfers'][uid]
        save_products()
        with state_lock: conv_state.pop(chat_id, None); return
    if data.get('success'):
        points = transfer['points']
        amount = transfer['amount']
        ub['points'] += points
        save_users()
        del products_data['pending_transfers'][uid]
        save_products()
        try:
            run_async(client.send_message(int(OWNER_ID),
                f"💰 <b>وصل رصيد</b>\n\n👤 <code>{uid}</code>\n"
                f"💰 {amount}$\n⭐ {points}", parse_mode='html'))
        except: pass
        try:
            bot.send_message(chat_id,
                f"✅ <b>تم الشحن!</b>\n\n"
                f"⭐ <b>{points}</b> نقطة\n"
                f"💳 رصيدك: <code>{ub['points']}</code>",
                parse_mode='HTML')
        except: pass
        with state_lock: conv_state.pop(chat_id, None)
    else:
        try:
            bot.send_message(chat_id,
                "❌ <b>الرمز غير صحيح</b>\n\n🔄 أعد الإرسال:")
        except: pass


async def process_star_receipt(chat_id, m):
    with state_lock:
        state = conv_state.pop(chat_id, None)
    if not state: return
    phone = state['data']['phone']
    amount = state['data']['amount']
    fid = None
    if m.content_type == 'photo': fid = m.photo[-1].file_id
    elif m.content_type == 'document': fid = m.document.file_id
    else:
        try: bot.send_message(chat_id, "❌ أرسل صورة.")
        except: pass
        with state_lock: conv_state[chat_id] = state
        return
    rid = f"R{int(time.time())}_{chat_id}"
    star_receipts[rid] = {
        'user_id': str(chat_id), 'phone': phone, 'amount': amount,
        'file_id': fid, 'status': 'pending', 'ts': time.time()
    }
    save_receipts()
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✅ تأكيد", callback_data=f"star_approve:{rid}"))
    kb.add(InlineKeyboardButton("❌ رفض", callback_data=f"star_reject:{rid}"))
    caption = (f"💫 <b>دفع بالنجوم</b>\n\n"
               f"👤 <code>{chat_id}</code>\n"
               f"📞 <code>{phone}</code>\n⭐ {amount}")
    try:
        bot.send_photo(int(OWNER_ID), fid, caption=caption,
                       parse_mode='HTML', reply_markup=kb)
    except:
        try: bot.send_message(int(OWNER_ID), caption, parse_mode='HTML', reply_markup=kb)
        except: pass
    try: bot.send_message(chat_id, "✅ استلمنا. بانتظار التحقق.")
    except: pass

# ==========================================================
#              أوامر
# ==========================================================
@bot.message_handler(commands=['addpoints'])
def cmd_addpoints(m):
    if not is_adm(m.chat.id): return
    try:
        _, u_, p = m.text.split()
        get_bal(u_)['points'] += int(p)
        save_users()
        bot.reply_to(m, f"✅ +{p}")
    except: bot.reply_to(m, "/addpoints uid عدد")

@bot.message_handler(commands=['forcepoints'])
def cmd_forcepoints(m):
    if not is_adm(m.chat.id): return
    try:
        parts = m.text.split()
        u_ = parts[1]; pts = int(parts[2])
        get_bal(u_)['points'] += pts
        save_users()
        bot.reply_to(m, f"✅ +{pts} لـ {u_}")
    except: bot.reply_to(m, "/forcepoints uid عدد")

@bot.message_handler(commands=['broadcast'])
def cmd_broadcast(m):
    if not is_owner(m.chat.id): return
    if not m.reply_to_message:
        bot.reply_to(m, "رد على رسالة."); return
    cnt = 0
    for u in list(syyad_users.keys()):
        try:
            bot.copy_message(u, m.chat.id, m.reply_to_message.message_id); cnt += 1
        except: pass
    bot.reply_to(m, f"✅ {cnt}")

# ==========================================================
#              التشغيل
# ==========================================================
def run_poll():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try: bot.remove_webhook()
    except: pass
    time.sleep(2)
    while True:
        try:
            bot.polling(none_stop=True, timeout=90, long_polling_timeout=90)
        except telebot.apihelper.ApiTelegramException as e:
            if "409" in str(e):
                print("[BOT] 409 - نسخة أخرى تعمل، إعادة المحاولة بعد 30s")
                time.sleep(30)
            else:
                print(f"[BOT] {e}")
                time.sleep(5)
        except requests.exceptions.ConnectionError:
            time.sleep(10)
        except requests.exceptions.ReadTimeout:
            time.sleep(5)
        except Exception as e:
            print(f"[poll] {type(e).__name__}: {e}")
            time.sleep(5)

async def main():
    global MAIN_LOOP, client
    MAIN_LOOP = asyncio.get_running_loop()
    load_all()
    _clean_session()
    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    await client.start(bot_token=BOT_TOKEN)
    await run_accs()
    await init_resv()
    print("✅ Telethon started")
    print(f"👑 المالك: {OWNER_ID}")
    print(f"🛠️ الأدمن: {ADMIN2_ID}")
    threading.Thread(target=run_poll, daemon=True).start()
    print("✅ Bot running...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        save_all()