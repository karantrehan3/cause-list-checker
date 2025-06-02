#!/bin/bash

# Setup IAM role for Lambda function
set -e

ROLE_NAME="lambda-execution-role"
POLICY_NAME="lambda-execution-policy"

echo "🔐 Setting up IAM role for Lambda..."

# Create trust policy for Lambda
cat > trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# Create execution policy
cat > execution-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    }
  ]
}
EOF

# Check if role exists
if aws iam get-role --role-name $ROLE_NAME > /dev/null 2>&1; then
    echo "🔄 Role $ROLE_NAME already exists"
else
    echo "🆕 Creating IAM role: $ROLE_NAME"
    aws iam create-role \
        --role-name $ROLE_NAME \
        --assume-role-policy-document file://trust-policy.json
fi

# Attach AWS managed policy for basic Lambda execution
aws iam attach-role-policy \
    --role-name $ROLE_NAME \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

# Create and attach custom policy if it doesn't exist
if aws iam get-policy --policy-arn arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):policy/$POLICY_NAME > /dev/null 2>&1; then
    echo "🔄 Policy $POLICY_NAME already exists"
else
    echo "🆕 Creating custom policy: $POLICY_NAME"
    aws iam create-policy \
        --policy-name $POLICY_NAME \
        --policy-document file://execution-policy.json
fi

# Attach custom policy
aws iam attach-role-policy \
    --role-name $ROLE_NAME \
    --policy-arn arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):policy/$POLICY_NAME

echo "🧹 Cleaning up temporary files..."
rm -f trust-policy.json execution-policy.json

echo "✅ IAM role setup completed!"
echo "📋 Role ARN: arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):role/$ROLE_NAME"
echo ""
echo "⏰ Waiting 10 seconds for role to propagate..."
sleep 10
echo "✅ Ready to deploy Lambda function!" 