#!/usr/bin/env bash
# ==============================================================================
# Viernes SSL Trust Setup Assistant & Guide
# ==============================================================================

# Detect LAN IP
get_lan_ip() {
    if command -v ip >/dev/null 2>&1; then
        ip route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}'
    elif command -v hostname >/dev/null 2>&1; then
        hostname -I | awk '{print $1}'
    else
        echo "127.0.0.1"
    fi
}

LAN_IP=$(get_lan_ip)
PORT=8000 # default port

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

clear
echo -e "${BLUE}======================================================================${NC}"
echo -e "${GREEN}             VIERNES ASSISTANT - SSL TRUST SETUP GUIDE                ${NC}"
echo -e "${BLUE}======================================================================${NC}"
echo ""
echo -e "Modern mobile browsers (Safari on iOS, Chrome/Firefox on Android)"
echo -e "require secure HTTPS connections to access the microphone."
echo -e "Because Viernes runs on your local network (LAN), it uses a self-signed"
echo -e "certificate. You must install and trust this certificate on your mobile"
echo -e "device so that voice commands work without security warnings."
echo ""
echo -e "${YELLOW}Detected LAN IP:${NC} ${CYAN}${LAN_IP}${NC}"
echo -e "${YELLOW}Server URL:${NC}      ${CYAN}https://${LAN_IP}:${PORT}/${NC}"
echo -e "${YELLOW}Certificate URL:${NC} ${CYAN}https://${LAN_IP}:${PORT}/cert.pem${NC}"
echo ""
echo -e "${BLUE}----------------------------------------------------------------------${NC}"
echo -e "${GREEN}OPTION 1: QUICK INSTALL FROM MOBILE DEVICE (EASIEST)${NC}"
echo -e "${BLUE}----------------------------------------------------------------------${NC}"
echo -e "1. Open your browser on the mobile device."
echo -e "2. Navigate to: ${CYAN}https://${LAN_IP}:${PORT}/${NC}"
echo -e "   (Accept any initial certificate warnings to access the page)."
echo -e "3. Download the certificate by visiting: ${CYAN}https://${LAN_IP}:${PORT}/cert.pem${NC}"
echo -e "4. Follow the OS-specific trust steps below."
echo ""
echo -e "${BLUE}----------------------------------------------------------------------${NC}"
echo -e "${GREEN}OPTION 2: MANUAL DOWNLOAD VIA CLI AND TRANSFER${NC}"
echo -e "${BLUE}----------------------------------------------------------------------${NC}"
echo -e "If you want to download the certificate on your PC first:"
echo -e "  Run: ${CYAN}curl -k https://${LAN_IP}:${PORT}/cert.pem -o viernes-cert.pem${NC}"
echo -e "  Then send it to your device via AirDrop, email, or USB storage."
echo ""
echo -e "${BLUE}----------------------------------------------------------------------${NC}"
echo -e "${GREEN}OS-SPECIFIC TRUST STEPS (REQUIRED TO ENABLE MICROPHONE)${NC}"
echo -e "${BLUE}----------------------------------------------------------------------${NC}"
echo -e "${YELLOW} iOS (iPhone / iPad):${NC}"
echo -e "  1. Download the certificate from Safari."
echo -e "  2. Go to ${GREEN}Settings${NC} -> ${GREEN}Profile Downloaded${NC} (right at the top)."
echo -e "  3. Tap ${GREEN}Install${NC} in the top-right corner, enter your passcode, and confirm."
echo -e "  4. ${RED}IMPORTANT STEP:${NC} Go to ${GREEN}Settings${NC} -> ${GREEN}General${NC} -> ${GREEN}About${NC} -> ${GREEN}Certificate Trust Settings${NC}."
echo -e "  5. Under 'Enable full trust for root certificates', locate the certificate with"
echo -e "     your local IP (${LAN_IP}) and toggle the switch to ${GREEN}ON${NC}."
echo ""
echo -e "${YELLOW}🤖 Android:${NC}"
echo -e "  1. Download the certificate file."
echo -e "  2. Go to ${GREEN}Settings${NC} -> ${GREEN}Security & Privacy${NC} -> ${GREEN}More Security Settings${NC}"
echo -e "     (or search for 'credentials' / 'certificates' in settings)."
echo -e "  3. Tap ${GREEN}Encryption & credentials${NC} -> ${GREEN}Install a certificate${NC} -> ${GREEN}CA certificate${NC}."
echo -e "  4. Select 'Install anyway' and choose the ${CYAN}viernes-cert.pem${NC} file."
echo ""
echo -e "${BLUE}----------------------------------------------------------------------${NC}"
echo -e "${GREEN}OPTION 3: ADVANCED LOCAL TRUST WITH MKCERT${NC}"
echo -e "${BLUE}----------------------------------------------------------------------${NC}"
echo -e "If you want to use 'mkcert' to avoid browser warnings entirely:"
echo -e "  1. Install mkcert on your host PC: ${CYAN}sudo apt install mkcert && mkcert -install${NC}"
echo -e "  2. Generate certs for your LAN IP: ${CYAN}mkcert localhost viernes.local ${LAN_IP}${NC}"
echo -e "  3. Copy the generated files to the Viernes server directory:"
echo -e "     - ${CYAN}cp ./localhost+2.pem core/.kiro/cert.pem${NC}"
echo -e "     - ${CYAN}cp ./localhost+2-key.pem core/.kiro/key.pem${NC}"
echo -e "  4. Email or transfer the Root CA (${CYAN}\$(mkcert -CAROOT)/rootCA.pem${NC}) to your mobile device"
echo -e "     and install it using the iOS/Android steps above."
echo -e "${BLUE}======================================================================${NC}"

# Also generate a markdown guide file for offline use
GUIDE_PATH="$(dirname "$0")/SSL_TRUST_GUIDE.md"
cat << EOF > "$GUIDE_PATH"
# Viernes Assistant - SSL Trust Configuration Guide

Modern mobile browsers require secure HTTPS connections to access the microphone. Because Viernes runs on your local network (LAN), it uses a self-signed certificate. You must install and trust this certificate on your mobile device so that voice commands work without security warnings.

## Dynamic Server Information
* **Detected LAN IP:** \`${LAN_IP}\`
* **Server URL:** [https://${LAN_IP}:${PORT}/](https://${LAN_IP}:${PORT}/)
* **Certificate Download URL:** [https://${LAN_IP}:${PORT}/cert.pem](https://${LAN_IP}:${PORT}/cert.pem)

---

## Option 1: Quick Install directly on Mobile Device (Recommended)
1. Open the browser on your phone or tablet.
2. Go to: \`https://${LAN_IP}:${PORT}/\` (if you see a warning screen, tap "Advanced" -> "Proceed anyway").
3. Download the certificate file by navigating to: \`https://${LAN_IP}:${PORT}/cert.pem\`
4. Install and trust the certificate following the OS-specific steps below.

---

## OS-Specific Installation Steps

###  iOS (iPhone / iPad)
1. Download the certificate using **Safari** (Chrome might download it as a plain text file without initiating the profile installation).
2. Go to **Settings** -> **Profile Downloaded** (appears near the top).
3. Tap **Install** in the top-right corner, enter your passcode, and confirm.
4. **CRITICAL STEP:** Go to **Settings** -> **General** -> **About** -> **Certificate Trust Settings**.
5. Locate the root certificate labeled with your LAN IP under "Enable full trust for root certificates" and **toggle the switch to ON**.

### 🤖 Android
1. Download the certificate file (\`viernes-cert.pem\`).
2. Go to **Settings** -> **Security & Privacy** -> **More Security Settings** (or search for "certificates" or "credentials" in settings).
3. Select **Encryption & credentials** -> **Install a certificate** -> **CA certificate**.
4. Tap **Install Anyway** if warned, then browse to your Downloads and select the certificate file.

---

## Option 2: Advanced trust setup using \`mkcert\`
If you prefer to use a standard local CA tool like \`mkcert\`:
1. Install it on your host: \`sudo apt install mkcert && mkcert -install\`
2. Generate certificates for your LAN IP: \`mkcert localhost viernes.local ${LAN_IP}\`
3. Move the generated files to the server's certificate directory:
   * \`cp ./localhost+2.pem core/.kiro/cert.pem\`
   * \`cp ./localhost+2-key.pem core/.kiro/key.pem\`
4. Transfer the Root CA certificate (\`rootCA.pem\`) found in your \`\$(mkcert -CAROOT)\` directory to your mobile device and trust it.
EOF

chmod +x "$0" 2>/dev/null
echo -e "Markdown guide generated at: ${GREEN}${GUIDE_PATH}${NC}"
echo -e "${BLUE}======================================================================${NC}"
