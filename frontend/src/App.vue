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
  <div class="studio-shell">
    <aside class="studio-sidebar" aria-label="Main navigation">
      <RouterLink to="/" class="studio-brand">
        <span class="studio-brand-mark"><AppIcon name="film" :size="19" /></span>
        <span><strong>Script to Video</strong><small>CREATOR STUDIO</small></span>
      </RouterLink>

      <div class="studio-nav-label">WORKSPACE</div>
      <nav class="studio-nav">
        <RouterLink to="/" class="studio-nav-link" :class="{ active: onProjects }">
          <AppIcon name="folder" :size="18" /><span>Projects</span>
        </RouterLink>
        <RouterLink to="/youtube" class="studio-nav-link" :class="{ active: route.name === 'youtube' }">
          <AppIcon name="upload" :size="18" /><span>YouTube channels</span>
        </RouterLink>
      </nav>

      <RouterLink to="/new" class="studio-new-project">
        <span><AppIcon name="plus" :size="17" /></span>
        <span><strong>New video</strong><small>Start with an idea</small></span>
        <AppIcon name="arrow-right" :size="16" />
      </RouterLink>

      <div class="studio-sidebar-bottom">
        <span class="sidebar-bottom-icon"><AppIcon name="sparkles" :size="17" /></span>
        <div><strong>Make something worth watching.</strong><p>Your ideas, scripts and videos in one place.</p></div>
      </div>
    </aside>

    <div class="studio-main">
      <header class="studio-topbar">
        <div class="studio-breadcrumb"><span>Studio</span><AppIcon name="chevron-right" :size="14" /><strong>{{ pageTitle }}</strong></div>
        <RouterLink v-if="route.name !== 'new'" to="/new" class="topbar-new"><AppIcon name="plus" :size="15" /> Create video</RouterLink>
      </header>

      <main class="studio-content">
        <RouterView v-slot="{ Component }">
          <component :is="Component" />
        </RouterView>
      </main>
    </div>

    <nav class="studio-mobile-nav" aria-label="Main navigation">
      <RouterLink to="/" :class="{ active: onProjects }"><AppIcon name="folder" :size="19" /><span>Projects</span></RouterLink>
      <RouterLink to="/new" :class="{ active: route.name === 'new' }"><AppIcon name="plus" :size="19" /><span>Create</span></RouterLink>
      <RouterLink to="/youtube" :class="{ active: route.name === 'youtube' }"><AppIcon name="upload" :size="19" /><span>YouTube</span></RouterLink>
    </nav>
    <ToastHost />
  </div>
</template>
