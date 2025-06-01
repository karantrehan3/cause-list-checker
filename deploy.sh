#!/bin/bash

# Deployment script for Cause List Checker Lambda function
# This script deploys the application using AWS SAM with free AWS services

set -e

STACK_NAME="cause-list-checker"
REGION="us-east-1"  # Change this to your preferred region
PARAMETER_FILE="deploy-parameters.json"

echo "🚀 Starting deployment of Cause List Checker to AWS Lambda..."

# Check if AWS CLI is configured
if ! aws sts get-caller-identity > /dev/null 2>&1; then
    echo "❌ AWS CLI is not configured. Please run 'aws configure' first."
    exit 1
fi

# Check if SAM CLI is installed
if ! command -v sam &> /dev/null; then
    echo "❌ AWS SAM CLI is not installed. Please install it first:"
    echo "   https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html"
    exit 1
fi

# Check if parameter file exists
if [ ! -f "$PARAMETER_FILE" ]; then
    echo "❌ Parameter file '$PARAMETER_FILE' not found."
    echo "   Please copy deploy-parameters.json.example and customize it with your values."
    exit 1
fi

echo "📦 Building SAM application..."
sam build

echo "🔧 Validating template..."
sam validate

echo "☁️  Deploying to AWS..."
sam deploy \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --capabilities CAPABILITY_IAM \
    --parameter-overrides file://"$PARAMETER_FILE" \
    --no-confirm-changeset \
    --no-fail-on-empty-changeset

echo "✅ Deployment completed successfully!"

# Get the API endpoint
ENDPOINT=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`ApiGatewayEndpoint`].OutputValue' \
    --output text)

echo ""
echo "🎉 Your Cause List Checker is now running on AWS Lambda!"
echo "📍 API Endpoint: $ENDPOINT"
echo "🏥 Health Check: ${ENDPOINT}health"
echo ""
echo "💡 To test your deployment:"
echo "   curl ${ENDPOINT}health"
echo ""
echo "🔧 To update configuration later:"
echo "   1. Edit deploy-parameters.json"
echo "   2. Run this script again"
echo ""
echo "📊 Monitor your function in AWS Console:"
echo "   https://console.aws.amazon.com/lambda/home?region=$REGION#/functions" 