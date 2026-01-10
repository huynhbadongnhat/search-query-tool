#!/bin/bash
# Start the Streamlit app

cd "$(dirname "$0")"
uv run streamlit run app.py
