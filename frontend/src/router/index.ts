import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/locations', name: 'Locations', component: () => import('../views/Locations.vue') },
  { path: '/lanes', name: 'Lanes', component: () => import('../views/Lanes.vue') },
  { path: '/sales', name: 'Sales', component: () => import('../views/Sales.vue') },
  { path: '/refills', name: 'Refills', component: () => import('../views/Refills.vue') },
  { path: '/full', name: 'Full', component: () => import('../views/Full.vue') },
  { path: '/inspection', name: 'Inspection', component: () => import('../views/Inspection.vue') },
  { path: '/summary', name: 'Summary', component: () => import('../views/Summary.vue') },
  { path: '/', redirect: '/locations' },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
