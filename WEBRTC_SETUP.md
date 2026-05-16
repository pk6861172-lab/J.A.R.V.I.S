# WebRTC TURN Server & HTTPS Setup Guide

This document describes how to set up reliable WebRTC connectivity using TURN servers and HTTPS/WSS.

## Overview

WebRTC peer-to-peer connections work best when:
1. Both peers have public IPs (unlikely in production)
2. NAT is traversed via STUN (often works)
3. Direct connection fails and TURN relays traffic (reliable)
4. All signaling is over secure WSS (WebSocket Secure)

This setup covers:
- Local TURN server (coturn) for testing
- HTTPS with self-signed or Let's Encrypt certificates
- WebSocket Secure (WSS) endpoints
- TURN configuration in frontend

## Prerequisites

- Ubuntu 18.04+ or Windows with WSL2
- Python 3.8+, Node.js 14+
- Public domain (for Let's Encrypt) or self-signed certs for local testing
- Port access: 3478 (TURN/STUN), 5349 (TURNS), 443 (HTTPS)

## 1. Local TURN Server Setup (Linux/WSL)

### Install coturn

```bash
sudo apt-get update
sudo apt-get install -y coturn

# Enable coturn service
sudo systemctl enable coturn
```

### Configure TURN Server

Edit `/etc/coturn/turnserver.conf`:

```bash
sudo nano /etc/coturn/turnserver.conf
```

Add/update these settings:

```conf
# STUN and TURN listening ports
listening-port=3478
listening-ip=0.0.0.0
relay-ip=127.0.0.1

# TURN credentials
user=jarvis:turnpassword
realm=example.com

# Logging
log-file=/var/log/coturn/turnserver.log
pidfile=/var/run/coturn.pid

# Performance
bps-capacity=1000000
max-bps=100000
min-bps=0

# Security
fingerprint
lt-cred-mech
```

### Start TURN Server

```bash
# Local testing (no sudo needed)
turnserver -c /etc/coturn/turnserver.conf -v

# Or via systemctl
sudo systemctl restart coturn
sudo systemctl status coturn

# Verify it's listening
netstat -tlnp | grep 3478
```

## 2. HTTPS & WSS Setup

### Option A: Local Self-Signed Certificate (Testing)

```bash
# Generate self-signed cert (valid 365 days)
openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes

# Move to backend directory
mkdir -p backend/certs
mv cert.pem key.pem backend/certs/
```

### Option B: Let's Encrypt (Production)

```bash
# Install certbot
sudo apt-get install -y certbot python3-certbot-nginx

# Get certificate for your domain
sudo certbot certonly --standalone -d yourdomain.com

# Certificates stored in:
# /etc/letsencrypt/live/yourdomain.com/fullchain.pem
# /etc/letsencrypt/live/yourdomain.com/privkey.pem

# Copy to backend
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem backend/certs/cert.pem
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem backend/certs/key.pem
sudo chown $USER:$USER backend/certs/*
```

## 3. Update FastAPI for HTTPS

Modify `backend/main.py` to use SSL:

```python
import ssl
import uvicorn

if __name__ == "__main__":
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(
        certfile="backend/certs/cert.pem",
        keyfile="backend/certs/key.pem"
    )
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8443,
        ssl_keyfile="backend/certs/key.pem",
        ssl_certfile="backend/certs/cert.pem"
    )
```

Or use Nginx as reverse proxy:

```nginx
server {
    listen 443 ssl http2;
    server_name yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
```

## 4. Update Frontend WebRTC Config

Create `backend/static/webrtc_config.js`:

```javascript
// TURN/STUN configuration for WebRTC
const ICE_SERVERS = [
  {
    urls: ['stun:stun.l.google.com:19302', 'stun:stun1.l.google.com:19302'],
    username: '',
    credential: ''
  },
  {
    urls: ['turn:turn.yourdomain.com:3478'],
    username: 'jarvis',
    credential: 'turnpassword'
  },
  {
    urls: ['turns:turn.yourdomain.com:5349'],
    username: 'jarvis',
    credential: 'turnpassword'
  }
];

const RTCPeerConfig = {
  iceServers: ICE_SERVERS,
  iceTransportPolicy: 'all' // or 'relay' to force TURN
};

// Usage in peer connection
const peerConnection = new RTCPeerConnection({
  iceServers: ICE_SERVERS
});
```

Update `backend/static/meeting.js` to use this config:

```javascript
const peerConnection = new RTCPeerConnection({
  iceServers: [
    { urls: ['stun:stun.l.google.com:19302'] },
    {
      urls: ['turn:turn.yourdomain.com:3478'],
      username: 'jarvis',
      credential: 'turnpassword'
    }
  ]
});
```

## 5. Test WebRTC Connectivity

### Check TURN Server

```bash
# Test STUN
nmap -sU -p 3478 turn.yourdomain.com

# Test TURN with credentials
turnutils_uclient -v -u jarvis -w turnpassword turn.yourdomain.com
```

### Test from Browser

1. Open https://yourdomain.com/meeting
2. Open DevTools (F12) → Network → WS filter
3. Join a meeting room with two browsers/windows
4. Verify WebSocket connection to wss://yourdomain.com/ws/meet/{room}
5. Check ICE candidates in WebRTC stats (DevTools → Chrome only)

### WebRTC Stats Inspector

```javascript
// In browser console during meeting
const pc = peerConnection; // from your code
pc.getStats().then(report => {
  report.forEach(now => {
    if (now.type === 'candidate-pair' && now.state === 'succeeded') {
      console.log('Active connection:', {
        local: now.localCandidateId,
        remote: now.remoteCandidateId,
        protocol: now.availableOutgoingBitrate,
        currentRoundTripTime: now.currentRoundTripTime
      });
    }
  });
});
```

## 6. Production Checklist

- [ ] TURN server running and accessible from public internet
- [ ] TURN credentials changed from defaults
- [ ] HTTPS/WSS enabled with valid certificates
- [ ] Firewall rules: allow 3478/tcp, 3478/udp, 5349/tcp, 5349/udp
- [ ] TURN server monitoring/alerting configured
- [ ] Session limits configured (max connections, bandwidth)
- [ ] TURN bandwidth budgeted (relay uses ~1.5 Mbps per peer)
- [ ] Certificate auto-renewal configured (Let's Encrypt)
- [ ] HSTS header set in Nginx/FastAPI
- [ ] Mixed content blocked (no http:// in https page)

## Troubleshooting

### TURN server not reachable
```bash
# Check if service is running
sudo systemctl status coturn

# Check logs
sudo tail -f /var/log/coturn/turnserver.log

# Verify port is open
sudo ss -tlnp | grep 3478
```

### WSS connection fails
- Ensure backend is using HTTPS
- Check firewall/security groups allow 443
- Verify certificate is valid (no warnings)

### ICE candidates failing
- STUN/TURN servers may be slow to respond
- Try forcing TURN with `iceTransportPolicy: 'relay'`
- Check TURN server credentials are correct

### High CPU / bandwidth on TURN server
- Check for relay storms (many simultaneous connections)
- Enable rate limiting in coturn
- Monitor with `netstat`, `iftop`

## References

- [RFC 5766: TURN (Traversal Using Relays)](https://tools.ietf.org/html/rfc5766)
- [coturn Documentation](https://github.com/coturn/coturn)
- [WebRTC MDN Guide](https://developer.mozilla.org/en-US/docs/Web/API/WebRTC_API)
- [Let's Encrypt Getting Started](https://letsencrypt.org/getting-started/)
