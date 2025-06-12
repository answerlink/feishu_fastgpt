<template>
  <div class="apps-management">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>应用进程管理</span>
          <div class="header-controls">
            <el-button
              type="primary"
              :icon="Refresh"
              :loading="loading"
              @click="refreshStatus"
            >
              刷新状态
            </el-button>
          </div>
        </div>
      </template>

      <div v-loading="loading">
        <div v-if="appStatus.apps && appStatus.apps.length > 0" class="apps-grid">
          <el-card
            v-for="app in appStatus.apps"
            :key="app.app_id"
            class="app-card"
            :class="getCardClass(app.status)"
          >
            <div class="app-info">
              <div class="app-header">
                <h3>{{ app.app_name }}</h3>
                <el-tag :type="getStatusType(app.status)">
                  {{ getStatusText(app.status) }}
                </el-tag>
              </div>
              
              <div class="app-details">
                <el-descriptions :column="1" size="small" border>
                  <el-descriptions-item label="应用ID">
                    <el-text size="small" type="info">{{ app.app_id }}</el-text>
                  </el-descriptions-item>
                  <el-descriptions-item label="分配端口">
                    <el-tag v-if="app.port" size="small" type="primary">
                      {{ app.port }}
                    </el-tag>
                    <el-text v-else size="small" type="info">未分配</el-text>
                  </el-descriptions-item>
                  <el-descriptions-item label="进程ID" v-if="app.pid">
                    <el-text size="small">{{ app.pid }}</el-text>
                  </el-descriptions-item>
                  <el-descriptions-item label="退出码" v-if="app.exit_code !== undefined">
                    <el-tag size="small" type="danger">{{ app.exit_code }}</el-tag>
                  </el-descriptions-item>
                </el-descriptions>
              </div>

              <div class="app-actions">
                <el-button
                  size="small"
                  type="primary"
                  @click="restartApp(app)"
                  :loading="restarting[app.app_id]"
                  :disabled="app.status === 'running'"
                >
                  重启应用
                </el-button>
                <el-button
                  v-if="app.port && app.status === 'running'"
                  size="small"
                  type="info"
                  @click="testConnection(app)"
                  :loading="testing[app.app_id]"
                >
                  测试连接
                </el-button>
              </div>
            </div>
          </el-card>
        </div>
        
        <div v-else class="no-apps">
          <el-empty description="暂无应用数据" />
        </div>
      </div>

      <template #footer>
        <div class="status-summary">
          <el-row :gutter="20">
            <el-col :span="6">
              <el-statistic title="总应用数" :value="appStatus.total_apps || 0" />
            </el-col>
            <el-col :span="6">
              <el-statistic title="运行中" :value="appStatus.running_processes || 0">
                <template #suffix>
                  <el-icon style="color: #67c23a"><CircleCheck /></el-icon>
                </template>
              </el-statistic>
            </el-col>
            <el-col :span="6">
              <el-statistic title="已停止" :value="stoppedCount">
                <template #suffix>
                  <el-icon style="color: #f56c6c"><CircleClose /></el-icon>
                </template>
              </el-statistic>
            </el-col>
            <el-col :span="6">
              <el-statistic title="管理器状态" :value="appStatus.running ? '运行中' : '已停止'">
                <template #suffix>
                  <el-icon :style="{color: appStatus.running ? '#67c23a' : '#f56c6c'}">
                    <CircleCheck v-if="appStatus.running" />
                    <CircleClose v-else />
                  </el-icon>
                </template>
              </el-statistic>
            </el-col>
          </el-row>
        </div>
      </template>
    </el-card>

    <!-- 端口信息提示 -->
    <el-alert
      title="端口分配说明"
      type="info"
      show-icon
      :closable="false"
      style="margin-top: 20px;"
    >
      <template #default>
        <p><strong>动态端口分配：</strong> 系统自动为每个应用分配可用端口，避免端口冲突</p>
        <p><strong>内部使用：</strong> 这些端口仅用于飞书回调和内部服务通信，用户无需直接访问</p>
        <p><strong>管理入口：</strong> 请通过主控界面（端口8000）进行所有操作</p>
      </template>
    </el-alert>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, CircleCheck, CircleClose } from '@element-plus/icons-vue'
import axios from 'axios'

const appStatus = ref({})
const loading = ref(false)
const restarting = ref({})
const testing = ref({})

// 计算属性
const stoppedCount = computed(() => {
  if (!appStatus.value.apps) return 0
  return appStatus.value.apps.filter(app => app.status === 'stopped' || app.status === 'failed').length
})

// 获取应用状态
const fetchAppStatus = async () => {
  loading.value = true
  try {
    const response = await axios.get('/api/v1/multi-app/status')
    if (response.data.code === 0) {
      appStatus.value = response.data.data
    } else {
      ElMessage.error('获取应用状态失败: ' + response.data.msg)
    }
  } catch (error) {
    console.error('获取应用状态失败:', error)
    ElMessage.error('获取应用状态失败')
  } finally {
    loading.value = false
  }
}

// 刷新状态
const refreshStatus = () => {
  fetchAppStatus()
}

// 重启应用
const restartApp = async (app) => {
  restarting.value[app.app_id] = true
  try {
    const response = await axios.post('/api/v1/multi-app/restart', {
      app_id: app.app_id
    })
    if (response.data.code === 0) {
      ElMessage.success(`${app.app_name} 重启成功`)
      await fetchAppStatus()
    } else {
      ElMessage.error('重启失败: ' + response.data.msg)
    }
  } catch (error) {
    ElMessage.error('重启请求失败')
  } finally {
    restarting.value[app.app_id] = false
  }
}

// 测试连接
const testConnection = async (app) => {
  testing.value[app.app_id] = true
  try {
    const response = await axios.get(`http://localhost:${app.port}/api/v1/test/ping`, {
      timeout: 5000
    })
    
    if (response.status === 200) {
      ElMessage.success(`${app.app_name} (端口${app.port}) 连接正常`)
    } else {
      ElMessage.warning(`${app.app_name} 连接异常`)
    }
  } catch (error) {
    ElMessage.error(`${app.app_name} 连接失败`)
  } finally {
    testing.value[app.app_id] = false
  }
}

// 获取状态类型
const getStatusType = (status) => {
  const typeMap = {
    'running': 'success',
    'stopped': 'info',
    'failed': 'danger'
  }
  return typeMap[status] || 'warning'
}

// 获取状态文字
const getStatusText = (status) => {
  const textMap = {
    'running': '运行中',
    'stopped': '已停止',
    'failed': '异常'
  }
  return textMap[status] || '未知'
}

// 获取卡片样式
const getCardClass = (status) => {
  return `status-${status}`
}

onMounted(() => {
  fetchAppStatus()
})
</script>

<style scoped>
.apps-management {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-controls {
  display: flex;
  gap: 10px;
  align-items: center;
}

.apps-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(450px, 1fr));
  gap: 20px;
  margin-bottom: 20px;
}

.app-card {
  border-radius: 8px;
  transition: all 0.3s ease;
}

.app-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.app-card.status-running {
  border-left: 4px solid #67c23a;
}

.app-card.status-stopped {
  border-left: 4px solid #909399;
}

.app-card.status-failed {
  border-left: 4px solid #f56c6c;
}

.app-info {
  padding: 10px;
}

.app-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.app-header h3 {
  margin: 0;
  color: #303133;
}

.app-details {
  margin-bottom: 15px;
}

.app-actions {
  display: flex;
  gap: 10px;
}

.no-apps {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 200px;
}

.status-summary {
  margin-top: 20px;
  padding: 20px;
  background-color: #f5f7fa;
  border-radius: 8px;
}
</style> 