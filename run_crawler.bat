@echo off
setlocal
cd /d C:\WORK\crawler-gmarket-best

if not exist output\logs mkdir output\logs
set RUN_LOG=output\logs\run_crawler_last.log

git pull

echo Running production crawl...
python gmarket_best_crawler.py --max-items 200 --mode auto --detail-pages auto --max-detail-items 20 --detail-delay-sec 3 > "%RUN_LOG%" 2>&1
set EXIT_CODE=%errorlevel%
type "%RUN_LOG%"
if not "%EXIT_CODE%"=="0" (
    echo.
    echo Crawl failed. Check %RUN_LOG% and output\logs before retrying.
    pause
    exit /b %EXIT_CODE%
)

echo.
echo Crawl completed. Sending email...
python send_email.py >> "%RUN_LOG%" 2>&1
set EXIT_CODE=%errorlevel%
type "%RUN_LOG%"
if not "%EXIT_CODE%"=="0" (
    echo.
    echo Email failed. Check %RUN_LOG%.
    pause
    exit /b %EXIT_CODE%
)

echo.
echo Production run completed.
echo Log saved to %RUN_LOG%.
pause

endlocal
