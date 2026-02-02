# راه‌اندازی Agent روی Ubuntu 24 (با Docker)

این راهنما نحوه‌ی اجرای ایجنت روی سرورهای اوبونتو ۲۴ را نشان می‌دهد.

۱) روی سرور نصب Docker و Docker Compose

```bash
sudo apt update
sudo apt install -y docker.io docker-compose
sudo systemctl enable --now docker
```

۲) کپی کردن فایل‌های ایجنت

روی سرور، از repository یک کپی بیاورید و فایل `agent_config.yaml` را بسازید (می‌توانید از `agent_config.yaml.example` استفاده کنید).

۳) تنظیم متغیرهای محیطی

- `DISPLAY_URL`: آدرس سرویس نمایش (مثلاً `https://radar.example.com`)
- `API_KEY`: کلید API که در `config.yaml` نمایش تنظیم کرده‌اید
- `AGENT_ID`: شناسه‌ای برای این ایجنت (مثلاً `server-1`)

۴) اجرای با Docker Compose

می‌توانید `docker-compose.agent.yml` را با مقادیر خود ویرایش کنید و سپس:

```bash
docker-compose -f docker-compose.agent.yml up -d --build
```

۵) راهنمایی‌های عملیاتی

- برای کاهش فشار روی سرور، مقدار `concurrency` و `check_interval` را در `agent_config.yaml` تنظیم کنید.
- اگر می‌خواهید بدون Docker اجرا کنید، نصبی از Python3 و نصب وابستگی‌ها و اجرای `python agent.py` کافی است.

۶) امنیت

- از TLS در جلوی Display استفاده کنید (Nginx/Traefik) — شما گفتید TLS را خودتان تنظیم می‌کنید.
- کلید API را امن نگه دارید و در فایل‌های عمومی قرار ندهید.
