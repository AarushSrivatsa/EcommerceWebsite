<script setup lang="ts" generic="T extends string">
defineProps<{ options: { value: T; label: string }[]; modelValue: T; ariaLabel?: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: T] }>()
</script>

<template>
  <div class="tab-control" role="tablist" :aria-label="ariaLabel">
    <button
      v-for="o in options"
      :key="o.value"
      type="button"
      role="tab"
      :aria-selected="o.value === modelValue"
      class="tab-control-item"
      :class="{ 'tab-control-item-active': o.value === modelValue }"
      @click="emit('update:modelValue', o.value)"
    >
      {{ o.label }}
    </button>
  </div>
</template>
