# mandate-guard — سناریوی ارائه‌ی خط‌به‌خط 🇮🇷

این فایل رو موقع ارائه جلوت بذار. صفحه‌ی دمو انگلیسیه (اد می‌بینه)، توضیحات اینجا فارسیه (تو می‌فهمی).

## ۰. نصب روی لپ‌تاپ (ویندوز) — ۳ دقیقه

ترمینال ۱:
```
git clone https://github.com/lil-ichi/Mandate-Guard.git
cd Mandate-Guard
pip install -r requirements.txt
python setup_keys.py
python -m uvicorn server:app --port 8123
```

ترمینال ۲ (یه پنجره‌ی جدا):
```
cd Mandate-Guard
python merchant.py
```

بعد مرورگر: `http://127.0.0.1:8123` — صفحه‌ی دمو میاد بالا.
دو تا چراغ بالا باید سبز باشن (guard و merchant). اگه merchant قرمزه یعنی ترمینال ۲ رو یادت رفته.

دکمه‌ی **Reset demo** = همه‌چی صفر می‌شه (mandate می‌مونه). قبل از ارائه یه بار بزنش که تمیز شروع کنی.

## ۱. نقشه‌ی صفحه — ۵ بخش

| بخش | چیه | تو چی می‌گی |
|---|---|---|
| ۱. The mandate | سقف روزانه/ماهانه، لیست vendorهای مجاز، آستانه‌ی تأیید انسانی | «این mandateـه — اپراتور تعیینش می‌کنه، ایجنت نمی‌تونه عوضش کنه» |
| ۲. Ask the guard | فرم: مبلغ، vendor، کلید idempotency | «حالا نقش ایجنت رو بازی می‌کنم» |
| ۳. Verdict & check trace | تصمیم + تک‌تک چک‌ها + توکن JWT دیکدشده | «ببین دقیقاً کدوم چک چی گفت» |
| ۴. The story | ۵ تا سناریوی آماده + اجرای کامل | «حالا کل داستان رو پشت سر هم ببین» |
| ۵. The wire | چیزی که مرچنت واقعاً شارژ کرده | «سیم فقط همون چیزی رو دید که گارد اجازه داد» |

## ۲. سناریوی ۶۰ ثانیه‌ای (پیشنهاد ترتیب)

**ثانیه‌ی ۰–۱۰ — mandate رو نشون بده:**
> "This is the mandate: $2,000 a day, $5,000 a month, only these two vendors, and anything above $500 needs a human. The agent can't change any of this."

**ثانیه‌ی ۱۰–۲۵ — دکمه‌ی ▶ Run full story رو بزن و حرف بزن روش:**
- سناریوی ۱ ($۱۲۰ به acme-cloud): سبز می‌شه، مرچنت شارژ می‌کنه.
  > "Allowed — within the mandate. The merchant verifies the signature itself and charges."
- سناریوی ۲ ($۵۰ به evil-vendor): قرمز.
  > "Denied — vendor's not on the allowlist. The agent never even calls the merchant."
- سناریوی ۳ ($۴۹.۹۹ همون vendor): قرمز با دلیل retry-gaming.
  > "The agent tries again with a tweaked amount. The guard recognizes the same denied intent and blocks it."
- سناریوی ۴ ($۹۰۰): کهربایی needs_human.
  > "Above the threshold — it doesn't deny, it routes to a person."
- سناریوی ۵ (tamper): مرچنت 402 می‌ده.
  > "The agent reuses a valid verdict but lies about the amount. The merchant catches it — 402."

**ثانیه‌ی ۲۵–۴۰ — بخش ۵ (The wire):**
> "One charge on the wire. Everything else never left the agent. The verdict — not the agent — decides."

**ثانیه‌ی ۴۰–۶۰ — اگه خواست عمیق بشه:** برو بخش ۲، خودت یه مبلغ بزن (مثلاً $۶۰۰ به acme-cloud → needs_human می‌شه) و trace رو خط‌به‌خط نشونش بده.

## ۳. trace خط‌به‌خط — هر چک یعنی چی

ترتیب چک‌ها عمداً اینه (اگه اد پرسید چرا این ترتیبه، بگو: «ارزون‌ترین و قطعی‌ترین چک‌ها اول»):

1. **Idempotency** (آبی، info) — کلید تکراریه؟ اگه آره، همون تصمیم قبلی برمی‌گرده، هیچ‌چی دوباره authorize نمی‌شه.
2. **Mandate lookup** — اصلاً mandate برای این ایجنت هست؟
3. **Retry-gaming scan** — تو ۱۰ تصمیم آخر، همین نیتِ ردشده با یه تغییر کوچیک دوباره اومده؟ (fingerprint = agent + vendor + مبلغ روندشده)
4. **Currency check** — ارز درخواستی با ارز mandate یکیه؟
5. **Vendor allowlist** — vendor تو لیست مجازه؟
6. **Daily cap** — جمع امروز + این مبلغ از سقف روزانه رد می‌شه؟
7. **Monthly cap** — همون برای ماهانه.
8. **Human-approval threshold** — بالای آستانه‌ست؟ اگه آره → needs_human (نه deny — مسیر عوض می‌شه، رد نمی‌شه).

بعدش: verdict امضا می‌شه (ES256، عمر ۵ دقیقه) و تصمیم لاگ می‌شه.

## ۴. اگه اد سؤال پیچیده پرسید

- **«کلیدها کجان؟»** → مرچنت کلید رو از `/.well-known/jwks.json` می‌گیره (همون discovery path واقعی). هیچ secret مشترکی، هیچ کپی کلید.
- **«چرا verdict رو هم برای deny امضا می‌کنی؟»** → چون مرچنت باید بتونه بفهمه deny واقعاً از گارده، نه اینکه ایجنت الکی بگه «گارد رد کرد». (این دقیقاً نکته‌ی درافت ایتلیاست.)
- **«اگه ایجنت کلید idempotency رو حدس بزنه؟»** → کلید رو خودِ caller می‌سازه و گارد فقط replay می‌کنه؛ ضرری نداره چون تصمیمِ ذخیره‌شده همون تصمیمِ درسته.
- **«اسکیل می‌شه؟»** → صادقانه: «این نسخه‌ی نمایشی تک‌پروسس با SQLiteـه. نسخه‌ی واقعی رو شما با HSM و دیتابیس واقعی می‌سازین — معماریش همینه.»
- **«چرا amount رو گرد می‌کنی تو fingerprint؟»** → چون retry-gaming دقیقاً یعنی «همون نیت با یه تغییر کوچیک» — $۵۰ و $۴۹.۹۹ یه نیتن.

## ۵. جمله‌ی بستن (اگه خواستی تمومش کنی)

> "The whole point in one line: the agent proposes, the mandate decides, and the wire only ever sees what the guard allowed."
