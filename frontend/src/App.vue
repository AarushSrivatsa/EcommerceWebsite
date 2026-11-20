<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import AppIcon from '@/components/AppIcon.vue'
import ToastHost from '@/components/ToastHost.vue'

const route = useRoute()
const pageTitle = computed(() => String(route.meta.title ?? 'Projects'))
const onProjects = computed(() => route.name === 'projects' || route.name === 'project')
</script>

<template>
  <div class="app-shell">
    <aside class="app-sidebar" aria-label="Main navigation">
      <RouterLink to="/" class="brand-lockup">
        <span class="brand-mark"><AppIcon name="film" :size="19" /></span>
        <span class="brand-copy">
          <strong>Script to Video</strong>
          <small>VIDEO STUDIO</small>
        </span>
      </RouterLink>

      <div class="sidebar-label">WORKSPACE</div>
      <nav class="sidebar-nav">
        <RouterLink to="/" class="nav-link" :class="{ 'nav-link-active': onProjects }">
          <AppIcon name="folder" :size="18" />
          <span>Projects</span>
        </RouterLink>
        <RouterLink to="/youtube" class="nav-link" :class="{ 'nav-link-active': route.name === 'youtube' }">
          <AppIcon name="upload" :size="18" />
          <span>YouTube channels</span>
        </RouterLink>
      </nav>

      <RouterLink to="/new" class="sidebar-create">
        <AppIcon name="sparkles" :size="17" />
        <span>Start a new video</span>
        <AppIcon name="arrow-right" :size="16" />
      </RouterLink>

      <div class="sidebar-foot">
        <span class="sidebar-foot-icon"><AppIcon name="wand" :size="17" /></span>
        <div>
          <strong>Your creative space</strong>
          <p>From a simple idea to a finished video.</p>
        </div>
      </div>
    </aside>

    <div class="app-main">
      <div class="mobile-bar">
        <RouterLink to="/" class="brand-lockup">
          <span class="brand-mark"><AppIcon name="film" :size="18" /></span>
          <span class="brand-copy"><strong>Script to Video</strong></span>
        </RouterLink>
        <nav class="mobile-nav" aria-label="Main navigation">
          <RouterLink to="/" :class="{ 'mobile-nav-active': onProjects }" aria-label="Projects"><AppIcon name="folder" /></RouterLink>
          <RouterLink to="/new" :class="{ 'mobile-nav-active': route.name === 'new' }" aria-label="Create a video"><AppIcon name="plus" /></RouterLink>
          <RouterLink to="/youtube" :class="{ 'mobile-nav-active': route.name === 'youtube' }" aria-label="YouTube channels"><AppIcon name="upload" /></RouterLink>
        </nav>
      </div>

      <header class="app-topbar">
        <div class="topbar-location">
          <span>Studio</span>
          <AppIcon name="chevron-right" :size="14" />
          <strong>{{ pageTitle }}</strong>
        </div>
      </header>

      <main class="app-content">
        <RouterView v-slot="{ Component }">
          <component :is="Component" />
        </RouterView>
      </main>
    </div>

    <ToastHost />
  </div>
</template>
