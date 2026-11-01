@echo off
title WhatsApp AI Agent Launcher
echo WhatsApp AI Agent start ho raha hai...
echo Teeno server chalu ho rahe hain, thodi der ruk?...

start "WhatsApp Bridge" /min cmd /k "cd /d E:\whatsapp-mcp\whatsapp-bridge && set CGO_ENABLED=1 && go run main.go"
start "Backend" /min cmd /k "cd /d E:\whatsapp-agent && call venv\Scripts\activate && uvicorn api:app --port 8000"
start "Frontend" /min cmd /k "cd /d E:\whatsapp-agent\frontend && npm run dev"

rem Frontend pehli dafa compile hone mein 30+ second leta hai, is liye tayyar hone tak ruko
:wait_frontend
timeout /t 3 /nobreak >nul
curl -s -o nul http://127.0.0.1:3000 || goto wait_frontend

start chrome --app=http://127.0.0.1:3000
exit
