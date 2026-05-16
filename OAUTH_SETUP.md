# OAuth Configuration Guide

This document describes how to set up OAuth 2.0 integrations for JARVIS CoWork.

## Overview

JARVIS supports three OAuth providers:
- **Slack**: team chat, message posting, file sharing
- **Google Drive**: file storage, collaboration
- **GitHub**: repository access, issue management

All integration tokens are **encrypted at rest** using Fernet (AES-128-CBC) and stored in the database.

## Prerequisites

1. Node.js & npm (for Yjs server)
2. Python 3.8+ with dependencies installed (`pip install -r requirements.txt`)
3. A public HTTPS URL or ngrok tunnel for local testing
4. Database initialized (`python -m backend.database` or auto-init on startup)

## Setting Up Environment Variables

Create a `.env` file in the repository root or set environment variables:

```bash
# Token encryption (auto-generated on first run if missing)
# INTEGRATIONS_ENCRYPTION_KEY=<base64-encoded-32-byte-key>

# Slack OAuth
SLACK_CLIENT_ID=<your-slack-client-id>
SLACK_CLIENT_SECRET=<your-slack-client-secret>
SLACK_REDIRECT_URI=/integrations/slack/oauth_callback

# Google Drive OAuth
GOOGLE_CLIENT_ID=<your-google-client-id>
GOOGLE_CLIENT_SECRET=<your-google-client-secret>
GOOGLE_REDIRECT_URI=/integrations/drive/oauth_callback

# GitHub OAuth
GITHUB_CLIENT_ID=<your-github-client-id>
GITHUB_CLIENT_SECRET=<your-github-client-secret>
GITHUB_REDIRECT_URI=/integrations/github/oauth_callback
```

## 1. Slack Integration

### Create Slack App

1. Go to https://api.slack.com/apps
2. Click "Create New App" → "From scratch"
3. Name: "JARVIS CoWork", Workspace: select your workspace
4. Go to **OAuth & Permissions**
5. Add redirect URL under **Redirect URLs**:
   - Local: `http://127.0.0.1:8000/integrations/slack/oauth_callback`
   - Production: `https://yourhost.com/integrations/slack/oauth_callback`
6. Under **Scopes**, add:
   - `chat:write` - post messages
   - `channels:read` - list channels
   - `files:write` - upload files
7. Install to workspace (top of page)
8. Copy **Client ID** and **Client Secret** to `.env`

### Test Slack OAuth

```bash
# 1. Start backend
python -m uvicorn backend.main:app --reload

# 2. Visit install endpoint
curl http://127.0.0.1:8000/integrations/slack/install

# 3. Authorize and verify token is saved
# 4. Post a message
curl -X POST http://127.0.0.1:8000/integrations/slack/post_message \
  -H "Content-Type: application/json" \
  -d '{"channel": "#general", "message": "Hello from JARVIS!"}'
```

## 2. Google Drive Integration

### Create OAuth Credentials

1. Go to https://console.cloud.google.com
2. Create a new project: "JARVIS CoWork"
3. Go to **APIs & Services** → **Credentials**
4. Click "Create Credentials" → "OAuth client ID"
5. Application type: "Web application"
6. Add authorized redirect URIs:
   - Local: `http://127.0.0.1:8000/integrations/drive/oauth_callback`
   - Production: `https://yourhost.com/integrations/drive/oauth_callback`
7. Copy **Client ID** and **Client Secret** to `.env`
8. Enable **Google Drive API** (APIs & Services → Library → search "Google Drive API")

### Test Google Drive OAuth

```bash
# 1. Start backend
python -m uvicorn backend.main:app --reload

# 2. Visit install endpoint (requires login)
curl http://127.0.0.1:8000/integrations/drive/install

# 3. Authorize and verify token is saved
# 4. List files (requires auth token in headers)
curl -H "Authorization: Bearer <jwt-token>" \
  http://127.0.0.1:8000/integrations/drive/files
```

## 3. GitHub Integration

### Create GitHub OAuth App

1. Go to https://github.com/settings/developers
2. Click "New OAuth App"
3. Fill in:
   - Application name: "JARVIS CoWork"
   - Homepage URL: `http://127.0.0.1:8000` (local) or `https://yourhost.com` (prod)
   - Authorization callback URL:
     - Local: `http://127.0.0.1:8000/integrations/github/oauth_callback`
     - Production: `https://yourhost.com/integrations/github/oauth_callback`
4. Copy **Client ID** and **Client Secret** to `.env`

### Test GitHub OAuth

```bash
# 1. Start backend
python -m uvicorn backend.main:app --reload

# 2. Visit install endpoint
curl http://127.0.0.1:8000/integrations/github/install

# 3. Authorize and verify token is saved
# 4. List repositories
curl -H "Authorization: Bearer <jwt-token>" \
  http://127.0.0.1:8000/integrations/github/repos
```

## Using ngrok for Local Testing

For local development with public redirect URIs:

```bash
# Install ngrok
# https://ngrok.com/download

# Start ngrok tunnel
ngrok http 8000

# Note the public URL (e.g., https://abc123.ngrok.io)

# Update OAuth app redirect URIs to:
# https://abc123.ngrok.io/integrations/{slack|drive|github}/oauth_callback

# Test with public URL
curl https://abc123.ngrok.io/integrations/slack/install
```

## Token Storage & Encryption

### How It Works

1. User authorizes OAuth app
2. Access token exchanged with provider
3. Token encrypted with Fernet key (INTEGRATIONS_ENCRYPTION_KEY)
4. Ciphertext stored in `integration_tokens` DB table
5. On retrieval, decrypted in-memory (never logged or cached)

### Rotating Encryption Key

⚠️ **Warning**: Changing the encryption key invalidates all stored tokens.

```python
from backend.integrations.token_storage import get_key, Fernet
import base64, os

# Generate new key
new_key = base64.urlsafe_b64encode(os.urandom(32)).decode()
os.environ['INTEGRATIONS_ENCRYPTION_KEY'] = new_key

# Re-encrypt all tokens (not implemented yet; manual migration required)
# For now, users must re-authorize after key rotation
```

## Testing Token Encryption

```bash
python -c "
from backend.integrations.token_storage import encrypt_token, decrypt_token
token = 'xoxb-123456789'
enc = encrypt_token(token)
print(f'Encrypted: {enc}')
dec = decrypt_token(enc)
print(f'Decrypted: {dec}')
assert dec == token
print('✓ Encryption working')
"
```

## Troubleshooting

### "OAuth not configured" error
- Ensure environment variables are set: `echo $SLACK_CLIENT_ID`
- Restart backend after setting env vars

### "Token not found" error
- User has not authorized the integration yet
- Visit `/integrations/{provider}/install` to authorize

### Redirect URI mismatch
- Ensure callback URL in OAuth app settings matches your public URL
- For local testing, use ngrok and update app settings

### Token expired / 401 errors
- Google Drive tokens refresh automatically
- GitHub tokens don't expire (valid indefinitely unless revoked)
- Slack tokens valid for ~12 hours; re-authorize if needed

## Production Checklist

- [ ] All OAuth apps configured with production redirect URLs
- [ ] HTTPS enabled (see WebRTC_SETUP.md)
- [ ] INTEGRATIONS_ENCRYPTION_KEY set in secrets manager
- [ ] Database backups configured
- [ ] Token rotation/cleanup job (optional)
- [ ] Rate limiting on OAuth endpoints
- [ ] CSRF protection enabled
- [ ] Audit logging for token access (optional)
