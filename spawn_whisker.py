#!/usr/bin/env python3
"""Spawn Whisker app with SSL pinning bypass using Frida."""

import frida
import sys

# Read the bypass script
with open('bypass_ssl_pinning.js', 'r') as f:
    script_code = f.read()

# Get device
device = frida.get_usb_device()
print(f"[*] Connected to: {device.name}")

# Spawn the app (starts paused)
print("[*] Spawning Whisker app...")
pid = device.spawn(["com.whisker.android"])
print(f"[+] Spawned with PID: {pid}")

# Attach to the spawned process
session = device.attach(pid)
print("[+] Attached to process")

# Load the SSL pinning bypass script
script = session.create_script(script_code)
script.on('message', lambda message, data: print(f"[Script] {message}"))
script.load()
print("[+] SSL bypass script loaded")

# Resume the app
device.resume(pid)
print("[+] App resumed - SSL pinning should be bypassed!")
print("[*] Press Ctrl+C to detach...")

try:
    sys.stdin.read()
except KeyboardInterrupt:
    print("\n[*] Detaching...")
    session.detach()
