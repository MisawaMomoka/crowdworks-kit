@echo off
chcp 65001 > nul
echo ============================================================
echo  クラウドワークス案件獲得自動化キット - セットアップ
echo ============================================================
echo.

echo [1/4] Python の確認...
python --version
if %errorlevel% neq 0 (
    echo ERROR: Python がインストールされていません。
    echo https://www.python.org/downloads/ からインストールしてください。
    pause
    exit /b 1
)

echo.
echo [2/4] 必要なライブラリをインストール中...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: インストールに失敗しました。
    pause
    exit /b 1
)

echo.
echo [3/4] Playwright ブラウザをインストール中（初回のみ）...
playwright install chromium
if %errorlevel% neq 0 (
    echo ERROR: Playwright のインストールに失敗しました。
    pause
    exit /b 1
)

echo.
echo [4/4] セットアップ完了！
echo.
echo 次のステップ:
echo   1. config.yaml をメモ帳で開いてメールアドレス/パスワードを設定
echo   2. Gemini APIキーを取得して config.yaml に貼り付け
echo   3. start.bat をダブルクリックしてツールを起動
echo.
pause
