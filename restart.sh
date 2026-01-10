#!/bin/bash
# Restart the Streamlit app (stop existing instance and start fresh)

cd "$(dirname "$0")"

# Kill existing streamlit processes for this app
pkill -f "streamlit run app.py" 2>/dev/null || true

# Wait a moment
sleep 1

# Start fresh
uv run streamlit run app.py
