@echo off
cd C:\WORK\crawler-gmarket-best
git pull
python gmarket_best_crawler.py --max-items 20 --mode auto --detail-pages auto --detail-delay-sec 2
python send_email.py
