#!/usr/bin/env python3
"""Attach to running Whisker app and bypass SSL pinning."""

import frida
import sys
import time

device = frida.get_usb_device()
print(f"[*] Connected to: {device.name}")

# Find Whisker process
processes = device.enumerate_processes()
whisker_proc = next((p for p in processes if 'whisker' in p.name.lower()), None)

if not whisker_proc:
    print("[-] Whisker app not running. Please start it and try again.")
    sys.exit(1)

print(f"[+] Found Whisker process: {whisker_proc.name} (PID: {whisker_proc.pid})")

# Attach
session = device.attach(whisker_proc.pid)
print("[+] Attached to process")

# Create SSL bypass script with Java readiness check
script_code = """
console.log("[*] Waiting for Java runtime...");

function bypassSSL() {
    Java.perform(function() {
        console.log("[+] Java runtime ready!");
        console.log("[*] Hooking SSL pinning...");
        
        // Hook OkHttp3 CertificatePinner
        try {
            var CertificatePinner = Java.use("okhttp3.CertificatePinner");
            CertificatePinner.check.overload("java.lang.String", "java.util.List").implementation = function(hostname, peerCertificates) {
                console.log("[+] okhttp3.CertificatePinner.check() bypassed for: " + hostname);
                return;
            };
            console.log("[+] OkHttp3 CertificatePinner hooked!");
        } catch(err) {
            console.log("[-] OkHttp3 hook failed: " + err);
        }
        
        // Hook HostnameVerifier
        try {
            var HostnameVerifier = Java.use("javax.net.ssl.HostnameVerifier");
            HostnameVerifier.verify.overload("java.lang.String", "javax.net.ssl.SSLSession").implementation = function(hostname, session) {
                console.log("[+] HostnameVerifier bypassed for: " + hostname);
                return true;
            };
            console.log("[+] HostnameVerifier hooked!");
        } catch(err) {
            console.log("[-] HostnameVerifier hook failed: " + err);
        }
        
        console.log("[*] SSL pinning bypass complete!");
    });
}

// Try to hook when Java is ready
setTimeout(bypassSSL, 0);
"""

script = session.create_script(script_code)

def on_message(message, data):
    if message['type'] == 'send':
        print(f"[Script] {message['payload']}")
    elif message['type'] == 'error':
        print(f"[Error] {message}")

script.on('message', on_message)
script.load()
print("[+] Script loaded and running")
print("[*] Now use the Whisker app - SSL pinning should be bypassed!")
print("[*] Press Ctrl+C to detach...")

try:
    sys.stdin.read()
except KeyboardInterrupt:
    print("\n[*] Detaching...")
    session.detach()
