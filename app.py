import os
from flask import Flask, request
import requests
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

# Render Environment Variables-аас тохиргоог авна
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN", "REPLACE_WITH_PAGE_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "my_secret_matchchat_token_123")
DATABASE_URL = os.environ.get("DATABASE_URL")

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
                    gender VARCHAR(20) DEFAULT 'Тодорхойгүй',
                    age VARCHAR(10) DEFAULT 'Тодорхойгүй',
                    partner_id VARCHAR(100),
                    is_waiting BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()
        conn.close()

# Сервер асах үед хүснэгтийг автоматаар бэлдэх
init_db()

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

# --- МЕССЕЖ ИЛГЭЭХ СИСТЕМ ---

def send_message(recipient_id, text):
    url = f"https://graph.facebook.com/v19.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text}
    }
    requests.post(url, json=payload)

# --- ROUTES ---

@app.route("/", methods=["GET"])
def home():
    return "MatchChat PostgreSQL Server is running 24/7!CAMILAAXISMUS", 200

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
    data = request.get_json()

    if data.get("object") == "page":
        for entry in data.get("entry", []):
            for messaging_event in entry.get("messaging", []):
                sender_id = messaging_event.get("sender", {}).get("id")
                message = messaging_event.get("message", {})

                if not sender_id or not message:
                    continue

                # Хэрэглэгчийг баазаас олох эсвэл шинээр бүртгэх
                user = get_or_create_user(sender_id)

                # Зураг, дуу, видео, файл явуулбал хязгаарлах
                if "attachments" in message:
                    send_message(sender_id, "⚠️ Аюулгүй байдлын үүднээс зөвхөн бичвэр (текст) илгээхийг зөвшөөрнө.")
                    continue

                text = message.get("text", "").strip()
                if not text:
                    continue

                clean_text = text.lower()

                # 1. ТОХИРГООНЫ КОМАНДУУД
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

                # 2. ЧАТААС ГАРАХ
                elif clean_text in ["гарах", "stop", "exit", "гар"]:
                    u = get_or_create_user(sender_id)
                    if u["partner_id"]:
                        partner_id = u["partner_id"]
                        update_user_field(sender_id, "partner_id", None)
                        update_user_field(partner_id, "partner_id", None)
                        send_message(sender_id, "❌ Та чатаас гарлаа. Шинэ хүнтэй холбогдох бол 'Холбогдох' гэж бичнэ үү.")
                        send_message(partner_id, "❌ Ярилцагч чатаас гарлаа. Шинэ хүнтэй холбогдох бол 'Холбогдох' гэж бичнэ үү.")
                    elif u["is_waiting"]:
                        update_user_field(sender_id, "is_waiting", False)
                        send_message(sender_id, "Хайлтыг зогсоолоо. 'Холбогдох' гэж бичээд дахин эхлүүлэх боломжтой.")
                    else:
                        send_message(sender_id, "Та одоогоор хэнтэй ч холбогдоогүй байна.")

                # 3. ШИНЭ ХҮН ХАЙХ
                elif clean_text in ["холбогдох", "хайх", "start", "эхлэх"]:
                    u = get_or_create_user(sender_id)
                    if u["partner_id"]:
                        send_message(sender_id, "Та өөр хүнтэй холбогдсон байна. Чатаас гарах бол 'Гарах' гэж бичнэ үү.")
                    elif u["is_waiting"]:
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

                # 4. МЕССЕЖ ДАМЖУУЛАХ
                else:
                    u = get_or_create_user(sender_id)
                    if u["partner_id"]:
                        formatted_text = f"👤 {u['nickname']}:\n{text}"
                        send_message(u["partner_id"], formatted_text)
                    else:
                        send_message(sender_id, "Та одоогоор хэнтэй ч холбогдоогүй байна. 'Холбогдох' гэж бичнэ үү.\nПрофайлаа харах бол '/профайл' гэж бичээрэй.")

    return "EVENT_RECEIVED", 200

if __name__ == "__main__":
    app.run(port=5000)
