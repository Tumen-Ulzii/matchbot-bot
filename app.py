import os
from flask import Flask, request
import requests
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN", "REPLACE_WITH_PAGE_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "my_secret_matchchat_token_123")
DATABASE_URL = os.environ.get("DATABASE_URL")

ADMIN_SECRET = "/admin stat"

AVATAR_MALE = "https://cdn-icons-png.flaticon.com/512/4140/4140048.png"
AVATAR_FEMALE = "https://cdn-icons-png.flaticon.com/512/4140/4140047.png"
AVATAR_UNKNOWN = "https://cdn-icons-png.flaticon.com/512/149/149071.png"

# --- ӨГӨГДЛИЙН САН ---

def get_db_connection():
    if not DATABASE_URL:
        return None
    conn_url = DATABASE_URL
    if conn_url.startswith("postgres://"):
        conn_url = conn_url.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(conn_url)

def init_db():
    conn = get_db_connection()
    if conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    psid VARCHAR(100) PRIMARY KEY,
                    nickname VARCHAR(100),
                    gender VARCHAR(50) DEFAULT 'Тодорхойгүй',
                    age VARCHAR(50) DEFAULT 'Тодорхойгүй',
                    partner_id VARCHAR(100),
                    is_waiting BOOLEAN DEFAULT FALSE,
                    step VARCHAR(50) DEFAULT 'NONE',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS step VARCHAR(50) DEFAULT 'NONE';")
            cur.execute("ALTER TABLE users ALTER COLUMN age TYPE VARCHAR(50);")
            cur.execute("ALTER TABLE users ALTER COLUMN gender TYPE VARCHAR(50);")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS personas (
                    gender_type VARCHAR(20) PRIMARY KEY,
                    persona_id VARCHAR(100)
                );
            """)
            conn.commit()
        conn.close()

init_db()

# --- PERSONA API ---

def create_persona(name, profile_picture_url):
    if not PAGE_ACCESS_TOKEN or PAGE_ACCESS_TOKEN == "REPLACE_WITH_PAGE_TOKEN":
        return None
    url = f"https://graph.facebook.com/v19.0/me/personas?access_token={PAGE_ACCESS_TOKEN}"
    payload = {"name": name, "profile_picture_url": profile_picture_url}
    try:
        res = requests.post(url, json=payload, timeout=5)
        if res.status_code == 200:
            return res.json().get("id")
    except Exception as e:
        print(f"Persona алдаа: {e}")
    return None

def get_persona_id(gender):
    conn = get_db_connection()
    if not conn:
        return None
    g_key = "unknown"
    p_name = "Нууц ярилцагч"
    p_pic = AVATAR_UNKNOWN

    if gender == "Эрэгтэй":
        g_key = "male"
        p_name = "Залуу"
        p_pic = AVATAR_MALE
    elif gender == "Эмэгтэй":
        g_key = "female"
        p_name = "Бүсгүй"
        p_pic = AVATAR_FEMALE

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT persona_id FROM personas WHERE gender_type = %s;", (g_key,))
        row = cur.fetchone()
        if row and row["persona_id"]:
            conn.close()
            return row["persona_id"]

        new_id = create_persona(p_name, p_pic)
        if new_id:
            cur.execute(
                "INSERT INTO personas (gender_type, persona_id) VALUES (%s, %s) ON CONFLICT (gender_type) DO UPDATE SET persona_id = %s;",
                (g_key, new_id, new_id)
            )
            conn.commit()
            conn.close()
            return new_id
    conn.close()
    return None

# --- ХЭРЭГЛЭГЧИЙН УДИРДЛАГА ---

def get_or_create_user(psid):
    conn = get_db_connection()
    if not conn:
        return None
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM users WHERE psid = %s;", (psid,))
        user = cur.fetchone()
        if not user:
            short_id = psid[-4:]
            default_nick = f"Хэрэглэгч_{short_id}"
            cur.execute(
                "INSERT INTO users (psid, nickname, step) VALUES (%s, %s, 'NONE') RETURNING *;",
                (psid, default_nick)
            )
            user = cur.fetchone()
            conn.commit()
    conn.close()
    return user

def update_user_field(psid, field, value):
    conn = get_db_connection()
    if not conn:
        return
    with conn.cursor() as cur:
        cur.execute(f"UPDATE users SET {field} = %s WHERE psid = %s;", (value, psid))
        conn.commit()
    conn.close()

def get_statistics():
    conn = get_db_connection()
    if not conn:
        return {"total": 0, "today": 0, "chatting": 0, "waiting": 0}
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM users;")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM users WHERE DATE(created_at) = CURRENT_DATE;")
        today = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM users WHERE partner_id IS NOT NULL;")
        chatting = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM users WHERE is_waiting = TRUE;")
        waiting = cur.fetchone()[0]
    conn.close()
    return {"total": total, "today": today, "chatting": chatting, "waiting": waiting}

# --- МЕССЕЖ БОЛОН ТОВЧЛУУР ИЛГЭЭХ ---

def send_message(recipient_id, text, quick_replies=None, persona_id=None):
    if not PAGE_ACCESS_TOKEN or PAGE_ACCESS_TOKEN == "REPLACE_WITH_PAGE_TOKEN":
        return
    url = f"https://graph.facebook.com/v19.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text}
    }
    if quick_replies:
        payload["message"]["quick_replies"] = quick_replies
    if persona_id:
        payload["persona_id"] = persona_id

    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"API Error: {e}")

def ask_gender(psid):
    update_user_field(psid, "step", "ASK_GENDER")
    qr = [
        {"content_type": "text", "title": "👨 Эрэгтэй", "payload": "GENDER_MALE"},
        {"content_type": "text", "title": "👩 Эмэгтэй", "payload": "GENDER_FEMALE"}
    ]
    send_message(psid, "👋 MatchChat-д тавтай морил!\n\nЭхлээд өөрийн хүйсээ сонгоно уу:", quick_replies=qr)

def ask_age(psid):
    update_user_field(psid, "step", "ASK_AGE")
    qr = [
        {"content_type": "text", "title": "16-20", "payload": "AGE_16_20"},
        {"content_type": "text", "title": "21-25", "payload": "AGE_21_25"},
        {"content_type": "text", "title": "26-30", "payload": "AGE_26_30"},
        {"content_type": "text", "title": "31+", "payload": "AGE_30_PLUS"}
    ]
    send_message(psid, "Одоо насны ангиллаа сонгоно уу:", quick_replies=qr)

def ask_nickname(psid):
    update_user_field(psid, "step", "ASK_NICKNAME")
    send_message(psid, "Одоо чатад ашиглах нэрээ (хоч нэр) бичиж илгээнэ үү:")

def show_main_menu(psid, user):
    update_user_field(psid, "step", "COMPLETED")
    qr = [
        {"content_type": "text", "title": "🚀 Холбогдох", "payload": "CMD_START"},
        {"content_type": "text", "title": "📋 Профайл", "payload": "CMD_PROFILE"}
    ]
    text = (
        f"🎉 Тохиргоо амжилттай дууслаа!\n\n"
        f"• Нэр: {user['nickname']}\n"
        f"• Хүйс: {user['gender']}\n"
        f"• Нас: {user['age']}\n\n"
        f"Хүнтэй холбогдохын тулд доорх 'Холбогдох' товчийг дарна уу."
    )
    send_message(psid, text, quick_replies=qr)

# Функц: Холболт эхлүүлэх
def handle_start_matching(sender_id):
    u = get_or_create_user(sender_id)
    if u and u.get("partner_id"):
        send_message(sender_id, "Та хэдийн нэг хүнтэй холбогдсон байна. Чатаас гарах бол цэснээс 'Чатаас гарах'-ыг сонгоно уу.")
        return
    if u and u.get("is_waiting"):
        send_message(sender_id, "🔍 Танд тохирох хүнийг хайж байна... Түр хүлээнэ үү.")
        return

    conn = get_db_connection()
    waiting_partner = None
    if conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE is_waiting = TRUE AND psid != %s LIMIT 1;", (sender_id,))
            waiting_partner = cur.fetchone()
        conn.close()

    if waiting_partner:
        partner_id = waiting_partner["psid"]
        update_user_field(sender_id, "partner_id", partner_id)
        update_user_field(partner_id, "partner_id", sender_id)
        update_user_field(partner_id, "is_waiting", False)

        p_info = f"🎉 Холбогдлоо!\n👤 Ярилцагч: {waiting_partner['nickname']} ({waiting_partner['gender']}, {waiting_partner['age']})"
        s_info = f"🎉 Холбогдлоо!\n👤 Ярилцагч: {u['nickname']} ({u['gender']}, {u['age']})"

        send_message(sender_id, p_info)
        send_message(partner_id, s_info)
    else:
        update_user_field(sender_id, "is_waiting", True)
        send_message(sender_id, "🔍 Хайж байна... Хүн олдмогц шууд холбоно.")

# Функц: Чатаас гарах
def handle_exit_chat(sender_id):
    u = get_or_create_user(sender_id)
    qr = [{"content_type": "text", "title": "🚀 Холбогдох", "payload": "CMD_START"}]
    if u and u.get("partner_id"):
        partner_id = u["partner_id"]
        update_user_field(sender_id, "partner_id", None)
        update_user_field(partner_id, "partner_id", None)
        send_message(sender_id, "❌ Та чатаас гарлаа.", quick_replies=qr)
        send_message(partner_id, "❌ Ярилцагч тань чатаас гарлаа.", quick_replies=qr)
    elif u and u.get("is_waiting"):
        update_user_field(sender_id, "is_waiting", False)
        send_message(sender_id, "Хайлтыг зогсоолоо.", quick_replies=qr)
    else:
        send_message(sender_id, "Та одоогоор хэнтэй ч холбогдоогүй байна.", quick_replies=qr)

# Функц: Профайл харуулах
def handle_show_profile(sender_id):
    u = get_or_create_user(sender_id)
    qr = [
        {"content_type": "text", "title": "🚀 Холбогдох", "payload": "CMD_START"},
        {"content_type": "text", "title": "⚙️ Дахин тохируулах", "payload": "GET_STARTED"}
    ]
    profile_info = f"📋 Профайл:\n• Нэр: {u['nickname']}\n• Хүйс: {u['gender']}\n• Нас: {u['age']}"
    send_message(sender_id, profile_info, quick_replies=qr)

# --- ROUTES ---

@app.route("/", methods=["GET"])
def home():
    return "MatchChat Server is running 24/7!", 200

@app.route("/privacy", methods=["GET"])
def privacy_policy():
    return "<h1>MatchChat - Нууцлалын бодлого</h1><p>Хэрэглэгчийн мэдээлэл бүрэн нууцлагдана.</p>", 200

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge"), 200
    return "Verification failed", 403

@app.route("/webhook", methods=["POST"])
def handle_messages():
    try:
        data = request.get_json(silent=True, force=True)
        if not data or data.get("object") != "page":
            return "EVENT_RECEIVED", 200

        for entry in data.get("entry", []):
            for messaging_event in entry.get("messaging", []):
                sender_id = messaging_event.get("sender", {}).get("id")
                if not sender_id:
                    continue

                user = get_or_create_user(sender_id)

                # --- 1. PERSISTENT MENU БОЛОН POSTBACK ХҮЛЭЭН АВАХ ---
                if "postback" in messaging_event:
                    payload = messaging_event.get("postback", {}).get("payload")
                    if payload == "GET_STARTED":
                        ask_gender(sender_id)
                    elif payload == "CMD_START":
                        handle_start_matching(sender_id)
                    elif payload == "CMD_EXIT":
                        handle_exit_chat(sender_id)
                    elif payload == "CMD_PROFILE":
                        handle_show_profile(sender_id)
                    continue

                # --- 2. МЕССЕЖ / QUICK REPLY ХҮЛЭЭН АВАХ ---
                message = messaging_event.get("message", {})
                if not message:
                    continue

                if "attachments" in message:
                    send_message(sender_id, "⚠️ Аюулгүй байдлын үүднээс зөвхөн бичвэр илгээнэ үү.")
                    continue

                text = message.get("text", "").strip()
                payload = message.get("quick_reply", {}).get("payload", "")
                clean_text = text.lower()

                if text == ADMIN_SECRET:
                    st = get_statistics()
                    msg = f"Нийт: {st['total']} | Өнөөдөр: {st['today']} | Чаталж буй: {st['chatting']} | Хүлээж буй: {st['waiting']}"
                    send_message(sender_id, msg)
                    continue

                # Түргэн товчлуурууд / Цэс
                if payload == "CMD_START" or clean_text in ["холбогдох", "хайх", "start", "эхлэх"]:
                    handle_start_matching(sender_id)
                    continue

                if payload == "CMD_EXIT" or clean_text in ["гарах", "stop", "exit", "гар"]:
                    handle_exit_chat(sender_id)
                    continue

                if payload == "CMD_PROFILE" or clean_text == "/профайл":
                    handle_show_profile(sender_id)
                    continue

                # Хүйс сонгох
                if payload in ["GENDER_MALE", "GENDER_FEMALE"] or user.get("step") == "ASK_GENDER":
                    gender = "Эрэгтэй" if payload == "GENDER_MALE" or "эр" in clean_text else "Эмэгтэй"
                    update_user_field(sender_id, "gender", gender)
                    ask_age(sender_id)
                    continue

                # Нас сонгох
                if payload in ["AGE_16_20", "AGE_21_25", "AGE_26_30", "AGE_30_PLUS"] or user.get("step") == "ASK_AGE":
                    age_map = {
                        "AGE_16_20": "16-20",
                        "AGE_21_25": "21-25",
                        "AGE_26_30": "26-30",
                        "AGE_30_PLUS": "31+"
                    }
                    selected_age = age_map.get(payload, text)
                    update_user_field(sender_id, "age", selected_age)
                    ask_nickname(sender_id)
                    continue

                # Нэр оруулах
                if user.get("step") == "ASK_NICKNAME":
                    update_user_field(sender_id, "nickname", text)
                    updated_user = get_or_create_user(sender_id)
                    show_main_menu(sender_id, updated_user)
                    continue

                # Чатлах (дамжуулах)
                u = get_or_create_user(sender_id)
                if u and u.get("partner_id"):
                    p_id = get_persona_id(u["gender"])
                    formatted_text = f"[{u['nickname']}]: {text}"
                    send_message(u["partner_id"], formatted_text, persona_id=p_id)
                else:
                    qr = [{"content_type": "text", "title": "🚀 Холбогдох", "payload": "CMD_START"}]
                    send_message(sender_id, "Та одоогоор хэнтэй ч холбогдоогүй байна. 'Холбогдох' товчийг дарж хайна уу.", quick_replies=qr)

    except Exception as err:
        print(f"Webhook алдаа: {err}")

    return "EVENT_RECEIVED", 200

if __name__ == "__main__":
    app.run(port=5000)
