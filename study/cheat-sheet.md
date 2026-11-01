# چیت‌شیت mandate-guard ⚡

یه نگاه بنداز، همه‌چی یادت میاد. برای مرور ۱۰ دقیقه قبل مصاحبه.

## ایده در یک خط

ایجنت **پیشنهاد** می‌ده، **mandate** تصمیم می‌گیره، گارد **verdict امضاشده** برمی‌گردونه. گارد نه پول جابه‌جا می‌کنه، نه کلید نگه می‌داره.

## واژه‌ها در یک خط

| واژه | یعنی چی |
|---|---|
| mandate | قانون انسان برای ایجنت: سقف‌ها، فروشنده‌های مجاز، آستانه‌ی تایید انسان |
| verdict | جواب امضاشده (JWT با ES256): allowed / denied / needs_human + دلیل |
| JWKS | کلیدهای عمومی منتشرشده — هرکی می‌تونه امضا رو چک کنه |
| idempotency | کلید تکراری = همون جواب قبلی؛ هیچ‌وقت دوبار authorize نمی‌شه |
| retry-gaming | همون نیت ردشده با تغییر کوچیک (۵۰ ← ۴۹.۹۹) → بلاک |
| needs_human | رد نیست! یعنی وایسا، برو از آدم بپرس |
| allowlist | لیست فروشنده‌های مجاز |
| append-only | لاگ فقط اضافه می‌شه؛ audit trail |

## فلو تصمیم (به ترتیب!)

1. idempotency → تکراری؟ همون جواب قبلی
2. mandate هست؟ → نه = denied
3. retry-gaming → نیت ردشده‌ی تکراری = denied
4. ارز می‌خوره؟ → نه = denied
5. فروشنده تو allowlistـه؟ → نه = denied
6. سقف روزانه/ماهانه → رد شد = denied
7. بالای آستانه‌ی انسان؟ → **needs_human**
8. همه اوکی → **allowed** + ثبت خرج + امضا + لاگ

## دستورات

```bash
cd ~/workspace/mandate-guard
.venv/bin/python setup_keys.py   # ساخت کلید (یه بار)
.venv/bin/python evals.py        # ۶/۶ باید پاس بشه
.venv/bin/python agent_demo.py   # دمو
.venv/bin/uvicorn server:app --port 8123
.venv/bin/python mcp_server.py   # سرور MCP
```

## API در یک نگاه

- `POST /v1/check` → بدنه: agent_id, amount, currency, vendor, purpose, idempotency_key
- `GET /.well-known/jwks.json` → کلید عمومی
- `GET /v1/decisions` → لاگ
- `POST /v1/mandates` → ساخت/آپدیت قانون

## ۶ تا eval چی رو ثابت می‌کنن

1. پرداخت مجاز پاس می‌شه
2. فروشنده‌ی بد → denied، ایجنت وایمیسته
3. retry-gaming بلاک می‌شه
4. مبلغ بالا → needs_human
5. کلید تکراری → همون decision_id، بدون دوبار خرج
6. امضا با کلید عمومی تایید می‌شه

## دمو ۶۰ ثانیه‌ای (چی بگی)

1. «ایجنت پیشنهاد می‌ده، mandate تصمیم می‌گیره» — خروجی `agent_demo.py` رو نشون بده
2. یه verdict رو باز کن: «ببین، JWT امضاشده‌ست — طرف مقابل خودش verify می‌کنه، من به پول دست نمی‌زنم»
3. `evals.py`: «۶/۶ پاس — همون سه تا کیس تو آگهی شما»
4. «تول MCP فقط verdict برمی‌گردونه، نه پول»

## ۵ جواب یک‌خطی

- **یه ایجنت که شیپ کردی؟** → mandate-guard: مینیاتور ایده‌ی mandate، verdict امضاشده، MCP، ۶/۶ eval
- **MCP ساختی؟** → آره؛ `check_payment` — ورودی ۶ تا، خروجی تصمیم + دلیل + JWT امضاشده
- **چرا verdict امضا می‌شه؟** → طرف مقابل بدون اعتماد به ما، با کلید عمومی چک می‌کنه
- **فرق authorization با پرداخت؟** → اجازه‌ست در برابر جابه‌جایی؛ ما فقط اولی رو می‌دیم
- **چرا سایفورو؟** → ایده‌ی mandate؛ ۳۰ روز اول: اینتگریشن‌ها + MCP + evalها

## نگاشت به سایفورو

mandate = mandate | verdict امضاشده = verdict | jwks = کلیدهای منتشرشده | لاگ = audit log | «پول جابه‌جا نمی‌کنیم» = authorization نه PSP
