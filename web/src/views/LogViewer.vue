<template>
  <div class="log-viewer">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>系统日志查看器</span>
          <div class="header-controls">
            <el-select
              v-model="selectedLogType"
              placeholder="选择日志类型"
              style="width: 200px; margin-right: 10px;"
              :loading="loadingTypes"
            >
              <el-option 
                v-for="logType in logTypes" 
                :key="logType.type" 
                :label="logType.name" 
                :value="logType.type" 
              />
            </el-select>
            <el-input
              v-model="searchKeyword"
              placeholder="搜索关键词"
              style="width: 200px; margin-right: 10px;"
              clearable
              @clear="fetchLogs"
              @keyup.enter="fetchLogs"
            />
            <el-button
              type="primary"
              :icon="Refresh"
              :loading="loading"
              @click="refreshLogs"
            >
              刷新
            </el-button>
          </div>
        </div>
      </template>

      <div class="log-content" v-loading="loading">
        <div v-if="logs.length > 0" class="log-container">
          <pre v-for="(log, index) in logs" :key="index" :class="getLogClass(log)">{{ log }}</pre>
        </div>
        <div v-else class="no-logs">
          <el-empty description="暂无日志记录" />
        </div>
      </div>

      <template #footer>
        <div class="log-footer">
          <div class="log-info">
            <span>共 {{ totalLogs }} 条日志</span>
            <span v-if="searchKeyword">，搜索：{{ searchKeyword }}</span>
          </div>
          <div class="log-actions">
            <el-button size="small" @click="downloadLogs">下载日志</el-button>
            <el-button size="small" type="danger" @click="clearLogs">清空日志</el-button>
          </div>
        </div>
      </template>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import axios from 'axios'

const selectedLogType = ref('all')
const logTypes = ref([])
const loadingTypes = ref(false)
const logs = ref([])
const loading = ref(false)
const totalLogs = ref(0)
const searchKeyword = ref('')

// 监听日志类型变化
watch(selectedLogType, () => {
  fetchLogs()
})

// 获取日志类型列表
const fetchLogTypes = async () => {
  loadingTypes.value = true
  try {
    const response = await axios.get('/api/v1/logs/types')
    logTypes.value = response.data.types
    
    // 如果当前选择的类型不在列表中，重置为第一个
    if (!logTypes.value.find(t => t.type === selectedLogType.value)) {
      selectedLogType.value = logTypes.value[0]?.type || 'all'
    }
  } catch (error) {
    console.error('获取日志类型失败:', error)
    ElMessage.error('获取日志类型失败: ' + (error.response?.data?.detail || error.message))
    // 设置默认日志类型
    logTypes.value = [
      { type: 'all', name: '全部日志' },
      { type: 'error', name: '错误日志' }
    ]
  } finally {
    loadingTypes.value = false
  }
}

// 获取日志
const fetchLogs = async () => {
  loading.value = true
  try {
    const params = {
      type: selectedLogType.value,
      lines: 1000
    }
    
    // 如果有搜索关键词，添加到参数中
    if (searchKeyword.value && searchKeyword.value.trim()) {
      params.search = searchKeyword.value.trim()
    }
    
    const response = await axios.get('/api/v1/logs/', {
      params: params
    })
    
    logs.value = response.data.logs
    totalLogs.value = response.data.total
    
    if (logs.value.length === 0 && totalLogs.value === 0) {
      if (searchKeyword.value) {
        ElMessage.info('没有找到匹配的日志记录')
      } else {
        ElMessage.info('暂无日志记录')
      }
    }
  } catch (error) {
    console.error('获取日志失败:', error)
    ElMessage.error('获取日志失败: ' + (error.response?.data?.detail || error.message))
    logs.value = []
    totalLogs.value = 0
  } finally {
    loading.value = false
  }
}

// 刷新日志
const refreshLogs = () => {
  fetchLogs()
}

// 下载日志
const downloadLogs = async () => {
  try {
    loading.value = true
    const response = await axios.get('/api/v1/logs/download', {
      params: {
        type: selectedLogType.value
      },
      responseType: 'blob'
    })
    
    // 创建下载链接
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    
    // 根据日志类型生成文件名
    const currentLogType = logTypes.value.find(t => t.type === selectedLogType.value)
    const typeName = currentLogType ? currentLogType.name : selectedLogType.value
    const fileName = `${typeName}_${new Date().toISOString().split('T')[0]}.log`
    
    link.setAttribute('download', fileName)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    
    ElMessage.success('日志下载成功')
  } catch (error) {
    console.error('下载日志失败:', error)
    ElMessage.error('下载日志失败')
  } finally {
    loading.value = false
  }
}

// 清空日志
const clearLogs = async () => {
  try {
    const currentLogType = logTypes.value.find(t => t.type === selectedLogType.value)
    const typeName = currentLogType ? currentLogType.name : selectedLogType.value
    
    await ElMessageBox.confirm(
      `确定要清空${typeName}吗？此操作不可恢复`,
      '警告',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    loading.value = true
    const response = await axios.post('/api/v1/logs/clear', null, {
      params: {
        type: selectedLogType.value
      }
    })
    
    ElMessage.success(response.data.message || '日志已清空')
    fetchLogs()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('清空日志失败:', error)
      ElMessage.error('清空日志失败: ' + (error.response?.data?.detail || error.message))
    }
  } finally {
    loading.value = false
  }
}

// 根据日志内容设置样式
const getLogClass = (log) => {
  if (log.includes('[ERROR]') || log.includes('ERROR') || log.toLowerCase().includes('error')) {
    return 'log-line error'
  } else if (log.includes('[WARNING]') || log.includes('WARNING') || log.toLowerCase().includes('warning')) {
    return 'log-line warning'
  } else if (log.includes('[INFO]') || log.includes('INFO') || log.toLowerCase().includes('info')) {
    return 'log-line info'
  } else {
    return 'log-line'
  }
}

onMounted(async () => {
  await fetchLogTypes()
  await fetchLogs()
})
</script>

<style scoped>
.log-viewer {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-controls {
  display: flex;
  align-items: center;
}

.log-content {
  min-height: 500px;
  max-height: 600px;
  overflow-y: auto;
  background-color: #1e1e1e;
  border-radius: 4px;
  padding: 10px;
  font-family: 'Courier New', monospace;
  font-size: 14px;
}

.log-container {
  white-space: pre-wrap;
  word-break: break-all;
}

.log-line {
  margin: 0;
  padding: 2px 0;
  color: #d4d4d4;
}

.log-line.error {
  color: #ff6b6b;
  font-weight: bold;
}

.log-line.warning {
  color: #ffd166;
}

.log-line.info {
  color: #06d6a0;
}

.no-logs {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 300px;
}

.log-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 10px;
}

.log-info {
  display: flex;
  gap: 10px;
  color: #666;
  font-size: 14px;
}

.log-actions {
  display: flex;
  gap: 10px;
}
</style> 