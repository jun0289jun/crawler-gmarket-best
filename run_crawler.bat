@echo off
cd C:\WORK\crawler-gmarket-best
git pull
python gmarket_best_crawler.py --max-items 10 --mode auto --detail-pages force --detail-delay-sec 10
python send_email.py
