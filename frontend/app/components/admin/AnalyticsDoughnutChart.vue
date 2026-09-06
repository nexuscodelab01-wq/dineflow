<script setup lang="ts">
import {
  ArcElement,
  Chart as ChartJS,
  Legend,
  Tooltip,
} from 'chart.js'
import { Doughnut } from 'vue-chartjs'

ChartJS.register(ArcElement, Tooltip, Legend)

const props = defineProps<{
  title: string
  labels: string[]
  values: number[]
}>()

const colors = ['#2c6f53', '#5aa784', '#8bc4a9', '#3a8b68', '#b8dccb', '#255944', '#dceee5']

const chartData = computed(() => ({
  labels: props.labels,
  datasets: [
    {
      data: props.values,
      backgroundColor: props.labels.map((_, i) => colors[i % colors.length]),
      borderWidth: 0,
    },
  ],
}))

const chartOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { position: 'bottom' as const } },
}))
</script>

<template>
  <div class="rounded-2xl border border-brand-100 bg-surface-elevated p-5">
    <h3 class="mb-4 font-semibold text-ink">{{ title }}</h3>
    <div class="h-64">
      <Doughnut :data="chartData" :options="chartOptions" />
    </div>
  </div>
</template>
