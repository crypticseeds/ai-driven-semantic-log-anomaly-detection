#!/bin/bash
# Doppler Setup Script for AI Log Analytics
# This script helps set up Doppler secrets management for the project

set -e

PROJECT_NAME="ai-log-analytics"
CONFIG_NAME="dev"

echo "🔐 Doppler Secrets Management Setup"
echo "=================================="
echo ""

# Check if Doppler CLI is installed
if ! command -v doppler &> /dev/null; then
    echo "❌ Doppler CLI is not installed."
    echo "Please install it first: https://docs.doppler.com/docs/install-cli"
    exit 1
fi

echo "✅ Doppler CLI found"
echo ""

# Check if user is authenticated
if ! doppler me &> /dev/null; then
    echo "⚠️  Not authenticated with Doppler. Please run: doppler login"
    exit 1
fi

echo "✅ Authenticated with Doppler"
echo ""

# Check if project exists
if doppler projects get "$PROJECT_NAME" &> /dev/null; then
    echo "✅ Project '$PROJECT_NAME' already exists"
else
    echo "📦 Creating project '$PROJECT_NAME'..."
    doppler projects create "$PROJECT_NAME"
    echo "✅ Project created"
fi

echo ""

# Setup project configuration
echo "⚙️  Setting up configuration '$CONFIG_NAME'..."
doppler setup --project "$PROJECT_NAME" --config "$CONFIG_NAME" --no-interactive
echo "✅ Configuration set up"
echo ""

# Prompt for secrets
echo "📝 Adding secrets to Doppler..."
echo "You can add secrets now or later via: doppler secrets set KEY=value"
echo ""

read -p "Do you want to add secrets now? (y/n) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "Adding required secrets..."
    echo "(Press Enter to skip any secret)"
    echo ""
    
    read -p "DATABASE_URL (e.g., postgresql://ailog:changeme@localhost:5432/ailog): " db_url
    if [ -n "$db_url" ]; then
        doppler secrets set DATABASE_URL="$db_url"
        echo "✅ DATABASE_URL set"
    fi
    
    read -p "KAFKA_BOOTSTRAP_SERVERS (e.g., localhost:9092): " kafka_servers
    if [ -n "$kafka_servers" ]; then
        doppler secrets set KAFKA_BOOTSTRAP_SERVERS="$kafka_servers"
        echo "✅ KAFKA_BOOTSTRAP_SERVERS set"
    fi
    
    echo ""
    echo "Optional secrets (press Enter to skip):"
    
    read -p "OPENAI_API_KEY: " openai_key
    if [ -n "$openai_key" ]; then
        doppler secrets set OPENAI_API_KEY="$openai_key"
        echo "✅ OPENAI_API_KEY set"
    fi
    
    read -p "QDRANT_URL: " qdrant_url
    if [ -n "$qdrant_url" ]; then
        doppler secrets set QDRANT_URL="$qdrant_url"
        echo "✅ QDRANT_URL set"
    fi
    
    read -p "QDRANT_API_KEY: " qdrant_key
    if [ -n "$qdrant_key" ]; then
        doppler secrets set QDRANT_API_KEY="$qdrant_key"
        echo "✅ QDRANT_API_KEY set"
    fi
    
    read -p "LANGFUSE_SECRET_KEY: " langfuse_secret
    if [ -n "$langfuse_secret" ]; then
        doppler secrets set LANGFUSE_SECRET_KEY="$langfuse_secret"
        echo "✅ LANGFUSE_SECRET_KEY set"
    fi
    
    read -p "LANGFUSE_PUBLIC_KEY: " langfuse_public
    if [ -n "$langfuse_public" ]; then
        doppler secrets set LANGFUSE_PUBLIC_KEY="$langfuse_public"
        echo "✅ LANGFUSE_PUBLIC_KEY set"
    fi
    
    read -p "LANGFUSE_HOST (default: http://langfuse:3000): " langfuse_host
    if [ -n "$langfuse_host" ]; then
        doppler secrets set LANGFUSE_HOST="$langfuse_host"
        echo "✅ LANGFUSE_HOST set"
    fi
fi

echo ""
echo "🎉 Doppler setup complete!"
echo ""
echo "Next steps:"
echo "1. Run the app with: doppler run -- uvicorn app.main:app"
echo "2. Or use with Docker: doppler run -- docker-compose up"
echo "3. View secrets: doppler secrets"
echo "4. Update secrets: doppler secrets set KEY=value"
echo ""

