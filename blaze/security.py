"""
B.L.A.Z.E — Security & Authentication Middleware
Handles authentication, rate limiting, input validation, and security headers.
"""

import time
import logging
import re
from datetime import datetime
from functools import lru_cache
from typing import Optional, List
from collections import defaultdict

from fastapi import Request, HTTPException, WebSocket, WebSocketDisconnect
from starlette.responses import JSONResponse

from blaze.config import (
    API_TOKEN, REQUIRE_AUTH, IP_WHITELIST, RATE_LIMIT_REQUESTS,
    RATE_LIMIT_WINDOW, ENABLE_REQUEST_LOGGING, ENABLE_AUDIT_LOG,
    SECURITY_HEADERS, MAX_CONNECTIONS
)

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════════════════
#  Rate Limiting
# ════════════════════════════════════════════════════════════════════════════
class RateLimiter:
    """Simple rate limiter based on IP address."""
    
    def __init__(self, requests: int, window_minutes: int):
        self.requests = requests
        self.window_seconds = window_minutes * 60
        self.requests_by_ip: dict = defaultdict(list)
    
    def is_allowed(self, ip: str) -> bool:
        """Check if IP has exceeded rate limit."""
        now = time.time()
        cutoff = now - self.window_seconds
        
        # Clean old requests
        self.requests_by_ip[ip] = [
            req_time for req_time in self.requests_by_ip[ip]
            if req_time > cutoff
        ]
        
        # Check limit
        if len(self.requests_by_ip[ip]) >= self.requests:
            return False
        
        # Record new request
        self.requests_by_ip[ip].append(now)
        return True


rate_limiter = RateLimiter(RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW)

# ════════════════════════════════════════════════════════════════════════════
#  Authentication
# ════════════════════════════════════════════════════════════════════════════
def verify_token(token: Optional[str] = None) -> bool:
    """Verify API token for authentication."""
    if not REQUIRE_AUTH:
        return True
    
    if not token:
        raise HTTPException(status_code=401, detail="Missing authorization token")
    
    # Extract Bearer token if in format "Bearer <token>"
    if token.startswith("Bearer "):
        token = token[7:]
    
    if token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid authentication token")
    
    return True


async def verify_token_ws(websocket: WebSocket) -> bool:
    """Verify API token for WebSocket connections."""
    if not REQUIRE_AUTH:
        return True
    
    token = websocket.headers.get("Authorization")
    if not token:
        await websocket.close(code=1008, reason="Missing authorization token")
        raise WebSocketDisconnect("No auth token")
    
    if token.startswith("Bearer "):
        token = token[7:]
    
    if token != API_TOKEN:
        await websocket.close(code=1008, reason="Invalid authorization token")
        raise WebSocketDisconnect("Invalid token")
    
    return True

# ════════════════════════════════════════════════════════════════════════════
#  IP Whitelist
# ════════════════════════════════════════════════════════════════════════════
def is_ip_allowed(client_ip: str) -> bool:
    """Check if client IP is whitelisted."""
    if not IP_WHITELIST or IP_WHITELIST == ['']:
        return True  # No whitelist = allow all
    
    return client_ip in IP_WHITELIST


# ════════════════════════════════════════════════════════════════════════════
#  Request Logging & Audit
# ════════════════════════════════════════════════════════════════════════════
def log_request(method: str, path: str, client_ip: str, status_code: int = None):
    """Log API requests for audit trail."""
    if not ENABLE_REQUEST_LOGGING:
        return
    
    timestamp = datetime.now().isoformat()
    log_msg = f"[{timestamp}] {method} {path} from {client_ip}"
    
    if status_code:
        log_msg += f" → {status_code}"
    
    logger.info(log_msg)


def audit_security_event(event_type: str, details: dict):
    """Log security-related events."""
    if not ENABLE_AUDIT_LOG:
        return
    
    timestamp = datetime.now().isoformat()
    logger.warning(f"[SECURITY] [{timestamp}] {event_type}: {details}")


# ════════════════════════════════════════════════════════════════════════════
#  Input Validation
# ════════════════════════════════════════════════════════════════════════════
class InputValidator:
    """Validate and sanitize user inputs."""
    
    @staticmethod
    def validate_message(message: str, max_length: int = 5000) -> str:
        """Validate chat message."""
        if not message or not isinstance(message, str):
            raise ValueError("Message must be a non-empty string")
        
        if len(message) > max_length:
            raise ValueError(f"Message too long (max {max_length} characters)")
        
        # Remove potentially harmful characters but preserve normal text
        message = message.strip()
        return message
    
    @staticmethod
    def validate_time(time_str: str) -> bool:
        """Validate time format HH:MM."""
        pattern = r"^([0-1]\d|2[0-3]):[0-5]\d$"
        if not re.match(pattern, time_str):
            raise ValueError("Invalid time format. Use HH:MM (24-hour format)")
        return True
    
    @staticmethod
    def validate_city(city: str, max_length: int = 100) -> str:
        """Validate city name."""
        if not city or not isinstance(city, str):
            raise ValueError("City must be a non-empty string")
        
        if len(city) > max_length:
            raise ValueError(f"City name too long (max {max_length} characters)")
        
        # Only allow alphanumeric, spaces, and hyphens
        if not re.match(r"^[a-zA-Z0-9\s\-']+$", city):
            raise ValueError("City name contains invalid characters")
        
        return city.strip()
    
    @staticmethod
    def validate_name(name: str, max_length: int = 100) -> str:
        """Validate user name."""
        if not name or not isinstance(name, str):
            raise ValueError("Name must be a non-empty string")
        
        if len(name) > max_length:
            raise ValueError(f"Name too long (max {max_length} characters)")
        
        # Only allow alphanumeric, spaces, and basic punctuation
        if not re.match(r"^[a-zA-Z0-9\s\-'.,]+$", name):
            raise ValueError("Name contains invalid characters")
        
        return name.strip()
    
    @staticmethod
    def validate_rating(rating: int) -> int:
        """Validate feedback rating."""
        if not isinstance(rating, int) or rating < 1 or rating > 5:
            raise ValueError("Rating must be an integer between 1 and 5")
        return rating


validator = InputValidator()

# ════════════════════════════════════════════════════════════════════════════
#  Connection Management
# ════════════════════════════════════════════════════════════════════════════
class ConnectionLimiter:
    """Track and limit concurrent connections."""
    
    def __init__(self, max_connections: int):
        self.max_connections = max_connections
        self.active_connections: int = 0
    
    def can_connect(self) -> bool:
        """Check if new connection is allowed."""
        return self.active_connections < self.max_connections
    
    def increment(self):
        """Add a connection."""
        self.active_connections += 1
    
    def decrement(self):
        """Remove a connection."""
        self.active_connections = max(0, self.active_connections - 1)
    
    def get_count(self) -> int:
        """Get current connection count."""
        return self.active_connections


connection_limiter = ConnectionLimiter(MAX_CONNECTIONS)