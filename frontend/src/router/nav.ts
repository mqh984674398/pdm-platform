/** Navigation model for the 12 required interfaces (REQUIREMENTS UI-01..UI-12) plus administration. */
export type NavGroup = 'groupMonitor' | 'groupConfigure' | 'groupImprove' | 'groupAdmin'

export interface NavItem {
  name: string // route name and i18n key under nav.*
  path: string
  group: NavGroup
  task: string // contract task that delivers the screen
  icon: string // 16x16 SVG path data
  adminOnly?: boolean // administration screens: administrators only, never configurable per role
}

export const NAV: NavItem[] = [
  {
    name: 'overview',
    path: '/',
    group: 'groupMonitor',
    task: 'T007',
    icon: 'M2 2h5v5H2zM9 2h5v5H9zM2 9h5v5H2zM9 9h5v5H9z',
  },
  {
    name: 'machine',
    path: '/machine',
    group: 'groupMonitor',
    task: 'T007',
    icon: 'M2 12h12M4 12V6h3v6M9 12V3h3v9',
  },
  {
    name: 'component',
    path: '/component',
    group: 'groupMonitor',
    task: 'T007',
    icon: 'M8 2a6 6 0 1 0 0 12A6 6 0 0 0 8 2zM8 5v3l2 2',
  },
  {
    name: 'analysis',
    path: '/analysis',
    group: 'groupMonitor',
    task: 'T019',
    icon: 'M2 12l3-4 3 2 3-6 3 3',
  },
  {
    name: 'baselines',
    path: '/baselines',
    group: 'groupMonitor',
    task: 'T019',
    icon: 'M2 10h12M2 6c3 0 3 3 6 3s3-4 6-4',
  },
  {
    name: 'maintenance',
    path: '/maintenance',
    group: 'groupMonitor',
    task: 'T019',
    icon: 'M2 8h12M4 6v4M8 5v6M12 6v4',
  },
  {
    name: 'alarms',
    path: '/alarms',
    group: 'groupMonitor',
    task: 'T020',
    icon: 'M8 2l6 11H2zM8 6v3M8 11v.5',
  },
  {
    name: 'signals',
    path: '/signals',
    group: 'groupConfigure',
    task: 'T008',
    icon: 'M2 8h2l2-5 2 10 2-5h4',
  },
  {
    name: 'optimization',
    path: '/optimization',
    group: 'groupImprove',
    task: 'T025',
    icon: 'M3 13V9M8 13V3M13 13V6',
  },
  {
    name: 'models',
    path: '/models',
    group: 'groupImprove',
    task: 'T026',
    icon: 'M8 2l6 3-6 3-6-3zM2 8l6 3 6-3M2 11l6 3 6-3',
  },
  {
    name: 'assistant',
    path: '/assistant',
    group: 'groupImprove',
    task: 'T027',
    icon: 'M3 3h10v7H7l-3 3v-3H3z',
  },
  {
    name: 'users',
    path: '/users',
    group: 'groupAdmin',
    task: 'D-033',
    icon: 'M6 7a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM1.5 14c0-2.5 2-4.5 4.5-4.5s4.5 2 4.5 4.5M11 4.5h4M13 2.5v4',
    adminOnly: true,
  },
  {
    name: 'plant',
    path: '/plant',
    group: 'groupAdmin',
    task: 'D-037',
    icon: 'M2 14V7l4-3v3l4-3v3l4-3v10zM5 11h2M9 11h2',
    adminOnly: true,
  },
]

export const NAV_GROUPS: NavGroup[] = [
  'groupMonitor',
  'groupConfigure',
  'groupImprove',
  'groupAdmin',
]

/** The modules an administrator can switch on or off per role (everything but administration). */
export const MODULES = NAV.filter((n) => !n.adminOnly).map((n) => n.name)

/**
 * Whether a role may open a screen. Until the server has said which modules the role has, nothing is
 * hidden (the server still refuses what the role may not use).
 */
export function canOpen(name: string, role: string | null, modules: string[] | null): boolean {
  const item = NAV.find((n) => n.name === name)
  if (!item) return true
  if (item.adminOnly) return role === 'admin'
  return modules === null || modules.includes(name)
}
