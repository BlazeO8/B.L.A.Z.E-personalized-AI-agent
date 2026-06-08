# B.L.A.Z.E Security Policy & Guidelines

## 🔐 Security Features

### Authentication & Authorization
- **API Token Required**: All endpoints require `Authorization: Bearer <token>` header
- **Token Generation**: Use `python -c "import secrets; print(secrets.token_urlsafe(32))"`
- **Environment Variable**: Store token in `.env` file as `API_TOKEN=<your_token>`
- **WebSocket Auth**: WebSocket connections also require valid token in headers

### Rate Limiting
- **Default**: 100 requests per minute per IP address
- **Configurable**: Set `RATE_LIMIT_REQUESTS` and `RATE_LIMIT_WINDOW` in `.env`
- **Headers**: Returns `429 Too Many Requests` when limit exceeded

### CORS (Cross-Origin Resource Sharing)
- **Default Origins**: `http://localhost:8000`, `http://127.0.0.1:8000`
- **Restricted Methods**: Only `GET`, `POST`, `DELETE` allowed
- **Restricted Headers**: Only `Content-Type`, `Authorization` allowed
- **Development Only**: Set `ALLOW_ALL_ORIGINS=true` in `.env` (NOT for production)

### Input Validation
- **Message Length**: Max 5000 characters
- **Message Content**: Sanitized and validated
- **Time Format**: Must be `HH:MM` (24-hour format)
- **City/Name**: Alphanumeric + spaces/hyphens only
- **Rating**: Integer 1-5 only

### IP Whitelisting (Optional)
- Configure in `.env`: `IP_WHITELIST=127.0.0.1,192.168.1.100`
- Leave empty to allow all localhost connections
- Useful for Wi-Fi network access control

### HTTPS Support
- **Optional**: Set `ENABLE_HTTPS=true` in `.env`
- **Requires**: Certificate files (CERT_FILE, KEY_FILE paths)
- **Generate Self-Signed**: 
  ```bash
  openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 365
  ```

### Request Logging & Audit Trail
- All API requests logged with timestamp, method, path, client IP, status code
- Security events logged separately (auth failures, rate limits, IP blocks, etc.)
- Enable/disable with `ENABLE_REQUEST_LOGGING` and `ENABLE_AUDIT_LOG`

### Connection Management
- **Max Connections**: Default 50 concurrent WebSocket connections
- **Configurable**: Set `MAX_CONNECTIONS` in `.env`
- **Limit Enforcement**: New connections rejected when max reached

---

## 🔑 Secret Management

### API Keys
- **NEVER commit `.env` file** to Git
- **NEVER hardcode secrets** in Python files
- **Use `.env.example`** as template for setup
- **Rotate keys regularly** (every 3-6 months recommended)

### Encryption Key Storage
**Current (Less Secure):**
```
~/.blaze/blaze.key        ← Encryption key
~/.blaze/vault.enc        ← Encrypted vault
```

**Recommended (More Secure):**
- Move key to separate location (external drive, USB)
- Use OS-level key storage:
  - **Windows**: Credential Manager
  - **macOS**: Keychain
  - **Linux**: Secret Service / systemd

---

## 🛡️ Security Headers

All responses include:
```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Strict-Transport-Security: max-age=31536000 (HTTPS only)
```

---

## 📋 Pre-Deployment Checklist

Before going to production:

- [ ] Generate strong `API_TOKEN` and add to `.env`
- [ ] Set `REQUIRE_AUTH=true` in `.env`
- [ ] Set `DEBUG_MODE=false` in `.env`
- [ ] Set `ALLOW_ALL_ORIGINS=false` in `.env`
- [ ] Configure `SERVER_HOST` (127.0.0.1 for localhost, 0.0.0.0 for network)
- [ ] If network access needed: Configure `IP_WHITELIST` in `.env`
- [ ] If using HTTPS: Generate certificates and set paths
- [ ] Review all `RATE_LIMIT_*` settings
- [ ] Review `MAX_CONNECTIONS` setting
- [ ] Verify `.env` file is in `.gitignore`
- [ ] Run `pre-commit install` to enable secret detection
- [ ] Test authentication with token in header
- [ ] Test rate limiting
- [ ] Verify security headers in responses

---

## 🔄 Incident Response

### If API Token is Compromised:
1. Generate new token: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
2. Update `API_TOKEN` in `.env`
3. Restart B.L.A.Z.E server
4. Review audit logs

### If .env File is Leaked:
1. Rotate ALL API keys (Groq, Weather, News)
2. Generate new `API_TOKEN`
3. Update all keys in new `.env`
4. Restart server

---

**Version**: 2.0 - Security Hardened Edition