import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from jinja2 import Environment, FileSystemLoader
from app.config import settings


class Emailer:
    def __init__(self) -> None:
        self.sender_email = settings.SENDER_EMAIL
        self.sender_password = settings.SENDER_PASSWORD
        self.sender_name = settings.SENDER_NAME
        self.smtp_server = settings.SMTP_SERVER
        self.smtp_port = settings.SMTP_PORT
        self.env = Environment(
            loader=FileSystemLoader("app/services/emailer/templates")
        )

    def send_email(self, recipients, subject, template_name, context) -> None:
        # Create the email
        msg = MIMEMultipart()
        msg["From"] = f"{self.sender_name} <{self.sender_email}>"
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = subject

        # Render the HTML template
        template = self.env.get_template(template_name)
        html_content = template.render(context)
        msg.attach(MIMEText(html_content, "html"))

        # Connect to the SMTP server
        with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
            server.starttls()
            server.login(self.sender_email, self.sender_password)
            server.sendmail(self.sender_email, recipients, msg.as_string())
