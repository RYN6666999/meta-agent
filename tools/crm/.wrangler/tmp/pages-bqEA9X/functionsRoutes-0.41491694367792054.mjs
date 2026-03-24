import { onRequestPost as __api_ai_js_onRequestPost } from "/Users/ryan/meta-agent/tools/crm/functions/api/ai.js"
import { onRequestGet as __api_login_js_onRequestGet } from "/Users/ryan/meta-agent/tools/crm/functions/api/login.js"
import { onRequestOptions as __api_login_js_onRequestOptions } from "/Users/ryan/meta-agent/tools/crm/functions/api/login.js"
import { onRequestPost as __api_login_js_onRequestPost } from "/Users/ryan/meta-agent/tools/crm/functions/api/login.js"

export const routes = [
    {
      routePath: "/api/ai",
      mountPath: "/api",
      method: "POST",
      middlewares: [],
      modules: [__api_ai_js_onRequestPost],
    },
  {
      routePath: "/api/login",
      mountPath: "/api",
      method: "GET",
      middlewares: [],
      modules: [__api_login_js_onRequestGet],
    },
  {
      routePath: "/api/login",
      mountPath: "/api",
      method: "OPTIONS",
      middlewares: [],
      modules: [__api_login_js_onRequestOptions],
    },
  {
      routePath: "/api/login",
      mountPath: "/api",
      method: "POST",
      middlewares: [],
      modules: [__api_login_js_onRequestPost],
    },
  ]