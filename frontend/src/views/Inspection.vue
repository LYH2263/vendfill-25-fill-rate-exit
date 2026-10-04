<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const data = ref<any>(null)
const error = ref('')
const loading = ref(false)

async function inspect() {
  loading.value = true
  error.value = ''
  try {
    // 只读巡检入口：只按当前货道库存出数，不生成/改写补货单，也不走 /refills/latest。
    data.value = await api('/inspection?location_id=1')
  } catch (e: any) {
    error.value = e?.message || '巡检失败'
    data.value = null
  } finally {
    loading.value = false
  }
}
onMounted(inspect)

function statusText(s: string) {
  return s === 'need_fill' ? '待补' : s === 'full' ? '满仓' : '超占'
}
</script>
<template>
  <h1>只读巡检</h1>
  <p class="sub">按当前货道库存实时复算 · 与当场补货单同一套数 · 巡检不落单、不改单</p>
  <button class="btn" :disabled="loading" @click="inspect">
    {{ loading ? '巡检中…' : '重新巡检' }}
  </button>
  <p v-if="error" class="sub" style="color:#b3402f">巡检失败：{{ error }}</p>
  <div v-if="data" style="margin-top:1rem">
    <div class="card grid" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:1rem">
      <div><div class="muted">待补件数</div><div class="stat">{{ data.total_fill }}</div></div>
      <div><div class="muted">待补货道</div><div class="stat">{{ data.need_fill_count }}</div></div>
      <div><div class="muted">满仓道数</div><div class="stat">{{ data.full_count }}</div></div>
      <div><div class="muted">超占道数</div><div class="stat" style="color:#b3402f">{{ data.overbooked_count }}</div></div>
    </div>
    <div class="card" style="margin-top:1rem">
      <table>
        <thead><tr><th>货道</th><th>商品</th><th>容量</th><th>库存</th><th>在途</th><th>缺口</th><th>建议补量</th><th>状态</th></tr></thead>
        <tbody>
          <tr v-for="l in data.lines" :key="l.lane_id">
            <td>{{ l.slot_no }}</td>
            <td>{{ l.sku_name }}</td>
            <td>{{ l.capacity }}</td>
            <td>{{ l.stock }}</td>
            <td>{{ l.in_transit }}</td>
            <td>{{ l.gap }}</td>
            <td>{{ l.fill_qty }}</td>
            <td>{{ statusText(l.status) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="muted" style="margin-top:0.5rem;font-size:0.78rem">本页为只读对账：超占道（库存＋在途＞容量）单列，不计入满仓。</p>
  </div>
</template>
