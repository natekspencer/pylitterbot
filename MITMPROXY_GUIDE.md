# mitmproxy Traffic Capture Guide for LR5 API

## Setup Summary

**Server IP**: `<SERVER_IP>`
**Proxy Port**: `8080`
**Certificate URL**: `http://mitm.it`

## Step-by-Step Instructions

### 1. Start mitmproxy (Already Running)

The proxy server is running in the background. You can monitor it with:

```bash
# View the capture file
less ~/git/pylitterbot/whisker_capture.txt

# Or tail it live
tail -f ~/git/pylitterbot/whisker_capture.txt
```

### 2. Configure Your Phone

**For iPhone:**
1. Settings → Wi-Fi
2. Tap the (i) icon next to your connected network
3. Scroll down to "HTTP Proxy"
4. Select "Manual"
5. Server: `<SERVER_IP>`
6. Port: `8080`
7. Tap "Save"

**For Android:**
1. Settings → Wi-Fi
2. Long-press your connected network
3. Select "Modify network" or "Advanced"
4. Proxy: Manual
5. Hostname: `<SERVER_IP>`
6. Port: `8080`
7. Save

### 3. Install mitmproxy Certificate

**IMPORTANT**: Without this, you won't see HTTPS traffic!

1. On your phone, open any browser (Safari/Chrome)
2. Go to: `http://mitm.it`
3. You'll see a page with certificate downloads
4. Tap your OS (iOS or Android)
5. Follow the installation prompts

**For iPhone (iOS 10.3+):**
- After downloading, go to Settings → General → VPN & Device Management
- Find "mitmproxy" under Configuration Profile
- Tap it → Install
- Then: Settings → General → About → Certificate Trust Settings
- Enable full trust for mitmproxy certificate

**For Android:**
- Go to Settings → Security → Install from storage
- Find and install the mitmproxy certificate
- Set credential use to "VPN and apps"

### 4. Test the Proxy

Before using Whisker app:

1. Open browser on phone
2. Go to any HTTPS site (e.g., `https://google.com`)
3. Check the capture file on your server - you should see the traffic:
   ```bash
   tail ~/git/pylitterbot/whisker_capture.txt
   ```

If you see requests/responses, the proxy is working!

### 5. Capture Whisker App Traffic

Now we're ready to capture the LR5 API:

1. **Close** the Whisker app completely (swipe away from app switcher)
2. **Open** Whisker app fresh
3. **Navigate** to your Litter-Robot 5
4. **Perform actions**:
   - View robot status
   - Check activity history
   - View recent pet visits
   - (If available) Try to reassign a pet visit
5. **Check recent visits** - we want to see which pet IDs are assigned

### 6. What to Look For

The capture will show all HTTP/HTTPS requests. Look for:

**LR5 Base URL:**
- Probably contains "whisker", "litter", "robot", "lr5", etc.
- Examples: `https://lr5-api.whisker.com`, `https://api.whisker.com/v5/`

**Key Endpoints:**
```
GET  /api/users/{userId}/robots          # List robots
GET  /api/robots/{serial}/status          # Robot status
GET  /api/robots/{serial}/activity        # Activity history
POST /api/robots/{serial}/pet-visit       # Reassign pet visit
GET  /api/robots/{serial}/camera          # Camera access
```

**Authentication:**
- Look for `Authorization: Bearer <token>` header
- Should be same AWS Cognito token as LR4

**Pet Visit Data:**
Look for JSON with:
```json
{
  "visits": [
    {
      "timestamp": "2026-01-02T...",
      "petId": "PET-xxx",
      "petName": "Fluffy",
      "weight": 10.28,
      "identificationMethod": "ai" or "weight",
      "confidence": 0.85
    }
  ]
}
```

### 7. Save Important Requests

When you see LR5-related requests, note:
- Full URL
- HTTP method (GET/POST/PUT/DELETE)
- Request headers (especially Authorization)
- Request body (if any)
- Response body

### 8. When Done - Clean Up

**On your phone:**
1. Settings → Wi-Fi → Proxy → Off (or "Auto")
2. (Optional) Remove mitmproxy certificate:
   - iOS: Settings → General → VPN & Device Management → mitmproxy → Remove
   - Android: Settings → Security → Trusted credentials → Remove mitmproxy

**On server:**
```bash
# Stop the proxy
pkill mitmproxy

# Review the capture
cat ~/git/pylitterbot/whisker_capture.txt | grep -i "whisker\|litter\|robot\|lr5"
```

## Troubleshooting

**Certificate warnings on phone:**
- Normal! This means the proxy is intercepting HTTPS
- Install the certificate from mitm.it to fix

**No traffic showing:**
- Check phone proxy settings are correct
- Verify server IP: `hostname -I`
- Ensure phone and server on same network
- Try browser test first (go to google.com)

**Can't reach mitm.it:**
- Proxy might not be running
- Check: `ps aux | grep mitmproxy`
- Phone might not be using proxy - double-check settings

**App won't connect:**
- Some apps detect proxies and refuse to work
- This is called "certificate pinning"
- Try older version of Whisker app if possible
- Or try on Android (easier to bypass pinning)

## Next Steps

Once you have the API endpoints, we can:
1. Create `LitterRobot5` class
2. Implement activity history
3. Add pet visit reassignment
4. Submit PR to pylitterbot!
