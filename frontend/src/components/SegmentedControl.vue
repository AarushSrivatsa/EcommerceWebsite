<script setup lang="ts" generic="T extends string">
defineProps<{ options: { value: T; label: string }[]; modelValue: T; ariaLabel?: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: T] }>()
</script>

<template>
  <div class="inline-flex rounded-xl border border-white/10 bg-black/20 p-1" role="tablist" :aria-label="ariaLabel">
    <button
      v-for="o in options"
      :key="o.value"
      role="tab"
      :aria-selected="o.value === modelValue"
      class="rounded-lg px-3 py-1.5 text-sm font-medium transition"
      :class="o.value === modelValue ? 'bg-brand-600 text-white shadow' : 'text-zinc-400 hover:text-white'"
      @click="emit('update:modelValue', o.value)"
    >
      {{ o.label }}
    </button>
  </div>
</template>
