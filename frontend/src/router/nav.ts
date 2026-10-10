/** Navigation model for the 12 required interfaces (REQUIREMENTS UI-01..UI-12). */
export type NavGroup = 'groupMonitor' | 'groupConfigure' | 'groupImprove'

export interface NavItem {
  name: string // route name and i18n key under nav.*
  path: string
  group: NavGroup
  task: string // contract task that delivers the screen
  icon: string // 16x16 SVG path data
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
    name: 'datasource',
    path: '/datasource',
    group: 'groupConfigure',
    task: 'T008',
    icon: 'M3 4c0-1 2-2 5-2s5 1 5 2v8c0 1-2 2-5 2s-5-1-5-2zM3 4c0 1 2 2 5 2s5-1 5-2M3 8c0 1 2 2 5 2s5-1 5-2',
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
]

export const NAV_GROUPS: NavGroup[] = ['groupMonitor', 'groupConfigure', 'groupImprove']
