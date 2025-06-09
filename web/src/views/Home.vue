<template>
  <div class="home">
    <el-row :gutter="20">
      <el-col :span="8">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header">
              <span>应用总数</span>
            </div>
          </template>
          <div class="card-content">
            <el-statistic :value="appCount">
              <template #title>
                <div style="display: inline-flex; align-items: center">
                  已配置应用数量
                </div>
              </template>
            </el-statistic>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const appCount = ref(0)

const loadData = async () => {
  try {
    const response = await axios.get('/api/v1/test/apps')
    appCount.value = response.data.apps.length
  } catch (error) {
    console.error('加载数据失败:', error)
  }
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.home {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-content {
  text-align: center;
  padding: 20px 0;
}
</style> 