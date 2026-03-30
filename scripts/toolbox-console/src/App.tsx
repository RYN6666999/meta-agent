import { useEffect, useMemo, useState } from 'react'
import './App.css'
import { getToolboxItems } from './toolbox'

const RUNNER_API = 'http://127.0.0.1:8766'

type HealthReport = {
  checked_at: string
  ports?: Record<string, boolean>
}

type PreflightReport = {
  checked_at: string
  ready: boolean
}

type PruneCandidate = {
  tool_id: string
  dependency_up: boolean
  critical_dependency?: string
}

type PruneReport = {
  checked_at: string
  candidates: PruneCandidate[]
}

function App() {
  const toolboxItems = useMemo(() => getToolboxItems(), [])
  const [query, setQuery] = useState('')
  const [activeCategory, setActiveCategory] = useState<string>('All')
  const [hideUnavailable, setHideUnavailable] = useState(true)
  const [healthReport, setHealthReport] = useState<HealthReport | null>(null)
  const [preflightReport, setPreflightReport] = useState<PreflightReport | null>(null)
  const [pruneReport, setPruneReport] = useState<PruneReport | null>(null)
  const [statusMessage, setStatusMessage] = useState('')
  const [runningMap, setRunningMap] = useState<Record<string, boolean>>({})
  const [runnerOutput, setRunnerOutput] = useState('')

  useEffect(() => {
    async function loadReports() {
      try {
        const [h, p, pr] = await Promise.all([
          fetch('/toolbox-status/toolbox-health.json', { cache: 'no-store' }).then((res) => (res.ok ? res.json() : null)),
          fetch('/toolbox-status/douyin-preflight.json', { cache: 'no-store' }).then((res) => (res.ok ? res.json() : null)),
          fetch('/toolbox-status/toolbox-prune-report.json', { cache: 'no-store' }).then((res) => (res.ok ? res.json() : null)),
        ])
        setHealthReport(h)
        setPreflightReport(p)
        setPruneReport(pr)
      } catch {
        setStatusMessage('尚未載入狀態檔，先執行檢查並同步。')
      }
    }
    void loadReports()
  }, [])

  const categories = useMemo(() => {
    const unique = Array.from(new Set(toolboxItems.map((item) => item.category)))
    return ['All', ...unique]
  }, [toolboxItems])

  const filteredItems = useMemo(() => {
    const q = query.trim().toLowerCase()
    const hiddenIds = new Set(
      hideUnavailable
        ? (pruneReport?.candidates || [])
          .filter((item) => !item.dependency_up)
          .map((item) => item.tool_id)
        : [],
    )

    return toolboxItems.filter((item) => {
      if (hiddenIds.has(item.id)) {
        return false
      }

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
      ]
        .join(' ')
        .toLowerCase()

      return categoryMatch && searchable.includes(q)
    })
  }, [activeCategory, query, toolboxItems, hideUnavailable, pruneReport])

  const hiddenReasonMap = useMemo<Map<string, string>>(() => {
    const entries: Array<[string, string]> = (pruneReport?.candidates || [])
      .filter((item) => !item.dependency_up)
      .map((item) => [item.tool_id, item.critical_dependency || 'dependency down'])

    return new Map(entries)
  }, [pruneReport])

  async function runTool(toolId: string, action = 'run') {
    const key = `${toolId}:${action}`
    setRunningMap((prev) => ({ ...prev, [key]: true }))
    try {
      const res = await fetch(`${RUNNER_API}/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tool_id: toolId, action }),
      })

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`)
      }

      const data = await res.json()
      const outputText = [
        `tool: ${toolId}`,
        `action: ${action}`,
        `ok: ${data.ok}`,
        data.pid ? `pid: ${data.pid}` : '',
        data.log_path ? `log: ${data.log_path}` : '',
        data.stdout ? `\nstdout:\n${data.stdout}` : '',
        data.stderr ? `\nstderr:\n${data.stderr}` : '',
      ].filter(Boolean).join('\n')
      setRunnerOutput(outputText)
      setStatusMessage(data.ok ? '工具已觸發執行。' : '工具執行失敗，請看輸出區塊。')
      if (toolId === 'toolbox-full-cycle' || toolId === 'toolbox-health' || toolId === 'toolbox-prune' || toolId === 'sync-status') {
        await reloadReports()
      }
      window.setTimeout(() => setStatusMessage(''), 1800)
    } catch {
      setStatusMessage('無法連接 toolbox-runner，請先啟動本機 runner。')
      window.setTimeout(() => setStatusMessage(''), 2200)
    } finally {
      setRunningMap((prev) => ({ ...prev, [key]: false }))
    }
  }

  async function reloadReports() {
    try {
      const [h, p, pr] = await Promise.all([
        fetch('/toolbox-status/toolbox-health.json', { cache: 'no-store' }).then((res) => (res.ok ? res.json() : null)),
        fetch('/toolbox-status/douyin-preflight.json', { cache: 'no-store' }).then((res) => (res.ok ? res.json() : null)),
        fetch('/toolbox-status/toolbox-prune-report.json', { cache: 'no-store' }).then((res) => (res.ok ? res.json() : null)),
      ])
      setHealthReport(h)
      setPreflightReport(p)
      setPruneReport(pr)
      setStatusMessage('狀態檔已重新載入。')
      window.setTimeout(() => setStatusMessage(''), 1800)
    } catch {
      setStatusMessage('重載失敗，請先同步 status 檔。')
      window.setTimeout(() => setStatusMessage(''), 1800)
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
            <strong>{toolboxItems.length}</strong>
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
        <div className="ops-bar">
          <button type="button" onClick={() => runTool('toolbox-health')}>
            執行健康檢查
          </button>
          <button type="button" onClick={() => runTool('douyin-preflight')}>
            執行 Douyin 預檢
          </button>
          <button type="button" onClick={() => runTool('sync-status')}>
            同步狀態檔
          </button>
          <button type="button" onClick={() => runTool('toolbox-full-cycle')}>
            執行全流程
          </button>
          <button type="button" onClick={reloadReports}>重新載入狀態</button>
        </div>

        {runnerOutput ? (
          <pre className="run-output" aria-label="runner output">{runnerOutput}</pre>
        ) : null}

        <div className="status-line">
          <label className="toggle-hide">
            <input
              type="checkbox"
              checked={hideUnavailable}
              onChange={(event) => setHideUnavailable(event.target.checked)}
            />
            自動隱藏不可用工具
          </label>
          <span>
            Health: {healthReport?.checked_at || 'N/A'} | Douyin: {preflightReport?.ready ? 'Ready' : 'Not Ready'} | Prune: {pruneReport?.checked_at || 'N/A'}
          </span>
        </div>

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

        {statusMessage ? <p className="copy-hint">{statusMessage}</p> : null}
      </section>

      <section className="tool-grid" aria-label="toolbox grid">
        {filteredItems.map((item) => (
          <article className="tool-card" key={item.id}>
            <div className="card-head">
              <div className="head-tags">
                <span className="category-tag">{item.category}</span>
                <span className={`readiness ${item.readiness.replace(' ', '-').toLowerCase()}`}>
                  {item.readiness}
                </span>
              </div>
              <code>{item.location}</code>
            </div>

            <h2>{item.name}</h2>
            <p>{item.description}</p>

            {hiddenReasonMap.has(item.id) ? (
              <p className="hidden-reason">候選隱藏原因：{hiddenReasonMap.get(item.id) ?? 'dependency down'}</p>
            ) : null}

            <div className="tag-row" aria-label="tags">
              {item.tags.map((tag) => (
                <span key={tag} className="tag">
                  {tag}
                </span>
              ))}
            </div>

            <div className="action-row" aria-label="actions">
              {(() => {
                const primaryAction = item.id === 'novel-server' ? 'open_ui' : 'run'
                const primaryLabel = item.id === 'novel-server' ? '開啟小說 UI' : '執行'
                const primaryKey = `${item.id}:${primaryAction}`
                return (
                  <button
                    className="action-btn action-primary"
                    type="button"
                    onClick={() => runTool(item.id, primaryAction)}
                    disabled={runningMap[primaryKey]}
                  >
                    {runningMap[primaryKey] ? '執行中...' : primaryLabel}
                  </button>
                )
              })()}

              {(item.id === 'novel-server' || item.id === 'toolbox-console-dev') ? (
                <button
                  className="action-btn"
                  type="button"
                  onClick={() => runTool(item.id, item.id === 'novel-server' ? 'run' : 'open_ui')}
                  disabled={runningMap[`${item.id}:${item.id === 'novel-server' ? 'run' : 'open_ui'}`]}
                >
                  {item.id === 'novel-server' ? '啟動小說服務' : '開啟 UI'}
                </button>
              ) : null}
            </div>

            <details className="playbook">
              <summary>應用場景與啟用方式</summary>
              <div className="playbook-body">
                <p>
                  <span className="meta-key">場景</span>
                  {item.useCase}
                </p>
                <p>
                  <span className="meta-key">啟用</span>
                  由上方按鈕直接觸發
                </p>
                <p>
                  <span className="meta-key">成功判斷</span>
                  {item.verify}
                </p>
                <p>
                  <span className="meta-key">常見卡點</span>
                  {item.blocker}
                </p>
              </div>
            </details>
          </article>
        ))}
      </section>

      {filteredItems.length === 0 ? (
        <section className="empty-state">
          <h2>沒有符合的工具</h2>
          <p>試試看關鍵字：ssh、novel、memory、health。</p>
        </section>
      ) : null}
    </div>
  )
}

export default App
