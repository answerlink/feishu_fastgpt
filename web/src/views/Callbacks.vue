<template>
  <div class="callback-container">
    <h1>回调服务管理</h1>

    <el-card class="callback-card">
      <template #header>
        <div class="card-header">
          <span>回调服务状态</span>
          <div>
            <el-button type="primary" size="small" @click="refreshCallbackStatus">
              <el-icon><Refresh /></el-icon> 刷新
            </el-button>
            <el-button type="success" size="small" @click="startAllCallbacks">
              <el-icon><CaretRight /></el-icon> 启动全部
            </el-button>
            <el-button type="danger" size="small" @click="stopAllCallbacks">
              <el-icon><Close /></el-icon> 停止全部
            </el-button>
          </div>
        </div>
      </template>

      <el-table v-loading="loading" :data="callbackServices" style="width: 100%">
        <el-table-column prop="app_id" label="应用ID" />
        <el-table-column prop="app_name" label="应用名称" />
        <el-table-column prop="status" label="状态">
          <template #default="scope">
            <el-tag :type="getStatusType(scope.row.status)">
              {{ getStatusText(scope.row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="scope">
            <el-button 
              v-if="scope.row.status === 'failed' || scope.row.status === 'error'"
              type="warning" 
              size="small" 
              @click="restartCallback(scope.row.app_id)"
            >
              重启
            </el-button>
            <el-button 
              v-else-if="scope.row.status !== 'running'"
              type="success" 
              size="small" 
              @click="startCallback(scope.row.app_id)"
            >
              启动
            </el-button>
            <el-button 
              v-else
              type="danger" 
              size="small" 
              @click="stopCallback(scope.row.app_id)"
            >
              停止
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card class="callback-card callback-info">
      <template #header>
        <div class="card-header">
          <span>回调事件信息</span>
        </div>
      </template>

      <div class="callback-info-content">
        <h3>已配置的回调事件</h3>
        <el-descriptions border>
          <el-descriptions-item label="卡片回传交互">card.action.trigger</el-descriptions-item>
          <el-descriptions-item label="链接预览获取">url.preview.get</el-descriptions-item>
        </el-descriptions>

        <div class="callback-tips">
          <h3>使用说明</h3>
          <ol>
            <li>回调服务使用长连接方式，无需配置Webhook</li>
            <li>每个应用最多支持50个连接</li>
            <li>应用必须为企业自建应用</li>
            <li>服务启动后，在飞书开发者平台中订阅方式选择"使用长连接接收回调"</li>
            <li>如遇到服务启动失败，请点击"重启"按钮尝试重启服务</li>
          </ol>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import axios from 'axios'

export default {
  name: 'CallbacksView',

  setup() {
    const callbackServices = ref([])
    const loading = ref(false)

    // 获取回调服务状态
    const getCallbackStatus = async () => {
      loading.value = true
      try {
        const response = await axios.get('/api/v1/callback/status')
        callbackServices.value = response.data.services
      } catch (error) {
        console.error('获取回调服务状态失败:', error)
        ElMessage.error('获取回调服务状态失败')
      } finally {
        loading.value = false
      }
    }

    // 启动单个回调服务
    const startCallback = async (appId) => {
      loading.value = true
      try {
        const response = await axios.post('/api/v1/callback/start', { app_id: appId })
        ElMessage.success(`${response.data.app_name || appId} 回调服务启动成功`)
        await getCallbackStatus()
      } catch (error) {
        console.error('启动回调服务失败:', error)
        ElMessage.error('启动回调服务失败')
      } finally {
        loading.value = false
      }
    }

    // 重启单个回调服务
    const restartCallback = async (appId) => {
      loading.value = true
      try {
        const response = await axios.post('/api/v1/callback/restart', { app_id: appId })
        ElMessage.success(`${response.data.app_name || appId} 回调服务重启成功`)
        await getCallbackStatus()
      } catch (error) {
        console.error('重启回调服务失败:', error)
        ElMessage.error('重启回调服务失败')
      } finally {
        loading.value = false
      }
    }

    // 停止单个回调服务
    const stopCallback = async (appId) => {
      try {
        await ElMessageBox.confirm(
          '确定要停止该回调服务吗？停止后将无法接收回调事件。',
          '警告',
          {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            type: 'warning',
          }
        )
        
        loading.value = true
        const response = await axios.post('/api/v1/callback/stop', { app_id: appId })
        ElMessage.success(`${response.data.app_name || appId} 回调服务已停止`)
        await getCallbackStatus()
      } catch (error) {
        if (error !== 'cancel') {
          console.error('停止回调服务失败:', error)
          ElMessage.error('停止回调服务失败')
        }
      } finally {
        loading.value = false
      }
    }

    // 启动所有回调服务
    const startAllCallbacks = async () => {
      loading.value = true
      try {
        await axios.post('/api/v1/callback/start-all')
        ElMessage.success('所有回调服务启动成功')
        await getCallbackStatus()
      } catch (error) {
        console.error('启动所有回调服务失败:', error)
        ElMessage.error('启动所有回调服务失败')
      } finally {
        loading.value = false
      }
    }

    // 停止所有回调服务
    const stopAllCallbacks = async () => {
      try {
        await ElMessageBox.confirm(
          '确定要停止所有回调服务吗？停止后将无法接收任何回调事件。',
          '警告',
          {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            type: 'warning',
          }
        )
        
        loading.value = true
        await axios.post('/api/v1/callback/stop-all')
        ElMessage.success('所有回调服务已停止')
        await getCallbackStatus()
      } catch (error) {
        if (error !== 'cancel') {
          console.error('停止所有回调服务失败:', error)
          ElMessage.error('停止所有回调服务失败')
        }
      } finally {
        loading.value = false
      }
    }

    // 刷新回调状态
    const refreshCallbackStatus = () => {
      getCallbackStatus()
    }

    // 获取状态标签类型
    const getStatusType = (status) => {
      const statusMap = {
        'running': 'success',
        'initializing': 'warning',
        'failed': 'danger',
        'error': 'danger',
        'stopped': 'info',
        'not_started': 'info'
      }
      return statusMap[status] || 'info'
    }

    // 获取状态文本
    const getStatusText = (status) => {
      const statusMap = {
        'running': '运行中',
        'initializing': '初始化中',
        'failed': '失败',
        'error': '错误',
        'stopped': '已停止',
        'not_started': '未启动',
        'unknown': '未知'
      }
      return statusMap[status] || status
    }

    onMounted(() => {
      getCallbackStatus()
    })

    return {
      callbackServices,
      loading,
      startCallback,
      restartCallback,
      stopCallback,
      startAllCallbacks,
      stopAllCallbacks,
      refreshCallbackStatus,
      getStatusType,
      getStatusText
    }
  }
}
</script>

<style scoped>
.callback-container {
  padding: 20px;
}

.callback-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.callback-info-content {
  padding: 10px;
}

.callback-tips {
  margin-top: 20px;
  background-color: #f8f8f8;
  padding: 15px;
  border-radius: 4px;
}

h1 {
  margin-bottom: 20px;
}

h3 {
  margin-top: 0;
  margin-bottom: 15px;
}
</style> 