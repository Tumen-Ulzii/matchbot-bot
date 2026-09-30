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

# --- ӨГӨГДЛИЙН САНГИЙН ТОХИРГОО ---

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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("ALTER TABLE users ALTER COLUMN age TYPE VARCHAR(50);")
            cur.execute("ALTER TABLE users ALTER COLUMN gender TYPE VARCHAR(50);")
            cur.execute("ALTER TABLE users ALTER COLUMN age SET DEFAULT 'Тодорхойгүй';")
            cur.execute("ALTER TABLE users ALTER COLUMN gender SET DEFAULT 'Тодорхойгүй';")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS personas (
                    gender_type VARCHAR(20) PRIMARY KEY,
                    persona_id VARCHAR(100)
                );
            """)
            conn.commit()
        conn.close()

init_db()

# --- PERSONA API УДИРДЛАГА ---

def create_persona(name, profile_picture_url):
    if not PAGE_ACCESS_TOKEN or PAGE_ACCESS_TOKEN == "REPLACE_WITH_PAGE_TOKEN":
        return None
    url = f"https://graph.facebook.com/v19.0/me/personas?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "name": name,
        "profile_picture_url": profile_picture_url
    }
    try:
        res = requests.post(url, json=payload, timeout=5)
        if res.status_code == 200:
            return res.json().get("id")
    except Exception as e:
        print(f"Persona үүсгэхэд алдаа гарлаа: {e}")
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

# --- ХЭРЭГЛЭГЧИЙН УДИРДЛАГА БОЛОН СТАТИСТИК ---

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
                "INSERT INTO users (psid, nickname) VALUES (%s, %s) RETURNING *;",
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
        return {
            "total": 0, "today": 0, "chatting": 0, "waiting": 0,
            "male": 0, "female": 0, "unknown_gender": 0,
            "avg_age": "—", "age_16_20": 0, "age_21_25": 0,
            "age_26_30": 0, "age_30_plus": 0, "age_unknown": 0
        }
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM users;")
        total = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM users WHERE DATE(created_at) = CURRENT_DATE;")
        today = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM users WHERE gender = 'Эрэгтэй';")
        male = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM users WHERE gender = 'Эмэгтэй';")
        female = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM users WHERE gender NOT IN ('Эрэгтэй', 'Эмэгтэй');")
        unknown_gender = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM users WHERE partner_id IS NOT NULL;")
        chatting = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM users WHERE is_waiting = TRUE;")
        waiting = cur.fetchone()[0]

        cur.execute("""
            SELECT 
                ROUND(AVG(CASE WHEN age ~ '^[0-9]+$' THEN age::numeric END), 1) as avg_age,
                COUNT(*) FILTER (WHERE age ~ '^[0-9]+$' AND age::int BETWEEN 16 AND 20) as age_16_20,
                COUNT(*) FILTER (WHERE age ~ '^[0-9]+$' AND age::int BETWEEN 21 AND 25) as age_21_25,
                COUNT(*) FILTER (WHERE age ~ '^[0-9]+$' AND age::int BETWEEN 26 AND 30) as age_26_30,
                COUNT(*) FILTER (WHERE age ~ '^[0-9]+$' AND age::int > 30) as age_30_plus,
                COUNT(*) FILTER (WHERE NOT (age ~ '^[0-9]+$')) as age_unknown
            FROM users;
        """)
        age_row = cur.fetchone()
        avg_age = age_row[0] if age_row[0] is not None else "—"
        age_16_20 = age_row[1]
        age_21_25 = age_row[2]
        age_26_30 = age_row[3]
        age_30_plus = age_row[4]
        age_unknown = age_row[5]

    conn.close()
    return {
        "total": total, "today": today, "male": male, "female": female,
        "unknown_gender": unknown_gender, "chatting": chatting, "waiting": waiting,
        "avg_age": avg_age, "age_16_20": age_16_20, "age_21_25": age_21_25,
        "age_26_30": age_26_30, "age_30_plus": age_30_plus, "age_unknown": age_unknown
    }

# --- МЕССЕЖ ИЛГЭЭХ СИСТЕМ ---

def send_message(recipient_id, text, persona_id=None):
    if not PAGE_ACCESS_TOKEN or PAGE_ACCESS_TOKEN == "REPLACE_WITH_PAGE_TOKEN":
        print(f"[TEST / NO TOKEN] To={recipient_id} | Text={text} | Persona={persona_id}")
        return

    url = f"https://graph.facebook.com/v19.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text}
    }
    if persona_id:
        payload["persona_id"] = persona_id

    try:
        res = requests.post(url, json=payload, timeout=5)
        if res.status_code != 200:
            print(f"Facebook API алдаа: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"Facebook API илгээхэд сүлжээний алдаа: {e}")

# --- ROUTES ---

@app.route("/", methods=["GET"])
def home():
    return "MatchChat PostgreSQL & Persona Server is running 24/7! CAMILAAXISMUS", 200

@app.route("/stats", methods=["GET"])
def stats_page():
    st = get_statistics()
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>MatchChat Статистик</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0b132b; color: #fff; padding: 40px 15px; margin: 0; }}
            .container {{ max-width: 520px; margin: auto; background: #1c2541; padding: 25px; border-radius: 16px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }}
            h2 {{ color: #48cae4; text-align: center; margin-top: 0; margin-bottom: 20px; font-size: 22px; }}
            .section-title {{ font-size: 13px; text-transform: uppercase; color: #8d99ae; margin-top: 22px; margin-bottom: 8px; font-weight: bold; letter-spacing: 0.5px; }}
            .stat-box {{ display: flex; justify-content: space-between; padding: 11px 0; border-bottom: 1px solid #3a506b; font-size: 15px; }}
            .stat-val {{ font-weight: bold; color: #4ade80; }}
            .stat-sub {{ color: #a5b4fc; font-weight: 600; }}
            .stat-age {{ color: #fbbf24; font-weight: 600; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>📊 MatchChat Хяналтын Самбар</h2>
            <div class="section-title">Хэрэглэгчийн тоо баримт</div>
            <div class="stat-box"><span>Нийт хэрэглэгч:</span><span class="stat-val">{st['total']} хүн</span></div>
            <div class="stat-box"><span>Өнөөдөр шинээр:</span><span class="stat-val">+{st['today']} хүн</span></div>
            <div class="section-title">Хүйсний бүтэц</div>
            <div class="stat-box"><span>Эрэгтэй:</span><span class="stat-sub">{st['male']} хүн</span></div>
            <div class="stat-box"><span>Эмэгтэй:</span><span class="stat-sub">{st['female']} хүн</span></div>
            <div class="stat-box"><span>Тохируулаагүй:</span><span class="stat-sub">{st['unknown_gender']} хүн</span></div>
            <div class="section-title">Насны ангилал & Дундаж</div>
            <div class="stat-box"><span>Насны дундаж:</span><span class="stat-val">{st['avg_age']} нас</span></div>
            <div class="stat-box"><span>16 - 20 нас:</span><span class="stat-age">{st['age_16_20']} хүн</span></div>
            <div class="stat-box"><span>21 - 25 нас:</span><span class="stat-age">{st['age_21_25']} хүн</span></div>
            <div class="stat-box"><span>26 - 30 нас:</span><span class="stat-age">{st['age_26_30']} хүн</span></div>
            <div class="stat-box"><span>31+ нас:</span><span class="stat-age">{st['age_30_plus']} хүн</span></div>
            <div class="stat-box"><span>Насаа оруулаагүй:</span><span class="stat-sub">{st['age_unknown']} хүн</span></div>
            <div class="section-title">Бодит цагийн идэвх</div>
            <div class="stat-box"><span>Одоо чаталж буй:</span><span class="stat-val">{st['chatting']} хүн ({st['chatting'] // 2} хос)</span></div>
            <div class="stat-box"><span>Хайж буй (хүлээгдэж буй):</span><span class="stat-val">{st['waiting']} хүн</span></div>
        </div>
    </body>
    </html>
    """, 200

@app.route("/privacy", methods=["GET"])
def privacy_policy():
    html_content = """
    <!DOCTYPE html>
    <html lang="mn">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>MatchChat - Нууцлалын бодлого ба Үйлчилгээний нөхцөл</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; padding: 20px; max-width: 800px; margin: auto; color: #333; }
            h1 { color: #0d1b2a; border-bottom: 2px solid #e0e0e0; padding-bottom: 10px; }
            h2 { color: #1b263b; margin-top: 25px; }
            p, li { font-size: 15px; }
            .badge { background: #e0e1dd; padding: 4px 8px; border-radius: 4px; font-size: 12px; }
        </style>
    </head>
    <body>
        <h1>MatchChat - Үйлчилгээний нөхцөл ба Нууцлалын бодлого</h1>
        <p><span class="badge">Сүүлд шинэчлэгдсэн: 2026 он</span></p>
        <h2>1. Үйлчилгээний зорилго</h2>
        <p>MatchChat нь Facebook Messenger ашиглан хэрэглэгчдийг бодит цаг хугацаанд, нэргүйгээр хооронд нь холбож чатлуулах зорилготой платформ юм.</p>
        <h2>2. Мэдээллийн нууцлал ба цуглуулалт</h2>
        <ul>
            <li>Бид хэрэглэгчийн Facebook профайлын нэр, зураг, хувийн мэдээллийг ярилцагч талд ХЭЗЭЭ Ч харуулахгүй ба бүрэн нууцална.</li>
            <li>Чатлаж буй хоёр талын холболтыг зөвхөн хэрэглэгчийн түр үүссэн Page-Scoped ID (PSID) ашиглан хийнэ.</li>
            <li>Үйлчилгээний аюулгүй байдал, спам болон зүй бус үйлдлээс сэргийлэх зорилгоор чатын түүхийг дотоод системд түр хугацаанд хадгалж болно.</li>
        </ul>
        <h2>3. Хэрэглэгчийн баримтлах дүрэм (Community Guidelines)</h2>
        <p>MatchChat-ийг ашиглахдаа дараах үйлдлүүдийг хатуу хориглоно:</p>
        <ul>
            <li>Бусдыг доромжлох, заналхийлэх, ялгаварлан гадуурхсан үг хэллэг ашиглах;</li>
            <li>Садар самуун, хүчирхийлэл сурталчилсан агуулгатай бичвэр, линк илгээх;</li>
            <li>Бусдаас мөнгө, дансны мэдээлэл, нууц үг нэхэх зэрэг залилангийн шинж чанартай үйлдэл гаргах;</li>
            <li>Зөвшөөрөлгүй зар сурталчилгаа (spam) тасралтгүй илгээх.</li>
        </ul>
        <h2>4. Дүрмийн хариуцлага</h2>
        <p>Дээрх дүрмийг зөрчсөн хэрэглэгчийг урьдчилан сануулахгүйгээр ботоос бүрмөсөн хасах (хязгаарлах) эрхийг администратор эдэлнэ.</p>
        <h2>5. Холбоо барих</h2>
        <p>Хэрэв танд ямар нэг гомдол, санал байвал бидэнтэй холбогдоно уу:</p>
        <ul>
            <li><strong>Хөгжүүлэгч:</strong> CAMILAAX Match Chat Team</li>
            <li><strong>И-мэйл:</strong> camilasilvatg0219@gmail.com</li>
            <li><strong>Утас:</strong> +976-60608063</li>
            <li><strong>Facebook хуудас:</strong> Match Chat</li>
        </ul>
    </body>
    </html>
    """
    return html_content, 200

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
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

                # --- 1. GET STARTED ТОХИОЛДОЛ (POSTBACK) ---
                if "postback" in messaging_event:
                    payload = messaging_event.get("postback", {}).get("payload")
                    if payload == "GET_STARTED":
                        welcome_msg = (
                            f"👋 MatchChat-д тавтай морил!\n\n"
                            f"Таны нэр: {user['nickname']}\n"
                            f"Хүйс: {user['gender']}\n"
                            f"Нас: {user['age']}\n\n"
                            f"💡 Мэдээллээ өөрчлөх бол:\n"
                            f"/нэр [шинэ нэр]\n"
                            f"/хүйс [эр эсвэл эм]\n"
                            f"/нас [тоо]\n\n"
                            f"🚀 Хүнтэй холбогдох бол 'Холбогдох' гэж бичээрэй!"
                        )
                        send_message(sender_id, welcome_msg)
                    continue

                # --- 2. МЕССЕЖ ТОХИОЛДОЛ ---
                message = messaging_event.get("message", {})
                if not message:
                    continue

                if "attachments" in message:
                    send_message(sender_id, "⚠️ Аюулгүй байдлын үүднээс зөвхөн бичвэр (текст) илгээхийг зөвшөөрнө.")
                    continue

                text = message.get("text", "").strip()
                if not text:
                    continue

                clean_text = text.lower()

                # АДМИН СТАТИСТИК КОМАНД
                if text == ADMIN_SECRET:
                    st = get_statistics()
                    msg = (
                        f"📊 Системийн дэлгэрэнгүй тоо:\n\n"
                        f"👥 Нийт хэрэглэгч: {st['total']}\n"
                        f"✨ Өнөөдөр шинээр: +{st['today']}\n"
                        f"👨 Эрэгтэй: {st['male']} | 👩 Эмэгтэй: {st['female']}\n\n"
                        f"🎂 Насны бүтэц (Дундаж: {st['avg_age']}):\n"
                        f"• 16-20: {st['age_16_20']} хүн\n"
                        f"• 21-25: {st['age_21_25']} хүн\n"
                        f"• 26-30: {st['age_26_30']} хүн\n"
                        f"• 31+: {st['age_30_plus']} хүн\n\n"
                        f"💬 Чаталж буй: {st['chatting']} ({st['chatting']//2} хос)\n"
                        f"⏳ Хүлээж буй: {st['waiting']}"
                    )
                    send_message(sender_id, msg)
                    continue

                # ТОХИРГООНЫ КОМАНДУУД
                if clean_text.startswith("/нэр "):
                    new_name = text[5:].strip()
                    if 0 < len(new_name) <= 20:
                        update_user_field(sender_id, "nickname", new_name)
                        send_message(sender_id, f"✅ Таны нэрийг '{new_name}' болгож хадгаллаа.")
                    else:
                        send_message(sender_id, "Нэр 1-20 тэмдэгтийн хооронд байх ёстой.")
                    continue

                elif clean_text.startswith("/хүйс "):
                    val = clean_text[6:].strip()
                    if val in ["эр", "эрэгтэй", "man", "male"]:
                        gender_str = "Эрэгтэй"
                    elif val in ["эм", "эмэгтэй", "woman", "female"]:
                        gender_str = "Эмэгтэй"
                    else:
                        gender_str = "Тодорхойгүй"
                    update_user_field(sender_id, "gender", gender_str)
                    send_message(sender_id, f"✅ Таны хүйсийг '{gender_str}' болгож тохирууллаа.")
                    continue

                elif clean_text.startswith("/нас "):
                    age_val = text[5:].strip()
                    if age_val.isdigit() and 10 <= int(age_val) <= 90:
                        update_user_field(sender_id, "age", age_val)
                        send_message(sender_id, f"✅ Таны насыг '{age_val}' болгож тохирууллаа.")
                    else:
                        send_message(sender_id, "Насаа зөв тоогоор оруулна уу (жишээ: /нас 21).")
                    continue

                elif clean_text == "/профайл":
                    u = get_or_create_user(sender_id)
                    profile_info = (
                        f"📋 Таны профайл:\n"
                        f"• Нэр: {u['nickname']}\n"
                        f"• Хүйс: {u['gender']}\n"
                        f"• Нас: {u['age']}\n\n"
                        f"Өөрчлөх бол:\n/нэр [шинэ_нэр]\n/хүйс [эр/эм]\n/нас [тоо]"
                    )
                    send_message(sender_id, profile_info)
                    continue

                # ЧАТААС ГАРАХ
                elif clean_text in ["гарах", "stop", "exit", "гар"]:
                    u = get_or_create_user(sender_id)
                    if u and u.get("partner_id"):
                        partner_id = u["partner_id"]
                        update_user_field(sender_id, "partner_id", None)
                        update_user_field(partner_id, "partner_id", None)
                        send_message(sender_id, "❌ Та чатаас гарлаа. Шинэ хүнтэй холбогдох бол 'Холбогдох' гэж бичнэ үү.")
                        send_message(partner_id, "❌ Ярилцагч тань чатаас гарлаа. Шинэ хүнтэй холбогдох бол 'Холбогдох' гэж бичнэ үү.")
                    elif u and u.get("is_waiting"):
                        update_user_field(sender_id, "is_waiting", False)
                        send_message(sender_id, "Хайлтыг зогсоолоо. 'Холбогдох' гэж бичээд дахин эхлүүлэх боломжтой.")
                    else:
                        send_message(sender_id, "Та одоогоор хэнтэй ч холбогдоогүй байна.")

                # ХОЛБОГДОХ
                elif clean_text in ["холбогдох", "хайх", "start", "эхлэх"]:
                    u = get_or_create_user(sender_id)
                    if u and u.get("partner_id"):
                        send_message(sender_id, "Та хэдийн нэг хүнтэй холбогдсон байна. Чатаас гарах бол 'Гарах' гэж бичнэ үү.")
                    elif u and u.get("is_waiting"):
                        send_message(sender_id, "Танд тохирох хүнийг хайж байна... Түр хүлээнэ үү.")
                    else:
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

                            p_info = f"🎉 Холбогдлоо!\n👤 Ярилцагч: {waiting_partner['nickname']} ({waiting_partner['gender']}, {waiting_partner['age']} нас)\n(Гарах бол 'Гарах' гэж бичнэ)"
                            s_info = f"🎉 Холбогдлоо!\n👤 Ярилцагч: {u['nickname']} ({u['gender']}, {u['age']} нас)\n(Гарах бол 'Гарах' гэж бичнэ)"

                            send_message(sender_id, p_info)
                            send_message(partner_id, s_info)
                        else:
                            update_user_field(sender_id, "is_waiting", True)
                            send_message(sender_id, "🔍 Танд тохирох хүнийг хайж байна... Түр хүлээнэ үү.")

                # ЧАТЛАХ (PERSONA АШИГЛАН ДАМЖУУЛАХ)
                else:
                    u = get_or_create_user(sender_id)
                    if u and u.get("partner_id"):
                        p_id = get_persona_id(u["gender"])
                        formatted_text = f"[{u['nickname']}]: {text}"
                        send_message(u["partner_id"], formatted_text, persona_id=p_id)
                    else:
                        send_message(sender_id, "Та одоогоор хэнтэй ч холбогдоогүй байна. 'Холбогдох' гэж бичнэ үү.\nПрофайлаа харах бол '/профайл' гэж бичээрэй.")
    except Exception as err:
        print(f"Webhook боловсруулахад алдаа: {err}")

    return "EVENT_RECEIVED", 200

if __name__ == "__main__":
    app.run(port=5000)
