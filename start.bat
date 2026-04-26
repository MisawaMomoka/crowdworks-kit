@echo off
chcp 65001 > nul
echo ============================================================
echo  クラウドワークス案件獲得自動化キット を起動します
echo ============================================================
echo.
echo ブラウザが自動で開きます（数秒お待ちください）
echo 終了するにはこのウィンドウを閉じてください
echo.
streamlit run main.py --server.port 8501 --server.headless false
pause
