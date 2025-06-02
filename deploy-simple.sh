#!/bin/bash

# Simple Lambda deployment script
set -e

FUNCTION_NAME="cause-list-checker"
REGION="us-east-1"
RUNTIME="python3.9"
TIMEOUT="900"  # 15 minutes
MEMORY="512"   # 512 MB

echo "🚀 Deploying simple Lambda function..."

# Create deployment package
echo "📦 Creating deployment package..."
rm -rf lambda_package
mkdir lambda_package

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r lambda_requirements.txt -t lambda_package/

# Copy function code
cp lambda_function.py lambda_package/

# Create zip file
cd lambda_package
zip -r ../lambda_function.zip .
cd ..

echo "☁️  Deploying to AWS Lambda..."

# Check if function exists
if aws lambda get-function --function-name $FUNCTION_NAME --region $REGION > /dev/null 2>&1; then
    echo "🔄 Updating existing function..."
    aws lambda update-function-code \
        --function-name $FUNCTION_NAME \
        --zip-file fileb://lambda_function.zip \
        --region $REGION
    
    aws lambda update-function-configuration \
        --function-name $FUNCTION_NAME \
        --timeout $TIMEOUT \
        --memory-size $MEMORY \
        --region $REGION
else
    echo "🆕 Creating new function..."
    aws lambda create-function \
        --function-name $FUNCTION_NAME \
        --runtime $RUNTIME \
        --role arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):role/lambda-execution-role \
        --handler lambda_function.lambda_handler \
        --zip-file fileb://lambda_function.zip \
        --timeout $TIMEOUT \
        --memory-size $MEMORY \
        --region $REGION
fi

echo "📧 Setting environment variables..."
aws lambda update-function-configuration \
    --function-name $FUNCTION_NAME \
    --environment Variables="{
        SEARCH_TERMS=\"your,keywords,here\",
        EMAIL_RECIPIENTS=\"your-email@example.com\",
        SENDER_EMAIL=\"your-sender@gmail.com\",
        SENDER_PASSWORD=\"your-app-password\",
        SENDER_NAME=\"Cause List Checker\",
        CL_BASE_URL=\"https://your-causelist-url.com\",
        MAIN_BASE_URL=\"https://your-main-url.com\",
        FORM_ACTION_URL=\"https://your-site.com/form\"
    }" \
    --region $REGION

echo "⏰ Setting up EventBridge schedule..."
# Create EventBridge rule for daily execution
aws events put-rule \
    --name cause-list-checker-schedule \
    --schedule-expression "cron(30 4,7,8,9,10,11,12,13,14,15,16,17 * * ? *)" \
    --state ENABLED \
    --region $REGION

# Add permission for EventBridge to invoke Lambda
aws lambda add-permission \
    --function-name $FUNCTION_NAME \
    --statement-id eventbridge-invoke \
    --action lambda:InvokeFunction \
    --principal events.amazonaws.com \
    --source-arn arn:aws:events:$REGION:$(aws sts get-caller-identity --query Account --output text):rule/cause-list-checker-schedule \
    --region $REGION

# Add Lambda target to EventBridge rule
aws events put-targets \
    --rule cause-list-checker-schedule \
    --targets "Id"="1","Arn"="arn:aws:lambda:$REGION:$(aws sts get-caller-identity --query Account --output text):function:$FUNCTION_NAME" \
    --region $REGION

echo "🧹 Cleaning up..."
rm -rf lambda_package lambda_function.zip

echo "✅ Deployment completed!"
echo ""
echo "🎉 Your Lambda function is now deployed and scheduled!"
echo "📋 Function Name: $FUNCTION_NAME"
echo "⏰ Schedule: Runs daily at specified times (IST)"
echo ""
echo "🔧 To update environment variables:"
echo "   Edit this script and run again, or use AWS Console"
echo ""
echo "🧪 To test manually:"
echo "   aws lambda invoke --function-name $FUNCTION_NAME --region $REGION response.json"
echo ""
echo "📊 Monitor logs:"
echo "   aws logs tail /aws/lambda/$FUNCTION_NAME --follow --region $REGION" 