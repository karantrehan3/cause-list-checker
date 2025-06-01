import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List

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

    def send_email(
        self,
        recipients: List[str],
        subject: str,
        template_name: str,
        context: Dict[str, Any],
    ) -> None:
        """
        Send an email using a template

        Args:
            recipients: List of email addresses
            subject: Email subject
            template_name: Name of the template file
            context: Dictionary of variables to pass to the template
            attachments: Optional list of attachments, each with filename, content, and content_type
        """
        try:
            # Create the email
            msg = MIMEMultipart()
            msg["From"] = f"{self.sender_name} <{self.sender_email}>"
            msg["To"] = ", ".join(recipients)
            msg["Subject"] = subject

            # Render the HTML template
            template = self.env.get_template(template_name)
            html_content = template.render(
                {
                    **context,
                    "generated_timestamp": datetime.now(
                        timezone(timedelta(hours=5, minutes=30))
                    ).strftime("%Y-%m-%d %H:%M:%S IST"),
                }
            )
            msg.attach(MIMEText(html_content, "html"))

            # Connect to the SMTP server
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.sendmail(self.sender_email, recipients, msg.as_string())
        except Exception as e:
            print(f"Error sending email: {e}", flush=True)
            raise e
