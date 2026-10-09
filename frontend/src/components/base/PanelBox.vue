<script setup lang="ts">
defineProps<{ title?: string }>()
</script>

<template>
  <section class="panel">
    <header v-if="title || $slots.actions" class="panel-head">
      <h2 v-if="title">{{ title }}</h2>
      <div class="actions"><slot name="actions" /></div>
    </header>
    <div class="panel-body"><slot /></div>
  </section>
</template>

<style scoped>
.panel {
  background: var(--surface);
  border-radius: var(--radius-panel);
  box-shadow: var(--shadow-panel);
}
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--line);
}
h2 {
  font-size: var(--text-md);
}
.actions {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}
.panel-body {
  padding: var(--space-4);
}
</style>
