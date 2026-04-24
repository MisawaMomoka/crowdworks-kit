"""
proposal_generator.py - AI提案文生成モジュール
Gemini（デフォルト）/ Claude / OpenAI に対応
"""


def _job_type_label(job: dict) -> str:
    text = job.get("title", "") + job.get("description", "")
    if job.get("is_ongoing") or any(kw in text for kw in ["継続", "長期", "定期"]):
        return "継続・長期案件"
    elif any(kw in text for kw in ["初めて", "未経験歓迎", "初心者"]):
        return "初心者歓迎案件"
    else:
        return "単発案件"


def build_prompt(job: dict, profile: str = "") -> str:
    title = job.get("title", "（タイトル不明）")
    description = job.get("description", "（説明なし）")[:2000]
    budget_text = job.get("budget_text", "不明")
    category = job.get("category", "")
    job_type = _job_type_label(job)

    profile_section = ""
    if profile and profile.strip():
        profile_section = f"""
## 応募者のプロフィール
{profile.strip()}

"""

    return f"""あなたはクラウドワークスで採用率の高いフリーランサーです。
以下の募集要項を熟読し、クライアントが求めていることに正確に応えた提案文を書いてください。
{profile_section}
## 募集要項
タイトル: {title}
カテゴリ: {category}
報酬: {budget_text}
案件種別: {job_type}
依頼内容:
{description}

## 提案文の絶対ルール
1. 募集要項に書かれている具体的な要件・課題・キーワードを必ず盛り込む
2. 「この案件にしか使えない内容」にする。他の案件に流用できる汎用文は書かない
3. クライアントが気にしているポイント（納期・品質・スキル・コミュニケーションなど）を要項から読み取り、それに直接答える
4. プロフィールが提供されている場合は、その人の実際のスキルや経験を自然に盛り込む
5. 文字数は250〜400文字
6. 冒頭は「○○様」（○○はカテゴリや業種に合った自然な敬称）
7. 末尾に「[お名前]」と記載
8. 提案文の本文のみ出力（説明・コメント・補足は不要）

提案文:""".strip()


def generate_proposal(job: dict, provider: str, api_key: str, profile: str = "") -> dict:
    prompt = build_prompt(job, profile)
    job_type = _job_type_label(job)

    try:
        if provider == "gemini":
            proposal = _call_gemini(prompt, api_key)
        elif provider == "claude":
            proposal = _call_claude(prompt, api_key)
        elif provider == "openai":
            proposal = _call_openai(prompt, api_key)
        else:
            raise ValueError(f"未対応のプロバイダー: {provider}")

        return {
            "template_name": job_type,
            "proposal": proposal.strip(),
            "provider": provider,
            "error": None,
        }
    except Exception as e:
        return {
            "template_name": job_type,
            "proposal": "",
            "provider": provider,
            "error": str(e),
        }


def _call_gemini(prompt: str, api_key: str) -> str:
    from google import genai
    import time as _time
    client = genai.Client(api_key=api_key)
    models_to_try = [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-flash-latest",
    ]
    last_err = None
    for i, model_name in enumerate(models_to_try):
        for attempt in range(3):  # 各モデルを最大3回試す
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                return response.text
            except Exception as e:
                msg = str(e)
                if "503" in msg or "unavailable" in msg.lower() or "high demand" in msg.lower():
                    # 混雑中 → 10秒待ってリトライ
                    _time.sleep(10)
                    last_err = e
                    continue
                elif "429" in msg or "quota" in msg.lower() or "rate" in msg.lower():
                    # レート制限 → 次のモデルへ即切り替え
                    last_err = e
                    break
                elif "404" in msg or "not found" in msg.lower():
                    # 存在しないモデル → 即切り替え
                    last_err = e
                    break
                else:
                    raise
        else:
            continue  # 3回とも503だった場合は次のモデルへ
    raise last_err or RuntimeError("Gemini API: 利用可能なモデルがありません")


def _call_claude(prompt: str, api_key: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def _call_openai(prompt: str, api_key: str) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
    )
    return response.choices[0].message.content


def generate_all_proposals(scored_results: list, provider: str, api_key: str,
                            progress_cb=None, profile: str = "") -> list:
    passed = [r for r in scored_results if r["scoring"]["passed"]]
    total = len(passed)

    for i, result in enumerate(passed):
        job = result["job"]
        if progress_cb:
            progress_cb(f"提案文生成中 ({i + 1}/{total}): {job.get('title', '')[:30]}...")
        result["proposal"] = generate_proposal(job, provider, api_key, profile)

    return scored_results
