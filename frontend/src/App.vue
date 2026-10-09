<script setup lang="ts">
import { RouterView } from 'vue-router'
</script>

<template>
  <header class="app-header">
    <span class="app-title">Predictive Maintenance · 预测性维护</span>
  </header>
  <main class="app-main">
    <RouterView />
  </main>
</template>

<style>
body {
  margin: 0;
  font-family:
    system-ui,
    -apple-system,
    'Segoe UI',
    'Microsoft YaHei',
    sans-serif;
  background: #f5f6f8;
  color: #1d1f23;
}
.app-header {
  padding: 12px 20px;
  background: #fff;
  border-bottom: 1px solid #e3e5e8;
  font-weight: 600;
}
.app-main {
  padding: 20px;
}
</style>
