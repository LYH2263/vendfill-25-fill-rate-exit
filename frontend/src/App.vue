<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
</script>
<template>
  <div class="vf-cabinet">
    <div class="vf-cabinet-top">
      <span class="vf-logo">VendFill</span>
      <span class="vf-tag">售货机补货 · 机面操作台</span>
    </div>
    <div class="vf-body">
      <aside class="vf-site-rail">
        <div class="vf-rail-title">机位列表</div>
        <RouterLink to="/locations" class="vf-site-btn">点位</RouterLink>
        <RouterLink to="/lanes" class="vf-site-btn">货道格子</RouterLink>
        <RouterLink to="/sales" class="vf-site-btn">销量</RouterLink>
        <RouterLink to="/refills" class="vf-site-btn">补货小票</RouterLink>
        <RouterLink to="/inspection" class="vf-site-btn">只读巡检</RouterLink>
        <RouterLink to="/full" class="vf-site-btn">满仓</RouterLink>
        <RouterLink to="/summary" class="vf-site-btn">汇总</RouterLink>
      </aside>
      <section class="vf-glass">
        <RouterView />
      </section>
    </div>
  </div>
</template>
