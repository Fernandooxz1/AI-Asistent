# Viernes Assistant - SSL Trust Configuration Guide

Modern mobile browsers require secure HTTPS connections to access the microphone. Because Viernes runs on your local network (LAN), it uses a self-signed certificate. You must install and trust this certificate on your mobile device so that voice commands work without security warnings.

## Dynamic Server Information
* **Detected LAN IP:** `192.168.0.27`
* **Server URL:** [https://192.168.0.27:8000/](https://192.168.0.27:8000/)
* **Certificate Download URL:** [https://192.168.0.27:8000/cert.pem](https://192.168.0.27:8000/cert.pem)

---

## Option 1: Quick Install directly on Mobile Device (Recommended)
1. Open the browser on your phone or tablet.
2. Go to: `https://192.168.0.27:8000/` (if you see a warning screen, tap "Advanced" -> "Proceed anyway").
3. Download the certificate file by navigating to: `https://192.168.0.27:8000/cert.pem`
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
1. Download the certificate file (`viernes-cert.pem`).
2. Go to **Settings** -> **Security & Privacy** -> **More Security Settings** (or search for "certificates" or "credentials" in settings).
3. Select **Encryption & credentials** -> **Install a certificate** -> **CA certificate**.
4. Tap **Install Anyway** if warned, then browse to your Downloads and select the certificate file.

---

## Option 2: Advanced trust setup using `mkcert`
If you prefer to use a standard local CA tool like `mkcert`:
1. Install it on your host: `sudo apt install mkcert && mkcert -install`
2. Generate certificates for your LAN IP: `mkcert localhost viernes.local 192.168.0.27`
3. Move the generated files to the server's certificate directory:
   * `cp ./localhost+2.pem core/.kiro/cert.pem`
   * `cp ./localhost+2-key.pem core/.kiro/key.pem`
4. Transfer the Root CA certificate (`rootCA.pem`) found in your `$(mkcert -CAROOT)` directory to your mobile device and trust it.
