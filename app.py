import os
from flask import Flask, request, jsonify
import requests
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

# Render Environment Variables-аас тохиргоог авна
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN", "REPLACE_WITH_PAGE_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "my_secret_matchchat_token_123")
DATABASE_URL = os.environ.get("DATABASE_URL")

ADMIN_SECRET = "/admin stat"

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
            # Хэрэглэгчдийн хүснэгт үүсгэх
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
            
            # Баганын тэлэлт болон шалгалтууд
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS step VARCHAR(50) DEFAULT 'NONE';")
            cur.execute("ALTER TABLE users ALTER COLUMN age TYPE VARCHAR(50);")
            cur.execute("ALTER TABLE users ALTER COLUMN gender TYPE VARCHAR(50);")
            cur.execute("ALTER TABLE users ALTER COLUMN age SET DEFAULT 'Тодорхойгүй';")
            cur.execute("ALTER TABLE users ALTER COLUMN gender SET DEFAULT 'Тодорхойгүй';")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;")
            conn.commit()
        conn.close()

init_db()

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

# --- МЕССЕЖ ИЛГЭЭХ ҮНДСЭН СИСТЕМ ---

def send_message(recipient_id, text, quick_replies=None):
    if not PAGE_ACCESS_TOKEN or PAGE_ACCESS_TOKEN == "REPLACE_WITH_PAGE_TOKEN":
        print(f"[TEST / NO TOKEN] To={recipient_id} | Text={text}")
        return

    url = f"https://graph.facebook.com/v19.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text}
    }
    if quick_replies:
        payload["message"]["quick_replies"] = quick_replies
        
    try:
        res = requests.post(url, json=payload, timeout=5)
        if res.status_code != 200:
            print(f"Facebook API алдаа: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"Facebook API сүлжээний алдаа: {e}")

# Алхамт бүртгэлийн Quick Replies
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
    send_message(psid, "Баярлалаа! Одоо насны ангиллаа сонгоно уу:", quick_replies=qr)

def ask_nickname(psid):
    update_user_field(psid, "step", "ASK_NICKNAME")
    send_message(psid, "Одоо чатад ашиглах нэрээ (хоч нэр) чөлөөтэй бичиж илгээнэ үү:")

def show_main_menu(psid, user):
    update_user_field(psid, "step", "COMPLETED")
    qr = [
        {"content_type": "text", "title": "🚀 Холбогдох", "payload": "CMD_START"},
        {"content_type": "text", "title": "📋 Профайл", "payload": "CMD_PROFILE"}
    ]
    user_id = str(user['psid'])[-4:]
    text = (
        f"🎉 Тохиргоо амжилттай дууслаа!\n\n"
        f"• Хэрэглэгчийн ID: #{user_id}\n"
        f"• Нэр: {user['nickname']}\n"
        f"• Хүйс: {user['gender']}\n"
        f"• Нас: {user['age']}\n\n"
        f"Хүнтэй холбогдохын тулд доорх '🚀 Холбогдох' товчийг дарна уу."
    )
    send_message(psid, text, quick_replies=qr)

# Гарахын өмнө лавлах баталгаажуулалт
def ask_exit_confirmation(sender_id):
    u = get_or_create_user(sender_id)
    if not u.get("partner_id") and not u.get("is_waiting"):
        qr = [{"content_type": "text", "title": "🚀 Холбогдох", "payload": "CMD_START"}]
        send_message(sender_id, "Та одоогоор хэнтэй ч холбогдоогүй байна.", quick_replies=qr)
        return

    update_user_field(sender_id, "step", "CONFIRM_EXIT")
    qr = [
        {"content_type": "text", "title": "✅ Тийм, гарах", "payload": "EXIT_CONFIRMED_YES"},
        {"content_type": "text", "title": "❌ Үгүй, үргэлжлүүлэх", "payload": "EXIT_CONFIRMED_NO"}
    ]
    send_message(sender_id, "⚠️ Та одоогийн яриаг дуусгаж чатнаас гарахдаа итгэлтэй байна уу?", quick_replies=qr)

# Холболт эхлүүлэх
def handle_start_matching(sender_id):
    u = get_or_create_user(sender_id)
    if u and u.get("partner_id"):
        send_message(sender_id, "Та хэдийн нэг хүнтэй холбогдсон байна. Чатаас гарах бол 'Гарах' гэж бичнэ үү.")
        return
    if u and u.get("is_waiting"):
        send_message(sender_id, "🔍 Танд тохирох хүнийг хайж байна... Түр хүлээнэ үү.")
        return

    conn = get_db_connection()
    waiting_partner = None
    if conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE is_waiting = TRUE AND psid != %s LIMIT 1 FOR UPDATE;", (sender_id,))
            waiting_partner = cur.fetchone()
            if waiting_partner:
                partner_id = waiting_partner["psid"]
                cur.execute("UPDATE users SET partner_id = %s, is_waiting = FALSE, step = 'COMPLETED' WHERE psid = %s;", (partner_id, sender_id))
                cur.execute("UPDATE users SET partner_id = %s, is_waiting = FALSE, step = 'COMPLETED' WHERE psid = %s;", (sender_id, partner_id))
                conn.commit()
            else:
                cur.execute("UPDATE users SET is_waiting = TRUE, partner_id = NULL WHERE psid = %s;", (sender_id,))
                conn.commit()
        conn.close()

    if waiting_partner:
        partner_id = waiting_partner["psid"]
        u_id = str(u['psid'])[-4:]
        w_id = str(waiting_partner['psid'])[-4:]

        p_info = (
            f"🎉 Холбогдлоо!\n"
            f"👤 Ярилцагчийн мэдээлэл:\n"
            f"• ID: #{w_id}\n"
            f"• Нэр: {waiting_partner['nickname']}\n"
            f"• Хүйс: {waiting_partner['gender']}\n"
            f"• Нас: {waiting_partner['age']}\n\n"
            f"(Чатаас гарах бол цэснээс эсвэл 'Гарах' гэж бичнэ үү)"
        )
        s_info = (
            f"🎉 Холбогдлоо!\n"
            f"👤 Ярилцагчийн мэдээлэл:\n"
            f"• ID: #{u_id}\n"
            f"• Нэр: {u['nickname']}\n"
            f"• Хүйс: {u['gender']}\n"
            f"• Нас: {u['age']}\n\n"
            f"(Чатаас гарах бол цэснээс эсвэл 'Гарах' гэж бичнэ үү)"
        )

        send_message(sender_id, p_info)
        send_message(partner_id, s_info)
    else:
        send_message(sender_id, "🔍 Хайж байна... Хүн олдмогц шууд холбоно.")

# Чатаас бодитоор гарах
def handle_exit_chat(sender_id):
    u = get_or_create_user(sender_id)
    update_user_field(sender_id, "step", "COMPLETED")
    qr = [{"content_type": "text", "title": "🚀 Холбогдох", "payload": "CMD_START"}]

    if u and u.get("partner_id"):
        partner_id = u["partner_id"]
        update_user_field(sender_id, "partner_id", None)
        update_user_field(partner_id, "partner_id", None)
        update_user_field(partner_id, "step", "COMPLETED")
        send_message(sender_id, "❌ Та чатнаас гарлаа.", quick_replies=qr)
        send_message(partner_id, "❌ Ярилцагч тань чатнаас гарлаа.", quick_replies=qr)
    elif u and u.get("is_waiting"):
        update_user_field(sender_id, "is_waiting", False)
        send_message(sender_id, "Хайлтыг зогсоолоо.", quick_replies=qr)
    else:
        send_message(sender_id, "Та одоогоор хэнтэй ч холбогдоогүй байна.", quick_replies=qr)

# Профайл харуулах
def handle_show_profile(sender_id):
    u = get_or_create_user(sender_id)
    user_id = str(u['psid'])[-4:]
    qr = [
        {"content_type": "text", "title": "🚀 Холбогдох", "payload": "CMD_START"},
        {"content_type": "text", "title": "⚙️ Дахин тохируулах", "payload": "RESET_PROFILE"}
    ]
    profile_info = (
        f"📋 Таны профайл:\n"
        f"• ID: #{user_id}\n"
        f"• Нэр: {u['nickname']}\n"
        f"• Хүйс: {u['gender']}\n"
        f"• Нас: {u['age']}"
    )
    send_message(sender_id, profile_info, quick_replies=qr)

# --- ROUTES ---

@app.route("/", methods=["GET"])
def home():
    return "MatchChat Server is running 24/7! CAMILAAXISMUS", 200

# ЦЭС БОЛОН GET STARTED-ИЙГ БАТАЛГААТАЙ СУУЛГАХ ТУСГАЙ ХУУДАС
@app.route("/setup-menu", methods=["GET"])
def manual_setup_menu():
    if not PAGE_ACCESS_TOKEN or PAGE_ACCESS_TOKEN == "REPLACE_WITH_PAGE_TOKEN":
        return "PAGE_ACCESS_TOKEN тохируулаагүй байна!", 400

    url = f"https://graph.facebook.com/v19.0/me/messenger_profile?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "get_started": {"payload": "GET_STARTED"},
        "greeting": [
            {
                "locale": "default",
                "text": "MatchChat-д тавтай морилно уу! Танихгүй хүнтэй холбогдон нэргүйгээр чатлаарай."
            }
        ],
        "persistent_menu": [
            {
                "locale": "default",
                "composer_input_disabled": False,
                "call_to_actions": [
                    {
                        "type": "postback",
                        "title": "🚀 Холбогдох",
                        "payload": "CMD_START"
                    },
                    {
                        "type": "postback",
                        "title": "❌ Чатаас гарах",
                        "payload": "CMD_CONFIRM_EXIT"
                    },
                    {
                        "type": "postback",
                        "title": "📋 Профайл",
                        "payload": "CMD_PROFILE"
                    }
                ]
            }
        ]
    }
    res = requests.post(url, json=payload, timeout=8)
    return f"<h3>Facebook хариу:</h3><pre>{res.text}</pre><p>Хэрэв result: success гарсан бол тохиргоо амжилттай боллоо. Утаснаасаа чатаа устгаж (Delete chat) дахин нээнэ үү.</p>", 200

# ДЭЛГЭРЭНГҮЙ СТАТИСТИК ХУУДАС
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

# БҮРЭН ЭХЭЭРЭЭ ДЭЛГЭРЭНГҮЙ PRIVACY POLICY
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

                # --- 1. PERSISTENT MENU БОЛОН POSTBACK ХҮЛЭЭН АВАХ ---
                if "postback" in messaging_event:
                    payload = messaging_event.get("postback", {}).get("payload")
                    if payload in ["GET_STARTED", "RESET_PROFILE"]:
                        ask_gender(sender_id)
                    elif payload == "CMD_START":
                        if user.get("step") != "COMPLETED":
                            ask_gender(sender_id)
                        else:
                            handle_start_matching(sender_id)
                    elif payload in ["CMD_CONFIRM_EXIT", "CMD_EXIT"]:
                        ask_exit_confirmation(sender_id)
                    elif payload == "CMD_PROFILE":
                        handle_show_profile(sender_id)
                    continue

                # --- 2. МЕССЕЖ / QUICK REPLY ХҮЛЭЭН АВАХ ---
                message = messaging_event.get("message", {})
                if not message:
                    continue

                # Зураг, файл, стикер хориглох
                if "attachments" in message or "sticker_id" in message:
                    send_message(sender_id, "⚠️️ Аюулгүй байдлын үүднээс зөвхөн бичвэр (текст) илгээхийг зөвшөөрнө. Зураг, стикер дамжуулахгүй.")
                    continue

                text = message.get("text", "").strip()
                payload = message.get("quick_reply", {}).get("payload", "")
                clean_text = text.lower()

                # Админ статистик комманд
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

                # Гарах баталгаажуулалтын хариу шалгах
                if payload == "EXIT_CONFIRMED_YES":
                    handle_exit_chat(sender_id)
                    continue
                elif payload == "EXIT_CONFIRMED_NO":
                    update_user_field(sender_id, "step", "COMPLETED")
                    send_message(sender_id, "Та яриагаа үргэлжлүүлж болно.")
                    continue

                # Гарахыг оролдох үед (текстээр эсвэл товчоор) шууд лавлах
                if payload in ["CMD_EXIT", "CMD_CONFIRM_EXIT"] or clean_text in ["гарах", "stop", "exit", "гар", "/гарах"]:
                    ask_exit_confirmation(sender_id)
                    continue

                # Хэрэв баталгаажуулах төлөвт байхдаа товч даралгүй өөр зүйл бичвэл дахин лавлах
                if user.get("step") == "CONFIRM_EXIT":
                    ask_exit_confirmation(sender_id)
                    continue

                # Хүйс сонгох үе шат
                if payload in ["GENDER_MALE", "GENDER_FEMALE"] or user.get("step") == "ASK_GENDER":
                    gender = "Эрэгтэй" if payload == "GENDER_MALE" or "эр" in clean_text else "Эмэгтэй"
                    update_user_field(sender_id, "gender", gender)
                    ask_age(sender_id)
                    continue

                # Нас сонгох үе шат
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

                # Нэр оруулах үе шат
                if user.get("step") == "ASK_NICKNAME":
                    update_user_field(sender_id, "nickname", text)
                    updated_user = get_or_create_user(sender_id)
                    show_main_menu(sender_id, updated_user)
                    continue

                # ХЭРЭВ БҮРТГЭЛ ДУУСААГҮЙ БАЙЖ ДУРЫН ЗҮЙЛ БИЧВЭЛ ШУУД ЭХНЭЭС НЬ ЭХЛҮҮЛЭХ
                if user.get("step") != "COMPLETED":
                    ask_gender(sender_id)
                    continue

                # Түргэн коммандууд
                if payload == "CMD_START" or clean_text in ["холбогдох", "хайх", "start", "эхлэх"]:
                    handle_start_matching(sender_id)
                    continue

                if payload == "CMD_PROFILE" or clean_text == "/профайл":
                    handle_show_profile(sender_id)
                    continue

                if payload == "RESET_PROFILE":
                    ask_gender(sender_id)
                    continue

                # ЧАТЛАХ (ID, НЭР, НАС, ХҮЙСИЙГ МЕССЕЖИЙН ТОЛГОЙД ЦЭВЭРХЭН ДАМЖУУЛАХ)
                u = get_or_create_user(sender_id)
                if u and u.get("partner_id"):
                    user_id = str(u['psid'])[-4:]
                    gender_icon = "👨" if u.get("gender") == "Эрэгтэй" else ("👩" if u.get("gender") == "Эмэгтэй" else "👤")
                    formatted_text = f"[{gender_icon} #{user_id} | {u['nickname']} | {u['age']} | {u['gender']}]:\n{text}"
                    send_message(u["partner_id"], formatted_text)
                else:
                    qr = [{"content_type": "text", "title": "🚀 Холбогдох", "payload": "CMD_START"}]
                    send_message(sender_id, "Та одоогоор хэнтэй ч холбогдоогүй байна. '🚀 Холбогдох' товчийг дарж хайна уу.", quick_replies=qr)

    except Exception as err:
        print(f"Webhook боловсруулахад алдаа: {err}")

    return "EVENT_RECEIVED", 200

if __name__ == "__main__":
    app.run(port=5000)
