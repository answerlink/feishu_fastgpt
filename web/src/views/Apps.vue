<template>
  <div class="apps">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>应用列表</span>
        </div>
      </template>
      <el-table :data="apps" style="width: 100%">
        <el-table-column prop="app_id" label="应用ID" width="180" />
        <el-table-column prop="app_name" label="应用名称" width="180" />
        <el-table-column label="操作">
          <template #default="scope">
            <el-button
              type="primary"
              size="small"
              @click="testToken(scope.row.app_id)"
              :loading="loadingStates[scope.row.app_id]"
            >
              测试Token
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      title="Token信息"
      width="50%"
    >
      <pre>{{ tokenInfo }}</pre>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="dialogVisible = false">关闭</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive } from 'vue'
import axios from 'axios'
import { ElMessage } from 'element-plus'

const apps = ref([])
const dialogVisible = ref(false)
const tokenInfo = ref('')
const loadingStates = reactive({})

const loadApps = async () => {
  try {
    const response = await axios.get('/api/v1/test/apps')
    apps.value = response.data.apps
  } catch (error) {
    ElMessage.error('加载应用列表失败')
    console.error('加载应用列表失败:', error)
  }
}

const testToken = async (appId) => {
  loadingStates[appId] = true
  try {
    const response = await axios.get(`/api/v1/test/token/${appId}`)
    tokenInfo.value = JSON.stringify(response.data, null, 2)
    dialogVisible.value = true
  } catch (error) {
    ElMessage.error('获取Token失败')
    console.error('获取Token失败:', error)
  } finally {
    loadingStates[appId] = false
  }
}

onMounted(() => {
  loadApps()
})
</script>

<style scoped>
.apps {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

pre {
  background-color: #f5f7fa;
  padding: 15px;
  border-radius: 4px;
  overflow-x: auto;
}
</style> 