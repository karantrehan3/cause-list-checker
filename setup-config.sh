#!/bin/bash

# Configuration setup script for Cause List Checker
# This script helps you set up your deployment parameters interactively

set -e

CONFIG_FILE="deploy-parameters.json"
BACKUP_FILE="deploy-parameters.json.backup"

echo "🔧 Cause List Checker - Configuration Setup"
echo "==========================================="
echo ""

# Backup existing config if it exists
if [ -f "$CONFIG_FILE" ]; then
    echo "📋 Creating backup of existing configuration..."
    cp "$CONFIG_FILE" "$BACKUP_FILE"
    echo "   Backup saved as: $BACKUP_FILE"
    echo ""
fi

echo "Please provide the following configuration values:"
echo "(Press Enter to keep default values shown in brackets)"
echo ""

# Function to prompt for input with default
prompt_with_default() {
    local prompt_text="$1"
    local default_value="$2"
    local is_secret="$3"
    
    if [ "$is_secret" = "true" ]; then
        echo -n "$prompt_text [$default_value]: "
        read -s user_input
        echo ""  # New line after hidden input
    else
        echo -n "$prompt_text [$default_value]: "
        read user_input
    fi
    
    if [ -z "$user_input" ]; then
        echo "$default_value"
    else
        echo "$user_input"
    fi
}

# Collect configuration
AUTH_HEADER=$(prompt_with_default "🔑 Authorization Header (e.g., 'Bearer token123')" "Bearer your-auth-token-here" "true")

echo ""
echo "📧 Email Configuration:"
SENDER_EMAIL=$(prompt_with_default "   Sender Email" "your-email@gmail.com" "false")
SENDER_PASSWORD=$(prompt_with_default "   Sender App Password" "your-app-password-here" "true")
SENDER_NAME=$(prompt_with_default "   Sender Display Name" "Cause List Checker" "false")
EMAIL_RECIPIENTS=$(prompt_with_default "   Recipients (comma-separated)" "recipient1@example.com,recipient2@example.com" "false")

echo ""
echo "🌐 Website URLs:"
CL_BASE_URL=$(prompt_with_default "   Cause List Base URL" "https://your-causelist-base-url.com" "false")
MAIN_BASE_URL=$(prompt_with_default "   Main Base URL" "https://your-main-base-url.com" "false")
FORM_ACTION_URL=$(prompt_with_default "   Form Action URL" "https://your-site.com/form-action" "false")
CASE_SEARCH_URL=$(prompt_with_default "   Case Search URL" "https://your-site.com/case-search" "false")
CASE_DETAILS_URL=$(prompt_with_default "   Case Details URL" "https://your-site.com/case-details" "false")

echo ""
echo "🔍 Search Configuration:"
echo "   Enter search terms (comma-separated, e.g., 'John Doe,Case123'):"
read -r SEARCH_TERMS
if [ -z "$SEARCH_TERMS" ]; then
    SEARCH_TERMS="your,keyword,here"
fi

# Convert search terms to JSON array
IFS=',' read -ra TERMS_ARRAY <<< "$SEARCH_TERMS"
SEARCH_TERMS_JSON="["
for i in "${!TERMS_ARRAY[@]}"; do
    term=$(echo "${TERMS_ARRAY[$i]}" | xargs)  # Trim whitespace
    if [ $i -eq 0 ]; then
        SEARCH_TERMS_JSON+="\"$term\""
    else
        SEARCH_TERMS_JSON+=", \"$term\""
    fi
done
SEARCH_TERMS_JSON+="]"

# Create request body JSON
REQUEST_BODY="{\\\"search_terms\\\": $SEARCH_TERMS_JSON, \\\"date\\\": null, \\\"recipient_emails\\\": [\\\"$EMAIL_RECIPIENTS\\\"]}"

# Generate the configuration file
cat > "$CONFIG_FILE" << EOF
[
  {
    "ParameterKey": "AuthHeader",
    "ParameterValue": "$AUTH_HEADER"
  },
  {
    "ParameterKey": "RequestBodyJson",
    "ParameterValue": "$REQUEST_BODY"
  },
  {
    "ParameterKey": "SenderEmail",
    "ParameterValue": "$SENDER_EMAIL"
  },
  {
    "ParameterKey": "SenderPassword",
    "ParameterValue": "$SENDER_PASSWORD"
  },
  {
    "ParameterKey": "SenderName",
    "ParameterValue": "$SENDER_NAME"
  },
  {
    "ParameterKey": "EmailRecipients",
    "ParameterValue": "$EMAIL_RECIPIENTS"
  },
  {
    "ParameterKey": "CLBaseURL",
    "ParameterValue": "$CL_BASE_URL"
  },
  {
    "ParameterKey": "MainBaseURL",
    "ParameterValue": "$MAIN_BASE_URL"
  },
  {
    "ParameterKey": "FormActionURL",
    "ParameterValue": "$FORM_ACTION_URL"
  },
  {
    "ParameterKey": "CaseSearchURL",
    "ParameterValue": "$CASE_SEARCH_URL"
  },
  {
    "ParameterKey": "CaseDetailsURL",
    "ParameterValue": "$CASE_DETAILS_URL"
  }
]
EOF

echo ""
echo "✅ Configuration saved to $CONFIG_FILE"
echo ""
echo "🚀 Next steps:"
echo "   1. Review your configuration: cat $CONFIG_FILE"
echo "   2. Deploy to AWS: ./deploy.sh"
echo ""
echo "💡 To update configuration later:"
echo "   - Run this script again, or"
echo "   - Edit $CONFIG_FILE manually" 