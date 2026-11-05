<script setup lang="ts">
import { ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import AppIcon from '@/components/AppIcon.vue'
import ToastHost from '@/components/ToastHost.vue'

const route = useRoute()
const mobileOpen = ref(false)
watch(() => route.fullPath, () => (mobileOpen.value = false))

const nav = [
  { to: '/', label: 'Projects', icon: 'folder' as const },
  { to: '/new', label: 'New project', icon: 'plus' as const },
]

function isActive(to: string) {
  return to === '/' ? route.path === '/' || route.path.startsWith('/projects') : route.path === to
}
</script>

<template>
  <div class="relative min-h-screen lg:flex">
    <!-- Mobile top bar -->
    <header class="sticky top-0 z-30 flex items-center justify-between border-b border-white/5 bg-ink-950/80 px-4 py-3 backdrop-blur lg:hidden">
      <RouterLink to="/" class="flex items-center gap-2 font-semibold text-white">
        <span class="grid size-8 place-items-center rounded-lg bg-gradient-to-br from-brand-500 to-accent-500"><AppIcon name="film" :size="16" /></span>
        Script to Video
      </RouterLink>
      <button class="rounded-lg p-2 text-zinc-300 hover:bg-white/5" aria-label="Toggle navigation" @click="mobileOpen = !mobileOpen">
        <AppIcon :name="mobileOpen ? 'x' : 'menu'" />
      </button>
    </header>

    <!-- Sidebar -->
    <aside
      class="z-20 w-full shrink-0 border-b border-white/5 bg-ink-900/60 backdrop-blur lg:sticky lg:top-0 lg:block lg:h-screen lg:w-64 lg:border-b-0 lg:border-r"
      :class="mobileOpen ? 'block' : 'hidden'"
    >
      <div class="flex h-full flex-col gap-6 p-4 lg:p-5">
        <RouterLink to="/" class="hidden items-center gap-2.5 text-white lg:flex">
          <span class="grid size-9 place-items-center rounded-xl bg-gradient-to-br from-brand-500 to-accent-500 shadow-lg shadow-brand-600/30"><AppIcon name="film" :size="18" /></span>
          <span class="leading-tight">
            <span class="block text-sm font-semibold">Script to Video</span>
            <span class="block text-xs text-zinc-500">Studio</span>
          </span>
        </RouterLink>

        <nav class="flex flex-col gap-1">
          <RouterLink
            v-for="item in nav"
            :key="item.to"
            :to="item.to"
            class="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition"
            :class="isActive(item.to) ? 'bg-brand-500/15 text-white ring-1 ring-inset ring-brand-400/20' : 'text-zinc-400 hover:bg-white/5 hover:text-white'"
          >
            <AppIcon :name="item.icon" />
            {{ item.label }}
          </RouterLink>
        </nav>

      </div>
    </aside>

    <main class="relative min-w-0 flex-1">
      <div class="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 lg:px-10 lg:py-10">
        <RouterView v-slot="{ Component }">
          <component :is="Component" />
        </RouterView>
      </div>
    </main>

    <ToastHost />
  </div>
</template>
