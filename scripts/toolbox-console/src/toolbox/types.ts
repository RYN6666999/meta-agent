export type ToolboxCategory =
  | 'Decision'
  | 'Validation'
  | 'Memory'
  | 'SSH Gateway'
  | 'Bridge'
  | 'Novel Analyzer'
  | 'Toolbox'

export type ToolboxReadiness = 'Ready' | 'Needs Service' | 'Manual Setup'

export type ToolboxItem = {
  id: string
  name: string
  category: ToolboxCategory
  description: string
  location: string
  commands: string[]
  tags: string[]
  readiness: ToolboxReadiness
  useCase: string
  startup: string
  verify: string
  blocker: string
}
