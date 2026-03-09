#!/usr/bin/env bash
# theAunties — Setup Script
# Run this once to set up the development/production environment.

set -e

echo "==================================="
echo "  theAunties — Setup"
echo "==================================="
echo ""

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 || python --version 2>&1)
echo "Python: $PYTHON_VERSION"

PYTHON_CMD="python3"
if ! command -v python3 &> /dev/null; then
    PYTHON_CMD="python"
fi

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    $PYTHON_CMD -m venv venv
else
    echo "Virtual environment already exists."
fi

# Activate venv
source venv/bin/activate 2>/dev/null || source venv/Scripts/activate 2>/dev/null

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt --quiet

# Create data directories
echo "Creating data directories..."
mkdir -p data/context data/docs data/runs

# Create .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo "Creating .env from template..."
    cp .env.example .env
    echo ""
    echo "IMPORTANT: Edit .env with your API keys before running."
else
    echo ".env already exists."
fi

# Set permissions on data directory
if [[ "$OSTYPE" == "linux-gnu"* ]] || [[ "$OSTYPE" == "darwin"* ]]; then
    chmod 700 data/
    if [ -f ".env" ]; then
        chmod 600 .env
    fi
fi

# Run tests to verify setup
echo ""
echo "Running tests to verify setup..."
python -m pytest tests/ -q

echo ""
echo "==================================="
echo "  Setup complete!"
echo "==================================="
echo ""
echo "Next steps:"
echo "  1. Edit .env with your API keys (or keep USE_STUBS=true for testing)"
echo "  2. Start the chat:    python -m theaunties chat"
echo "  3. Start the server:  python -m theaunties serve"
echo ""
echo "With stubs enabled (USE_STUBS=true), the system runs with"
echo "canned responses — no API keys needed for testing the pipeline."
echo ""
