import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os


class Emailer:
    def __init__(self):
        self.sender_email = os.getenv("SENDER_EMAIL")
        self.sender_password = os.getenv("SENDER_PASSWORD")

    def send_email(self, results: dict, recipient_emails: list[str]) -> None:
        subject = "Scraper Results"
        body = "\n".join([f"{key}: {value}" for key, value in results.items()])

        msg = MIMEMultipart()
        msg["From"] = self.sender_email
        msg["To"] = ", ".join(recipient_emails)
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(self.sender_email, self.sender_password)
            server.sendmail(self.sender_email, recipient_emails, msg.as_string())
