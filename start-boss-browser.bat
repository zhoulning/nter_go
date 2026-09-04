@echo off
rem BOSS直聘提取专用浏览器：独立配置目录，登录一次长期有效，不影响日常使用的 Chrome
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\ai_coding\inter_go\data\chrome-boss-profile" --no-first-run --no-default-browser-check "https://www.zhipin.com/"
