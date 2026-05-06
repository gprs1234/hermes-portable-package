#!/usr/bin/env python3
"""
AC3: Concept Cell Intake Processor

Converts Nomi's raw natural language into a structured Concept Cell.
Reads from stdin or --text argument, outputs YAML-formatted concept cell.

Usage:
  echo "我想做攤車" | python3 concept_intake.py
  python3 concept_intake.py --text "百大這樣怪怪的"
  python3 concept_intake.py --text "我想做攤車" --source nomi

Output: concept cell YAML to stdout + saves to concept_cells/ directory
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

TZ = timezone(timedelta(hours=8))
COMPANY_DIR = Path.home() / ".hermes" / "company"
CONCEPTS_DIR = COMPANY_DIR / "01-concepts"
TEMPLATE_PATH = COMPANY_DIR / "03-sop" / "concept_cell_template.md"

# Classification patterns
CLASSIFICATION_PATTERNS = {
    "new_business": ["想做", "想開", "創業", "生意", "攤車", "店面", "產品"],
    "existing_bu_problem": ["怪怪的", "不對", "出問題", "壞了", "失常", "異常"],
    "process_improvement": ["改善", "優化", "流程", "效率", "更快"],
    "tool_tech": ["工具", "系統", "程式", "API", "架構"],
    "market_observation": ["市場", "用戶", "客戶", "需求", "競爭"],
    "cost_resource": ["成本", "花費", "預算", "省錢", "資源"],
    "architecture": ["設計", "架構", "結構", "模式"],
}

TITLE_CHECK_PATTERNS = {
    "describes_phenomenon": ["怪怪的", "感覺", "好像", "似乎"],
    "proposes_vision": ["想做", "想要", "希望", "目標"],
    "points_problem": ["不對", "問題", "錯誤", "bug", "壞"],
    "hypothesis": ["覺得", "可能", "應該", "假設"],
}


def classify(raw_idea: str) -> dict:
    """Classify the raw idea into type and title check."""
    idea_lower = raw_idea.lower()

    # Title check
    title_type = "unknown"
    for ttype, patterns in TITLE_CHECK_PATTERNS.items():
        if any(p in idea_lower for p in patterns):
            title_type = ttype
            break

    # Classification
    categories = []
    for cat, patterns in CLASSIFICATION_PATTERNS.items():
        if any(p in idea_lower for p in patterns):
            categories.append(cat)

    if not categories:
        categories = ["unknown"]

    return {
        "title_check": title_type,
        "classification": categories,
    }


def generate_concept_id() -> str:
    """Generate sequential concept ID."""
    now = datetime.now(TZ)
    date_str = now.strftime("%Y%m%d")
    CONCEPTS_DIR.mkdir(parents=True, exist_ok=True)
    existing = list(CONCEPTS_DIR.glob(f"CON-{date_str}-*.json"))
    seq = len(existing) + 1
    return f"CON-{date_str}-{seq:03d}"


def build_concept_cell(raw_idea: str, source: str = "nomi") -> dict:
    """Build a concept cell from raw idea."""
    now = datetime.now(TZ)
    concept_id = generate_concept_id()
    classification = classify(raw_idea)

    # Determine title
    title_check = classification["title_check"]
    if title_check == "describes_phenomenon":
        title = f"現象觀察: {raw_idea[:30]}"
    elif title_check == "proposes_vision":
        title = f"願景: {raw_idea[:30]}"
    elif title_check == "points_problem":
        title = f"問題: {raw_idea[:30]}"
    elif title_check == "hypothesis":
        title = f"假設: {raw_idea[:30]}"
    else:
        title = raw_idea[:40]

    # Generate cheapest verification suggestions based on type
    verifications = []
    necessary_parts = []
    unknowns = []
    cats = classification["classification"]
    if "new_business" in cats:
        verifications = [
            "找 3 個類似案例看他們怎麼做的",
            "畫一張最小可行的服務流程圖",
            "問自己：第一個客戶是誰？怎麼找到他？",
        ]
        # Enrich based on keywords in raw idea
        idea_lower = raw_idea.lower()
        if any(kw in idea_lower for kw in ["攤", "餐", "賣", "小吃", "雞排", "飲料", "咖啡"]):
            necessary_parts = [
                "商品/菜單設計",
                "器材與設備清單",
                "車體/攤位型態與尺寸",
                "動線規劃與空間配置",
                "食材供應鏈與進貨成本",
                "人力配置",
                "地點選擇與目標客群",
                "法規與營業許可",
                "定價策略",
                "現金流與損益平衡分析",
            ]
            unknowns = [
                "先選車還是先選器材",
                "目標客群與最佳地點",
                "單日損益平衡點是多少",
                "需要哪些法規許可證",
            ]
            verifications = [
                "先列器材尺寸並畫配置圖，再反推車型需求",
                "找 3 個同類攤車案例（地點、菜單、月營收）",
                "估算一日固定成本、食材成本與打平銷量",
                "實際去目標地點觀察人流量 3 天",
                "問 2 個有經驗的攤車老闆",
            ]
        elif any(kw in idea_lower for kw in ["網", "電商", "平台", "app", "網站"]):
            necessary_parts = [
                "目標用戶與需求驗證",
                "核心功能清單 (MVP)",
                "技術架構",
                "獲利模式",
                "行銷渠道",
                "競爭者分析",
            ]
            unknowns = [
                "用戶真的需要嗎？",
                "競品是誰？差異化在哪？",
                "第一版要做到什麼程度？",
            ]
        else:
            necessary_parts = [
                "產品/服務定義",
                "目標客群",
                "成本結構",
                "獲利模式",
                "第一個里程碑",
            ]
            unknowns = [
                "這個需求是真實的嗎？",
                "有人願意付錢嗎？",
                "最小可行版本是什麼？",
            ]
    elif "existing_bu_problem" in cats:
        verifications = [
            "確認問題是持續發生還是偶發",
            "查看最近的異常紀錄和日誌",
            "比對正常運作時和現在的差異",
        ]
    elif "process_improvement" in cats:
        verifications = [
            "記錄現在流程的實際時間和步驟",
            "找出最耗時的 3 個步驟",
            "先改一個最痛的點測試效果",
        ]
    else:
        verifications = ["收集更多資訊再判斷"]

    concept = {
        "concept_id": concept_id,
        "title": title,
        "source": source,
        "created_at": now.isoformat(),
        "status": "raw",
        "raw_idea": raw_idea,
        "classification": classification["classification"],
        "title_check": classification["title_check"],
        "shape": {
            "necessary_parts": necessary_parts,
            "unknowns": unknowns,
        },
        "cheapest_verification": verifications,
        "department_review": {
            "ceo": None,
            "coo": None,
            "cto": None,
            "cfo": None,
            "cmo": None,
            "chro": None,
            "cao": None,
        },
        "decision_readiness": {
            "ready": False,
            "blocking_unknowns": -1,
            "cheapest_verification_done": False,
            "department_reviews_complete": 0,
            "recommended_next_step": None,
        },
    }

    return concept


def save_concept(concept: dict) -> Path:
    """Save concept cell to file."""
    CONCEPTS_DIR.mkdir(parents=True, exist_ok=True)
    concept_id = concept["concept_id"]
    path = CONCEPTS_DIR / f"{concept_id}.json"
    path.write_text(json.dumps(concept, indent=2, ensure_ascii=False))
    return path


def format_concept(concept: dict) -> str:
    """Format concept cell as readable text."""
    lines = []
    lines.append(f"Concept Cell: {concept['concept_id']}")
    lines.append(f"Title: {concept['title']}")
    lines.append(f"Source: {concept['source']}")
    lines.append(f"Status: {concept['status']}")
    lines.append(f"Created: {concept['created_at'][:19]}")
    lines.append("")
    lines.append(f"Raw Idea: {concept['raw_idea']}")
    lines.append("")
    lines.append(f"Classification: {', '.join(concept['classification'])}")
    lines.append(f"Title Check: {concept['title_check']}")
    lines.append("")
    lines.append("Cheapest Verification:")
    for v in concept["cheapest_verification"]:
        lines.append(f"  - {v}")
    lines.append("")
    lines.append("Department Review: pending (7 agents)")
    lines.append(f"Decision Readiness: {concept['decision_readiness']['ready']}")
    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Concept Cell Intake Processor")
    parser.add_argument("--text", help="Raw idea text")
    parser.add_argument("--source", default="nomi", help="Source (default: nomi)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.text:
        raw_idea = args.text
    elif not sys.stdin.isatty():
        raw_idea = sys.stdin.read().strip()
    else:
        print("Usage: echo 'idea' | python3 concept_intake.py")
        print("   or: python3 concept_intake.py --text 'idea'")
        sys.exit(1)

    if not raw_idea:
        print("ERROR: No input provided")
        sys.exit(1)

    concept = build_concept_cell(raw_idea, args.source)
    path = save_concept(concept)

    if args.json:
        print(json.dumps(concept, indent=2, ensure_ascii=False))
    else:
        print(format_concept(concept))
        print(f"\nSaved: {path}")


if __name__ == "__main__":
    main()
