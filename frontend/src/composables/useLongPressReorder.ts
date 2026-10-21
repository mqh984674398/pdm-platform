/**
 * Long-press drag to reorder (D-054). Pressing a tile for 500 ms (administrators only) lifts it: the
 * tile follows the pointer as a floating copy (slightly larger, translucent, with a shadow) and the other
 * tiles make way with a 200 ms transition. Releasing earlier is an ordinary click, and moving more than a
 * few pixels before the press completes cancels it so scrolling is not blocked.
 */
import { onBeforeUnmount, ref, type Ref } from 'vue'

export const LONG_PRESS_MS = 500
const MOVE_TOLERANCE = 10
const SWAP_GAP_MS = 120

export function useLongPressReorder(opts: {
  enabled: Ref<boolean>
  ids: Ref<string[]>
  container: Ref<HTMLElement | null>
  onCommit: (ids: string[]) => void
  itemSelector?: string
  idAttribute?: string
}) {
  const itemSelector = opts.itemSelector ?? '[data-machine]'
  const idAttribute = opts.idAttribute ?? 'data-machine'
  const dragId = ref<string | null>(null)
  let timer: ReturnType<typeof setTimeout> | undefined
  let pending: { id: string; el: HTMLElement; x: number; y: number } | null = null
  let ghost: HTMLElement | null = null
  let grab = { x: 0, y: 0 }
  let lastSwap = 0
  let pointer = { x: 0, y: 0 }
  let retry: ReturnType<typeof setTimeout> | undefined
  let justDragged = false
  let startOrder: string[] = []

  function cleanupPending() {
    clearTimeout(timer)
    pending = null
  }

  function removeListeners() {
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
    window.removeEventListener('pointercancel', onUp)
    window.removeEventListener('touchmove', blockScroll)
    document.body.style.userSelect = ''
  }

  function blockScroll(e: TouchEvent) {
    if (dragId.value) e.preventDefault()
  }

  function activate() {
    if (!pending) return
    const { id, el, x, y } = pending
    pending = null
    const r = el.getBoundingClientRect()
    grab = { x: x - r.left, y: y - r.top }
    startOrder = [...opts.ids.value]
    ghost = el.cloneNode(true) as HTMLElement
    Object.assign(ghost.style, {
      position: 'fixed',
      left: `${r.left}px`,
      top: `${r.top}px`,
      width: `${r.width}px`,
      height: `${r.height}px`,
      margin: '0',
      zIndex: '1000',
      pointerEvents: 'none',
      opacity: '0.8',
      transform: 'scale(1.04)',
      boxShadow: '0 14px 32px rgba(0,0,0,.30)',
      transition: 'transform 150ms ease, opacity 150ms ease',
    })
    ghost.setAttribute('aria-hidden', 'true')
    ghost.removeAttribute('data-machine')
    document.body.appendChild(ghost)
    dragId.value = id
    document.body.style.userSelect = 'none'
    if (typeof navigator !== 'undefined' && 'vibrate' in navigator) navigator.vibrate(20)
  }

  function onMove(e: PointerEvent) {
    if (pending) {
      if (Math.hypot(e.clientX - pending.x, e.clientY - pending.y) > MOVE_TOLERANCE) {
        cleanupPending()
        removeListeners()
      }
      return
    }
    if (!dragId.value || !ghost) return
    ghost.style.left = `${e.clientX - grab.x}px`
    ghost.style.top = `${e.clientY - grab.y}px`
    pointer = { x: e.clientX, y: e.clientY }
    maybeSwap()
  }

  /** Moves the dragged tile to the slot under the pointer; a quick move is retried once the gap has passed. */
  function maybeSwap() {
    clearTimeout(retry)
    const wait = SWAP_GAP_MS - (Date.now() - lastSwap)
    if (wait > 0) {
      retry = setTimeout(maybeSwap, wait + 5)
      return
    }
    const root = opts.container.value
    if (!dragId.value || !root) return
    for (const item of Array.from(root.querySelectorAll<HTMLElement>(itemSelector))) {
      const target = item.getAttribute(idAttribute)
      if (!target || target === dragId.value) continue
      const r = item.getBoundingClientRect()
      if (
        pointer.x >= r.left &&
        pointer.x <= r.right &&
        pointer.y >= r.top &&
        pointer.y <= r.bottom
      ) {
        const next = [...opts.ids.value]
        const from = next.indexOf(dragId.value)
        const to = next.indexOf(target)
        if (from < 0 || to < 0) return
        next.splice(to, 0, next.splice(from, 1)[0]!)
        opts.ids.value = next
        lastSwap = Date.now()
        retry = setTimeout(maybeSwap, SWAP_GAP_MS + 5) // the pointer may now rest over another tile
        return
      }
    }
  }

  function onUp() {
    clearTimeout(retry)
    const wasDragging = dragId.value !== null
    cleanupPending()
    removeListeners()
    ghost?.remove()
    ghost = null
    if (wasDragging) {
      dragId.value = null
      justDragged = true // the click that follows the release must not open the machine
      setTimeout(() => (justDragged = false), 350)
      if (opts.ids.value.join('\u0000') !== startOrder.join('\u0000'))
        opts.onCommit([...opts.ids.value])
    }
  }

  function onPointerDown(e: PointerEvent, id: string) {
    if (!opts.enabled.value || (e.pointerType === 'mouse' && e.button !== 0)) return
    cleanupPending()
    pending = { id, el: e.currentTarget as HTMLElement, x: e.clientX, y: e.clientY }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    window.addEventListener('pointercancel', onUp)
    window.addEventListener('touchmove', blockScroll, { passive: false })
    timer = setTimeout(activate, LONG_PRESS_MS)
  }

  /** Capture-phase click handler: swallows the click that ends a drag. */
  function onClickCapture(e: Event) {
    if (justDragged) {
      e.preventDefault()
      e.stopPropagation()
    }
  }

  function onContextMenu(e: Event) {
    if (opts.enabled.value && (pending || dragId.value)) e.preventDefault()
  }

  onBeforeUnmount(() => {
    cleanupPending()
    removeListeners()
    ghost?.remove()
  })

  return { dragId, onPointerDown, onClickCapture, onContextMenu }
}
