#!/bin/bash

# WeCom Feedback System - Databricks Deployment Script
# Deploy API service and dashboard to Databricks Apps

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  WeCom Feedback System - Databricks Deploy${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check databricks CLI
if ! command -v databricks &> /dev/null; then
    echo -e "${RED}❌ Error: databricks CLI not found${NC}"
    echo "Please install: pip install databricks-cli"
    exit 1
fi

echo -e "${GREEN}✅ Databricks CLI installed${NC}"

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
    echo -e "${GREEN}✅ Loaded .env configuration${NC}"
else
    echo -e "${YELLOW}⚠️  .env file not found, using defaults${NC}"
fi

# Configuration variables
WORKSPACE_PATH="/Workspace/Users/${USER}/feedback"
API_APP_NAME="feedback-api"
DASHBOARD_APP_NAME="feedback-dashboard"
SECRET_SCOPE="feedback-scope"

echo ""
echo -e "${BLUE}Configuration:${NC}"
echo "  Workspace path: ${WORKSPACE_PATH}"
echo "  API app name: ${API_APP_NAME}"
echo "  Dashboard name: ${DASHBOARD_APP_NAME}"
echo "  Secret Scope: ${SECRET_SCOPE}"
echo ""

# Ask for user email
read -p "Enter your Databricks user email: " USER_EMAIL
WORKSPACE_PATH="/Workspace/Users/${USER_EMAIL}/feedback"

echo ""
echo -e "${BLUE}Step 1: Configure Secrets${NC}"
echo "----------------------------------------"

# Check if secret scope exists
if databricks secrets list-scopes | grep -q "${SECRET_SCOPE}"; then
    echo -e "${YELLOW}⚠️  Secret scope '${SECRET_SCOPE}' already exists${NC}"
else
    echo "Creating secret scope: ${SECRET_SCOPE}"
    databricks secrets create-scope --scope ${SECRET_SCOPE}
    echo -e "${GREEN}✅ Secret scope created${NC}"
fi

# Configure secrets
echo ""
echo "Configuring Databricks connection..."

if [ -z "$DATABRICKS_HOST" ]; then
    read -p "Databricks Host (https://...): " DATABRICKS_HOST
fi

if [ -z "$DATABRICKS_TOKEN" ]; then
    read -sp "Databricks Token: " DATABRICKS_TOKEN
    echo ""
fi

read -sp "Webhook Secret (for API verification): " WEBHOOK_SECRET
echo ""

# Save secrets
echo "${DATABRICKS_HOST}" | databricks secrets put --scope ${SECRET_SCOPE} --key databricks-host
echo "${DATABRICKS_TOKEN}" | databricks secrets put --scope ${SECRET_SCOPE} --key databricks-token
echo "${WEBHOOK_SECRET}" | databricks secrets put --scope ${SECRET_SCOPE} --key webhook-secret

echo -e "${GREEN}✅ Secrets configured${NC}"

echo ""
echo -e "${BLUE}Step 2: Upload code to Workspace${NC}"
echo "----------------------------------------"

# Create directories
databricks workspace mkdirs ${WORKSPACE_PATH}
databricks workspace mkdirs ${WORKSPACE_PATH}/api
databricks workspace mkdirs ${WORKSPACE_PATH}/dashboard

# Upload API files
echo "Uploading API service files..."
databricks workspace import databricks_app/api_app.py \
    ${WORKSPACE_PATH}/api/api_app.py --language PYTHON --overwrite

databricks workspace import databricks_app/requirements.txt \
    ${WORKSPACE_PATH}/api/requirements.txt --overwrite

databricks workspace import databricks_app/databricks-api-app.yaml \
    ${WORKSPACE_PATH}/api/databricks-api-app.yaml --overwrite

echo -e "${GREEN}✅ API files uploaded${NC}"

# Upload dashboard files
echo "Uploading dashboard files..."
databricks workspace import databricks_app/app.py \
    ${WORKSPACE_PATH}/dashboard/app.py --language PYTHON --overwrite

databricks workspace import databricks_app/requirements.txt \
    ${WORKSPACE_PATH}/dashboard/requirements.txt --overwrite

databricks workspace import databricks_app/databricks-app.yaml \
    ${WORKSPACE_PATH}/dashboard/databricks-app.yaml --overwrite

echo -e "${GREEN}✅ Dashboard files uploaded${NC}"

echo ""
echo -e "${BLUE}Step 3: Deploy applications${NC}"
echo "----------------------------------------"

# Deploy API service
echo "Deploying API service..."
if databricks apps list | grep -q "${API_APP_NAME}"; then
    echo "Updating existing app..."
    databricks apps deploy ${API_APP_NAME}
else
    echo "Creating new app..."
    databricks apps create \
        --name ${API_APP_NAME} \
        --source-code-path ${WORKSPACE_PATH}/api \
        --config-file ${WORKSPACE_PATH}/api/databricks-api-app.yaml
    
    databricks apps deploy ${API_APP_NAME}
fi

echo -e "${GREEN}✅ API service deployed${NC}"

# Deploy dashboard
echo ""
echo "Deploying dashboard..."
if databricks apps list | grep -q "${DASHBOARD_APP_NAME}"; then
    echo "Updating existing app..."
    databricks apps deploy ${DASHBOARD_APP_NAME}
else
    echo "Creating new app..."
    databricks apps create \
        --name ${DASHBOARD_APP_NAME} \
        --source-code-path ${WORKSPACE_PATH}/dashboard \
        --config-file ${WORKSPACE_PATH}/dashboard/databricks-app.yaml
    
    databricks apps deploy ${DASHBOARD_APP_NAME}
fi

echo -e "${GREEN}✅ Dashboard deployed${NC}"

echo ""
echo -e "${BLUE}Step 4: Get application URLs${NC}"
echo "----------------------------------------"

# Get app info
API_INFO=$(databricks apps get ${API_APP_NAME})
DASHBOARD_INFO=$(databricks apps get ${DASHBOARD_APP_NAME})

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}Application Info:${NC}"
echo ""
echo -e "${YELLOW}API Service:${NC}"
echo "  Name: ${API_APP_NAME}"
echo "  Status: Running"
echo "  View details: databricks apps get ${API_APP_NAME}"
echo ""
echo -e "${YELLOW}Dashboard:${NC}"
echo "  Name: ${DASHBOARD_APP_NAME}"
echo "  Status: Running"
echo "  View details: databricks apps get ${DASHBOARD_APP_NAME}"
echo ""
echo -e "${BLUE}Next Steps:${NC}"
echo "1. View application URLs in Databricks console"
echo "2. Configure WeCom webhook to point to your API endpoint"
echo "3. Test the webhook: POST /api/wecom/callback"
echo ""
echo -e "${GREEN}Deployment successful! 🎉${NC}"
