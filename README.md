# 📡 Network Radar

سرویس مانیتورینگ وضعیت اتصال شبکه - مشابه radar.chabokan.net

یک ابزار متن‌باز برای نظارت بر وضعیت اتصال به سرورها، سرویس‌ها و دیتاسنترهای مختلف به صورت **زنده** و **لحظه‌ای**.

![Dashboard Preview](https://img.shields.io/badge/Status-Active-green) ![License](https://img.shields.io/badge/License-MIT-blue) ![Python](https://img.shields.io/badge/Python-3.8+-yellow)

---

## ✨ ویژگی‌ها

- 🔴🟡🟢 **نمایش وضعیت لحظه‌ای** - آنلاین، کند، آفلاین
- ⏱️ **اندازه‌گیری تأخیر (Latency)** - به میلی‌ثانیه
- 📊 **نمودار تاریخچه** - مشاهده روند تغییرات
- 🏷️ **دسته‌بندی سرویس‌ها** - DNS، Web، Cloud، Development
- 🔄 **به‌روزرسانی خودکار** - هر ۵ ثانیه در داشبورد
- 📱 **رابط کاربری واکنش‌گرا** - سازگار با موبایل و دسکتاپ
- 🌙 **تم تیره** - راحت برای چشم
- 🔧 **پیکربندی آسان** - با فایل YAML

---

## 🚀 روش‌های نصب

### روش ۱: نصب مستقیم (توصیه شده)

```bash
# دانلود پروژه
git clone https://github.com/YOUR_USERNAME/network-radar.git
cd network-radar

# اجرای اسکریپت نصب
sudo bash install.sh
```

بعد از نصب، داشبورد در آدرس زیر قابل دسترسی است:
```
http://YOUR_SERVER_IP:5000
```

### روش ۲: نصب با Docker

```bash
# دانلود پروژه
git clone https://github.com/YOUR_USERNAME/network-radar.git
cd network-radar

# اجرا با Docker Compose
docker-compose up -d
```

### روش ۳: نصب دستی

```bash
# نصب وابستگی‌های سیستمی
sudo apt update
sudo apt install python3 python3-pip python3-venv iputils-ping dnsutils

# دانلود پروژه
git clone https://github.com/YOUR_USERNAME/network-radar.git
cd network-radar

# ایجاد محیط مجازی
python3 -m venv venv
source venv/bin/activate

# نصب وابستگی‌های پایتون
pip install -r requirements.txt

# اجرا
python app.py
```

---

## ⚙️ پیکربندی

فایل `config.yaml` را ویرایش کنید تا سرویس‌های مورد نظر خود را اضافه کنید:

```yaml
# فاصله زمانی بررسی (ثانیه)
check_interval: 30

# پورت وب سرور
web_port: 5000

# لیست اهداف مانیتورینگ
targets:
  # بررسی با پینگ
  - name: "Google DNS"
    host: "8.8.8.8"
    type: "ping"
    category: "DNS"

  # بررسی HTTP
  - name: "GitHub"
    host: "https://github.com"
    type: "http"
    category: "Development"

  # بررسی پورت TCP
  - name: "SSH Server"
    host: "your-server.com"
    type: "tcp"
    port: 22
    category: "Servers"

  # بررسی DNS Resolution
  - name: "Domain Check"
    host: "example.com"
    type: "dns"
    category: "DNS"
```

### انواع بررسی (Types)

| Type | توضیحات | پارامترهای اضافی |
|------|---------|-----------------|
| `ping` | پینگ ICMP | - |
| `http` | درخواست HTTP/HTTPS | - |
| `tcp` | اتصال TCP به پورت | `port` (الزامی) |
| `dns` | رزولو DNS | `dns_server` (اختیاری) |

---

## 🔧 مدیریت سرویس

```bash
# بررسی وضعیت
sudo systemctl status network-radar

# راه‌اندازی مجدد
sudo systemctl restart network-radar

# توقف
sudo systemctl stop network-radar

# مشاهده لاگ‌ها
sudo journalctl -u network-radar -f

# مشاهده لاگ‌های امروز
sudo journalctl -u network-radar --since today
```

---

## 🌐 API Endpoints

سرویس دارای API ساده برای دریافت اطلاعات است:

| Endpoint | توضیحات |
|----------|---------|
| `GET /api/status` | وضعیت تمام سرویس‌ها |
| `GET /api/summary` | خلاصه وضعیت (تعداد آنلاین/آفلاین) |
| `GET /api/target/<name>` | وضعیت یک سرویس خاص (پارامتر `hours` برای تاریخچه) |
| `POST /api/ingest` | (Agents) ارسال batch نتایج به سرور — نیاز به Header `X-API-Key` |

مثال:
```bash
curl http://localhost:5000/api/summary
```

### Agent

برای استقرار ایجنت روی سرورهای هدف، از `agent.py` استفاده کنید یا کانتینر `Dockerfile.agent` را اجرا کنید. ایجنت‌ها نتایج را به `POST /api/ingest` ارسال می‌کنند و باید header `X-API-Key` را به مقدار `api_key` موجود در `config.yaml` ست کنید. فایل نمونه کانفیگ ایجنت در `agent_config.yaml.example` قرار دارد.

خروجی:
```json
{
  "total": 15,
  "online": 12,
  "degraded": 2,
  "offline": 1,
  "timestamp": "2024-01-15T14:30:00"
}
```

---

## 🔒 تنظیمات امنیتی

### فایروال

```bash
# Ubuntu/Debian (UFW)
sudo ufw allow 5000/tcp

# CentOS/RHEL (firewalld)
sudo firewall-cmd --add-port=5000/tcp --permanent
sudo firewall-cmd --reload
```

### استفاده با Nginx (Reverse Proxy)

```nginx
server {
    listen 80;
    server_name radar.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_cache_bypass $http_upgrade;
    }
}
```

### فعال‌سازی SSL با Certbot

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d radar.yourdomain.com
```

---

## 📁 ساختار پروژه

```
network-radar/
├── app.py              # برنامه اصلی
├── config.yaml         # فایل پیکربندی
├── requirements.txt    # وابستگی‌های پایتون
├── install.sh          # اسکریپت نصب
├── Dockerfile          # برای Docker
├── docker-compose.yml  # برای Docker Compose
├── templates/
│   └── index.html      # قالب داشبورد
└── README.md           # این فایل
```

---

## 🤝 مشارکت

از مشارکت شما استقبال می‌کنیم! برای گزارش باگ یا پیشنهاد ویژگی جدید، یک Issue باز کنید.

---

## 📄 مجوز

این پروژه تحت مجوز MIT منتشر شده است.

---

## 🙏 تقدیر

الهام گرفته از [radar.chabokan.net](https://radar.chabokan.net) و تیم چابکان.

---

<div dir="rtl">

**ساخته شده با ❤️ برای جامعه توسعه‌دهندگان ایران**

</div>
