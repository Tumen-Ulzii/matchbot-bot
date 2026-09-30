import os
from flask import Flask, request
import requests

app = Flask(__name__)

# Тохиргоонуудыг орчны хувьсагчаас авна (дараа нь Render дээр хялбар тохируулна)
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN", "REPLACE_WITH_PAGE_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "my_secret_matchchat_token_123")

# Чатын санах ой
waiting_users = []  # Хүлээлгийн жагсаалт
active_pairs = {}   # Идэвхтэй холбогдсон хосууд

def send_message(recipient_id, text):
    """Facebook Messenger рүү хариу зурвас илгээх функц"""
    url = f"https://graph.facebook.com/v19.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text}
    }
    requests.post(url, json=payload)

@app.route("/", methods=["GET"])
def home():
    """Сервер ажиллаж байгааг шалгах үндсэн хуудас"""
    return "MatchChat Server is running 24/7!CAMILAAXISMUS", 800


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
        <p>Хэрэв танд ямар нэг гомдол, санал байвал манай албан ёсны Facebook хуудсаар дамжуулан холбогдоно уу.</p>
    </body>
    </html>
    """
    return html_content, 200

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    """Meta-аас Webhook-ийг баталгаажуулах хэсэг"""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Verification failed", 403

@app.route("/webhook", methods=["POST"])
def handle_messages():
    """Зурвас ирэх бүрд хооронд нь холбох үндсэн логик"""
    data = request.get_json()

    if data.get("object") == "page":
        for entry in data.get("entry", []):
            for messaging_event in entry.get("messaging", []):
                sender_id = messaging_event.get("sender", {}).get("id")
                message = messaging_event.get("message", {})
                text = message.get("text", "").strip()

                if not text or not sender_id:
                    continue

                clean_text = text.lower()

                # 1. Чатаас гарах
                if clean_text in ["гарах", "stop", "exit", "гар"]:
                    if sender_id in active_pairs:
                        partner_id = active_pairs.pop(sender_id)
                        active_pairs.pop(partner_id, None)
                        send_message(sender_id, "❌ Та чатаас гарлаа. Шинэ хүнтэй холбогдох бол 'Холбогдох' гэж бичээрэй.")
                        send_message(partner_id, "❌ Ярилцагч чатаас гарлаа. Шинэ хүнтэй холбогдох бол 'Холбогдох' гэж бичээрэй.")
                    elif sender_id in waiting_users:
                        waiting_users.remove(sender_id)
                        send_message(sender_id, "Хайлтыг зогсоолоо. 'Холбогдох' гэж бичээд дахин эхлүүлэх боломжтой.")
                    else:
                        send_message(sender_id, "Та одоогоор хэнтэй ч холбогдоогүй байна.")

                # 2. Шинэ хүн хайх
                elif clean_text in ["холбогдох", "хайх", "start", "эхлэх"]:
                    if sender_id in active_pairs:
                        send_message(sender_id, "Та өөр хүнтэй холбогдсон байна. Гарах бол 'Гарах' гэж бичнэ үү.")
                    elif sender_id in waiting_users:
                        send_message(sender_id, "Таныг хүлээлгэнд бүртгэсэн байна. Түр хүлээнэ үү...")
                    else:
                        if waiting_users:
                            partner_id = waiting_users.pop(0)
                            active_pairs[sender_id] = partner_id
                            active_pairs[partner_id] = sender_id

                            msg = "🎉 Танихгүй хүнтэй холбогдлоо! Бие биедээ хүндэтгэлтэй хандана уу. (Гарах бол 'Гарах' гэж бичнэ)"
                            send_message(sender_id, msg)
                            send_message(partner_id, msg)
                        else:
                            waiting_users.append(sender_id)
                            send_message(sender_id, "🔍 Танд тохирох хүнийг хайж байна... Түр хүлээнэ үү.")

                # 3. Мессеж дамжуулах
                else:
                    if sender_id in active_pairs:
                        partner_id = active_pairs[sender_id]
                        send_message(partner_id, text)
                    else:
                        send_message(sender_id, "Танихгүй хүнтэй холбогдохын тулд 'Холбогдох' гэж бичнэ үү.")

    return "EVENT_RECEIVED", 200

if __name__ == "__main__":
    app.run(port=5000)
