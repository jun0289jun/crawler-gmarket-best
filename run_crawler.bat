@echo off
cd C:\WORK\crawler-gmarket-best
git pull
python gmarket_best_crawler.py --max-items 10 --mode auto --detail-pages force --detail-delay-sec 2 --headed --browser-executable-path "C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir "C:\Users\SAMSUNG-JUN\AppData\Local\Google\Chrome\User Data"
python send_email.py
