#!/bin/bash
set -e

FUNCTION_NAME="cause-list-checker"
REGION="ap-south-1"
PYTHON_VERSION="3.13"
BUILD_DIR="lambda_build"
ZIP_FILE="lambda_deployment.zip"

echo "=== Lambda Deployment Script ==="

# Clean previous build
echo "Cleaning previous build..."
rm -rf "$BUILD_DIR" "$ZIP_FILE"
mkdir "$BUILD_DIR"

# Install dependencies for Amazon Linux
echo "Installing dependencies for Python $PYTHON_VERSION (Amazon Linux)..."
pip install \
  --platform manylinux2014_x86_64 \
  --target "$BUILD_DIR/" \
  --implementation cp \
  --python-version "$PYTHON_VERSION" \
  --only-binary=:all: \
  -r requirements-lambda.txt \
  --quiet

# Copy application code
echo "Copying application code..."
cp -r app/ "$BUILD_DIR/app/"
cp lambda_handler.py "$BUILD_DIR/"

# Create zip
echo "Creating deployment zip..."
cd "$BUILD_DIR"
zip -r "../$ZIP_FILE" . -q
cd ..

ZIP_SIZE=$(du -h "$ZIP_FILE" | cut -f1)
echo "Deployment zip created: $ZIP_FILE ($ZIP_SIZE)"

# Check if AWS CLI is available
if ! command -v aws &> /dev/null; then
  echo ""
  echo "AWS CLI not found. Upload manually:"
  echo "  Lambda > cause-list-checker > Code > Upload from > .zip file"
  exit 0
fi

# Deploy to Lambda
echo "Deploying to Lambda function: $FUNCTION_NAME..."
aws lambda update-function-code \
  --function-name "$FUNCTION_NAME" \
  --zip-file "fileb://$ZIP_FILE" \
  --region "$REGION" \
  --no-cli-pager

echo ""
echo "=== Deployment complete ==="
