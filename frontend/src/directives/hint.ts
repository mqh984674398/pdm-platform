/**
 * `v-hint="text"`: explanatory text that stays hidden until the pointer has rested on the element for one
 * second (or it has keyboard focus for one second). Keeps forms compact while the notes remain reachable.
 */
import type { Directive } from 'vue'

const DELAY_MS = 1000

type Host = HTMLElement & { __hint?: { text: string; stop: () => void } }

let tip: HTMLDivElement | null = null

function hide() {
  tip?.remove()
  tip = null
}

function show(el: HTMLElement, text: string) {
  hide()
  tip = document.createElement('div')
  tip.setAttribute('role', 'tooltip')
  tip.dataset.testid = 'hint-tip'
  tip.textContent = text
  Object.assign(tip.style, {
    position: 'fixed',
    zIndex: '1000',
    maxWidth: '360px',
    padding: '6px 10px',
    borderRadius: '6px',
    background: 'var(--ink, #222)',
    color: 'var(--surface, #fff)',
    fontSize: '12px',
    lineHeight: '1.5',
    boxShadow: '0 4px 14px rgba(0,0,0,.25)',
    pointerEvents: 'none',
  })
  document.body.appendChild(tip)
  const r = el.getBoundingClientRect()
  const w = tip.offsetWidth
  tip.style.left = `${Math.max(8, Math.min(r.left, window.innerWidth - w - 8))}px`
  tip.style.top = `${r.bottom + 6}px`
}

export const vHint: Directive<Host, string> = {
  mounted(el, binding) {
    let timer: ReturnType<typeof setTimeout> | undefined
    const start = () => {
      clearTimeout(timer)
      timer = setTimeout(() => {
        if (el.__hint?.text) show(el, el.__hint.text)
      }, DELAY_MS)
    }
    const stop = () => {
      clearTimeout(timer)
      hide()
    }
    el.addEventListener('mouseenter', start)
    el.addEventListener('focus', start)
    el.addEventListener('mouseleave', stop)
    el.addEventListener('blur', stop)
    el.addEventListener('input', stop)
    el.__hint = { text: binding.value ?? '', stop }
  },
  updated(el, binding) {
    if (el.__hint) el.__hint.text = binding.value ?? ''
  },
  unmounted(el) {
    el.__hint?.stop()
  },
}
