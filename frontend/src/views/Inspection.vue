<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const data = ref<any>(null)
const loading = ref(false)

async function inspect() {
  // 只读巡检：后端不落补货单、不改已有单据，可放心反复执行。
  loading.value = true
  try {
    data.value = await api('/refills/inspection?location_id=1')
  } finally {
    loading.value = false
  }
}
onMounted(inspect)

const codeText: Record<number, string> = {
  0: '对账成功 · 与当场补货单同一套数',
  2: '点位不存在（退出码 2）',
  3: '超占道被算进满仓（退出码 3）',
}
const statusText: Record<string, string> = { need_fill: '待补', full: '满仓', overbooked: '超占' }
</script>
<template>
  <h1>只读巡检</h1>
  <p class="sub">按当前货道库存现算待补件数 / 满仓道数 / 超占道数 · 不生成、不改写补货单</p>
  <button class="btn" :disabled="loading" @click="inspect">
    {{ loading ? '巡检中…' : '重新巡检（只读）' }}
  </button>
  <div v-if="data" style="margin-top:1rem">
    <span class="badge" :class="data.code === 0 ? 'badge-ok' : 'badge-bad'">
      {{ codeText[data.code] ?? ('未知状态 ' + data.code) }}
    </span>
    <template v-if="data.found">
      <div class="card grid" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:1rem;margin-top:1rem">
        <div><div class="muted">待补件数</div><div class="stat">{{ data.pending_fill }}</div></div>
        <div><div class="muted">满仓道数</div><div class="stat">{{ data.full_count }}</div></div>
        <div><div class="muted">超占道数</div><div class="stat" style="color:var(--vf-red)">{{ data.overbooked_count }}</div></div>
      </div>
      <div class="card" style="margin-top:1rem">
        <table>
          <thead><tr><th>货道</th><th>商品</th><th>库存</th><th>在途</th><th>容量</th><th>缺口</th><th>建议补量</th><th>状态</th></tr></thead>
          <tbody>
            <tr v-for="l in data.lines" :key="l.lane_id">
              <td>{{ l.slot_no }}</td><td>{{ l.sku_name }}</td>
              <td>{{ l.stock }}</td><td>{{ l.in_transit }}</td><td>{{ l.capacity }}</td>
              <td>{{ l.gap }}</td><td>{{ l.fill_qty }}</td>
              <td>
                <span class="badge" :class="l.status === 'overbooked' ? 'badge-bad' : l.status === 'full' ? 'badge-ok' : 'badge-warn'">
                  {{ statusText[l.status] }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="muted" style="margin-top:0.6rem;font-size:0.72rem">
        超占道（库存＋在途＞容量，如种子里的口香糖 C2）只计入超占道数，不计入满仓。
      </p>
    </template>
  </div>
</template>
