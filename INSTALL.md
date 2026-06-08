# Installation & Security Setup Guide

## Quick Start (Secure)

```bash
# 1. Clone repo
git clone https://github.com/BlazeO8/B.L.A.Z.E-personalized-AI-agent.git
cd B.L.A.Z.E-personalized-AI-agent

# 2. Create .env from template
cp .env.example .env

# 3. Generate strong API token
python -c "import secrets; print(secrets.token_urlsafe(32))"
# Copy output and paste into .env as API_TOKEN=<output>

# 4. Add your API keys to .env
# - GROQ_API_KEY from https://console.groq.com (REQUIRED)
# - WEATHER_API_KEY from openweathermap.org (optional)
# - NEWS_API_KEY from newsapi.org (optional)
# - BLAZE_CITY with your city name

# 5. Install dependencies
pip install -r necessary\ things/requirements.txt

# 6. Setup pre-commit hooks (prevent secret commits)
pip install pre-commit
pre-commit install

# 7. Run server
cd "Blaze project"
python blaze_server.py

# 8. Access at http://localhost:8000
```

## Using the API

```bash
# Set token
TOKEN="your-api-token-from-step-3"

# Get status
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/status

# Get history
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/history

# WebSocket with token
wscat -H "Authorization: Bearer $TOKEN" ws://localhost:8000/ws
```

## Network Access (Wi-Fi)

To access from other devices on same Wi-Fi:

```env
# In .env:
SERVER_HOST=0.0.0.0
API_TOKEN=<strong-token>
REQUIRE_AUTH=true
IP_WHITELIST=127.0.0.1,192.168.1.100,192.168.1.101
```

## HTTPS (Production)

```bash
# Generate self-signed certificate
openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 365

# In .env:
ENABLE_HTTPS=true
CERT_FILE=./cert.pem
KEY_FILE=./key.pem
```

## Security Checklist

- [ ] `.env` file created and NOT committed to Git
- [ ] `API_TOKEN` is strong (32+ chars)
- [ ] `GROQ_API_KEY` added to `.env`
- [ ] `REQUIRE_AUTH=true` in `.env`
- [ ] Pre-commit hooks installed
- [ ] All sensitive data in `.env` (not in code)

## Environment Variables

```env
# Core
GROQ_API_KEY=              # REQUIRED
WEATHER_API_KEY=           # Optional
NEWS_API_KEY=              # Optional
BLAZE_CITY=                # Your city

# Security
API_TOKEN=                 # Generated token
REQUIRE_AUTH=true
IP_WHITELIST=              # Optional

# Server
SERVER_HOST=127.0.0.1      # 127.0.0.1 = localhost, 0.0.0.0 = network
SERVER_PORT=8000
```

## Support

- See [SECURITY.md](SECURITY.md) for security details
- See [README.md](README.md) for full documentation
- Check `~/.blaze/blaze.log` for error details