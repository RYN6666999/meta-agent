import { CORE_TOOLBOX_ITEMS } from './core-tools'
import { TOOLBOX_EXTENSIONS } from './extensions'
import type { ToolboxItem } from './types'

function dedupeById(items: ToolboxItem[]): ToolboxItem[] {
  const seen = new Set<string>()
  const result: ToolboxItem[] = []

  for (const item of items) {
    if (seen.has(item.id)) {
      continue
    }
    seen.add(item.id)
    result.push(item)
  }

  return result
}

export function getToolboxItems(): ToolboxItem[] {
  return dedupeById([...CORE_TOOLBOX_ITEMS, ...TOOLBOX_EXTENSIONS])
}

export type { ToolboxItem, ToolboxCategory, ToolboxReadiness } from './types'
