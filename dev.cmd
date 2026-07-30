@echo off
REM One-command dev launcher (double-click or run `dev` from this folder).
REM Starts Postgres (Docker) + backend + frontend + Market Analyst.
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0dev.ps1"
