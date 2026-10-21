@echo off
title Push to GitHub - autoShorts
echo =========================================================
echo Pushing Auto Shorts to https://github.com/swaekaa/autoShorts
echo =========================================================

echo 1. Initializing Git repository...
git init

echo.
echo 2. Staging files (excluding .env and local db via .gitignore)...
git add .

echo.
echo 3. Creating commit...
git commit -m "feat: Autonomous Hindu Educational YouTube Shorts Factory (100% Free Tier, No Docker)"

echo.
echo 4. Setting branch to main...
git branch -M main

echo.
echo 5. Setting remote origin...
git remote remove origin >nul 2>&1
git remote add origin https://github.com/swaekaa/autoShorts.git

echo.
echo 6. Pushing to GitHub...
git push -u origin main

echo.
echo =========================================================
echo Done! Check https://github.com/swaekaa/autoShorts
echo =========================================================
pause
