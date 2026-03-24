import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv

load_dotenv()

APP_PASSWORD= os.getenv("APP_PASSWORD", "")

def notify(body, subject="Someone Tried your Application"):
    # Your email credentials
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    sender_email = "sidduramagiri3@gmail.com"
    sender_password = APP_PASSWORD

    try:
        # Create message
        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = "sidduramagiri34@gmail.com"
        msg["Subject"] = subject

        msg.attach(MIMEText(body, "plain"))

        # Connect to server
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, sender_password)

        # Send email
        server.send_message(msg)
        server.quit()

        return True

    except Exception as e:
        print("Error:", e)
        return False
    
    
if __name__ == "__main__" :
    notify("Join columns ")