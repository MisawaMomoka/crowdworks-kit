"""
scraper.py - クラウドワークス案件収集モジュール
Playwright を使用（networkidle + 十分な待機で Vue レンダリングを待つ）
Windows + Python 3.12 対応（スレッド内で ProactorEventLoop を使用）
"""

import re
import os
import time
import html as html_module
import json
import urllib.parse
import threading


BASE_URL = "https://crowdworks.jp"


# ======================================================================
# スクレイパー本体（Playwright 同期 API）
# ======================================================================

class CrowdWorksScraper:

    def __init__(self):
        self.browser = None
        self.page = None
        self.playwright = None
        self.is_logged_in = False

    def start(self):
        from playwright.sync_api import sync_playwright
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--single-process",
                "--no-zygote",
                "--disable-setuid-sandbox",
                "--disable-extensions",
                "--disable-background-networking",
            ],
        )
        context = self.browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        self.page = context.new_page()

    def close(self):
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    # ------------------------------------------------------------------
    # ログイン
    # ------------------------------------------------------------------

    def login(self, email: str, password: str) -> bool:
        self.page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded")
        time.sleep(1)

        if "/login" not in self.page.url:
            self.is_logged_in = True
            return True

        self.page.fill('input[name="username"]', email)
        self.page.fill('input[name="password"]', password)
        self.page.click('input[type="submit"], button[type="submit"]')
        self.page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(1)

        if "/login" in self.page.url:
            raise RuntimeError("ログインに失敗しました。メールアドレスとパスワードを確認してください。")

        self.is_logged_in = True
        return True

    # ------------------------------------------------------------------
    # 案件一覧収集
    # ------------------------------------------------------------------

    def search_jobs(self, keywords: list, max_pages: int = 3,
                    progress_cb=None, exclude_keywords: list = None) -> list:
        all_jobs = []
        seen_urls = set()

        # 除外キーワードのURLパラメータ
        exclude_param = ""
        if exclude_keywords:
            exc_enc = urllib.parse.quote(" ".join(exclude_keywords))
            exclude_param = f"&search[exclude_keywords]={exc_enc}"

        for keyword in keywords:
            if progress_cb:
                progress_cb(f"キーワード「{keyword}」を検索中...")

            for page_num in range(1, max_pages + 1):
                kw_enc = urllib.parse.quote(keyword)
                url = (
                    f"{BASE_URL}/public/jobs/search"
                    f"?search[keywords]={kw_enc}&order=new_order&page={page_num}"
                    f"{exclude_param}"
                )

                self.page.goto(url, wait_until="networkidle", timeout=20000)
                time.sleep(4)  # Vue コンポーネントのレンダリングを待つ

                # ページ HTML から案件データを抽出
                page_html = self.page.content()
                jobs = _parse_jobs_from_html(page_html, keyword)

                if not jobs:
                    break

                for job in jobs:
                    if job["url"] not in seen_urls:
                        seen_urls.add(job["url"])
                        all_jobs.append(job)

                time.sleep(1)

        return all_jobs

    # ------------------------------------------------------------------
    # 案件詳細取得
    # ------------------------------------------------------------------

    def get_job_detail(self, url: str) -> dict:
        self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
        time.sleep(0.8)

        page_html = self.page.content()
        return _parse_job_detail(page_html, url)

    # ------------------------------------------------------------------
    # クライアント評価のみ取得（詳細ページから）
    # ------------------------------------------------------------------

    def get_client_rating(self, url: str) -> float | None:
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
            time.sleep(0.8)
            page_html = self.page.content()
            return _extract_client_rating(page_html)
        except Exception:
            return None


# ======================================================================
# HTML パース関数（Playwright から取得した内容を解析）
# ======================================================================

def _parse_jobs_from_html(page_html: str, keyword: str) -> list:
    """
    HTML に埋め込まれた JSON オブジェクトを丸ごとパースして案件情報を抽出する。
    詳細ページ取得なしで budget / is_hourly / client_rating / category も取得する。
    """
    jobs = []
    seen_ids = set()
    unescaped = html_module.unescape(page_html)

    for m in re.finditer(r'\{"id":(\d{5,}),', unescaped):
        job_id = m.group(1)
        if job_id in seen_ids:
            continue

        # ブレース深さを追って JSON オブジェクト全体を切り出す
        start = m.start()
        depth = 0
        end = start
        for i, ch in enumerate(unescaped[start:start + 10000], start):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

        try:
            obj = json.loads(unescaped[start:end])
        except Exception:
            continue

        title = obj.get("title", "")
        if not title:
            continue  # 案件以外の JSON オブジェクトはスキップ

        seen_ids.add(job_id)
        desc = obj.get("description_digest", "")

        # 予算
        budget = 0
        budget_text = ""
        is_hourly = False
        reward = obj.get("reward") or {}
        if isinstance(reward, dict):
            min_r = int(reward.get("min_reward") or reward.get("lower_limit") or 0)
            max_r = int(reward.get("max_reward") or reward.get("upper_limit") or 0)
            rtype = str(reward.get("reward_type", "")).lower()
            is_hourly = "hourly" in rtype or "時給" in rtype
            if max_r:
                budget = max_r
                budget_text = f"{min_r:,}〜{max_r:,}円" if min_r else f"{max_r:,}円"
            elif min_r:
                budget = min_r
                budget_text = f"{min_r:,}円"
        if not budget:
            bm = re.search(r'(\d[\d,]+)\s*円', json.dumps(obj, ensure_ascii=False))
            if bm:
                budget = int(re.sub(r"[^\d]", "", bm.group(1)))
                budget_text = bm.group(0)

        # クライアント評価
        client_rating = None
        client = obj.get("client") or obj.get("client_company") or {}
        if isinstance(client, dict):
            for key in ("rating", "score", "review_score", "average_score"):
                val = client.get(key)
                if val is not None:
                    try:
                        fval = float(val)
                        if 1.0 <= fval <= 5.0:
                            client_rating = fval
                            break
                    except Exception:
                        pass

        # カテゴリ
        category = ""
        cat = obj.get("job_category") or obj.get("category") or {}
        if isinstance(cat, dict):
            category = cat.get("name", "")

        # 継続性
        text = title + desc
        is_ongoing = bool(
            obj.get("is_long_term_job")
            or any(kw in text for kw in ["継続", "長期", "定期", "毎月", "毎週"])
        )

        jobs.append({
            "url": f"{BASE_URL}/public/jobs/{job_id}",
            "title": title,
            "description": desc,
            "is_ongoing": is_ongoing,
            "budget_text": budget_text,
            "budget": budget,
            "is_hourly": is_hourly,
            "client_rating": client_rating,
            "client_name": client.get("name", "") if isinstance(client, dict) else "",
            "category": category,
            "search_keyword": keyword,
        })

    return jobs


def _extract_client_rating(page_html: str) -> float | None:
    """詳細ページHTMLから「総合評価 X.X」のクライアント評価を抽出する"""
    from bs4 import BeautifulSoup

    # HTMLタグを除去してプレーンテキストにしてから検索
    soup = BeautifulSoup(page_html, "html.parser")
    page_text = soup.get_text()

    # パターン1: 「総合評価」の直後にある数値（改行・空白を挟んでもOK）
    m = re.search(r'総合評価\s*(\d+\.\d+)', page_text)
    if m:
        val = float(m.group(1))
        if 1.0 <= val <= 5.0:
            return val

    # パターン2: 「総合評価」の近く（100文字以内）にある数値
    m = re.search(r'総合評価(.{0,100})', page_text, re.DOTALL)
    if m:
        m2 = re.search(r'(\d+\.\d+)', m.group(1))
        if m2:
            val = float(m2.group(1))
            if 1.0 <= val <= 5.0:
                return val

    return None


def _parse_job_detail(page_html: str, url: str) -> dict:
    """案件詳細ページを解析して情報を返す"""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(page_html, "html.parser")
    detail = {"url": url}

    # タイトル
    h1 = soup.find("h1")
    detail["title"] = h1.get_text(strip=True) if h1 else ""

    # 本文
    page_text = soup.get_text()
    detail["description"] = page_text[:3000]

    # 予算
    budget_match = re.search(r"([\d,]+)\s*円", page_text)
    budget_text = budget_match.group(0) if budget_match else ""
    detail["budget_text"] = budget_text
    detail["budget"] = int(re.sub(r"[^\d]", "", budget_text)) if budget_text else 0
    detail["is_hourly"] = any(kw in page_text for kw in ["時給", "時間単価"])

    # 継続性
    detail["is_ongoing"] = any(kw in page_text for kw in ["継続", "長期", "定期", "毎月", "毎週"])

    # クライアント評価
    detail["client_rating"] = _extract_client_rating(page_html)
    detail["client_name"] = ""
    detail["category"] = ""

    return detail


# ======================================================================
# Streamlit から呼び出す関数（Windows ProactorEventLoop 対応）
# ======================================================================

def _preliminary_score(job: dict) -> int:
    """クライアント評価なしで仮スコアを算出する（高速な事前フィルタ用）"""
    score = 0
    text = job.get("title", "") + job.get("description", "")
    budget = job.get("budget", 0)

    # 時給（簡易）
    if budget >= 50000:
        score += 4
    elif budget >= 20000:
        score += 3
    elif budget >= 5000:
        score += 2
    elif budget > 0:
        score += 1

    # 継続性
    if job.get("is_ongoing") or any(kw in text for kw in ["継続", "長期", "定期", "毎月", "毎週"]):
        score += 4

    # スキル習得度（簡易）
    high_skills = ["プログラミング", "デザイン", "開発", "マーケティング", "SEO", "動画編集", "ライティング", "Python", "WordPress"]
    mid_skills = ["ライター", "記事", "ブログ", "編集", "事務", "Excel", "リサーチ"]
    if any(kw in text for kw in high_skills):
        score += 4
    elif any(kw in text for kw in mid_skills):
        score += 3
    else:
        score += 2

    # 精神コスト（簡易）
    red_flags = ["即日", "急ぎ", "緊急", "修正無制限", "無料", "テスト", "格安"]
    flag_count = sum(1 for kw in red_flags if kw in text)
    score += max(0, 4 - flag_count)

    return score


def run_scraping(email: str, password: str, keywords: list,
                 max_pages: int = 3, progress_cb=None,
                 threshold: int = 15, exclude_keywords: list = None) -> list:
    """
    案件を収集して詳細リストを返す
    Windows + Python 3.12 対応: スレッド内で ProactorEventLoop を設定
    threshold: スコア閾値（クライアント評価の詳細取得を絞り込むために使用）
    """
    import sys
    import asyncio

    results = []
    errors = []

    LOG_PATH = os.path.join(os.path.dirname(__file__), "scraper_thread.log")

    def worker():
        import traceback

        def log(msg):
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(msg + "\n")

        log("=== worker 開始 ===")
        scraper = CrowdWorksScraper()
        try:
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                loop = asyncio.ProactorEventLoop()
                asyncio.set_event_loop(loop)
                log("WindowsProactorEventLoopPolicy + ProactorEventLoop 設定済み")

            log("scraper.start() 呼び出し...")
            scraper.start()
            log("scraper.start() 完了")

            if progress_cb:
                progress_cb("クラウドワークスにログイン中...")
            scraper.login(email, password)
            log("ログイン完了")

            if progress_cb:
                progress_cb("案件一覧を収集中...")
            basic_jobs = scraper.search_jobs(keywords, max_pages, progress_cb, exclude_keywords)
            log(f"案件一覧取得完了: {len(basic_jobs)} 件")

            # 仮スコアで絞り込み、合格圏内の案件だけ詳細ページにアクセス
            # クライアント評価は最大+3点（None=1点 → 満点=4点）なので
            # 仮スコア >= (閾値 - 3) の案件だけ詳細を取得する
            min_preliminary = max(0, threshold - 3)
            candidates = []
            for job in basic_jobs:
                pre_score = _preliminary_score(job)
                if pre_score >= min_preliminary:
                    candidates.append(job)

            if progress_cb:
                progress_cb(
                    f"{len(basic_jobs)} 件中 {len(candidates)} 件が合格圏内。"
                    f"クライアント評価を取得中..."
                )

            for idx, job in enumerate(candidates):
                if progress_cb:
                    progress_cb(f"クライアント評価を取得中... ({idx + 1}/{len(candidates)})")
                rating = scraper.get_client_rating(job["url"])
                if rating is not None:
                    job["client_rating"] = rating
                time.sleep(0.3)

            results.extend(basic_jobs)
            if progress_cb:
                progress_cb(f"{len(basic_jobs)} 件取得完了。スコアリングへ...")
            log(f"=== worker 正常終了: {len(results)} 件 ===")

        except Exception as e:
            log(f"=== worker 例外: {traceback.format_exc()} ===")
            errors.append(e)
        finally:
            scraper.close()

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(timeout=600)

    if errors:
        raise errors[0]
    return results
