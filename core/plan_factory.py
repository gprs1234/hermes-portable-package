#!/usr/bin/env python3
"""
PLAN Factory — 從點子到全自治 PLAN 的誕生引擎
=============================================

核心原則：
  1. 每個 PLAN 是一個完整的生命個體，不只是監控腳本
  2. 建的路徑 = 修的路徑（創造路徑即全貌）
  3. 內外都要自治（內部服務 + 外部 bot/API）
  4. 主人的使用習慣決定媒介選擇

用法:
  python3 plan_factory.py create "我想做一個材料管理系統"
  python3 plan_factory.py create --json '{"name":"材料管理","description":"..."}'
  python3 plan_factory.py list                          # 列出所有已誕生的 PLAN
  python3 plan_factory.py trace <plan_id>               # 追蹤 PLAN 的創造路徑
  python3 plan_factory.py debug <plan_id> "查庫存沒反應" # 沿創造路徑排查問題

PLAN 誕生流程 (Phase 1-8):
  Phase 1: 需求分析（這個 PLAN 做什麼）
  Phase 2: 媒介選擇（TG Bot / Web / Dashboard / 本地）
  Phase 3: 資料管理（SQLite / JSON / Notion / Google）
  Phase 4: 技術棧決定
  Phase 5: 自治規則（什麼自動處理 / 什麼告訴主人）
  Phase 6: 建造（代碼 + bot + 監控 + skill）
  Phase 7: 登記（PLAN Registry + 心跳 + 指令通道）
  Phase 8: 回報（通知主人：bot 名稱、連結、功能摘要）
"""

import json
import os
import sys
import yaml
import subprocess
from datetime import datetime
from pathlib import Path

# ─── 路徑 ────────────────────────────────────────────────────
HERMES_HOME = Path.home() / ".hermes"
REFERENCES = HERMES_HOME / "references"
REGISTRY_DIR = HERMES_HOME / "plan_registry"
REGISTRY_FILE = REGISTRY_DIR / "registry.json"
PROFILE_FILE = REFERENCES / "Owner_profile.yaml"
FACTORY_DIR = HERMES_HOME / "plan_factory"
PLANS_DIR = FACTORY_DIR / "plans"

# 確保目錄存在
FACTORY_DIR.mkdir(parents=True, exist_ok=True)
PLANS_DIR.mkdir(parents=True, exist_ok=True)


# ══════════════════════════════════════════════════════════════
#  工具函式
# ══════════════════════════════════════════════════════════════

def load_json(path, default=None):
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
        return json.loads(text.replace("\r\n", "\n"))
    except Exception:
        return default if default is not None else {}


def save_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def load_yaml(path):
    try:
        return yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def now_iso():
    return datetime.now().isoformat()


# ══════════════════════════════════════════════════════════════
#  Phase 1: 需求分析
# ══════════════════════════════════════════════════════════════

def analyze_idea(description, profile):
    """
    分析一個點子，自動決定 PLAN 的各項參數。
    基於 Owner 的使用習慣資料庫做判斷。
    """
    plan = {
        "description": description,
        "analyzed_at": now_iso(),
        "phases": {},  # 每個 phase 的決策都會記錄在這裡
    }
    
    # Phase 1: 需求分析
    analysis = {
        "core_need": description,
        "users": infer_users(description),
        "usage_scenario": infer_scenario(description),
        "data_volume": infer_data_volume(description),
        "realtime_need": infer_realtime(description),
        "existing_integrations": infer_integrations(description),
    }
    plan["phases"]["phase_1_analysis"] = analysis
    
    return plan, analysis


def infer_users(description):
    """推斷使用者"""
    keywords_team = ["員工", "團隊", "多人", "協作", "客戶"]
    for kw in keywords_team:
        if kw in description:
            return {"type": "multi", "note": f"偵測到「{kw}」，需要多人存取"}
    return {"type": "single", "note": "Owner 獨自使用"}


def infer_scenario(description):
    """推斷使用場景"""
    scenarios = []
    if any(kw in description for kw in ["手機", "隨時", "外出", "行動"]):
        scenarios.append("mobile")
    if any(kw in description for kw in ["倉庫", "掃碼", "進出"]):
        scenarios.append("warehouse")
    if any(kw in description for kw in ["報表", "圖表", "分析", "統計"]):
        scenarios.append("analytics")
    if any(kw in description for kw in ["即時", "監控", "watch"]):
        scenarios.append("realtime")
    if not scenarios:
        scenarios.append("general")
    return scenarios


def infer_data_volume(description):
    """推斷資料量"""
    if any(kw in description for kw in ["大量", "百萬", "big data", "高頻"]):
        return "large"
    if any(kw in description for kw in ["中等", "幾百", "幾千"]):
        return "medium"
    return "small"


def infer_realtime(description):
    """推斷即時需求"""
    if any(kw in description for kw in ["即時", "每秒", "live", "監控"]):
        return "high"
    if any(kw in description for kw in ["每小時", "定時"]):
        return "medium"
    return "low"


def infer_integrations(description):
    """推斷需要整合的系統"""
    integrations = []
    if any(kw in description for kw in ["POS", "pos", "收銀"]):
        integrations.append("pos-backend")
    if any(kw in description for kw in ["交易", "Trading", "MT4", "EA"]):
        integrations.append("trading")
    if any(kw in description for kw in ["Notion", "notion"]):
        integrations.append("notion")
    if any(kw in description for kw in ["Google", "google", "日曆"]):
        integrations.append("google")
    return integrations


# ══════════════════════════════════════════════════════════════
#  Phase 2-5: 決策引擎
# ══════════════════════════════════════════════════════════════

def decide_channels(analysis, profile):
    """Phase 2: 決定通訊媒介"""
    channels = []
    prefs = profile.get("preferences", {}).get("interface_priority", [])
    users = analysis.get("users", {}).get("type", "single")
    scenarios = analysis.get("usage_scenario", [])
    realtime = analysis.get("realtime_need", "low")
    
    # Telegram 幾乎一定需要（Owner 主要介面）
    tg_config = {
        "type": "telegram",
        "reason": "Owner 主要通訊介面",
        "features": ["查詢", "通知", "操作"],
        "bot_name": None,  # 待自動生成
        "bot_token": None,  # 待自動創建
    }
    
    # 如果需要圖表/報表 → 加 Web Dashboard
    if "analytics" in scenarios:
        channels.append({
            "type": "web_dashboard",
            "reason": "需要圖表/報表展示",
            "features": ["庫存總覽", "趨勢圖", "報表匯出"],
            "port": None,  # 待分配
        })
    
    # 如果需要即時 → 加 WebSocket
    if realtime == "high":
        tg_config["features"].append("即時推播")
    
    channels.insert(0, tg_config)
    return channels


def decide_data_layer(analysis, profile):
    """Phase 3: 決定資料管理"""
    volume = analysis.get("data_volume", "small")
    integrations = analysis.get("existing_integrations", [])
    
    if volume == "large":
        db = {"type": "postgresql", "reason": "資料量大"}
    elif volume == "medium":
        db = {"type": "sqlite", "reason": "中等資料量，SQLite 夠用"}
    else:
        db = {"type": "json", "reason": "小規模，JSON 檔案即可"}
    
    # 如果需要協作 → 加雲端
    if analysis.get("users", {}).get("type") == "multi":
        db["sync"] = "needed"
        db["note"] = "多人使用需要同步機制"
    
    # 如果接 POS 或 Trading → 需要 API
    if integrations:
        db["api_layer"] = True
        db["integrations"] = integrations
    
    return db


def decide_tech_stack(channels, data_layer, profile):
    """Phase 4: 決定技術棧"""
    tech = {
        "language": "python",
        "framework": {},
        "libraries": [],
    }
    
    for ch in channels:
        if ch["type"] == "telegram":
            tech["libraries"].append("python-telegram-bot")
        elif ch["type"] == "web_dashboard":
            tech["framework"]["web"] = "Flask"
            tech["libraries"].append("flask")
    
    if data_layer["type"] == "sqlite":
        tech["libraries"].append("sqlite3")
    elif data_layer["type"] == "postgresql":
        tech["libraries"].append("psycopg2")
    
    if data_layer.get("api_layer"):
        tech["framework"]["api"] = "FastAPI"
        tech["libraries"].append("fastapi")
    
    return tech


def decide_autonomy_rules(analysis, profile):
    """Phase 5: 決定自治規則"""
    rules = {
        "auto_fix": list(profile.get("autonomy_rules", {}).get("auto_fix", [])),
        "notify_owner": list(profile.get("autonomy_rules", {}).get("notify_owner", [])),
        "silent": list(profile.get("autonomy_rules", {}).get("silent", [])),
        "escalation_threshold": "CRITICAL",
        "report_frequency": "daily_summary",
    }
    
    # 根據分析結果調整
    if analysis.get("realtime_need") == "high":
        rules["report_frequency"] = "realtime"
    
    if analysis.get("existing_integrations"):
        rules["notify_owner"].append("外部 API 連線失敗")
    
    return rules


# ══════════════════════════════════════════════════════════════
#  Phase 6-8: 建造、登記、回報
# ══════════════════════════════════════════════════════════════

def generate_plan_id(name):
    """Generate a PLAN ID that's safe for filesystems AND Telegram bot usernames.

    Telegram bot username rules: 5–32 chars, ASCII alphanumeric + underscore,
    must start with a letter, must end with a letter or digit (not underscore),
    must end with `bot` (handled by caller — we just give the slug).

    This function:
      - lowercases
      - keeps a-z 0-9 _ only (everything else, incl. CJK, becomes _)
      - collapses repeated underscores
      - strips leading/trailing underscores
      - ensures it starts with a letter (prefix `p_` if it doesn't)
      - truncates to 24 chars (leaving room for `_bot` suffix)
      - falls back to `plan_<short hash>` if input collapses to empty
    """
    import re
    import hashlib

    raw = (name or "").strip().lower()
    # Replace any non [a-z0-9_] with _
    slug = re.sub(r'[^a-z0-9_]+', '_', raw)
    # Collapse repeats
    slug = re.sub(r'_+', '_', slug).strip('_')

    if not slug:
        # Pure CJK / symbols → fall back to deterministic hash slug
        h = hashlib.sha1(raw.encode('utf-8')).hexdigest()[:8]
        slug = f"plan_{h}"

    # Must start with a letter (Telegram bot rule). Digit-leading slugs get a `p_` prefix.
    if not slug[0].isalpha():
        slug = f"p_{slug}"

    # Truncate (leave 8 chars of headroom for `_bot` etc.)
    if len(slug) > 24:
        # Use a hash suffix to keep uniqueness when truncating
        h = hashlib.sha1(slug.encode('utf-8')).hexdigest()[:6]
        slug = slug[:17].rstrip('_') + '_' + h

    return slug


# ══════════════════════════════════════════════════════════════
#  Phase 6b: 自動建立 PLAN 專屬 Telegram Bot
# ══════════════════════════════════════════════════════════════

BOT_TEMPLATE_PY = r'''#!/usr/bin/env python3
"""
__PLAN_NAME__ — 專屬 Telegram Bot
================================
Bot: __BOT_NAME__
自動由 PLAN Factory 生成，只需填入 token 即可運作。

用法:
  1. 編輯此目錄的 bot_config.yaml，填入 bot_token 和 chat_id
  2. pip install python-telegram-bot --upgrade
  3. python3 bot_template.py

指令:
  /status  — 查看 PLAN 目前狀態
  /report  — 取得最新報告
  /escalate <問題描述> — 上報問題給 Hermes
  /help    — 顯示指令列表
"""

import asyncio
import json
import os
import sys
import yaml
from datetime import datetime
from pathlib import Path

try:
    from telegram import Update, BotCommand
    from telegram.ext import (
        Application,
        CommandHandler,
        MessageHandler,
        ContextTypes,
        filters,
    )
except ImportError:
    print("請先安裝: pip install python-telegram-bot --upgrade")
    sys.exit(1)


PLAN_NAME = "__PLAN_NAME__"
PLAN_ID = "__PLAN_ID__"
BOT_NAME = "__BOT_NAME__"

BOT_DIR = Path(__file__).parent
CONFIG_FILE = BOT_DIR / "bot_config.yaml"
BLUEPRINT_FILE = BOT_DIR / "blueprint.json"
HEARTBEAT_FILE = BOT_DIR / "heartbeat.json"
REPORTS_DIR = BOT_DIR / "reports"


def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def load_blueprint():
    if BLUEPRINT_FILE.exists():
        with open(BLUEPRINT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_heartbeat():
    if HEARTBEAT_FILE.exists():
        with open(HEARTBEAT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def get_latest_report():
    if REPORTS_DIR.exists():
        reports = sorted(REPORTS_DIR.glob("*.md"), reverse=True)
        if reports:
            return reports[0].read_text(encoding="utf-8")[:2000]
    return "目前沒有報告。"


# ─── 指令處理 ────────────────────────────────────────────────

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """顯示 PLAN 目前狀態"""
    bp = load_blueprint()
    hb = load_heartbeat()

    name = bp.get("name", PLAN_NAME)
    status = hb.get("status", "unknown")
    last_heartbeat = hb.get("timestamp", "N/A")
    score = hb.get("score", "N/A")

    lines = [
        f"📊 *{PLAN_NAME}* 狀態",
        "",
        f"狀態: `{status}`",
        f"心跳: `{last_heartbeat}`",
        f"分數: `{score}`",
    ]
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """顯示最新報告"""
    report = get_latest_report()
    await update.message.reply_text(
        f"📋 *最新報告*\n\n{report}", parse_mode="Markdown"
    )


async def cmd_escalate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """上報問題給 Hermes"""
    problem = " ".join(context.args) if context.args else "未描述"
    ts = datetime.now().isoformat()

    escalation = {
        "from": BOT_NAME,
        "plan": PLAN_ID,
        "problem": problem,
        "timestamp": ts,
        "chat_id": update.effective_chat.id,
    }

    escalation_file = BOT_DIR / "escalations.json"
    escalations = []
    if escalation_file.exists():
        with open(escalation_file, "r") as f:
            escalations = json.load(f)
    escalations.append(escalation)
    with open(escalation_file, "w") as f:
        json.dump(escalations, f, indent=2, ensure_ascii=False)

    await update.message.reply_text(
        f"🚨 已上報問題給 Hermes:\n> {problem}\n\n等待回覆中..."
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """顯示指令列表"""
    text = (
        f"🤖 *{BOT_NAME}* 指令列表\n\n"
        "/status  — 查看 PLAN 目前狀態\n"
        "/report  — 取得最新報告\n"
        "/escalate <問題> — 上報問題給 Hermes\n"
        "/help    — 顯示此訊息\n\n"
        "任何訊息都會轉發給 Hermes Agent 處理。"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """接收一般訊息，記錄並回覆"""
    user_msg = update.message.text
    ts = datetime.now().isoformat()

    messages_file = BOT_DIR / "inbox.json"
    messages = []
    if messages_file.exists():
        with open(messages_file, "r") as f:
            messages = json.load(f)
    messages.append({
        "text": user_msg,
        "from": update.effective_user.username or "unknown",
        "chat_id": update.effective_chat.id,
        "timestamp": ts,
    })
    # 只保留最近 200 則
    messages = messages[-200:]
    with open(messages_file, "w") as f:
        json.dump(messages, f, indent=2, ensure_ascii=False)

    await update.message.reply_text("✅ 已收到，Hermes 會盡快處理。")


async def post_init(app: Application):
    """設定 bot 指令選單"""
    await app.bot.set_my_commands([
        BotCommand("status", "查看 PLAN 目前狀態"),
        BotCommand("report", "取得最新報告"),
        BotCommand("escalate", "上報問題給 Hermes"),
        BotCommand("help", "顯示指令列表"),
    ])


# ─── 啟動 ────────────────────────────────────────────────────

def main():
    config = load_config()
    token = config.get("bot_token")

    if not token:
        print("❌ bot_token 尚未設定！")
        print(f"   請編輯 {CONFIG_FILE} 並填入 bot_token")
        print(f"   或設定環境變數 PLAN_BOT_TOKEN")
        token = os.environ.get("PLAN_BOT_TOKEN")

    if not token:
        print("❌ 無法取得 token，請先設定。")
        sys.exit(1)

    print(f"🤖 啟動 {BOT_NAME}...")
    print(f"   計畫: {PLAN_NAME}")
    print(f"   設定: {CONFIG_FILE}")

    app = Application.builder().token(token).post_init(post_init).build()

    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("escalate", cmd_escalate))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ Bot 已啟動，等待訊息...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
'''


def create_plan_bot(plan_name, plan_id):
    """
    為每個 PLAN 自動建立專屬 Telegram Bot。
    生成 bot_config.yaml 和 bot_template.py。
    """
    plan_dir = PLANS_DIR / plan_id
    plan_dir.mkdir(parents=True, exist_ok=True)

    bot_name = f"@Owner_{plan_id}_bot"
    bot_description = f"{plan_name} — 專屬管理機器人"

    # ─── 1. bot_config.yaml ──────────────────────────────────
    bot_config = {
        "bot_name": bot_name,
        "bot_description": bot_description,
        "bot_token": None,  # 創建 bot 後填入
        "chat_id": None,    # 綁定 chat 後填入
        "plan_id": plan_id,
        "plan_name": plan_name,
        "commands": ["status", "report", "escalate", "help"],
        "features": ["status_query", "progress_report", "escalation"],
        "created_at": now_iso(),
        "botfather_instructions": {
            "step_1": f"在 Telegram 開啟 @BotFather",
            "step_2": f"輸入 /newbot",
            "step_3": f"名稱: {plan_name} Bot",
            "step_4": f"username: Owner_{plan_id}_bot",
            "step_5": "取得 token 後填入此檔的 bot_token 欄位",
            "step_6": "執行 python3 bot_template.py 啟動 bot",
        },
    }

    config_path = plan_dir / "bot_config.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(bot_config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    # ─── 2. bot_template.py ──────────────────────────────────
    bot_code = BOT_TEMPLATE_PY
    bot_code = bot_code.replace("__PLAN_NAME__", plan_name)
    bot_code = bot_code.replace("__PLAN_ID__", plan_id)
    bot_code = bot_code.replace("__BOT_NAME__", bot_name)
    bot_code = bot_code.replace("__BOT_DESCRIPTION__", bot_description)
    bot_path = plan_dir / "bot_template.py"
    with open(bot_path, "w", encoding="utf-8") as f:
        f.write(bot_code)
    os.chmod(str(bot_path), 0o755)

    # ─── 3. 回傳 bot 資訊 ────────────────────────────────────
    result = {
        "bot_name": bot_name,
        "bot_description": bot_description,
        "config_path": str(config_path),
        "bot_template_path": str(bot_path),
        "next_steps": [
            f"1. 在 @BotFather 建立 bot: /newbot → {bot_name}",
            f"2. 取得 token 填入 {config_path}",
            f"3. 執行: python3 {bot_path}",
            f"4. 在 bot 對話中發送 /start 測試",
        ],
    }

    print(f"    🤖 Bot 名稱: {bot_name}")
    print(f"    📝 描述: {bot_description}")
    print(f"    📄 設定檔: {config_path}")
    print(f"    🐍 Bot 代碼: {bot_path}")

    return result

# ══════════════════════════════════════════════════════════════
#  Phase 6: 建造 — 從藍圖生成實際檔案
# ══════════════════════════════════════════════════════════════

def _gen_main_py(blueprint):
    """根據技術棧生成 main.py"""
    plan_id = blueprint["plan_id"]
    plan_name = blueprint["name"]
    tech = blueprint.get("tech_stack", {})
    channels = blueprint.get("channels", [])
    data_layer = blueprint.get("data_layer", {})
    libs = tech.get("libraries", [])
    framework = tech.get("framework", {})

    has_fastapi = "fastapi" in libs or framework.get("api") == "FastAPI"
    has_flask = "flask" in libs or framework.get("web") == "Flask"

    if has_fastapi:
        return _gen_fastapi_main(plan_id, plan_name, data_layer)
    elif has_flask:
        return _gen_flask_main(plan_id, plan_name, data_layer)
    else:
        return _gen_script_main(plan_id, plan_name, data_layer)


def _gen_fastapi_main(plan_id, plan_name, data_layer):
    lines = [
        '#!/usr/bin/env python3',
        '"""',
        '%s — FastAPI Server' % plan_name,
        'Auto-generated by PLAN Factory.',
        '"""',
        'import json',
        'import os',
        'import sys',
        'from datetime import datetime',
        'from pathlib import Path',
        '',
        'from fastapi import FastAPI, HTTPException',
        'from pydantic import BaseModel',
        '',
        'app = FastAPI(title="%s", version="0.1.0")' % plan_name,
        '',
        'PLAN_DIR = Path(__file__).parent',
        'DATA_FILE = PLAN_DIR / "data.json"',
        'HEARTBEAT_FILE = PLAN_DIR / "heartbeat.json"',
        '',
        '',
        'def load_data():',
        '    if DATA_FILE.exists():',
        '        with open(DATA_FILE, "r", encoding="utf-8") as f:',
        '            return json.load(f)',
        '    return {}',
        '',
        '',
        'def save_data(data):',
        '    with open(DATA_FILE, "w", encoding="utf-8") as f:',
        '        json.dump(data, f, indent=2, ensure_ascii=False, default=str)',
        '',
        '',
        'def update_heartbeat(status="ok"):',
        '    hb = {',
        '        "plan_id": "%s",' % plan_id,
        '        "status": status,',
        '        "timestamp": datetime.now().isoformat(),',
        '        "pid": os.getpid(),',
        '        "score": 100,',
        '    }',
        '    with open(HEARTBEAT_FILE, "w", encoding="utf-8") as f:',
        '        json.dump(hb, f, indent=2)',
        '',
        '',
        '@app.on_event("startup")',
        'async def startup():',
        '    update_heartbeat("started")',
        '    print("%s server started")' % plan_name,
        '',
        '',
        '@app.get("/")',
        'async def root():',
        '    return {"plan": "%s", "status": "running"}' % plan_name,
        '',
        '',
        '@app.get("/health")',
        'async def health():',
        '    update_heartbeat("ok")',
        '    return {"status": "ok", "timestamp": datetime.now().isoformat()}',
        '',
        '',
        '@app.get("/data")',
        'async def get_data():',
        '    return load_data()',
        '',
        '',
        '@app.post("/data")',
        'async def post_data(payload: dict):',
        '    data = load_data()',
        '    data.update(payload)',
        '    save_data(data)',
        '    return {"status": "saved", "keys": list(payload.keys())}',
        '',
        '',
        'if __name__ == "__main__":',
        '    import uvicorn',
        '    port = int(os.environ.get("PORT", 8000))',
        '    uvicorn.run(app, host="0.0.0.0", port=port)',
        '',
    ]
    return '\n'.join(lines)


def _gen_flask_main(plan_id, plan_name, data_layer):
    lines = [
        '#!/usr/bin/env python3',
        '"""',
        '%s — Flask Server' % plan_name,
        'Auto-generated by PLAN Factory.',
        '"""',
        'import json',
        'import os',
        'import sys',
        'from datetime import datetime',
        'from pathlib import Path',
        '',
        'from flask import Flask, jsonify, request',
        '',
        'app = Flask(__name__)',
        '',
        'PLAN_DIR = Path(__file__).parent',
        'DATA_FILE = PLAN_DIR / "data.json"',
        'HEARTBEAT_FILE = PLAN_DIR / "heartbeat.json"',
        '',
        '',
        'def load_data():',
        '    if DATA_FILE.exists():',
        '        with open(DATA_FILE, "r", encoding="utf-8") as f:',
        '            return json.load(f)',
        '    return {}',
        '',
        '',
        'def save_data(data):',
        '    with open(DATA_FILE, "w", encoding="utf-8") as f:',
        '        json.dump(data, f, indent=2, ensure_ascii=False, default=str)',
        '',
        '',
        'def update_heartbeat(status="ok"):',
        '    hb = {',
        '        "plan_id": "%s",' % plan_id,
        '        "status": status,',
        '        "timestamp": datetime.now().isoformat(),',
        '        "pid": os.getpid(),',
        '        "score": 100,',
        '    }',
        '    with open(HEARTBEAT_FILE, "w", encoding="utf-8") as f:',
        '        json.dump(hb, f, indent=2)',
        '',
        '',
        '@app.route("/")',
        'def root():',
        '    return jsonify({"plan": "%s", "status": "running"})' % plan_name,
        '',
        '',
        '@app.route("/health")',
        'def health():',
        '    update_heartbeat("ok")',
        '    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})',
        '',
        '',
        '@app.route("/data", methods=["GET"])',
        'def get_data():',
        '    return jsonify(load_data())',
        '',
        '',
        '@app.route("/data", methods=["POST"])',
        'def post_data():',
        '    data = load_data()',
        '    data.update(request.get_json(force=True))',
        '    save_data(data)',
        '    return jsonify({"status": "saved"})',
        '',
        '',
        'if __name__ == "__main__":',
        '    port = int(os.environ.get("PORT", 5000))',
        '    update_heartbeat("started")',
        '    app.run(host="0.0.0.0", port=port, debug=False)',
        '',
    ]
    return '\n'.join(lines)


def _gen_script_main(plan_id, plan_name, data_layer):
    lines = [
        '#!/usr/bin/env python3',
        '"""',
        '%s — Background Script' % plan_name,
        'Auto-generated by PLAN Factory.',
        '',
        'Minimal skeleton. Add your business logic in the main loop.',
        '"""',
        'import json',
        'import os',
        'import signal',
        'import sys',
        'import time',
        'from datetime import datetime',
        'from pathlib import Path',
        '',
        'PLAN_DIR = Path(__file__).parent',
        'HEARTBEAT_FILE = PLAN_DIR / "heartbeat.json"',
        'DATA_FILE = PLAN_DIR / "data.json"',
        'PID_FILE = PLAN_DIR / "main.pid"',
        '',
        'running = True',
        '',
        '',
        'def handle_signal(sig, frame):',
        '    global running',
        '    print(f"[{datetime.now()}] Received signal {sig}, shutting down...")',
        '    running = False',
        '',
        '',
        'signal.signal(signal.SIGTERM, handle_signal)',
        'signal.signal(signal.SIGINT, handle_signal)',
        '',
        '',
        'def update_heartbeat(status="ok"):',
        '    hb = {',
        '        "plan_id": "%s",' % plan_id,
        '        "status": status,',
        '        "timestamp": datetime.now().isoformat(),',
        '        "pid": os.getpid(),',
        '        "score": 100,',
        '    }',
        '    with open(HEARTBEAT_FILE, "w", encoding="utf-8") as f:',
        '        json.dump(hb, f, indent=2)',
        '',
        '',
        'def load_data():',
        '    if DATA_FILE.exists():',
        '        with open(DATA_FILE, "r", encoding="utf-8") as f:',
        '            return json.load(f)',
        '    return {}',
        '',
        '',
        'def save_data(data):',
        '    with open(DATA_FILE, "w", encoding="utf-8") as f:',
        '        json.dump(data, f, indent=2, ensure_ascii=False, default=str)',
        '',
        '',
        'def main():',
        '    global running',
        '    print(f"Starting %s...")' % plan_name,
        '    print(f"PID: {os.getpid()}")',
        '',
        '    # Write PID file',
        '    PID_FILE.write_text(str(os.getpid()))',
        '',
        '    update_heartbeat("started")',
        '',
        '    while running:',
        '        try:',
        '            # -- Your main logic here --',
        '            pass',
        '',
        '            update_heartbeat("ok")',
        '            time.sleep(60)  # Run every 60 seconds',
        '',
        '        except Exception as e:',
        '            print(f"Error: {e}", file=sys.stderr)',
        '            update_heartbeat(f"error: {e}")',
        '            time.sleep(10)',
        '',
        '    update_heartbeat("stopped")',
        '    if PID_FILE.exists():',
        '        PID_FILE.unlink()',
        '    print("Shutdown complete.")',
        '',
        '',
        'if __name__ == "__main__":',
        '    main()',
        '',
    ]
    return '\n'.join(lines)


def _gen_monitor_py(blueprint):
    """生成標準監控腳本"""
    plan_id = blueprint["plan_id"]
    plan_name = blueprint["name"]
    tech = blueprint.get("tech_stack", {})
    libs = tech.get("libraries", [])

    has_fastapi = "fastapi" in libs
    has_flask = "flask" in libs
    if has_fastapi:
        port = 8000
    elif has_flask:
        port = 5000
    else:
        port = 0

    lines = [
        '#!/usr/bin/env python3',
        '"""',
        '%s — Health Monitor' % plan_name,
        'Auto-generated by PLAN Factory.',
        '',
        'Checks:',
        '  1. Is the main process running?',
        '  2. Is the service port accessible?',
        '  3. Is the heartbeat file fresh?',
        '',
        'Writes heartbeat to the standard location.',
        'Run via cron: */2 * * * * python3 monitor.py',
        '"""',
        'import json',
        'import os',
        'import subprocess',
        'import sys',
        'from datetime import datetime, timedelta',
        'from pathlib import Path',
        '',
        'PLAN_DIR = Path(__file__).parent',
        'HEARTBEAT_FILE = PLAN_DIR / "heartbeat.json"',
        'PID_FILE = PLAN_DIR / "main.pid"',
        'BLUEPRINT_FILE = PLAN_DIR / "blueprint.json"',
        'MONITOR_LOG = PLAN_DIR / "monitor.log"',
        '',
        '',
        'def load_json(path):',
        '    try:',
        '        with open(path, "r", encoding="utf-8") as f:',
        '            return json.load(f)',
        '    except Exception:',
        '        return {}',
        '',
        '',
        'def check_process():',
        '    """Check if the main process is running."""',
        '    if not PID_FILE.exists():',
        '        return False, "No PID file found"',
        '    try:',
        '        pid = int(PID_FILE.read_text().strip())',
        '        os.kill(pid, 0)  # Signal 0 = check if alive',
        '        return True, "PID %d is alive" % pid',
        '    except (ValueError, ProcessLookupError, PermissionError) as e:',
        '        return False, str(e)',
        '',
        '',
        'def check_heartbeat_fresh(max_age_seconds=300):',
        '    """Check if heartbeat is recent."""',
        '    if not HEARTBEAT_FILE.exists():',
        '        return False, "No heartbeat file"',
        '    try:',
        '        hb = load_json(HEARTBEAT_FILE)',
        '        ts = hb.get("timestamp")',
        '        if not ts:',
        '            return False, "No timestamp in heartbeat"',
        '        last = datetime.fromisoformat(ts)',
        '        age = (datetime.now() - last).total_seconds()',
        '        if age > max_age_seconds:',
        '            return False, "Heartbeat is %.0fs old (max %ds)" % (age, max_age_seconds)',
        '        return True, "Heartbeat is %.0fs old" % age',
        '    except Exception as e:',
        '        return False, "Heartbeat parse error: %s" % e',
        '',
        '',
        'def run_health_check():',
        '    """Run all checks and return result."""',
        '    issues = []',
        '    score = 100',
        '    details = {}',
        '',
        '    # Check 1: Process running',
        '    alive, msg = check_process()',
        '    details["process"] = msg',
        '    if not alive:',
        '        issues.append("Process not running: %s" % msg)',
        '        score -= 50',
        '',
    ]

    if port:
        lines.extend([
            '    # Check 2: Port accessible',
            '    import socket',
            '    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)',
            '    sock.settimeout(3)',
            '    port_result = sock.connect_ex(("127.0.0.1", %d))' % port,
            '    sock.close()',
            '    if port_result != 0:',
            '        issues.append("Port %d is not accessible (code: %%d)" %% port_result)' % port,
            '        score -= 30',
            '    else:',
            '        details["port_%d"] = "open"' % port,
            '',
        ])

    lines.extend([
        '    # Check 3: Heartbeat fresh',
        '    fresh, msg = check_heartbeat_fresh()',
        '    details["heartbeat"] = msg',
        '    if not fresh:',
        '        issues.append("Heartbeat stale: %s" % msg)',
        '        score -= 20',
        '',
        '    result = {',
        '        "plan_id": "%s",' % plan_id,
        '        "plan_name": "%s",' % plan_name,
        '        "check_time": datetime.now().isoformat(),',
        '        "score": max(0, score),',
        '        "status": "ok" if score >= 70 else "degraded" if score >= 40 else "critical",',
        '        "issues": issues,',
        '        "details": details,',
        '    }',
        '    return result',
        '',
        '',
        'def write_heartbeat(result):',
        '    """Write monitor heartbeat."""',
        '    hb = {',
        '        "plan_id": "%s",' % plan_id,
        '        "source": "monitor",',
        '        "status": result["status"],',
        '        "score": result["score"],',
        '        "timestamp": datetime.now().isoformat(),',
        '        "issues": result["issues"],',
        '        "pid": os.getpid(),',
        '    }',
        '    with open(HEARTBEAT_FILE, "w", encoding="utf-8") as f:',
        '        json.dump(hb, f, indent=2, ensure_ascii=False)',
        '',
        '',
        'def attempt_restart():',
        '    """Try to restart the main process if it died."""',
        '    main_py = PLAN_DIR / "main.py"',
        '    if not main_py.exists():',
        '        return False, "main.py not found"',
        '    try:',
        '        subprocess.Popen(',
        '            [sys.executable, str(main_py)],',
        '            cwd=str(PLAN_DIR),',
        '            stdout=open(PLAN_DIR / "main.log", "a"),',
        '            stderr=subprocess.STDOUT,',
        '            start_new_session=True,',
        '        )',
        '        return True, "Restart triggered"',
        '    except Exception as e:',
        '        return False, "Restart failed: %s" % e',
        '',
        '',
        'def main():',
        '    result = run_health_check()',
        '',
        '    # Log',
        '    log_line = "[%s] score=%d status=%s" % (result["check_time"], result["score"], result["status"])',
        '    if result["issues"]:',
        '        log_line += " issues=%s" % ", ".join(result["issues"])',
        '    print(log_line)',
        '',
        '    with open(MONITOR_LOG, "a", encoding="utf-8") as f:',
        '        f.write(log_line + "\\n")',
        '',
        '    # Write heartbeat',
        '    write_heartbeat(result)',
        '',
        '    # Auto-restart if critical',
        '    if result["status"] == "critical" and any("Process not running" in i for i in result["issues"]):',
        '        print("Process is down, attempting restart...")',
        '        ok, msg = attempt_restart()',
        '        print("  Restart: %s" % msg)',
        '',
        '    # Trim log to last 500 lines',
        '    if MONITOR_LOG.exists():',
        '        lines = MONITOR_LOG.read_text().splitlines()',
        '        if len(lines) > 500:',
        '            MONITOR_LOG.write_text("\\n".join(lines[-500:]) + "\\n")',
        '',
        '    return result',
        '',
        '',
        'if __name__ == "__main__":',
        '    main()',
        '',
    ])
    return '\n'.join(lines)


def _gen_skill_json(blueprint):
    """生成 skill.json — 基本重啟 skill"""
    plan_id = blueprint["plan_id"]
    plan_name = blueprint["name"]
    tech = blueprint.get("tech_stack", {})
    libs = tech.get("libraries", [])
    plan_dir = str(PLANS_DIR / plan_id)

    has_fastapi = "fastapi" in libs
    has_flask = "flask" in libs
    if has_fastapi:
        port = 8000
    elif has_flask:
        port = 5000
    else:
        port = 0

    skill = {
        "name": "restart_%s" % plan_id,
        "description": "Restart and manage %s" % plan_name,
        "plan_id": plan_id,
        "version": "1.0.0",
        "triggers": [
            "%s down" % plan_id,
            "restart %s" % plan_id,
            "%s not responding" % plan_id,
        ],
        "actions": [
            {
                "type": "check",
                "description": "Check if process is alive",
                "command": "python3 %s/monitor.py" % plan_dir,
            },
            {
                "type": "restart",
                "description": "Restart %s" % plan_name,
                "command": "cd %s && python3 main.py" % plan_dir,
            },
        ],
        "health_check": {
            "heartbeat_path": "%s/heartbeat.json" % plan_dir,
            "max_age_seconds": 300,
        },
        "cron": {
            "monitor": "*/2 * * * *",
            "description": "Run monitor every 2 minutes",
        },
    }
    if port:
        skill["health_check"]["port"] = port

    return json.dumps(skill, indent=2, ensure_ascii=False)


def _gen_heartbeat_template(blueprint):
    """生成 heartbeat.json 模板"""
    hb = {
        "plan_id": blueprint["plan_id"],
        "status": "not_started",
        "timestamp": now_iso(),
        "pid": None,
        "score": 0,
        "source": "template",
    }
    return json.dumps(hb, indent=2, ensure_ascii=False)


def _gen_bot_register_template(blueprint):
    """生成 bot 註冊指引"""
    plan_id = blueprint["plan_id"]
    plan_name = blueprint["name"]
    bot_name = "@Owner_%s_bot" % plan_id

    lines = [
        "# Telegram Bot Registration Guide for %s" % plan_name,
        "# ================================================",
        "# Bot: %s" % bot_name,
        "# Auto-generated by PLAN Factory",
        "",
        "# Step 1: Create bot via @BotFather",
        "#   - Open Telegram, search @BotFather",
        "#   - Send /newbot",
        "#   - Name: %s Bot" % plan_name,
        "#   - Username: Owner_%s_bot" % plan_id,
        "#   - Save the token",
        "",
        "# Step 2: Configure",
        "#   Edit bot_config.yaml and fill in:",
        "#     bot_token: <your-token-here>",
        "#     chat_id: <your-chat-id>",
        "",
        "# Step 3: Start bot",
        "#   python3 bot_template.py",
        "",
        "# Step 4: Test",
        "#   Open the bot in Telegram, send /start",
        "",
        "# Step 5: Register with Hermes",
        "#   The bot will auto-register via heartbeat.",
        "#   Monitor with: python3 monitor.py",
        "",
    ]
    return '\n'.join(lines)


def build_plan(blueprint):
    """
    Phase 6: 建造 — 從藍圖生成實際檔案。

    Takes a blueprint dict and creates:
      1. PLAN directory
      2. main.py (based on tech stack)
      3. monitor.py (health check)
      4. skill.json (restart skill)
      5. heartbeat.json (template)
      6. If telegram: bot register template + bot_config.yaml
    """
    plan_id = blueprint["plan_id"]
    plan_name = blueprint["name"]
    plan_dir = PLANS_DIR / plan_id
    plan_dir.mkdir(parents=True, exist_ok=True)

    files_created = []

    print("\n" + "=" * 60)
    print("  Phase 6: Building PLAN '%s'" % plan_name)
    print("  Directory: %s" % plan_dir)
    print("=" * 60)

    # 1. Generate main.py
    print("\n  Generating main.py...")
    main_code = _gen_main_py(blueprint)
    main_path = plan_dir / "main.py"
    with open(main_path, "w", encoding="utf-8") as f:
        f.write(main_code)
    os.chmod(str(main_path), 0o755)
    files_created.append(str(main_path))
    print("    OK %s" % main_path)

    # 2. Generate monitor.py
    print("  Generating monitor.py...")
    monitor_code = _gen_monitor_py(blueprint)
    monitor_path = plan_dir / "monitor.py"
    with open(monitor_path, "w", encoding="utf-8") as f:
        f.write(monitor_code)
    os.chmod(str(monitor_path), 0o755)
    files_created.append(str(monitor_path))
    print("    OK %s" % monitor_path)

    # 3. Generate skill.json
    print("  Generating skill.json...")
    skill_code = _gen_skill_json(blueprint)
    skill_path = plan_dir / "skill.json"
    with open(skill_path, "w", encoding="utf-8") as f:
        f.write(skill_code)
    files_created.append(str(skill_path))
    print("    OK %s" % skill_path)

    # 4. Create heartbeat.json template
    print("  Creating heartbeat.json...")
    hb_code = _gen_heartbeat_template(blueprint)
    hb_path = plan_dir / "heartbeat.json"
    with open(hb_path, "w", encoding="utf-8") as f:
        f.write(hb_code)
    files_created.append(str(hb_path))
    print("    OK %s" % hb_path)

    # 5. If telegram channel: generate bot register template
    channels = blueprint.get("channels", [])
    has_telegram = any(c.get("type") == "telegram" for c in channels)
    if has_telegram:
        print("  Generating bot registration guide...")
        reg_code = _gen_bot_register_template(blueprint)
        reg_path = plan_dir / "bot_register.md"
        with open(reg_path, "w", encoding="utf-8") as f:
            f.write(reg_code)
        files_created.append(str(reg_path))
        print("    OK %s" % reg_path)

        # Check if bot_config.yaml already exists (from Phase 6b)
        bot_config_path = plan_dir / "bot_config.yaml"
        if not bot_config_path.exists():
            print("  Generating bot_config.yaml + bot_template.py...")
            create_plan_bot(plan_name, plan_id)

    # 6. Save blueprint if not already saved
    bp_path = plan_dir / "blueprint.json"
    if not bp_path.exists():
        save_json(bp_path, blueprint)
        files_created.append(str(bp_path))
        print("    OK %s (blueprint)" % bp_path)

    # Summary
    print("\n" + "=" * 60)
    print("  Build complete: %s" % plan_name)
    print("  Files created: %d" % len(files_created))
    for f in files_created:
        print("    %s" % f)
    print("=" * 60 + "\n")

    return {
        "plan_id": plan_id,
        "plan_name": plan_name,
        "files_created": files_created,
        "status": "built",
    }



def build_creation_path(plan):
    """
    建立創造路徑（A→B→C→D→E→F）
    這是將來排查問題的依據：建的時候怎麼建的，修的時候就怎麼查。
    """
    channels = plan["phases"].get("phase_2_channels", [])
    data = plan["phases"].get("phase_3_data", {})
    tech = plan["phases"].get("phase_4_tech", {})
    
    path = []
    step = ord("A")
    
    # 每個 channel 都是一個節點
    for ch in channels:
        path.append({
            "step": chr(step),
            "name": f"{ch['type']}_setup",
            "description": f"建立 {ch['type']} 通訊管道",
            "components": ch.get("features", []),
            "check_when_debug": f"檢查 {ch['type']} 連線、token、進程",
        })
        step += 1
    
    # 資料層是一個節點
    path.append({
        "step": chr(step),
        "name": "data_layer",
        "description": f"建立 {data['type']} 資料層",
        "components": ["資料庫連線", "CRUD API", "備份機制"],
        "check_when_debug": f"檢查 {data['type']} 連線、資料完整性、磁碟空間",
    })
    step += 1
    
    # 監控是一個節點
    path.append({
        "step": chr(step),
        "name": "monitoring",
        "description": "建立監控和自治系統",
        "components": ["健康檢查", "心跳", "自動修復", "skill"],
        "check_when_debug": "檢查心跳是否更新、cron job 是否運行",
    })
    
    return path


def create_plan_blueprint(name, description, plan):
    """Phase 6: 生成 PLAN 藍圖（不是直接建，而是產出規格書）"""
    blueprint = {
        "plan_id": generate_plan_id(name),
        "name": name,
        "description": description,
        "created_at": now_iso(),
        
        "channels": plan["phases"].get("phase_2_channels", []),
        "data_layer": plan["phases"].get("phase_3_data", {}),
        "tech_stack": plan["phases"].get("phase_4_tech", {}),
        "autonomy_rules": plan["phases"].get("phase_5_autonomy", {}),
        "creation_path": plan["phases"].get("creation_path", []),
        
        "files_to_create": [],
        "external_actions": [],  # 需要外部操作的（如創建 TG Bot）
        "registry_entry": {},
    }
    
    # 生成檔案清單
    plan_dir = PLANS_DIR / blueprint["plan_id"]
    blueprint["files_to_create"] = [
        str(plan_dir / "main.py"),
        str(plan_dir / "monitor.py"),
        str(plan_dir / "skill.json"),
        str(plan_dir / "heartbeat.json"),
    ]
    
    # Phase 6b: 自動建立 PLAN 專屬 Telegram Bot
    bot_info = None
    for ch in blueprint["channels"]:
        if ch["type"] == "telegram":
            print(f"    🤖 自動建立 Telegram Bot...")
            bot_info = create_plan_bot(name, blueprint["plan_id"])
            blueprint["files_to_create"].append(bot_info["config_path"])
            blueprint["files_to_create"].append(bot_info["bot_template_path"])
            break
    
    # 外部動作清單
    for ch in blueprint["channels"]:
        if ch["type"] == "telegram":
            action = {
                "action": "create_telegram_bot",
                "description": f"創建 Telegram Bot: {bot_info['bot_name'] if bot_info else '@Owner_xxx_bot'}",
                "steps": bot_info["next_steps"] if bot_info else [
                    "1. 決定 bot 名稱（跟 PLAN 相關）",
                    "2. 呼叫 BotFather 創建 bot",
                    "3. 取得 bot token",
                    "4. 寫入 .env",
                    "5. 部署 bot 代碼",
                    "6. 測試 /start 指令",
                ],
                "requires_human": True,
                "human_action": f"在 @BotFather 建立 bot，取得 token 後填入 bot_config.yaml",
                "bot_config": str(plan_dir / "bot_config.yaml") if bot_info else None,
                "bot_template": str(plan_dir / "bot_template.py") if bot_info else None,
            }
            blueprint["external_actions"].append(action)
    
    # Registry 登記資訊
    blueprint["registry_entry"] = {
        "plan_id": blueprint["plan_id"],
        "name": name,
        "description": description,
        "domain": infer_domain(description),
        "heartbeat_path": str(plan_dir / "heartbeat.json"),
    }
    
    return blueprint


def infer_domain(description):
    """推斷 PLAN 所屬領域"""
    if any(kw in description for kw in ["交易", "Trading", "策略", "競技場"]):
        return "trading"
    if any(kw in description for kw in ["POS", "收銀", "訂單"]):
        return "pos"
    if any(kw in description for kw in ["材料", "庫存", "倉庫"]):
        return "inventory"
    if any(kw in description for kw in ["bot", "Bot", "Telegram"]):
        return "bots"
    return "general"


# ══════════════════════════════════════════════════════════════
#  創造路徑追蹤 & 問題排查
# ══════════════════════════════════════════════════════════════

def trace_creation_path(plan_id):
    """追蹤 PLAN 的創造路徑"""
    plan_file = PLANS_DIR / plan_id / "blueprint.json"
    if not plan_file.exists():
        return {"error": f"PLAN '{plan_id}' 不存在"}
    
    blueprint = load_json(plan_file)
    path = blueprint.get("creation_path", [])
    
    result = {
        "plan_id": plan_id,
        "name": blueprint.get("name"),
        "creation_path": path,
        "total_steps": len(path),
    }
    
    return result


def debug_plan(plan_id, problem_description):
    """
    沿創造路徑排查問題。
    建的時候怎麼建的，修的時候就怎麼查。
    """
    plan_file = PLANS_DIR / plan_id / "blueprint.json"
    if not plan_file.exists():
        return {"error": f"PLAN '{plan_id}' 不存在"}
    
    blueprint = load_json(plan_file)
    path = blueprint.get("creation_path", [])
    channels = blueprint.get("channels", [])
    
    diagnosis = {
        "plan_id": plan_id,
        "problem": problem_description,
        "traced_at": now_iso(),
        "steps_checked": [],
        "likely_cause": None,
        "suggested_fix": None,
    }
    
    # 沿創造路徑逐節點檢查
    for step in path:
        check = {
            "step": step["step"],
            "name": step["name"],
            "description": step["description"],
            "check_method": step.get("check_when_debug", ""),
            "status": "pending",
        }
        diagnosis["steps_checked"].append(check)
    
    # 根據問題描述推斷最可能的問題節點
    problem_lower = problem_description.lower()
    
    if any(kw in problem_lower for kw in ["沒反應", "不回應", "無回覆", "沒回"]):
        # 通常是通訊層問題
        for step in diagnosis["steps_checked"]:
            if "telegram" in step["name"]:
                step["status"] = "suspect"
                diagnosis["likely_cause"] = f"可能是 {step['name']} 的問題"
                diagnosis["suggested_fix"] = "檢查 bot 進程、token 有效性、網路連線"
                break
    
    elif any(kw in problem_lower for kw in ["資料", "數據", "查不到", "錯誤"]):
        # 通常是資料層問題
        for step in diagnosis["steps_checked"]:
            if "data" in step["name"]:
                step["status"] = "suspect"
                diagnosis["likely_cause"] = f"可能是 {step['name']} 的問題"
                diagnosis["suggested_fix"] = "檢查資料庫連線、資料完整性、最近的寫入操作"
                break
    
    elif any(kw in problem_lower for kw in ["慢", "lag", "延遲"]):
        # 通常是效能問題
        diagnosis["likely_cause"] = "效能問題"
        diagnosis["suggested_fix"] = "檢查 CPU/記憶體使用、資料庫查詢效率、網路延遲"
    
    else:
        # 未知問題，全路徑掃描
        diagnosis["likely_cause"] = "需要全路徑掃描"
        diagnosis["suggested_fix"] = "沿 A→B→C→D→E→F 逐節點檢查"
    
    return diagnosis


# ══════════════════════════════════════════════════════════════
#  主流程
# ══════════════════════════════════════════════════════════════

def create_plan(name, description):
    """
    PLAN 工廠的主入口。
    從一個點子開始，走完 Phase 1-8，產出完整藍圖。
    """
    # 載入 Owner 使用習慣
    profile = load_yaml(PROFILE_FILE)
    
    print(f"\n{'='*60}")
    print(f"  PLAN Factory — 誕生新 PLAN")
    print(f"  名稱: {name}")
    print(f"  描述: {description}")
    print(f"{'='*60}")
    
    # Phase 1: 需求分析
    print(f"\n  Phase 1: 需求分析...")
    plan, analysis = analyze_idea(description, profile)
    print(f"    使用者: {analysis['users']['type']} ({analysis['users']['note']})")
    print(f"    場景: {analysis['usage_scenario']}")
    print(f"    資料量: {analysis['data_volume']}")
    print(f"    即時需求: {analysis['realtime_need']}")
    if analysis['existing_integrations']:
        print(f"    整合需求: {analysis['existing_integrations']}")
    
    # Phase 2: 媒介選擇
    print(f"\n  Phase 2: 媒介選擇...")
    channels = decide_channels(analysis, profile)
    plan["phases"]["phase_2_channels"] = channels
    for ch in channels:
        print(f"    ✅ {ch['type']} — {ch['reason']}")
        print(f"       功能: {ch['features']}")
    
    # Phase 3: 資料管理
    print(f"\n  Phase 3: 資料管理...")
    data_layer = decide_data_layer(analysis, profile)
    plan["phases"]["phase_3_data"] = data_layer
    print(f"    類型: {data_layer['type']} ({data_layer['reason']})")
    if data_layer.get("api_layer"):
        print(f"    API 層: 需要（整合: {data_layer.get('integrations', [])}）")
    
    # Phase 4: 技術棧
    print(f"\n  Phase 4: 技術棧...")
    tech = decide_tech_stack(channels, data_layer, profile)
    plan["phases"]["phase_4_tech"] = tech
    print(f"    語言: {tech['language']}")
    print(f"    套件: {', '.join(tech['libraries'])}")
    if tech.get("framework"):
        print(f"    框架: {tech['framework']}")
    
    # Phase 5: 自治規則
    print(f"\n  Phase 5: 自治規則...")
    autonomy = decide_autonomy_rules(analysis, profile)
    plan["phases"]["phase_5_autonomy"] = autonomy
    print(f"    自動處理: {len(autonomy['auto_fix'])} 條規則")
    print(f"    通知主人: {len(autonomy['notify_owner'])} 條規則")
    print(f"    報告頻率: {autonomy['report_frequency']}")
    
    # 建立創造路徑
    print(f"\n  建立創造路徑...")
    creation_path = build_creation_path(plan)
    plan["phases"]["creation_path"] = creation_path
    for step in creation_path:
        print(f"    {step['step']}: {step['name']} — {step['description']}")
    
    # Phase 6: 生成藍圖
    print(f"\n  Phase 6: 生成藍圖...")
    blueprint = create_plan_blueprint(name, description, plan)
    
    # 儲存藍圖
    plan_dir = PLANS_DIR / blueprint["plan_id"]
    plan_dir.mkdir(parents=True, exist_ok=True)
    save_json(plan_dir / "blueprint.json", blueprint)
    print(f"    藍圖已儲存: {plan_dir / 'blueprint.json'}")
    
    # 列出需要建立的檔案
    print(f"\n  需要建立的檔案:")
    for f in blueprint["files_to_create"]:
        print(f"    📄 {f}")
    
    # 列出外部動作
    if blueprint["external_actions"]:
        print(f"\n  需要外部操作:")
        for action in blueprint["external_actions"]:
            print(f"    🔗 {action['description']}")
            if action.get("requires_human"):
                print(f"       ⚠️ 需要人類介入: {action['human_action']}")
    
    # Phase 7: 登記到 Registry
    print(f"\n  Phase 7: 登記到 PLAN Registry...")
    register_plan(blueprint["registry_entry"])
    print(f"    ✅ 已登記: {blueprint['plan_id']}")
    
    # Phase 8: 回報
    print(f"\n  Phase 8: 回報")
    report = {
        "plan_id": blueprint["plan_id"],
        "name": name,
        "status": "blueprint_ready",
        "channels": [ch["type"] for ch in channels],
        "data_layer": data_layer["type"],
        "creation_path_steps": len(creation_path),
        "external_actions_needed": len(blueprint["external_actions"]),
        "next_step": "執行建造（需要人類確認後開始）",
    }
    
    print(f"\n{'='*60}")
    print(f"  ✅ PLAN 藍圖完成!")
    print(f"  plan_id: {report['plan_id']}")
    print(f"  媒介: {', '.join(report['channels'])}")
    print(f"  資料: {report['data_layer']}")
    print(f"  創造路徑: {report['creation_path_steps']} 個節點")
    if report["external_actions_needed"]:
        print(f"  ⚠️ 需要 {report['external_actions_needed']} 個外部操作")
    print(f"{'='*60}\n")
    
    return report


def register_plan(entry):
    """登記到 PLAN Registry.

    Routes through ``PlanRegistry.register()`` so that:
      - registry.json updates go through the same locked path as manual register
      - registry_log.json gets the audit entry
      - events.jsonl gets a ``plan_registered`` event
    Falls back to direct file write only if the registry module can't be imported.
    """
    try:
        # Try to call into the canonical class so we share locking + audit log.
        # plan_registry.py lives in the same `core/` directory at install time.
        from pathlib import Path as _P
        import sys as _sys
        _sys.path.insert(0, str(_P(__file__).resolve().parent))
        try:
            from plan_registry import PlanRegistry  # type: ignore
        finally:
            _sys.path.pop(0)
        reg = PlanRegistry()
        reg.register(
            plan_id=entry["plan_id"],
            name=entry["name"],
            description=entry.get("description", ""),
            heartbeat_path=entry.get("heartbeat_path", ""),
            domain=entry.get("domain", "general"),
            owner="Owner",
        )
        return
    except Exception as exc:
        print(f"  ⚠ register via PlanRegistry failed ({exc}), falling back to direct write")

    # Fallback (best-effort, no audit log)
    registry = load_json(REGISTRY_FILE, {"plans": {}})
    if "plans" not in registry:
        registry["plans"] = {}
    registry["plans"][entry["plan_id"]] = {
        "plan_id": entry["plan_id"],
        "name": entry["name"],
        "description": entry.get("description", ""),
        "domain": entry.get("domain", "general"),
        "owner": "Owner",
        "created_at": now_iso(),
        "status": "registered",
        "heartbeat": {
            "path": entry.get("heartbeat_path", ""),
            "last_read": None,
            "last_score": None,
            "last_status": None,
        },
        "paths": {"report": None, "command": None, "response": None},
        "metadata": {},
        "stats": {"total_heartbeats": 0, "total_commands": 0},
    }
    registry["last_updated"] = now_iso()
    save_json(REGISTRY_FILE, registry)


def list_plans():
    """列出所有由 Factory 誕生的 PLAN"""
    plans = []
    for plan_dir in PLANS_DIR.iterdir():
        if plan_dir.is_dir():
            bp_file = plan_dir / "blueprint.json"
            if bp_file.exists():
                bp = load_json(bp_file)
                plans.append({
                    "plan_id": bp.get("plan_id"),
                    "name": bp.get("name"),
                    "channels": [ch["type"] for ch in bp.get("channels", [])],
                    "created_at": bp.get("created_at"),
                })
    return plans


# ══════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    args = sys.argv[1:]
    
    if not args or args[0] == "help":
        print("""
PLAN Factory — 從點子到全自治 PLAN 的誕生引擎

用法:
  python3 plan_factory.py create <name> <description>
  python3 plan_factory.py bot <plan_name> <plan_id>    # 為 PLAN 建立專屬 TG Bot
  python3 plan_factory.py list
  python3 plan_factory.py trace <plan_id>
  python3 plan_factory.py debug <plan_id> <problem>
  python3 plan_factory.py build <plan_id>          # Build actual files from blueprint
""")

    elif args[0] == "create":
        if len(args) >= 3:
            create_plan(args[1], " ".join(args[2:]))
        elif len(args) == 2:
            desc = args[1]
            name = desc[:20].replace(" ", "_")
            create_plan(name, desc)
        else:
            print("Usage: python3 plan_factory.py create <name> <description>")

    elif args[0] == "bot":
        if len(args) >= 3:
            create_plan_bot(args[1], args[2])
        elif len(args) == 2:
            plan_id = generate_plan_id(args[1])
            create_plan_bot(args[1], plan_id)
        else:
            print("Usage: python3 plan_factory.py bot <plan_name> [plan_id]")

    elif args[0] == "list":
        plans = list_plans()
        if plans:
            print(f"\n  Plans created by Factory ({len(plans)}):")
            for p in plans:
                print(f"    {p['plan_id']:20s} | {p['name']} | {', '.join(p['channels'])}")
        else:
            print("  No plans created by Factory yet")

    elif args[0] == "trace":
        if len(args) >= 2:
            result = trace_creation_path(args[1])
            if "error" in result:
                print(f"  ERROR: {result['error']}")
            else:
                print(f"\n  Creation path: {result['name']}")
                for step in result["creation_path"]:
                    print(f"    {step['step']}: {step['name']} - {step['description']}")

    elif args[0] == "debug":
        if len(args) >= 3:
            result = debug_plan(args[1], " ".join(args[2:]))
            if "error" in result:
                print(f"  ERROR: {result['error']}")
            else:
                print(f"\n  Problem trace: {result['problem']}")
                print(f"  Likely cause: {result['likely_cause']}")
                print(f"  Suggested fix: {result['suggested_fix']}")
                print(f"\n  Steps checked:")
                for step in result["steps_checked"]:
                    marker = ">>>" if step["status"] == "suspect" else "   "
                    print(f"    {marker} {step['step']}: {step['name']}")

    elif args[0] == "build":
        if len(args) >= 2:
            plan_id = args[1]
            plan_dir = PLANS_DIR / plan_id
            bp_file = plan_dir / "blueprint.json"
            if not bp_file.exists():
                print(f"  Blueprint not found: {bp_file}")
                print("  Run 'create' first to generate a blueprint.")
            else:
                blueprint = load_json(bp_file)
                build_plan(blueprint)
        else:
            print("Usage: python3 plan_factory.py build <plan_id>")
