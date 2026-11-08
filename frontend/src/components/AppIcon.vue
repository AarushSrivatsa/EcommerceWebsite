<script setup lang="ts">
// Minimal inline icon set (stroke icons, 24x24 viewBox).
const paths = {
  film: 'M4 4h16v16H4zM8 4v16M16 4v16M4 9h4M4 15h4M16 9h4M16 15h4',
  plus: 'M12 5v14M5 12h14',
  folder: 'M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z',
  search: 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM21 21l-4.3-4.3',
  sparkles: 'M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z',
  check: 'M5 12.5l4.5 4.5L19 7.5',
  x: 'M6 6l12 12M18 6L6 18',
  trash: 'M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3',
  pencil: 'M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16z',
  refresh: 'M20 11a8 8 0 0 0-14-4L4 9M4 4v5h5M4 13a8 8 0 0 0 14 4l2-2M20 20v-5h-5',
  play: 'M7 4.5v15l13-7.5z',
  clock: 'M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16zM12 8v4l3 2',
  mic: 'M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM5 11a7 7 0 0 0 14 0M12 18v3',
  image: 'M4 5h16v14H4zM4 16l5-5 4 4 3-3 4 4M9 9.5a.5.5 0 1 0 0 .01',
  alert: 'M12 4l9 16H3zM12 10v4M12 17.5v.01',
  'chevron-left': 'M15 5l-7 7 7 7',
  'chevron-right': 'M9 5l7 7-7 7',
  menu: 'M4 7h16M4 12h16M4 17h16',
  wand: 'M5 19L17 7M14 4l1 2 2 1-2 1-1 2-1-2-2-1 2-1zM18 13l.7 1.3L20 15l-1.3.7L18 17l-.7-1.3L16 15l1.3-.7z',
  'arrow-right': 'M5 12h14M13 6l6 6-6 6',
  settings: 'M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM19 12l2 1.5-2 3.5-2.4-.8a7 7 0 0 1-1.6.9L14.5 19h-5l-.5-2.4a7 7 0 0 1-1.6-.9L5 16.5 3 13l2-1.5a7 7 0 0 1 0-1.9L3 8l2-3.5 2.4.8a7 7 0 0 1 1.6-.9L9.5 2h5l.5 2.4a7 7 0 0 1 1.6.9L19 4.5 21 8l-2 1.6a7 7 0 0 1 0 2.4z',
  download: 'M12 4v11M7 11l5 5 5-5M5 20h14',
  layers: 'M12 3l9 5-9 5-9-5zM3 13l9 5 9-5M3 17.5l9 5 9-5',
  book: 'M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3zM5 17a3 3 0 0 1 3-3h11',
  copy: 'M8 8h12v12H8zM4 16V4h12',
  upload: 'M12 16V5M7 9l5-5 5 5M5 20h14',
  loader: 'M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8',
} as const

export type IconName = keyof typeof paths

defineProps<{ name: IconName; size?: number }>()
</script>

<template>
  <svg
    :width="size ?? 18"
    :height="size ?? 18"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.8"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    class="shrink-0"
  >
    <path :d="paths[name]" />
  </svg>
</template>
