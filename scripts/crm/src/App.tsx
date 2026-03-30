import { useMemo, useState } from 'react'
import './App.css'

type ToolboxItem = {
  id: string
  name: string
  category: 'Decision' | 'Validation' | 'Memory' | 'SSH Gateway' | 'Bridge' | 'Novel Analyzer' | 'CRM'
  description: string
  location: string
  commands: string[]
  tags: string[]
}

const TOOLBOX_ITEMS: ToolboxItem[] = [
  {
    id: 'decision-engine',
    name: 'Decision Engine',
    category: 'Decision',
    description: '單一事實驅動決策入口，輸出 machine-readable 報告。',
    location: 'scripts/decision-engine.py',
    commands: ['python3 scripts/decision-engine.py', 'python3 scripts/decision-engine.py --execute'],
    tags: ['pdca', 'decision-loop', 'report'],
  },
  {
    id: 'auto-loop',
    name: 'Auto Decision Loop',
    category: 'Decision',
    description: '持續跑決策迴圈，自動推進下一步。',
    location: 'scripts/auto-decision-loop.py',
    commands: ['python3 scripts/auto-decision-loop.py'],
    tags: ['automation', 'scheduler'],
  },
  {
    id: 'health-check',
    name: 'Health Check',
    category: 'Validation',
    description: '系統健康狀態檢查，確認關鍵流程可用。',
    location: 'scripts/health_check.py',
    commands: ['python3 scripts/health_check.py'],
    tags: ['health', 'status'],
  },
  {
    id: 'e2e',
    name: 'E2E Test',
    category: 'Validation',
    description: '端對端測試，驗證主流程完整性。',
    location: 'scripts/e2e_test.py',
    commands: ['python3 scripts/e2e_test.py'],
    tags: ['e2e', 'qa'],
  },
  {
    id: 'truth-xval',
    name: 'Truth Cross-Validation',
    category: 'Validation',
    description: '交叉查核事實一致性，失敗修復流程核心工具。',
    location: 'scripts/truth-xval.py',
    commands: ['python3 scripts/truth-xval.py'],
    tags: ['truth', 'xval', 'consistency'],
  },
  {
    id: 'memory-mcp',
    name: 'Memory MCP Server',
    category: 'Memory',
    description: '本地記憶查詢與寫入伺服器，供多代理共用。',
    location: 'tools/memory-mcp/server.py',
    commands: ['python3 tools/memory-mcp/server.py'],
    tags: ['mcp', 'memory', 'lightrag'],
  },
  {
    id: 'agent-status',
    name: 'Agent SSH Status',
    category: 'SSH Gateway',
    description: '查看 gateway 開關、失敗 job 與基礎狀態。',
    location: 'tools/agent-ssh-gateway/host/bin/agent-status',
    commands: ['tools/agent-ssh-gateway/host/bin/agent-status'],
    tags: ['ssh', 'status', 'gateway'],
  },
  {
    id: 'agent-switch',
    name: 'Agent SSH Switch',
    category: 'SSH Gateway',
    description: '快速開關受控 SSH 執行通道。',
    location: 'tools/agent-ssh-gateway/host/bin/agent-switch',
    commands: ['tools/agent-ssh-gateway/host/bin/agent-switch on', 'tools/agent-ssh-gateway/host/bin/agent-switch off'],
    tags: ['ssh', 'safety', 'on-off'],
  },
  {
    id: 'agent-run',
    name: 'Agent Run Job',
    category: 'SSH Gateway',
    description: '透過 job JSON 觸發遠端指令執行。',
    location: 'tools/agent-ssh-gateway/scripts/agent-run',
    commands: ['tools/agent-ssh-gateway/scripts/agent-run /tmp/my-job.json'],
    tags: ['ssh', 'job-runner', 'queue'],
  },
  {
    id: 'mobile-bridge',
    name: 'Mobile Bridge Start',
    category: 'Bridge',
    description: '啟動 mobile bridge 服務供外部事件接入。',
    location: 'scripts/start_mobile_bridge.sh',
    commands: ['bash scripts/start_mobile_bridge.sh'],
    tags: ['bridge', 'mobile', 'launchd'],
  },
  {
    id: 'novel-server',
    name: 'Novel Analyzer Web',
    category: 'Novel Analyzer',
    description: '局心欲變分析系統 Web 入口。',
    location: 'tools/novel-framework-analyzer/server.py',
    commands: ['cd tools/novel-framework-analyzer && python3 server.py'],
    tags: ['novel', 'framework', 'fastapi'],
  },
  {
    id: 'novel-batch',
    name: 'Novel Batch Analyze',
    category: 'Novel Analyzer',
    description: '批次分析章節場景，寫入資料庫。',
    location: 'tools/novel-framework-analyzer/scripts/batch_analyze.py',
    commands: ['python3 tools/novel-framework-analyzer/scripts/batch_analyze.py'],
    tags: ['novel', 'batch', 'scene'],
  },
  {
    id: 'crm-dev',
    name: 'CRM Frontend Dev',
    category: 'CRM',
    description: '目前這個 React CRM 專案的開發模式。',
    location: 'scripts/crm/package.json',
    commands: ['npm run dev', 'npm run build', 'npm run lint'],
    tags: ['react', 'vite', 'crm'],
  },
]

function App() {
  const [query, setQuery] = useState('')
  const [activeCategory, setActiveCategory] = useState<string>('All')
  const [copiedKey, setCopiedKey] = useState('')

  const categories = useMemo(() => {
    const unique = Array.from(new Set(TOOLBOX_ITEMS.map((item) => item.category)))
    return ['All', ...unique]
  }, [])

  const filteredItems = useMemo(() => {
    const q = query.trim().toLowerCase()

    return TOOLBOX_ITEMS.filter((item) => {
      const categoryMatch = activeCategory === 'All' || item.category === activeCategory

      if (!q) {
        return categoryMatch
      }

      const searchable = [
        item.name,
        item.description,
        item.location,
        item.category,
        ...item.tags,
        ...item.commands,
      ]
        .join(' ')
        .toLowerCase()

      return categoryMatch && searchable.includes(q)
    })
  }, [activeCategory, query])

  async function copyCommand(key: string, command: string) {
    try {
      await navigator.clipboard.writeText(command)
      setCopiedKey(key)
      window.setTimeout(() => setCopiedKey(''), 1300)
    } catch {
      setCopiedKey('copy-failed')
      window.setTimeout(() => setCopiedKey(''), 1300)
    }
  }

  return (
    <div className="toolbox-page">
      <header className="toolbox-header">
        <p className="eyebrow">META-AGENT OPS</p>
        <h1>可視化工具箱</h1>
        <p className="subtitle">
          把常用腳本、服務與 SSH gateway 統一成一個操作面板。
        </p>

        <div className="stats-row" aria-label="summary">
          <div className="stat-card">
            <span>工具數量</span>
            <strong>{TOOLBOX_ITEMS.length}</strong>
          </div>
          <div className="stat-card">
            <span>分類數量</span>
            <strong>{categories.length - 1}</strong>
          </div>
          <div className="stat-card">
            <span>目前顯示</span>
            <strong>{filteredItems.length}</strong>
          </div>
        </div>
      </header>

      <section className="controls" aria-label="filters">
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="搜尋工具、路徑、命令（例如 ssh / truth / novel）"
          aria-label="搜尋工具"
        />

        <div className="category-pills">
          {categories.map((category) => (
            <button
              key={category}
              className={category === activeCategory ? 'pill active' : 'pill'}
              onClick={() => setActiveCategory(category)}
              type="button"
            >
              {category}
            </button>
          ))}
        </div>
      </section>

      <section className="tool-grid" aria-label="toolbox grid">
        {filteredItems.map((item) => (
          <article className="tool-card" key={item.id}>
            <div className="card-head">
              <span className="category-tag">{item.category}</span>
              <code>{item.location}</code>
            </div>

            <h2>{item.name}</h2>
            <p>{item.description}</p>

            <div className="tag-row" aria-label="tags">
              {item.tags.map((tag) => (
                <span key={tag} className="tag">
                  {tag}
                </span>
              ))}
            </div>

            <ul className="command-list" aria-label="commands">
              {item.commands.map((command, index) => {
                const key = `${item.id}-${index}`
                return (
                  <li key={key}>
                    <code>{command}</code>
                    <button type="button" onClick={() => copyCommand(key, command)}>
                      {copiedKey === key ? 'Copied' : 'Copy'}
                    </button>
                  </li>
                )
              })}
            </ul>
          </article>
        ))}
      </section>

      {filteredItems.length === 0 ? (
        <section className="empty-state">
          <h2>沒有符合的工具</h2>
          <p>試試看關鍵字：ssh、novel、memory、health。</p>
        </section>
      ) : null}

      {copiedKey === 'copy-failed' ? (
        <p className="copy-hint">Clipboard 權限不可用，請手動複製命令。</p>
      ) : null}
    </div>
  )
}

export default App
