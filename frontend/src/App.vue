<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
import AppIcon from '@/components/AppIcon.vue'
import ToastHost from '@/components/ToastHost.vue'
</script>

<template>
  <div class="relative min-h-screen">
    <header class="sticky top-0 z-30 border-b border-white/5 bg-ink-950/80 backdrop-blur">
      <div class="mx-auto flex w-full max-w-6xl items-center px-4 py-3 sm:px-6 lg:px-10">
        <RouterLink to="/" class="flex items-center gap-2.5 text-white">
          <span class="grid size-8 place-items-center rounded-lg bg-gradient-to-br from-brand-500 to-accent-500"><AppIcon name="film" :size="16" /></span>
          <span class="text-sm font-semibold">Script to Video</span>
        </RouterLink>
      </div>
    </header>

    <main class="relative min-w-0">
      <div class="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 lg:px-10 lg:py-10">
        <RouterView v-slot="{ Component }">
          <component :is="Component" />
        </RouterView>
      </div>
    </main>

    <ToastHost />
  </div>
</template>
