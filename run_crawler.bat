@echo off
cd C:\WORK\crawler-gmarket-best
git pull
echo Close all Chrome windows before continuing, then press any key.
pause
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --profile-directory="Default" --new-window "https://www.gmarket.co.kr"
timeout /t 5 /nobreak
python gmarket_best_crawler.py --max-items 10 --mode auto --detail-pages force --detail-delay-sec 2 --cdp-url http://127.0.0.1:9222
python send_email.py
