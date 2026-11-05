import { onBeforeUnmount } from 'vue'

/**
 * Calls `tick` every `intervalMs` until `stop()` (or the component unmounts).
 * Ticks never overlap and errors are swallowed so a blip doesn't kill the loop.
 */
export function usePolling(tick: () => Promise<void>, intervalMs = 2000) {
  let timer: ReturnType<typeof setTimeout> | null = null
  let running = false

  async function loop() {
    if (!running) return
    try {
      await tick()
    } catch {
      /* keep polling */
    }
    if (running) timer = setTimeout(loop, intervalMs)
  }

  function start() {
    if (running) return
    running = true
    timer = setTimeout(loop, intervalMs)
  }
  function stop() {
    running = false
    if (timer) clearTimeout(timer)
    timer = null
  }

  onBeforeUnmount(stop)
  return { start, stop, isRunning: () => running }
}
