# Cause List Checker

The application searches for a keyword through all the cause list PDF files on a particular date.

## 🚀 Deploy to AWS Lambda (Free Tier)

This application is configured to run on AWS Lambda using only **free AWS services**:
- **AWS Lambda**: 1M free requests/month + 400K GB-seconds compute
- **API Gateway**: 1M free API calls/month  
- **Systems Manager Parameter Store**: 10K free standard parameters
- **CloudFormation**: Free service for infrastructure management

With 50 requests/day, you'll stay well within the free tier limits.

### Prerequisites

1. **AWS CLI** configured with your credentials:
   ```bash
   aws configure
   ```

2. **AWS SAM CLI** installed:
   ```bash
   # macOS (using Homebrew)
   brew install aws-sam-cli
   
   # Or download from: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html
   ```

### Quick Deployment

1. **Configure your settings**:
   ```bash
   # Edit the parameter file with your actual values
   cp deploy-parameters.json deploy-parameters.json.backup
   ```
   
   Edit `deploy-parameters.json`:
   ```json
   [
     {
       "ParameterKey": "AuthHeader",
       "ParameterValue": "Bearer your-actual-auth-token"
     },
     {
       "ParameterKey": "RequestBodyJson", 
       "ParameterValue": "{\"search_terms\": [\"John\", \"Doe\", \"Case123\"], \"date\": null, \"recipient_emails\": [\"your-email@example.com\", \"another@example.com\"]}"
     }
   ]
   ```

2. **Deploy with one command**:
   ```bash
   ./deploy.sh
   ```

### Manual Deployment Steps

If you prefer manual control:

```bash
# 1. Build the application
sam build

# 2. Deploy to AWS
sam deploy --guided  # First time only
# OR
sam deploy  # Uses saved config from samconfig.toml
```

### Configuration Details

#### Request Body Configuration
The `RequestBodyJson` parameter defines what your scheduled Lambda will search for:

```json
{
  "search_terms": ["keyword1", "keyword2", "Case123"],
  "date": null,  // null = tomorrow's date, or specify "DD/MM/YYYY"
  "recipient_emails": ["alert@example.com"],
  "case_details": {  // Optional
    "type": "CR",
    "no": "1234", 
    "year": "2023"
  }
}
```

#### Environment Variables Needed

Your application expects these environment variables (configured in `app/config.py`):

- `AUTH_TOKEN`: Your API authentication token
- `SENDER_EMAIL`: Email address for sending notifications
- `SENDER_PASSWORD`: Email password or app password
- `SENDER_NAME`: Display name for emails
- `CL_BASE_URL`: Base URL for cause list service
- `MAIN_BASE_URL`: Main website base URL
- `FORM_ACTION_URL`: Form submission endpoint
- `CASE_SEARCH_URL`: Case search endpoint
- `CASE_DETAILS_URL`: Case details endpoint
- `EMAIL_RECIPIENTS`: Comma-separated list of recipient emails

#### Adding Environment Variables

You can add environment variables to the Lambda function in the `template.yaml`:

```yaml
Environment:
  Variables:
    AUTH_TOKEN: !Sub "{{resolve:ssm-secure:/${AWS::StackName}/auth-header}}"
    SENDER_EMAIL: "your-email@gmail.com"
    SENDER_PASSWORD: !Sub "{{resolve:ssm-secure:/${AWS::StackName}/email-password}}"
    # Add other variables as needed
```

### Schedule Configuration

The Lambda runs automatically at these times (IST):
- 10:00 AM
- 1:00 PM - 11:00 PM (every hour)

To modify the schedule, edit the `cron` expression in `template.yaml`:
```yaml
Schedule: cron(30 4,7,8,9,10,11,12,13,14,15,16,17 * * ? *)
```

### Cost Breakdown (All Free Tier)

- **Lambda**: 50 requests × 10s avg = 500s/month (vs 400K free seconds) ✅
- **API Gateway**: Manual API calls (vs 1M free calls) ✅  
- **Parameter Store**: <10 parameters (vs 10K free) ✅
- **CloudWatch Logs**: <5GB (vs 5GB free) ✅

**Total Cost: $0/month** 🎉

### Monitoring & Debugging

1. **View logs**:
   ```bash
   sam logs -n CauseListCheckerFunction --tail
   ```

2. **AWS Console**:
   - Lambda: https://console.aws.amazon.com/lambda/
   - API Gateway: https://console.aws.amazon.com/apigateway/
   - Parameter Store: https://console.aws.amazon.com/systems-manager/parameters

3. **Test the API**:
   ```bash
   # Get the API endpoint from deployment output
   curl https://your-api-id.execute-api.us-east-1.amazonaws.com/Prod/health
   ```

### Local Development

```bash
# Run locally
uvicorn app.server:app --host 0.0.0.0 --port 3080

# Or with Docker
docker-compose up
```

### Updating Configuration

To update your search terms or notification settings:

1. Edit `deploy-parameters.json`
2. Run `./deploy.sh` again

The deployment will update only the changed parameters without downtime.

### Cleanup

To remove everything from AWS:
```bash
sam delete --stack-name cause-list-checker
```
