<script setup lang="ts" generic="T extends string">
defineProps<{ options: { value: T; label: string }[]; label: string }>()
const model = defineModel<T>({ required: true })
</script>

<template>
  <div class="segmented" role="radiogroup" :aria-label="label">
    <button
      v-for="o in options"
      :key="o.value"
      type="button"
      role="radio"
      :aria-checked="model === o.value"
      :class="{ active: model === o.value }"
      @click="model = o.value"
    >
      {{ o.label }}
    </button>
  </div>
</template>

<style scoped>
.segmented {
  display: inline-flex;
  padding: 2px;
  border-radius: var(--radius-control);
  background: var(--surface-inset);
  box-shadow: inset 0 0 0 1px var(--line);
}
button {
  border: 0;
  background: transparent;
  padding: 3px 10px;
  border-radius: 5px;
  font-size: var(--text-sm);
  color: var(--ink-soft);
  cursor: pointer;
  transition:
    background var(--dur-fast) var(--ease),
    color var(--dur-fast) var(--ease);
}
button.active {
  background: var(--surface);
  color: var(--ink);
  box-shadow: 0 1px 2px rgb(29 35 42 / 14%);
}
</style>
