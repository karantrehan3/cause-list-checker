# 🚀 Simple Lambda Deployment

This is the **simplest way** to deploy your Cause List Checker to AWS Lambda - just one Python file!

## ✅ What You Get
- **Single Lambda function** with all functionality
- **Automatic scheduling** (runs 14 times daily)
- **Email notifications** when matches found
- **100% Free** (within AWS free tier)
- **No complex infrastructure** - just pure Python

## 🏃‍♂️ Quick Start

### 1. Setup AWS Connection
```bash
# Install AWS CLI (if not already installed)
curl "https://awscli.amazonaws.com/AWSCLIV2.pkg" -o "AWSCLIV2.pkg"
sudo installer -pkg AWSCLIV2.pkg -target /

# Configure AWS credentials
aws configure
```

You'll need:
- **AWS Access Key ID**: Get from AWS Console → IAM → Users → Security credentials
- **AWS Secret Access Key**: Generated with the Access Key
- **Region**: `us-east-1` (or your preferred region)

### 2. Deploy in 2 Commands
```bash
# Step 1: Setup IAM role (one-time setup)
./setup-iam.sh

# Step 2: Deploy your function
./deploy-simple.sh
```

### 3. Configure Your Settings
Edit `deploy-simple.sh` and update these values:
```bash
SEARCH_TERMS="John Doe,Case123,your keywords"
EMAIL_RECIPIENTS="your-email@example.com"
SENDER_EMAIL="your-gmail@gmail.com"
SENDER_PASSWORD="your-app-password"  # Gmail app password
CL_BASE_URL="https://your-causelist-site.com"
MAIN_BASE_URL="https://your-main-site.com"
FORM_ACTION_URL="https://your-site.com/form-endpoint"
```

Then run: `./deploy-simple.sh` again to update.

## 🔧 How to Connect AWS

### Option 1: AWS Console (Beginner-Friendly)
1. Go to [AWS Console](https://aws.amazon.com/console/)
2. Sign up for free account (requires credit card but won't be charged)
3. Go to **IAM** → **Users** → **Create User**
4. Attach policy: **PowerUserAccess** (for deployment permissions)
5. Go to **Security credentials** → **Create access key**
6. Copy the **Access Key ID** and **Secret**
7. Run `aws configure` and paste these values

### Option 2: AWS CLI (Programmatic)
```bash
# Install AWS CLI
curl "https://awscli.amazonaws.com/AWSCLIV2.pkg" -o "AWSCLIV2.pkg"
sudo installer -pkg AWSCLIV2.pkg -target /

# Configure credentials
aws configure
# AWS Access Key ID: YOUR_KEY_HERE
# AWS Secret Access Key: YOUR_SECRET_HERE  
# Default region: us-east-1
# Default output format: json
```

## 📧 Gmail Setup
1. Enable **2-Step Verification** in your Google account
2. Go to **Google Account** → **Security** → **App passwords**
3. Generate password for "Mail"
4. Use this app password (not your Gmail password) in `SENDER_PASSWORD`

## ⏰ Schedule
Your function automatically runs at these times (IST):
- **10:00 AM** daily
- **1:00 PM - 11:00 PM** (every hour)

## 🧪 Testing

### Test Locally
```bash
# Test the function
python3 -c "
import lambda_function
result = lambda_function.lambda_handler({
    'search_terms': ['test', 'keyword'],
    'recipient_emails': ['your-email@example.com']
}, None)
print(result)
"
```

### Test on AWS
```bash
# Invoke the deployed function
aws lambda invoke \
    --function-name cause-list-checker \
    --region us-east-1 \
    --payload '{"search_terms": ["test"], "recipient_emails": ["your-email@example.com"]}' \
    response.json

cat response.json
```

### Monitor Logs
```bash
# Watch live logs
aws logs tail /aws/lambda/cause-list-checker --follow --region us-east-1
```

## 💰 Cost (FREE!)
- **Lambda**: 50 executions × 30s = 1,500 seconds/month (vs 400,000 free)
- **CloudWatch Logs**: ~100MB logs (vs 5GB free)
- **EventBridge**: 50 events (vs 14M free)

**Total: $0/month** ✅

## 🛠️ File Structure
```
cause-list-checker/
├── lambda_function.py       # ← All your app logic (340 lines)
├── lambda_requirements.txt  # ← Just 4 dependencies  
├── setup-iam.sh           # ← One-time IAM setup
├── deploy-simple.sh        # ← Deploy & update function
└── README-Simple.md        # ← This file
```

## 🔄 Updates
To update your function or settings:
1. Edit `lambda_function.py` (for code changes)
2. Edit `deploy-simple.sh` (for environment variables)
3. Run `./deploy-simple.sh`

## 🧹 Cleanup
To remove everything:
```bash
# Delete the function
aws lambda delete-function --function-name cause-list-checker --region us-east-1

# Delete the schedule
aws events delete-rule --name cause-list-checker-schedule --region us-east-1

# Delete IAM role (optional)
aws iam delete-role --role-name lambda-execution-role
```

## 🆘 Troubleshooting

### "AccessDenied" errors
- Make sure your AWS user has sufficient permissions
- Try attaching `PowerUserAccess` policy

### "Role not found" errors  
- Run `./setup-iam.sh` first
- Wait 10 seconds after role creation

### Email not sending
- Use Gmail **app password**, not regular password
- Enable 2-Step Verification first
- Check the sender email in environment variables

### No PDFs found
- Check your `CL_BASE_URL` and `FORM_ACTION_URL` values
- Test the URLs manually in browser

This approach is **10x simpler** than the SAM template - just one Python file that does everything! 🎯 