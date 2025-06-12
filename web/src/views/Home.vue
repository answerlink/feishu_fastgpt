<template>
  <div class="home">
    <el-row>
      <el-col :span="12" :md="10" :lg="8" :xl="6">
        <el-card shadow="hover" class="status-card">
          <template #header>
            <div class="card-header">
              <span>🚀 系统状态</span>
            </div>
          </template>
          <div class="card-content">
            <div class="status-number">{{ runningApps }}</div>
            <h3>运行中的应用</h3>
            <p class="status-text">{{ statusText }}</p>
            <div class="status-details">
              <p><strong>总应用数:</strong> {{ totalApps }}</p>
              <p><strong>运行状态:</strong> 
                <el-tag :type="runningApps > 0 ? 'success' : 'danger'" size="small">
                  {{ runningApps > 0 ? '正常运行' : '未启动' }}
                </el-tag>
              </p>
            </div>
            <el-button type="primary" @click="checkStatus" :loading="loading" size="large">
              检查应用状态
            </el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'

const loading = ref(false)
const runningApps = ref(0)
const totalApps = ref(0)
const statusText = ref('正在检查应用状态...')

// 获取应用状态
const fetchAppStatus = async () => {
  try {
    const response = await axios.get('/api/v1/multi-app/status')
    if (response.data.code === 0) {
      const data = response.data.data
      runningApps.value = data.running_processes || 0
      totalApps.value = data.total_apps || 0
      
      if (data.running) {
        if (runningApps.value > 0) {
          statusText.value = `多应用管理器正在运行，${runningApps.value}个应用进程活跃`
        } else {
          statusText.value = '多应用管理器已启动，但无活跃进程'
        }
      } else {
        statusText.value = '多应用管理器未启动'
      }
    } else {
      statusText.value = '获取状态失败'
    }
  } catch (error) {
    console.error('获取应用状态失败:', error)
    statusText.value = '连接失败，请检查服务状态'
    runningApps.value = 0
    totalApps.value = 0
  }
}

const checkStatus = async () => {
  loading.value = true
  await fetchAppStatus()
  loading.value = false
  ElMessage.success('状态已刷新！')
}

// 页面加载时获取状态
onMounted(() => {
  fetchAppStatus()
})
</script>

<style scoped>
.home {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: center;
  align-items: center;
  font-size: 18px;
  font-weight: 600;
}

.status-card {
  min-height: 400px;
  min-width: 400px;
  max-width: 600px;
  width: 100%;
}

.card-content {
  text-align: center;
  padding: 30px 20px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  min-height: 320px;
}

.status-number {
  font-size: 96px;
  font-weight: bold;
  color: #409eff;
  line-height: 1;
  margin-bottom: 15px;
  text-shadow: 0 2px 4px rgba(64, 158, 255, 0.3);
}

.card-content h3 {
  margin: 15px 0;
  color: #303133;
  font-size: 20px;
  white-space: nowrap;
}

.status-text {
  margin: 15px 0;
  color: #606266;
  font-size: 16px;
  line-height: 1.5;
  text-align: center;
  max-width: 100%;
}

.status-details {
  margin: 20px 0;
  padding: 15px;
  background-color: #f5f7fa;
  border-radius: 8px;
  width: 100%;
  max-width: 350px;
  min-width: 280px;
}

.status-details p {
  margin: 8px 0;
  font-size: 14px;
  color: #303133;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.status-details strong {
  font-weight: 600;
}

.el-button {
  margin-top: 20px;
  padding: 12px 30px;
  font-size: 16px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .home {
    padding: 15px;
  }
  
  .status-card {
    min-width: 300px;
  }
  
  .status-number {
    font-size: 72px;
  }
  
  .card-content h3 {
    font-size: 18px;
  }
  
  .status-text {
    font-size: 14px;
  }
  
  .status-details {
    min-width: 250px;
  }
}

@media (max-width: 480px) {
  .home {
    padding: 10px;
  }
  
  .status-card {
    min-width: 280px;
  }
  
  .status-details {
    min-width: 220px;
  }
  
  .card-content {
    padding: 20px 15px;
  }
}
</style> 