<script setup lang="ts">
import { computed } from 'vue'
import AppIcon from './AppIcon.vue'

// Placeholder "scene" thumbnail. Replace with <img :src="imageUrl"> once real images exist.
const props = defineProps<{ seed: number; label?: string }>()

const style = computed(() => {
  const h1 = (props.seed * 47 + 250) % 360
  const h2 = (h1 + 55) % 360
  return { backgroundImage: `linear-gradient(135deg, hsl(${h1} 55% 28%), hsl(${h2} 60% 18%))` }
})
</script>

<template>
  <div class="relative grid aspect-video place-items-center overflow-hidden rounded-lg ring-1 ring-white/10" :style="style">
    <AppIcon name="image" :size="22" class="text-white/40" />
    <span v-if="label" class="absolute bottom-1 left-1.5 rounded bg-black/40 px-1.5 py-0.5 text-[10px] font-medium text-white/80">{{ label }}</span>
  </div>
</template>
