/** Scales a picture down in the browser so a background stays small enough to store (D-054). */
const MAX_CHARS = 650_000

export async function fileToBackground(file: File): Promise<string> {
  const bitmap = await createImageBitmap(file)
  for (const [width, quality] of [
    [900, 0.8],
    [700, 0.7],
    [500, 0.6],
    [360, 0.5],
  ] as const) {
    const scale = Math.min(1, width / bitmap.width)
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(bitmap.width * scale))
    canvas.height = Math.max(1, Math.round(bitmap.height * scale))
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('canvas unavailable')
    ctx.fillStyle = '#fff'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
    const url = canvas.toDataURL('image/jpeg', quality)
    if (url.length <= MAX_CHARS) return url
  }
  throw new Error('picture too large')
}
