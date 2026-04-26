#!/bin/bash
# ============================================================
#  AUTO-SETUP SCRIPT — runs automatically when Codespace opens
# ============================================================

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   TRADING BOT — Environment Setup        ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 1. Install Python dependencies ───────────────────────────
echo "📦 Installing dependencies..."
pip install -q -r requirements.txt
echo "✅ Dependencies installed"
echo ""

# ── 2. Check if .env exists, if not copy the example ─────────
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "📄 Created .env file from template"
else
  echo "📄 .env file already exists"
fi

# ── 3. Run the config wizard ──────────────────────────────────
echo ""
echo "════════════════════════════════════════════"
echo "  Let's configure your bot credentials"
echo "════════════════════════════════════════════"
echo ""

python3 .devcontainer/wizard.py

echo ""
echo "════════════════════════════════════════════"
echo "  ✅ Setup complete!"
echo "  To start your bot, run:"
echo ""
echo "     python bot.py"
echo ""
echo "  To run in background (keeps running):"
echo ""
echo "     nohup python bot.py > bot.log 2>&1 &"
echo "     tail -f bot.log"
echo "════════════════════════════════════════════"
echo ""
