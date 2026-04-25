# AWS Lambda Deployment Guide

## Prerequisites

- Python 3.13 installed locally
- AWS account (free tier is sufficient)
- AWS CLI installed (`brew install awscli`) and configured (`aws configure`)

## Quick Deploy (after initial setup)

```bash
./deploy-lambda.sh
```

If AWS CLI is not configured, the script builds the zip and you upload it manually via the Lambda console.

## Manual Upload

1. Run `./deploy-lambda.sh` to build `lambda_deployment.zip`
2. Go to **Lambda** > `cause-list-checker` > **Code** tab
3. Click **Upload from** > **.zip file**
4. Select `lambda_deployment.zip`
5. Click **Save**

## Initial Lambda Setup (one time)

### 1. Create the Lambda Function

1. Go to **Lambda** > **Create function**
2. Select **Author from scratch**
3. Function name: `cause-list-checker`
4. Runtime: **Python 3.13**
5. Architecture: **x86_64**
6. Click **Create function**
7. Upload the zip (see Manual Upload above)
8. Go to **Runtime settings** > **Edit** > Handler: `lambda_handler.handler` > **Save**

### 2. Configure Settings

**General configuration** (Configuration > General configuration > Edit):
- Memory: **1024 MB**
- Ephemeral storage: **512 MB** (default)
- Timeout: **15 min 0 sec**

### 3. Environment Variables

Configuration > Environment variables > Edit:

| Key | Value |
|-----|-------|
| `AUTH_TOKEN` | *(from .env)* |
| `CASE_SEARCH_URL` | *(from .env)* |
| `CL_BASE_URL` | *(from .env)* |
| `CL_FORM_ACTION_URL` | *(from .env)* |
| `CL_JUDGE_WISE_REGULAR_URL` | *(from .env)* |
| `EMAIL_RECIPIENTS` | *(from .env)* |
| `PHHC_API_BASE_URL` | *(from .env)* |
| `SENDER_EMAIL` | *(from .env)* |
| `SENDER_PASSWORD` | *(from .env)* |
| `SENDER_NAME` | *(from .env)* |
| `SMTP_SERVER` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |

### 4. Create Schedules (EventBridge Scheduler)

Go to **Amazon EventBridge** > **Scheduler** > **Schedules** > **Create schedule**.

#### Schedule 1 — Search Term 1

- Name: `cause-list-search-config-1`
- Schedule type: **Recurring schedule**
- Cron: `cron(30 4,7,8,9,10,11,12,13,14,15,16,17 * * ? *)`
- Timezone: **UTC**
- Flexible time window: **Off**
- Target: **AWS Lambda — Invoke** > `cause-list-checker`
- Payload:
  ```json
  {
    "detail": {
      "search_terms": ["Search Term 1", "XX-0000-0000"],
      "case_details": {"type": "CR", "no": "0000", "year": "2010"}
    }
  }
  ```

#### Schedule 2 — Search Term 2

- Name: `cause-list-search-config-2`
- Cron: `cron(45 4,7,8,9,10,11,12,13,14,15,16,17 * * ? *)`
- Timezone: **UTC**
- Target: **AWS Lambda — Invoke** > `cause-list-checker`
- Payload:
  ```json
  {
    "detail": {
      "search_terms": ["Search Term 2"],
      "recipient_emails": ["redacted@example.com"]
    }
  }
  ```

### 5. Cron Schedule Reference

Local crons run at :00 and :15 past hours 10,13-23 IST. IST = UTC+5:30:

| IST | UTC |
|-----|-----|
| 10:00 | 04:30 |
| 13:00 | 07:30 |
| 14:00 | 08:30 |
| ... | ... |
| 23:00 | 17:30 |

## Testing

1. Go to Lambda > `cause-list-checker` > **Test** tab
2. Create a test event with one of the schedule payloads above
3. Click **Test**
4. Check **Monitor** > **View CloudWatch logs** for output

## Post-Deploy Checklist

- [ ] Lambda handler is set to `lambda_handler.handler`
- [ ] Timeout is 15 minutes
- [ ] Memory is 1024 MB
- [ ] All environment variables are set
- [ ] Test event runs successfully and email is received
- [ ] Both EventBridge schedules are created and enabled
- [ ] CloudWatch logs show no errors

## Cost

Everything runs within AWS free tier ($0/month):
- Lambda: ~900 invocations/month, ~54,000 GB-seconds (free tier: 1M invocations, 400K GB-seconds)
- EventBridge Scheduler: ~720 invocations/month (free tier: 14M)
- Data transfer: ~300 MB/month (free tier: 100 GB)
