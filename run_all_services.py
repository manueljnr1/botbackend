#!/usr/bin/env python3
"""
Run all chatbot services
"""
import subprocess
import threading
import webbrowser
import os
import time
import signal
import sys

# Define services
services = [
    {
        "name": "Chatbot API",
        "command": ["python", "simple_api_with_cors.py"],
        "port": 8001
    },
    {
        "name": "Onboarding API",
        "command": ["python", "onboarding_api.py"],
        "port": 8002
    }
]

# Global variables
processes = []
running = True

def run_service(service):
    """Run a service in a subprocess"""
    print(f"Starting {service['name']} on port {service['port']}...")
    process = subprocess.Popen(
        service["command"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        bufsize=1
    )
    
    processes.append(process)
    
    while running:
        output = process.stdout.readline()
        if output:
            print(f"[{service['name']}] {output.strip()}")
        
        error = process.stderr.readline()
        if error:
            print(f"[{service['name']} ERROR] {error.strip()}")
        
        # Check if process is still running
        if process.poll() is not None:
            print(f"{service['name']} stopped with exit code {process.returncode}")
            break
    
    # Clean up if we broke out of the loop
    if process.poll() is None:
        process.terminate()

def open_browser():
    """Open browser with the chatbot interface"""
    # Wait for services to start
    time.sleep(2)
    
    # Open the chatbot interface
    tenant_registration_url = "file://" + os.path.abspath("tenant_registration.html")
    print(f"Opening {tenant_registration_url} in browser...")
    webbrowser.open(tenant_registration_url)

def signal_handler(sig, frame):
    """Handle Ctrl+C"""
    global running
    print("\nShutting down services...")
    running = False
    
    # Terminate all processes
    for process in processes:
        if process.poll() is None:
            process.terminate()
    
    # Wait for processes to terminate
    for process in processes:
        process.wait()
    
    print("All services stopped")
    sys.exit(0)

if __name__ == "__main__":
    # Register signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    # Start services
    threads = []
    for service in services:
        thread = threading.Thread(target=run_service, args=(service,))
        thread.daemon = True
        thread.start()
        threads.append(thread)
    
    # Open browser
    threading.Thread(target=open_browser, daemon=True).start()
    
    # Keep main thread running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        signal_handler(None, None)