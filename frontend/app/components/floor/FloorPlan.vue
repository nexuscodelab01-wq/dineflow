<script setup lang="ts">
import type { PlanTable } from '~/utils/floorplan'
import {
  PLAN_H,
  PLAN_W,
  SEAT_RADIUS,
  STATE_LABELS,
  STATE_STYLES,
  UNASSIGNED_ZONE,
  clampPercent,
  normalizeShape,
  seatPoints,
  tableMargin,
  tableSize,
  withLayout,
} from '~/utils/floorplan'

/**
 * 2D seating plan. Read-only for customers (pick a table), editable for staff (drag tables).
 * Positions are percentages of the plan, so it scales to any screen.
 */
const props = withDefaults(defineProps<{
  tables: PlanTable[]
  selectedId?: number | null
  editable?: boolean
  /** Dim every table outside this zone (use UNASSIGNED_ZONE for tables with no zone). */
  zoneFilter?: string | null
  showLegend?: boolean
}>(), {
  selectedId: null,
  editable: false,
  zoneFilter: null,
  showLegend: true,
})

const emit = defineEmits<{
  select: [id: number]
  move: [id: number, x: number, y: number]
}>()

const svg = ref<SVGSVGElement | null>(null)

const laid = computed(() => withLayout(props.tables).map((t) => {
  const inZone = !props.zoneFilter || (t.zone || UNASSIGNED_ZONE) === props.zoneFilter
  const size = tableSize(t.shape, t.capacity)
  const style = STATE_STYLES[t.state] ?? STATE_STYLES.NEUTRAL!
  const selectable = props.editable || (inZone && (t.selectable ?? t.state === 'AVAILABLE'))
  return {
    ...t,
    inZone,
    size,
    style,
    shape: normalizeShape(t.shape),
    seats: seatPoints(t.shape, t.capacity),
    cx: (t.x / 100) * PLAN_W,
    cy: (t.y / 100) * PLAN_H,
    selectable,
    selected: t.id === props.selectedId,
  }
}))

const legend = computed(() => {
  const states = new Set(props.tables.map(t => t.state))
  const order = ['AVAILABLE', 'UNAVAILABLE', 'RESERVED', 'OCCUPIED', 'CLEANING', 'TOO_SMALL', 'INACTIVE']
  return order.filter(s => states.has(s)).map(s => ({ state: s, label: STATE_LABELS[s], style: STATE_STYLES[s]! }))
})

function ariaLabel(t: (typeof laid.value)[number]) {
  const parts = [`Table ${t.table_number}`, `seats ${t.capacity}`]
  if (t.zone) parts.push(t.zone)
  parts.push(STATE_LABELS[t.state] ?? t.state)
  if (t.note) parts.push(t.note)
  return parts.join(', ')
}

function labelSize(name: string) {
  return name.length > 5 ? 2.2 : name.length > 3 ? 2.8 : 3.4
}

// ---- pointer handling -------------------------------------------------------------------

let drag: { id: number, startX: number, startY: number, originX: number, originY: number, moved: boolean } | null = null

function toPlanPoint(event: PointerEvent) {
  const el = svg.value
  const ctm = el?.getScreenCTM()
  if (!el || !ctm) return { x: 0, y: 0 }
  const pt = el.createSVGPoint()
  pt.x = event.clientX
  pt.y = event.clientY
  const p = pt.matrixTransform(ctm.inverse())
  return { x: p.x, y: p.y }
}

function onPointerDown(event: PointerEvent, t: (typeof laid.value)[number]) {
  if (!t.selectable) return
  if (!props.editable) return // read-only plans select on click
  ;(event.currentTarget as Element).setPointerCapture(event.pointerId)
  const p = toPlanPoint(event)
  drag = { id: t.id, startX: p.x, startY: p.y, originX: t.x, originY: t.y, moved: false }
  emit('select', t.id)
}

function onPointerMove(event: PointerEvent, t: (typeof laid.value)[number]) {
  if (!drag || drag.id !== t.id) return
  const p = toPlanPoint(event)
  const dx = ((p.x - drag.startX) / PLAN_W) * 100
  const dy = ((p.y - drag.startY) / PLAN_H) * 100
  if (!drag.moved && Math.hypot(p.x - drag.startX, p.y - drag.startY) < 0.8) return
  drag.moved = true
  const m = tableMargin(t.shape, t.capacity)
  const snap = (v: number) => Math.round(v * 2) / 2 // half-percent grid keeps layouts tidy
  emit(
    'move',
    t.id,
    clampPercent(snap(drag.originX + dx), m.x, 100 - m.x),
    clampPercent(snap(drag.originY + dy), m.y, 100 - m.y),
  )
}

function onPointerUp() {
  drag = null
}

function onClick(t: (typeof laid.value)[number]) {
  if (props.editable || !t.selectable) return
  emit('select', t.id)
}

function onKeydown(event: KeyboardEvent, t: (typeof laid.value)[number]) {
  if (props.editable) {
    const step = event.shiftKey ? 5 : 1
    const moves: Record<string, [number, number]> = {
      ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step],
    }
    const delta = moves[event.key]
    if (delta) {
      event.preventDefault()
      const m = tableMargin(t.shape, t.capacity)
      emit('move', t.id, clampPercent(t.x + delta[0], m.x, 100 - m.x), clampPercent(t.y + delta[1], m.y, 100 - m.y))
      return
    }
  }
  if ((event.key === 'Enter' || event.key === ' ') && t.selectable) {
    event.preventDefault()
    emit('select', t.id)
  }
}
</script>

<template>
  <figure class="m-0">
    <svg
      ref="svg"
      :viewBox="`0 0 ${PLAN_W} ${PLAN_H}`"
      class="block w-full select-none rounded-2xl border border-brand-100 bg-[#fbfaf7]"
      :class="editable ? 'touch-none' : ''"
      role="group"
      aria-label="Restaurant seating plan"
    >
      <defs>
        <pattern id="plan-grid" width="8" height="8" patternUnits="userSpaceOnUse">
          <path d="M 8 0 L 0 0 0 8" fill="none" stroke="#e8e4da" stroke-width="0.25" />
        </pattern>
      </defs>
      <rect x="0.6" y="0.6" :width="PLAN_W - 1.2" :height="PLAN_H - 1.2" rx="3" fill="url(#plan-grid)" stroke="#d6d1c4" stroke-width="0.6" />

      <g
        v-for="t in laid"
        :key="t.id"
        :transform="`translate(${t.cx} ${t.cy})`"
        :opacity="t.inZone ? (t.style.opacity ?? 1) : 0.22"
        :role="t.selectable ? 'button' : 'img'"
        :tabindex="t.selectable ? 0 : -1"
        :aria-label="ariaLabel(t)"
        :aria-pressed="t.selectable ? t.selected : undefined"
        :class="[
          t.selectable ? (editable ? 'cursor-grab active:cursor-grabbing' : 'cursor-pointer') : 'cursor-not-allowed',
          'focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600',
        ]"
        @pointerdown="onPointerDown($event, t)"
        @pointermove="onPointerMove($event, t)"
        @pointerup="onPointerUp"
        @pointercancel="onPointerUp"
        @click="onClick(t)"
        @keydown="onKeydown($event, t)"
      >
        <title>{{ ariaLabel(t) }}</title>

        <circle
          v-for="(s, i) in t.seats"
          :key="i"
          :cx="s.x"
          :cy="s.y"
          :r="SEAT_RADIUS"
          :fill="t.selected ? '#2c6f53' : t.style.stroke"
          opacity="0.55"
        />

        <circle
          v-if="t.shape === 'ROUND'"
          class="plan-shape"
          :r="t.size.w / 2"
          :fill="t.selected ? '#2c6f53' : t.style.fill"
          :stroke="t.selected ? '#1a3b2f' : t.style.stroke"
          :stroke-width="t.selected ? 1 : 0.7"
          :stroke-dasharray="t.style.dashed ? '1.4 1' : undefined"
        />
        <rect
          v-else
          class="plan-shape"
          :x="-t.size.w / 2"
          :y="-t.size.h / 2"
          :width="t.size.w"
          :height="t.size.h"
          :rx="t.shape === 'RECT' ? 1.4 : 1.2"
          :fill="t.selected ? '#2c6f53' : t.style.fill"
          :stroke="t.selected ? '#1a3b2f' : t.style.stroke"
          :stroke-width="t.selected ? 1 : 0.7"
          :stroke-dasharray="t.style.dashed ? '1.4 1' : undefined"
        />

        <text
          y="0.4"
          text-anchor="middle"
          font-weight="700"
          :font-size="labelSize(t.table_number)"
          :fill="t.selected ? '#ffffff' : t.style.text"
          pointer-events="none"
        >{{ t.table_number }}</text>
        <text
          v-if="t.size.w >= 12"
          y="3.3"
          text-anchor="middle"
          font-size="2"
          :fill="t.selected ? '#dceee5' : t.style.text"
          opacity="0.8"
          pointer-events="none"
        >{{ t.capacity }} seats</text>
      </g>
    </svg>

    <figcaption v-if="showLegend && (legend.length || selectedId)" class="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-muted">
      <span v-for="l in legend" :key="l.state" class="inline-flex items-center gap-1.5">
        <span class="inline-block h-3 w-3 rounded-sm border" :style="{ background: l.style.fill, borderColor: l.style.stroke }" />
        {{ l.label }}
      </span>
      <span v-if="selectedId" class="inline-flex items-center gap-1.5">
        <span class="inline-block h-3 w-3 rounded-sm border border-brand-900 bg-brand-600" />
        Selected
      </span>
      <span v-if="editable" class="text-ink-subtle">Drag a table to move it · arrow keys nudge the selected one</span>
    </figcaption>
  </figure>
</template>
