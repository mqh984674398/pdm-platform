<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { fetchHealth, type HealthResponse } from '@/api/health'

const health = ref<HealthResponse | null>(null)
const loaded = ref(false)

onMounted(async () => {
  health.value = await fetchHealth()
  loaded.value = true
})
</script>

<template>
  <section>
    <h1>Skeleton</h1>
    <p data-testid="backend-status">
      <template v-if="!loaded">Checking backend…</template>
      <template v-else-if="health">Backend {{ health.status }} · v{{ health.version }}</template>
      <template v-else>Backend unreachable</template>
    </p>
  </section>
</template>
