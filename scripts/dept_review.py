#!/usr/bin/env python3
"""
AC4: Department Review Processor

Takes a concept cell and generates structured review for each C-Level agent.
Reads concept from file or stdin, outputs review template.

Usage:
  python3 dept_review.py CON-20260506-001
  python3 dept_review.py --file concept.json
  echo '{"concept_id":...}' | python3 dept_review.py --stdin

This processor generates the review FRAMEWORK.
Actual agent opinions come from Hermes's integrated analysis.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

TZ = timezone(timedelta(hours=8))
COMPANY_DIR = Path.home() / ".hermes" / "company"
CONCEPTS_DIR = COMPANY_DIR / "01-concepts"
AGENT_REG = COMPANY_DIR / "agent_registry.json"

# Department review question templates per agent
REVIEW_QUESTIONS = {
    "ceo": {
        "role": "Chief Executive Officer",
        "questions": [
            "這件事的方向對嗎？符合公司長期目標嗎？",
            "值不值得投入資源？ROI 如何？",
            "和其他正在做的事情有衝突嗎？",
            "如果只做一件事，這件是對的嗎？",
        ],
        "output_fields": ["direction_aligned", "worth_investing", "conflicts", "priority_rank"],
    },
    "coo": {
        "role": "Chief Operating Officer",
        "questions": [
            "運作上可行嗎？需要什麼流程？",
            "現有 BU 會受影響嗎？",
            "日常維護成本多高？",
            "從開始到上線需要幾步？",
        ],
        "output_fields": ["operational_feasibility", "bu_impact", "maintenance_cost", "steps_to_launch"],
    },
    "cto": {
        "role": "Chief Technology Officer",
        "questions": [
            "技術上可行嗎？需要什麼基礎設施？",
            "現有技術棧能支持嗎？",
            "有技術債要先還嗎？",
            "安全性 / 可靠性如何保證？",
        ],
        "output_fields": ["tech_feasibility", "infrastructure_needed", "tech_debt", "security_risk"],
    },
    "cfo": {
        "role": "Chief Financial Officer",
        "questions": [
            "成本結構是什麼？固定 vs 變動？",
            "API / Token 用量預估？",
            "回收期多長？",
            "有沒有更便宜的替代方案？",
        ],
        "output_fields": ["cost_structure", "api_usage_estimate", "payback_period", "cheaper_alternatives"],
    },
    "cmo": {
        "role": "Chief Marketing Officer",
        "questions": [
            "用戶 / 客戶是誰？他們要什麼？",
            "現有管道能觸及嗎？",
            "品牌定位一致嗎？",
            "競爭者在做什麼？",
        ],
        "output_fields": ["target_user", "channel_reach", "brand_fit", "competitor_analysis"],
    },
    "chro": {
        "role": "Chief Human Resources Officer",
        "questions": [
            "需要什麼角色 / 技能？現有 Agent 夠嗎？",
            "工作量分配合理嗎？",
            "有技能差距嗎？怎麼補？",
            "衝突風險？",
        ],
        "output_fields": ["roles_needed", "agent_capacity", "skill_gap", "conflict_risk"],
    },
    "cao": {
        "role": "Chief Assurance Officer",
        "questions": [
            "有什麼風險？最壞情況是什麼？",
            "驗證夠嗎？有沒有虛假前提？",
            "如果失敗，損失是什麼？",
            "有沒有看不見的副作用？",
        ],
        "output_fields": ["risk_assessment", "false_premise_risk", "failure_impact", "hidden_side_effects"],
    },
}


def load_concept(concept_id: str = None, file_path: str = None) -> dict:
    """Load concept cell from file."""
    if file_path:
        return json.loads(Path(file_path).read_text())
    elif concept_id:
        path = CONCEPTS_DIR / f"{concept_id}.json"
        return json.loads(path.read_text())
    elif not sys.stdin.isatty():
        return json.loads(sys.stdin.read())
    else:
        raise ValueError("Provide concept_id, --file, or pipe JSON to stdin")


def generate_review_framework(concept: dict) -> dict:
    """Generate review framework for all 7 departments."""
    now = datetime.now(TZ)
    raw_idea = concept.get("raw_idea", "")
    cats = concept.get("classification", [])

    framework = {
        "concept_id": concept["concept_id"],
        "raw_idea": raw_idea,
        "classification": cats,
        "generated_at": now.isoformat(),
        "reviews": {},
    }

    for agent_id, agent_config in REVIEW_QUESTIONS.items():
        review = {
            "agent_id": agent_id,
            "role": agent_config["role"],
            "questions": agent_config["questions"],
            "output_fields": agent_config["output_fields"],
            "answers": {field: None for field in agent_config["output_fields"]},
            "opinion": None,
            "risk_level": None,
            "recommendation": None,  # proceed / investigate / reject / defer
        }
        framework["reviews"][agent_id] = review

    return framework


def calculate_readiness(framework: dict) -> dict:
    """Calculate decision readiness based on review completeness."""
    reviews = framework.get("reviews", {})
    total = len(reviews)
    completed = sum(1 for r in reviews.values() if r.get("opinion") is not None)

    blockers = []
    for agent_id, review in reviews.items():
        if review.get("recommendation") == "reject":
            blockers.append(f"{agent_id}: rejected")
        elif review.get("risk_level") == "critical":
            blockers.append(f"{agent_id}: critical risk")

    ready = (
        completed >= 5  # at least 5/7 reviews
        and len(blockers) == 0
        and framework.get("cheapest_verification_done", False)
    )

    # Determine recommended next step
    if not ready:
        if completed < 3:
            next_step = "need_more_reviews"
        elif blockers:
            next_step = "resolve_blockers"
        else:
            next_step = "run_cheapest_verification"
    else:
        reject_count = sum(1 for r in reviews.values() if r.get("recommendation") == "reject")
        if reject_count >= 3:
            next_step = "reject"
        else:
            proceed_count = sum(1 for r in reviews.values() if r.get("recommendation") == "proceed")
            if proceed_count >= 4:
                next_step = "create_plan_candidate"
            else:
                next_step = "run_small_test"

    return {
        "ready": ready,
        "reviews_complete": f"{completed}/{total}",
        "blockers": blockers,
        "recommended_next_step": next_step,
    }


def format_review(framework: dict) -> str:
    """Format review framework as readable text."""
    lines = []
    lines.append(f"Department Review: {framework['concept_id']}")
    lines.append(f"Raw Idea: {framework['raw_idea']}")
    lines.append(f"Classification: {', '.join(framework['classification'])}")
    lines.append(f"Generated: {framework['generated_at'][:19]}")
    lines.append("")

    for agent_id, review in framework["reviews"].items():
        lines.append(f"### {agent_id.upper()} ({review['role']})")
        lines.append(f"  Questions:")
        for q in review["questions"]:
            lines.append(f"    - {q}")
        opinion = review.get("opinion") or "(pending)"
        recommendation = review.get("recommendation") or "(pending)"
        risk = review.get("risk_level") or "(pending)"
        lines.append(f"  Opinion: {opinion}")
        lines.append(f"  Risk: {risk}")
        lines.append(f"  Recommendation: {recommendation}")
        lines.append("")

    readiness = calculate_readiness(framework)
    lines.append("### Decision Readiness")
    lines.append(f"  Ready: {readiness['ready']}")
    lines.append(f"  Reviews: {readiness['reviews_complete']}")
    lines.append(f"  Blockers: {readiness['blockers'] or 'none'}")
    lines.append(f"  Next: {readiness['recommended_next_step']}")

    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Department Review Processor")
    parser.add_argument("concept_id", nargs="?", help="Concept ID")
    parser.add_argument("--file", help="Concept cell JSON file")
    parser.add_argument("--stdin", action="store_true", help="Read from stdin")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--save", action="store_true", help="Save review to file")
    args = parser.parse_args()

    try:
        if args.stdin:
            concept = json.loads(sys.stdin.read())
        elif args.file:
            concept = load_concept(file_path=args.file)
        elif args.concept_id:
            concept = load_concept(concept_id=args.concept_id)
        else:
            parser.print_help()
            sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    framework = generate_review_framework(concept)

    if args.save:
        review_dir = COMPANY_DIR / "01-concepts"
        review_dir.mkdir(parents=True, exist_ok=True)
        cid = concept["concept_id"]
        path = review_dir / f"{cid}_review.json"
        path.write_text(json.dumps(framework, indent=2, ensure_ascii=False))
        print(f"Saved: {path}")

    if args.json:
        print(json.dumps(framework, indent=2, ensure_ascii=False))
    else:
        print(format_review(framework))


if __name__ == "__main__":
    main()
