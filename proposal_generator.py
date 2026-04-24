"""
proposal_generator.py - AI提案文生成モジュール
Gemini（デフォルト）/ Claude / OpenAI に対応
"""

TEMPLATE_ONGOING = """\
○○様

◯◯と申します。
「【案件名】」を拝見しました。継続的にお手伝いできる方を
探されているとのこと、ぜひご応募させてください。

【継続案件としての強み】
・週5日、毎日安定稼働が可能です
・連絡はいつでもレスポンス可能です
・長期でじっくりお付き合いさせていただきたいと考えています

【類似業務の経験】
過去に類似業務を継続させていただいた経験があります。
（実績がない場合は「長期での貢献をお約束します」でOK）

末長くお付き合いさせていただけたら嬉しいです。
よろしくお願いいたします。
"""

TEMPLATE_SPOT = """\
○○様

◯◯と申します。
「【案件名】」について、私の経験が活かせる内容でしたのでご応募いたしました。

【納品までの流れ提案】
1. 着手後、迅速に下書きを提出
2. ご確認後、1日以内に修正対応
3. 合意した期日までに最終納品

【類似業務の実績】
過去に類似のご依頼を納品しております。
（実績がない場合は省略OK）

【お見積もり】
今回の業務、ご提示の予算で対応可能です。

ご検討のほど、よろしくお願いいたします。
"""

TEMPLATE_BEGINNER = """\
○○様

はじめまして、◯◯と申します。
「【案件名】」を拝見し、ぜひお力になりたくご応募いたしました。

【ご応募の理由】
今回の業務内容は、私が普段から取り組んでいる作業と近く、
自分のスキルが活かせると感じました。

【お約束できること】
・連絡のレスポンスは迅速に対応します
・納期は必ず守ります
・分からない部分は早めにご相談します

未経験ジャンルではありますが、丁寧に取り組ませていただきます。
ご検討よろしくお願いいたします。
"""


def select_template(job: dict) -> tuple:
    text = job.get("title", "") + job.get("description", "")
    if job.get("is_ongoing") or any(kw in text for kw in ["継続", "長期", "定期"]):
        return "継続案件向け", TEMPLATE_ONGOING
    elif any(kw in text for kw in ["初めて", "未経験歓迎", "初心者"]):
        return "未経験ジャンル向け", TEMPLATE_BEGINNER
    else:
        return "単発スポット向け", TEMPLATE_SPOT


def build_prompt(job: dict, template_name: str, template: str) -> str:
    title = job.get("title", "（タイトル不明）")
    description = job.get("description", "（説明なし）")[:1500]
    budget_text = job.get("budget_text", "不明")
    is_ongoing = job.get("is_ongoing", False)
    category = job.get("category", "")

    return f"""
あなたはクラウドワークスで案件を獲得するための提案文を書くライターです。
以下の案件情報とテンプレートを参考に、採用されやすい提案文を日本語で作成してください。

## 案件情報
- タイトル: {title}
- カテゴリ: {category}
- 報酬: {budget_text}
- 継続案件: {"はい" if is_ongoing else "いいえ"}
- 案件説明:
{description}

## 使用するテンプレート（{template_name}）
{template}

## 作成ルール
1. テンプレートの構造を守りつつ、この案件に合わせてカスタマイズする
2. プレースホルダー（◯◯、△△）は案件に合った具体的な内容に書き換える
3. 応募者の名前は「[お名前]」のままにしておく
4. 文字数は250〜400文字を目安にする
5. 提案文の本文だけを出力する（説明・コメント不要）

提案文:
""".strip()


def generate_proposal(job: dict, provider: str, api_key: str) -> dict:
    template_name, template = select_template(job)
    prompt = build_prompt(job, template_name, template)

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
            "template_name": template_name,
            "proposal": proposal.strip(),
            "provider": provider,
            "error": None,
        }
    except Exception as e:
        return {
            "template_name": template_name,
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
                            progress_cb=None) -> list:
    passed = [r for r in scored_results if r["scoring"]["passed"]]
    total = len(passed)

    for i, result in enumerate(passed):
        job = result["job"]
        if progress_cb:
            progress_cb(f"提案文生成中 ({i + 1}/{total}): {job.get('title', '')[:30]}...")
        result["proposal"] = generate_proposal(job, provider, api_key)

    return scored_results
