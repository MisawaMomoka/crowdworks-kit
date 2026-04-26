"""
main.py - クラウドワークス案件獲得自動化キット
Streamlit アプリ メインファイル

起動方法: streamlit run main.py
"""

import os
import yaml
import streamlit as st
import pandas as pd
from datetime import datetime

from scraper import run_scraping
from scorer import score_all_jobs, get_score_emoji
from proposal_generator import generate_all_proposals, generate_proposal
from exporter import export_to_excel


# ======================================================================
# ページ設定
# ======================================================================

st.set_page_config(
    page_title="クラウドワークス案件獲得自動化キット",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ======================================================================
# 設定読み込み
# ======================================================================

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_config(config: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)


# ======================================================================
# セッション状態の初期化
# ======================================================================

if "scored_results" not in st.session_state:
    st.session_state.scored_results = []
if "scraping_done" not in st.session_state:
    st.session_state.scraping_done = False
if "proposals_done" not in st.session_state:
    st.session_state.proposals_done = False


# ======================================================================
# サイドバー（設定）
# ======================================================================

with st.sidebar:
    st.title("⚙️ 設定")

    try:
        config = load_config()
    except Exception as e:
        st.error(f"config.yaml 読み込みエラー: {e}")
        st.stop()

    st.subheader("🔐 クラウドワークス ログイン情報")
    cw_email = st.text_input(
        "メールアドレス",
        value=config["crowdworks"]["email"],
        type="default",
    )
    cw_password = st.text_input(
        "パスワード",
        value=config["crowdworks"]["password"],
        type="password",
    )

    st.subheader("🔍 検索キーワード")
    keywords_str = st.text_area(
        "1行に1キーワード",
        value="\n".join(config["crowdworks"]["keywords"]),
        height=120,
    )
    keywords = [k.strip() for k in keywords_str.split("\n") if k.strip()]

    max_pages = st.slider(
        "各キーワードの取得ページ数",
        min_value=1, max_value=10,
        value=config["crowdworks"]["max_pages"],
    )

    st.subheader("🤖 AI設定")
    provider = st.selectbox(
        "AIプロバイダー",
        options=["gemini", "claude", "openai"],
        index=["gemini", "claude", "openai"].index(config["ai"]["provider"]),
        format_func=lambda x: {
            "gemini": "Gemini（無料枠あり）",
            "claude": "Claude（高品質）",
            "openai": "OpenAI GPT-4o mini",
        }[x],
    )
    api_key_map = {
        "gemini": "gemini_api_key",
        "claude": "claude_api_key",
        "openai": "openai_api_key",
    }
    api_key = st.text_input(
        f"{provider.upper()} APIキー",
        value=config["ai"][api_key_map[provider]],
        type="password",
    )

    threshold = st.slider(
        "✅ 提案文を生成するスコア閾値",
        min_value=10, max_value=20,
        value=config["scoring"]["threshold"],
        help="20点満点中この点数以上の案件に提案文を生成します",
    )

    if st.button("💾 設定を保存"):
        config["crowdworks"]["email"] = cw_email
        config["crowdworks"]["password"] = cw_password
        config["crowdworks"]["keywords"] = keywords
        config["crowdworks"]["max_pages"] = max_pages
        config["ai"]["provider"] = provider
        config["ai"][api_key_map[provider]] = api_key
        config["scoring"]["threshold"] = threshold
        save_config(config)
        st.success("設定を保存しました！")


# ======================================================================
# メインエリア
# ======================================================================

st.title("🚀 クラウドワークス案件獲得自動化キット")
st.caption("案件リサーチ → スコアリング → 提案文生成まで全自動")

tab1, tab2, tab3 = st.tabs(["① 案件リサーチ＆スコアリング", "② スコア結果一覧", "③ 提案文確認・出力"])


# ======================================================================
# Tab 1: リサーチ＆スコアリング
# ======================================================================

with tab1:
    st.header("① 案件リサーチ＆スコアリング")

    col1, col2 = st.columns([2, 1])
    with col1:
        st.info(
            f"**検索キーワード:** {' / '.join(keywords)}  \n"
            f"**最大ページ数:** {max_pages}ページ / キーワード  \n"
            f"**スコア閾値:** {threshold}点以上で提案文生成"
        )
    with col2:
        run_btn = st.button("▶️ リサーチ開始", type="primary", use_container_width=True)

    if run_btn:
        if not cw_email or cw_email == "your_email@example.com":
            st.error("⚠️ サイドバーでクラウドワークスのメールアドレスを設定してください")
        elif not cw_password or cw_password == "your_password":
            st.error("⚠️ サイドバーでクラウドワークスのパスワードを設定してください")
        elif not keywords:
            st.error("⚠️ 検索キーワードを1つ以上入力してください")
        else:
            progress_area = st.empty()
            progress_bar = st.progress(0)
            log_area = st.empty()
            logs = []

            def update_progress(msg: str):
                logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
                log_area.text_area("ログ", "\n".join(logs[-10:]), height=200)

            with st.spinner("クラウドワークスにアクセス中..."):
                try:
                    # スクレイピング実行
                    jobs = run_scraping(
                        email=cw_email,
                        password=cw_password,
                        keywords=keywords,
                        max_pages=max_pages,
                        progress_cb=update_progress,
                    )

                    progress_bar.progress(50)
                    update_progress(f"✅ {len(jobs)}件の案件を取得しました")

                    # スコアリング
                    update_progress("📊 スコアリング中...")
                    config["scoring"]["threshold"] = threshold
                    scored_results = score_all_jobs(jobs, config)
                    st.session_state.scored_results = scored_results
                    st.session_state.scraping_done = True
                    st.session_state.proposals_done = False

                    progress_bar.progress(100)

                    # サマリー表示
                    passed = sum(1 for r in scored_results if r["scoring"]["passed"])
                    st.success(
                        f"✅ 完了！ {len(jobs)}件取得 → "
                        f"スコア{threshold}点以上: **{passed}件**が提案文生成対象です"
                    )

                except Exception as e:
                    st.error(f"❌ エラーが発生しました: {e}")
                    st.exception(e)

    if st.session_state.scraping_done and not run_btn:
        results = st.session_state.scored_results
        passed = sum(1 for r in results if r["scoring"]["passed"])
        st.success(
            f"前回の結果: {len(results)}件取得済み / "
            f"提案文生成対象: {passed}件"
        )
        st.info("「② スコア結果一覧」タブで結果を確認できます")


# ======================================================================
# Tab 2: スコア結果一覧
# ======================================================================

with tab2:
    st.header("② スコア結果一覧")

    if not st.session_state.scored_results:
        st.info("まず「① 案件リサーチ」タブで案件を取得してください")
    else:
        results = st.session_state.scored_results

        # フィルター
        col1, col2 = st.columns(2)
        with col1:
            show_filter = st.radio(
                "表示フィルター",
                ["全件", "✅ 合格のみ", "❌ 除外のみ"],
                horizontal=True,
            )
        with col2:
            sort_by = st.selectbox("並び順", ["スコア高い順", "スコア低い順"])

        filtered = results
        if show_filter == "✅ 合格のみ":
            filtered = [r for r in results if r["scoring"]["passed"]]
        elif show_filter == "❌ 除外のみ":
            filtered = [r for r in results if not r["scoring"]["passed"]]

        if sort_by == "スコア低い順":
            filtered = sorted(filtered, key=lambda x: x["scoring"]["total"])

        st.caption(f"表示: {len(filtered)}件")

        for r in filtered:
            job = r["job"]
            scoring = r["scoring"]
            passed = scoring["passed"]

            with st.expander(
                f"{'✅' if passed else '❌'} "
                f"【{scoring['total']}/20点】 {job.get('title', '不明')[:60]}"
            ):
                col1, col2 = st.columns([3, 2])

                with col1:
                    st.markdown(f"**🔗 URL:** [{job.get('url','')}]({job.get('url','')})")
                    st.markdown(f"**💴 報酬:** {job.get('budget_text', '不明')}")
                    st.markdown(f"**🔄 継続案件:** {'◎ 継続' if job.get('is_ongoing') else '単発'}")
                    st.markdown(f"**⭐ クライアント評価:** {job.get('client_rating', '不明')}")
                    st.markdown(f"**📁 カテゴリ:** {job.get('category', '不明')}")

                with col2:
                    st.markdown("**📊 スコア内訳**")
                    score_items = [
                        ("時給", "🕐"),
                        ("継続性", "🔄"),
                        ("クライアント評価", "⭐"),
                        ("スキル習得度", "📚"),
                        ("精神コスト", "😤"),
                    ]
                    for item_name, emoji in score_items:
                        s = scoring["scores"].get(item_name, 0)
                        detail = scoring["details"].get(item_name, "")
                        st.markdown(
                            f"{get_score_emoji(s)} {emoji} **{item_name}**: "
                            f"{s}/4点 — {detail}"
                        )

                    st.markdown(f"**合計: {scoring['total']}/20点**")

                if job.get("description"):
                    with st.expander("案件説明を見る"):
                        st.text(job["description"][:500] + "..." if len(job.get("description","")) > 500 else job.get("description",""))

        # まとめてExcelで保存（提案文なし）
        if st.button("📥 この結果をExcelで保存（提案文なし）"):
            filepath = export_to_excel(results, config["output"]["save_folder"])
            st.success(f"保存しました: {filepath}")


# ======================================================================
# Tab 3: 提案文確認・出力
# ======================================================================

with tab3:
    st.header("③ 提案文確認・出力")

    if not st.session_state.scored_results:
        st.info("まず「① 案件リサーチ」タブで案件を取得してください")
    else:
        results = st.session_state.scored_results
        passed_results = [r for r in results if r["scoring"]["passed"]]

        if not passed_results:
            st.warning(f"スコア{threshold}点以上の案件が0件でした。閾値を下げるか、キーワードを変更してください")
        else:
            st.info(
                f"✅ 合格案件: **{len(passed_results)}件**  \n"
                f"使用AI: **{provider.upper()}** / "
                f"APIキー: {'設定済み ✅' if api_key and 'your_' not in api_key else '未設定 ⚠️'}"
            )

            # 一括生成ボタン
            gen_col1, gen_col2 = st.columns(2)
            with gen_col1:
                gen_all_btn = st.button(
                    f"✍️ 全{len(passed_results)}件の提案文を一括生成",
                    type="primary",
                    use_container_width=True,
                )

            if gen_all_btn:
                if not api_key or "your_" in api_key:
                    st.error(f"⚠️ サイドバーで{provider.upper()} APIキーを設定してください")
                else:
                    progress_bar = st.progress(0)
                    log_area = st.empty()
                    logs = []
                    total = len(passed_results)

                    def update_gen_progress(msg):
                        logs.append(msg)
                        log_area.text(logs[-1])
                        count = sum(1 for r in passed_results if "proposal" in r)
                        progress_bar.progress(count / total if total > 0 else 1)

                    with st.spinner("提案文を生成中..."):
                        generate_all_proposals(
                            st.session_state.scored_results,
                            provider=provider,
                            api_key=api_key,
                            progress_cb=update_gen_progress,
                        )
                        st.session_state.proposals_done = True
                        st.success(f"✅ {total}件の提案文を生成しました！")
                        st.rerun()

            # 提案文表示
            if st.session_state.proposals_done:
                st.divider()

                for i, r in enumerate(passed_results):
                    job = r["job"]
                    proposal_info = r.get("proposal", {})

                    with st.expander(
                        f"【{r['scoring']['total']}/20点】 {job.get('title','不明')[:60]}",
                        expanded=(i == 0),
                    ):
                        st.markdown(f"**使用テンプレート:** {proposal_info.get('template_name','')}")
                        st.markdown(f"**[案件を開く]({job.get('url','')})**")

                        if proposal_info.get("error"):
                            st.error(f"生成エラー: {proposal_info['error']}")
                        else:
                            # 提案文（編集可能）
                            edited = st.text_area(
                                "提案文（ここで編集できます）",
                                value=proposal_info.get("proposal", ""),
                                height=250,
                                key=f"proposal_{i}",
                            )
                            # 編集内容を反映
                            if edited != proposal_info.get("proposal", ""):
                                r["proposal"]["proposal"] = edited

                            # 個別再生成
                            if st.button("🔄 この案件の提案文を再生成", key=f"regen_{i}"):
                                if api_key and "your_" not in api_key:
                                    with st.spinner("再生成中..."):
                                        new_proposal = generate_proposal(job, provider, api_key)
                                        r["proposal"] = new_proposal
                                        st.rerun()
                                else:
                                    st.error("APIキーを設定してください")

                # Excel出力（提案文込み）
                st.divider()
                if st.button("📥 全結果をExcelで保存（提案文込み）", type="primary"):
                    filepath = export_to_excel(
                        st.session_state.scored_results,
                        config["output"]["save_folder"],
                    )
                    st.success(f"✅ 保存完了！")
                    st.code(filepath)

            elif not st.session_state.proposals_done and not gen_all_btn:
                st.info("「全件の提案文を一括生成」ボタンを押してください")
