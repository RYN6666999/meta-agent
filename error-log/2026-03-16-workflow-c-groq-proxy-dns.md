---
date: 2026-03-16
type: error_fix
status: active
last_triggered: 2026-03-16
expires_after_days: 365
topic: workflow-c-groq-proxy-dns
---

# Error: Workflow C Groq 節點使用 groq-proxy:3456（Docker 內部 DNS），但 groq-p

## 根本原因
Workflow C Groq 節點使用 groq-proxy:3456（Docker 內部 DNS），但 groq-proxy 容器未加入 n8n 同一 Docker 網路，導致 ENOTFOUND。同時 host.docker.internal:3456 因 macOS 網路路由問題 ETIMEDOUT。

## 解決方案
改用 Groq 官方 API 直接呼叫：url=https://api.groq.com/openai/v1/chat/completions，Authorization header 直接帶入 Bearer key。避免所有 proxy 依賴。

## 背景
n8n Docker 容器內，groq-proxy 服務雖在 docker-compose 定義但未共用網路。host.docker.internal 對 3456 port ETIMEDOUT。解法：直接呼叫 api.groq.com。
