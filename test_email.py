import os, smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()

msg = EmailMessage()
msg["From"] = os.getenv("EMAIL_FROM")
msg["To"] = os.getenv("EMAIL_TO")
msg["Subject"] = "✅ Coinbase Bot Email Test"
msg.set_content("If you see this, Gmail SMTP is working.")

try:
    with smtplib.SMTP(os.getenv("EMAIL_SMTP_HOST"), int(os.getenv("EMAIL_SMTP_PORT")), timeout=20) as s:
        s.ehlo()
        if os.getenv("EMAIL_USE_TLS", "1") == "1":
            s.starttls()
        s.login(os.getenv("EMAIL_USER"), os.getenv("EMAIL_PASS"))
        s.send_message(msg)
    print("Email sent successfully!")
except Exception as e:
    print("Email failed:", e)