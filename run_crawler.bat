@echo off
cd C:\WORK\crawler-gmarket-best
git pull
python gmarket_best_crawler.py --max-items 200 --mode auto
python send_email.py