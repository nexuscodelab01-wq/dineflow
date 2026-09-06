<script setup lang="ts">
import {
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LineElement,
  LinearScale,
  PointElement,
  Title,
  Tooltip,
} from 'chart.js'
import { Line } from 'vue-chartjs'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend)

const props = defineProps<{
  title: string
  labels: string[]
  values: number[]
  color?: string
}>()

const chartData = computed(() => ({
  labels: props.labels,
  datasets: [
    {
      label: props.title,
      data: props.values,
      borderColor: props.color || '#2c6f53',
      backgroundColor: `${props.color || '#2c6f53'}33`,
      tension: 0.35,
      fill: true,
    },
  ],
}))

const chartOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { display: false } },
  scales: { y: { beginAtZero: true } },
}))
</script>

<template>
  <div class="rounded-2xl border border-brand-100 bg-surface-elevated p-5">
    <h3 class="mb-4 font-semibold text-ink">{{ title }}</h3>
    <div class="h-64">
      <Line :data="chartData" :options="chartOptions" />
    </div>
  </div>
</template>
