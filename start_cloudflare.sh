#!/bin/bash

# Start Cloudflare Tunnel for email tracking
# This gives you a stable HTTPS URL that won't change

echo ""
echo "=============================================="
echo "  Starting Cloudflare Tunnel"
echo "=============================================="
echo ""
echo "Your tracking server will be accessible at a stable cloudflare URL."
echo "Keep this running and use the https://xxx.trycloudflare.com URL"
echo "in your .env file as TRACKING_BASE_URL"
echo ""
echo "Starting tunnel to localhost:8003..."
echo ""

cloudflared tunnel --url http://localhost:8003

