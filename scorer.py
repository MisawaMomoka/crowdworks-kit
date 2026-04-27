"""
scorer.py - 5項目スコアリングモジュール
"""

import re

HIGH_SKILL_KEYWORDS = [
    "プログラミング", "エンジニア", "開発", "デザイン", "Webデザイン",
    "マーケティング", "SEO", "広告", "動画編集", "映像", "ライティング",
    "コピーライティング", "翻訳", "SNS運用", "コンサル", "分析",
    "Python", "JavaScript", "PHP", "WordPress",
]

MID_SKILL_KEYWORDS = [
    "ライター", "記事", "ブログ", "文章", "編集", "校正",
    "カスタマーサポート", "メール", "電話対応", "事務", "アシスタント",
    "リサーチ", "調査", "資料作成", "スライド", "Excel", "Word",
]

RED_FLAG_KEYWORDS = [
    "即日", "即時", "急ぎ", "緊急", "24時間対応", "土日対応",
    "修正無制限", "無制限修正", "無料", "テスト", "お試し",
    "格安", "低単価", "安価", "見積もり後", "相談後に決定",
]


def score_job(job: dict, config: dict = None) -> dict:
    threshold = 15
    if config and "scoring" in config:
        threshold = config["scoring"].get("threshold", 15)

    scores = {}
    details = {}

    s, d = _score_hourly_rate(job)
    scores["時給"] = s
    details["時給"] = d

    s, d = _score_continuity(job)
    scores["継続性"] = s
    details["継続性"] = d

    s, d = _score_client_rating(job)
    scores["クライアント評価"] = s
    details["クライアント評価"] = d

    s, d = _score_skill_learning(job)
    scores["スキル習得度"] = s
    details["スキル習得度"] = d

    s, d = _score_mental_cost(job)
    scores["精神コスト"] = s
    details["精神コスト"] = d

    total = sum(scores.values())

    return {
        "scores": scores,
        "total": total,
        "max": 20,
        "details": details,
        "passed": total >= threshold,
    }


def _score_hourly_rate(job: dict) -> tuple:
    budget = job.get("budget", 0)
    description = job.get("description", "")
    is_hourly = job.get("is_hourly", False)

    if budget <= 0:
        return 0, "予算情報なし"

    if is_hourly:
        hourly = budget
    else:
        estimated_hours = _estimate_hours(description, budget)
        if estimated_hours <= 0:
            return 1, f"固定報酬 {budget:,}円（時間推定不可）"
        hourly = budget / estimated_hours

    label = f"推定時給 {hourly:,.0f}円"
    if hourly >= 3000:
        return 4, f"{label} (3000円以上)"
    elif hourly >= 2000:
        return 3, f"{label} (2000円以上)"
    elif hourly >= 1000:
        return 2, f"{label} (1000円以上)"
    elif hourly >= 500:
        return 1, f"{label} (500円以上)"
    else:
        return 0, f"{label} (500円未満)"


def _estimate_hours(description: str, budget: int) -> float:
    m = re.search(r"(\d+)\s*時間", description)
    if m:
        return float(m.group(1))
    if budget > 0:
        return max(1, min(budget / 1000, 100))
    return 0


def _score_continuity(job: dict) -> tuple:
    text = job.get("title", "") + job.get("description", "")
    if job.get("is_ongoing") or any(kw in text for kw in ["継続", "長期", "定期", "毎月", "毎週"]):
        return 4, "継続・長期案件"
    elif any(kw in text for kw in ["継続の可能性", "長期も可"]):
        return 2, "継続可能性あり"
    else:
        return 0, "単発案件"


def _score_client_rating(job: dict) -> tuple:
    rating = job.get("client_rating")
    if rating is None:
        return 1, "評価なし（新規クライアントの可能性）"
    if rating >= 4.8:
        return 4, f"評価 {rating} (優良)"
    elif rating >= 4.5:
        return 3, f"評価 {rating} (良好)"
    elif rating >= 4.0:
        return 2, f"評価 {rating} (普通)"
    elif rating >= 3.5:
        return 1, f"評価 {rating} (要注意)"
    else:
        return 0, f"評価 {rating} (低評価)"


def _score_skill_learning(job: dict) -> tuple:
    text = job.get("title", "") + job.get("description", "") + job.get("category", "")
    high = [kw for kw in HIGH_SKILL_KEYWORDS if kw in text]
    mid = [kw for kw in MID_SKILL_KEYWORDS if kw in text]

    if high:
        return 4, f"高スキル ({', '.join(high[:2])})"
    elif mid:
        return 3, f"中スキル ({', '.join(mid[:2])})"
    elif any(kw in text for kw in ["データ入力", "コピペ", "単純"]):
        return 1, "スキル習得が限られる作業"
    else:
        return 2, "標準的なスキル習得見込み"


def _score_mental_cost(job: dict) -> tuple:
    text = job.get("title", "") + job.get("description", "")
    flags = [kw for kw in RED_FLAG_KEYWORDS if kw in text]
    count = len(flags)

    if count == 0:
        return 4, "問題なし"
    elif count == 1:
        return 3, f"注意点あり ({flags[0]})"
    elif count == 2:
        return 2, f"注意点複数 ({', '.join(flags[:2])})"
    elif count == 3:
        return 1, f"要注意 ({', '.join(flags[:3])})"
    else:
        return 0, f"レッドフラグ {count}個 ({', '.join(flags[:3])}...)"


def score_all_jobs(jobs: list, config: dict = None) -> list:
    results = []
    for job in jobs:
        scoring = score_job(job, config)
        results.append({"job": job, "scoring": scoring})
    results.sort(key=lambda x: x["scoring"]["total"], reverse=True)
    return results


def score_bar(score: int, max_score: int = 4) -> str:
    filled = round(score / max_score * 5)
    return "[" + "#" * filled + "-" * (5 - filled) + "]"


def get_score_emoji(score: int) -> str:
    if score >= 4:
        return "🟢"
    elif score >= 3:
        return "🔵"
    elif score >= 2:
        return "🟡"
    elif score >= 1:
        return "🟠"
    else:
        return "🔴"
