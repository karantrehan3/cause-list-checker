# [Cause List Checker](https://karantrehan3.github.io/cause-list-checker/)

{% include header.html %}

![Cause List Checker](./assets/thumbnail.png)

An internal tool built for searching case details on Punjab and Haryana High Court and checking if you have a hearing date on a specified date. Results are automatically emailed to recipient emails.

## Features

- **Automated Case Search**: Searches through cause list PDF files for specific case details
- **Date-based Filtering**: Check hearing dates for specific dates (defaults to next day)
- **Email Notifications**: Automatic email alerts with search results
- **Case Details Integration**: Fetches detailed case information from the court website
- **Docker Support**: Easy deployment and setup with Docker
- **Queue Management**: Asynchronous task queue for managing inbound requests with retry logic
- **Weekend Date Processing**: Automatically processes weekend dates when searching on Fridays/Saturdays/Sundays
- **Rate Limiting**: Built-in protection against too many concurrent requests

## Architecture

The application follows a modular architecture with the following components:

- **FastAPI Server**: RESTful API endpoints for case search operations
- **Queue Manager**: Asynchronous task queue for processing search requests with retry logic
- **PDF Searcher**: Searches through downloaded cause list PDFs for specific terms
- **Web Scraper**: Downloads cause list PDFs and extracts case details from court website
- **Email Service**: Sends formatted email notifications with search results
- **Authentication**: Token-based API authentication for security

## Prerequisites

- Docker and Docker Compose
- Gmail account with App Password enabled
- Access to Punjab and Haryana High Court website

## Setup

### 1. Clone the Repository

```bash
git clone <repository-url>
cd cause-list-checker
```

### 2. Environment Configuration

Create a `.env` file in the root directory with the following variables:

```env
# Authentication
AUTH_TOKEN=your_secure_auth_token_here

# Court Website URLs
CASE_SEARCH_URL=https://phhc.gov.in/case-search
CASE_DETAILS_URL=https://phhc.gov.in/case-details
CL_BASE_URL=https://phhc.gov.in/cause-list
CL_FORM_ACTION_URL=https://phhc.gov.in/cause-list/form
CL_JUDGE_WISE_REGULAR_URL=https://phhc.gov.in/cause-list/judge-wise
MAIN_BASE_URL=https://phhc.gov.in

# Email Configuration
EMAIL_RECIPIENTS=recipient1@example.com,recipient2@example.com
SENDER_EMAIL=your_email@gmail.com
SENDER_PASSWORD=your_gmail_app_password
SENDER_NAME=Your Name
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
```

### 3. Gmail App Password Setup

To use Gmail for sending emails, you need to set up an App Password:

1. **Enable 2-Factor Authentication**:

   - Go to your Google Account settings
   - Navigate to Security → 2-Step Verification
   - Enable 2-Step Verification if not already enabled

2. **Generate App Password**:
   - Go to Security → App passwords
   - Select "Mail" as the app and "Other" as the device
   - Enter a custom name (e.g., "Cause List Checker")
   - Click "Generate"
   - Copy the 16-character password and use it in your `.env` file

### 4. Docker Deployment

```bash
# Build and start the application
docker-compose up --build

# Run in background
docker-compose up -d --build
```

The application will be available at `http://localhost:3080`

## API Usage

### Health Check

```bash
curl http://localhost:3080/health
```

Response:

```json
{
  "status": "ok"
}
```

### Search for Cases

```bash
curl -X POST http://localhost:3080/search/cause-list \
  -H "Authorization: Bearer your_secure_auth_token_here" \
  -H "Content-Type: application/json" \
  -d '{
    "search_terms": ["CWP-12345-2023", "Criminal Appeal 789"],
    "date": "15/12/2024",
    "recipient_emails": ["lawyer@example.com", "client@example.com"],
    "case_details": {
      "no": "12345",
      "type": "CWP",
      "year": "2023"
    }
  }'
```

### Request Parameters

- **search_terms** (required): List of case numbers or keywords to search for
- **date** (optional): Date in DD/MM/YYYY format (defaults to next day)
- **recipient_emails** (optional): List of email addresses to receive notifications
- **case_details** (optional): Detailed case information for enhanced search

### Response Format

```json
{
  "message": "Search and notification process queued for 1 date(s)",
  "dates": ["15/12/2024"],
  "queue_size": 1
}
```

## Queue Management

The application now includes a robust queue management system that handles inbound requests asynchronously:

### Features

- **Asynchronous Processing**: All search requests are queued and processed in the background
- **Retry Logic**: Failed tasks are automatically retried up to 3 times with exponential backoff
- **Concurrent Request Handling**: Multiple requests can be queued simultaneously
- **Task Tracking**: Each task has a unique ID for tracking and debugging
- **Queue Status Monitoring**: Real-time queue status and processor health

### Weekend Date Processing

The system automatically handles weekend date processing:

- **Friday Searches**: Automatically includes Saturday, Sunday, and Monday
- **Saturday Searches**: Automatically includes Sunday and Monday
- **Sunday Searches**: Automatically includes Monday
- **Weekday Searches**: Process only the specified date

This ensures comprehensive coverage when searching around weekends.

## How It Works

1. **Request Queuing**: Search requests are added to an asynchronous queue
2. **Background Processing**: The queue processor handles tasks one at a time
3. **PDF Download**: The scraper downloads cause list PDFs for the specified date(s) from the Punjab and Haryana High Court website
4. **Case Details Fetching**: Simultaneously fetches detailed case information from the court database
5. **PDF Search**: Searches through downloaded PDFs for the specified search terms
6. **Email Notification**: Sends a formatted email with search results to all recipients
7. **Error Handling**: Comprehensive error handling with automatic retries and email notifications for failures

## Email Notifications

The application sends detailed email notifications containing:

- Search terms used
- Date searched
- List of PDFs processed
- Search results with page numbers and context
- Case details (if available)
- Regular cause list matches (if found)

## Development

### Local Development Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the application
uvicorn app.server:app --host 0.0.0.0 --port 3080 --reload
```

### Project Structure

```
cause-list-checker/
├── app/
│   ├── config.py              # Configuration settings
│   ├── server.py              # FastAPI application
│   ├── managers/
│   │   ├── pdf_searcher.py    # PDF search functionality
│   │   ├── queue.py           # Queue management system
│   │   └── scraper.py         # Web scraping logic
│   ├── routes/
│   │   ├── auth.py            # Authentication middleware
│   │   └── search/
│   │       └── cause_list/    # Search endpoints
│   ├── services/
│   │   └── emailer/           # Email service
│   └── utils/
│       ├── error_handler.py   # Error handling utilities
│       └── helpers.py         # Helper functions
├── docker-compose.yml         # Docker configuration
├── Dockerfile                 # Docker image definition
└── requirements.txt           # Python dependencies
```

## Troubleshooting

### Common Issues

1. **Gmail Authentication Error**:

   - Ensure 2-Factor Authentication is enabled
   - Verify the App Password is correctly set in `.env`
   - Check that the email and password are correct

2. **PDF Download Failures**:

   - Verify the court website URLs are accessible
   - Check network connectivity
   - Ensure the date format is correct (DD/MM/YYYY)

3. **Queue Processing Issues**:

   - Check application logs for task execution details
   - Monitor queue status for stuck tasks
   - Verify the queue processor is running

4. **Rate Limiting**:
   - The application prevents concurrent searches through queue management
   - Requests are processed sequentially to avoid overwhelming the court website

### Logs

View application logs:

```bash
# Docker logs
docker-compose logs -f app

# Local development logs
# Check the terminal where uvicorn is running
```

### Queue Status

Monitor queue status through application logs:

- Task queuing: "Task {task_id} added to queue"
- Task execution: "Executing task {task_id} (attempt {attempt}/{max_attempts})"
- Task completion: "Task {task_id} completed successfully"
- Task failures: "Task {task_id} failed: {error}"

## Security Considerations

- **Authentication**: All API endpoints require a valid AUTH_TOKEN
- **Queue Management**: Asynchronous processing prevents request overload
- **Environment Variables**: Sensitive data stored in `.env` file (not committed to version control)
- **Docker Security**: Container runs with limited resources and non-root user

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

For issues and questions, please create an issue in the repository or contact the development team.
