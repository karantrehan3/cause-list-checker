import traceback
from typing import Tuple
from app.services.emailer import Emailer


class ErrorHandler:
    def __init__(self, emailer: Emailer, recipients: list) -> None:
        self.emailer = emailer
        self.recipients = recipients

    def handle_exception(self, exception: Exception, context: dict) -> Tuple[str, str]:
        error_message = str(exception)
        stack_trace = traceback.format_exc()
        context.update({"error_message": error_message, "stack_trace": stack_trace})

        try:
            self.emailer.send_email(
                recipients=self.recipients,
                subject="Cause List Search Error Notification",
                template_name="error_template.html",
                context=context,
            )
        except Exception as email_error:
            print(f"Error sending error email: {email_error}")

        return error_message, stack_trace
