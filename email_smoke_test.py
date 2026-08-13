# email_smoke_test.py
# Purpose: Verify that email sending works from your current Wi-Fi using the same .env configuration as your bot.

import os
import smtplib
import ssl
import socket
from dotenv import load_dotenv

# ---------- Load your .env ----------
load_dotenv()

SMTP_HOST = os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "587"))  # 587 = STARTTLS, 465 = SSL
SMTP_USER = os.getenv("EMAIL_USER")
SMTP_PASS = os.getenv("EMAIL_PASS")
TO = os.getenv("EMAIL_TO") or SMTP_USER

def send_test():
    print(f"Connecting to {SMTP_HOST}:{SMTP_PORT} ...", flush=True)
    try:
        if SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(
                SMTP_HOST,
                SMTP_PORT,
                timeout=10,
                context=ssl.create_default_context()
            )
        else:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10)
            server.ehlo()
            server.starttls(context=ssl.create_default_context())

        server.login(SMTP_USER, SMTP_PASS)
        msg = (
            f"Subject: Bot Email Smoke Test\n\n"
            f"If you see this email, your SMTP connection from Wi-Fi {socket.gethostname()} is working.\n"
            f"Host: {SMTP_HOST}:{SMTP_PORT}"
        )
        server.sendmail(SMTP_USER, [TO], msg)
        server.quit()
        print("✅ OK: Test email sent successfully.")
        print(f"Sent from: {SMTP_USER}\nTo: {TO}")
    except (socket.gaierror, socket.timeout) as e:
        print(f"❌ NETWORK ERROR: {e}")
    except smtplib.SMTPAuthenticationError as e:
        print(f"❌ AUTH ERROR: {e.smtp_error.decode(errors='ignore')}")
    except smtplib.SMTPException as e:
        print(f"❌ SMTP ERROR: {e}")

if __name__ == "__main__":
    send_test()