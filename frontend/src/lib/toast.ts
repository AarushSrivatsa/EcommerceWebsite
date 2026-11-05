import { reactive } from 'vue'

export interface Toast {
  id: number
  message: string
  tone: 'info' | 'success' | 'error'
}

const toasts = reactive<Toast[]>([])
let nextId = 1

export function useToast() {
  function push(message: string, tone: Toast['tone'] = 'info', durationMs = 3200) {
    const id = nextId++
    toasts.push({ id, message, tone })
    setTimeout(() => dismiss(id), durationMs)
  }
  function dismiss(id: number) {
    const i = toasts.findIndex((t) => t.id === id)
    if (i !== -1) toasts.splice(i, 1)
  }
  return { toasts, push, dismiss }
}
