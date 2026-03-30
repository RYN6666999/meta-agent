#!/usr/bin/env bash
set -euo pipefail

if [[ -d "/Users/ryan/Desktop/替身工具箱.app" ]]; then
  open "/Users/ryan/Desktop/替身工具箱.app"
  echo "Opened /Users/ryan/Desktop/替身工具箱.app"
  exit 0
fi

if [[ -x "/Users/ryan/Desktop/替身工具箱.command" ]]; then
  "/Users/ryan/Desktop/替身工具箱.command"
  echo "Ran /Users/ryan/Desktop/替身工具箱.command"
  exit 0
fi

echo "No desktop launcher found."
exit 1
