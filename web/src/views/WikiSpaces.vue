<template>
  <div class="wiki-spaces">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>知识空间列表</span>
          <div class="header-controls">
            <el-select
              v-model="selectedAppId"
              placeholder="请选择应用"
              @change="handleAppChange"
              style="margin-right: 10px; width: 200px;"
            >
              <el-option
                v-for="app in apps"
                :key="app.app_id"
                :label="app.app_name"
                :value="app.app_id"
              />
            </el-select>
            <el-button
              type="primary"
              :icon="Refresh"
              circle
              :loading="loading"
              @click="refreshData"
              :disabled="!selectedAppId"
              title="刷新列表"
            />
            <el-dropdown @command="handleSchedulerCommand" trigger="click">
              <el-button type="info" size="default" style="margin-left: 10px;">
                定时任务 <el-icon class="el-icon--right"><arrow-down /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="status">查看状态</el-dropdown-item>
                  <el-dropdown-item command="start">启动任务</el-dropdown-item>
                  <el-dropdown-item command="stop">停止任务</el-dropdown-item>
                  <el-dropdown-item command="manual-run">立即执行</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
      </template>

      <el-row :gutter="20">
        <el-col :span="8">
          <div class="space-list">
            <el-table
              v-loading="loading"
              :data="paginatedSpaces"
              style="width: 100%"
              @row-click="handleSpaceClick"
              highlight-current-row
              :show-header="true"
            >
              <el-table-column prop="name" label="空间名称" />
              <el-table-column prop="space_type" label="类型" width="80">
                <template #default="scope">
                  <el-tag :type="scope.row.space_type === 'team' ? 'success' : 'info'" size="small">
                    {{ scope.row.space_type }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="订阅状态" width="100">
                <template #default="scope">
                  <el-switch
                    v-model="scope.row.subscribed"
                    :loading="scope.row.subscribing"
                    @change="(val) => handleSubscriptionChange(scope.row, val)"
                    :active-value="true"
                    :inactive-value="false"
                    size="small"
                  />
                </template>
              </el-table-column>
            </el-table>

            <!-- 表格分页 -->
            <div class="table-pagination" v-if="spaces.length > 0">
              <el-pagination
                v-model:current-page="currentPage"
                v-model:page-size="pageSize"
                :page-sizes="[10, 20, 50, 100]"
                layout="total, sizes, prev, pager, next, jumper"
                :total="spaces.length"
                :small="true"
                background
                @size-change="handleSizeChange"
                @current-change="handleCurrentChange"
              />
            </div>

            <!-- 加载更多按钮 -->
            <div class="load-more" v-if="hasMore">
              <el-button :loading="loading" @click="loadMore" size="small" type="primary">
                加载更多空间
              </el-button>
            </div>
          </div>
        </el-col>

        <el-col :span="16">
          <div class="node-tree" v-loading="nodeLoading">
            <div class="tree-header" v-if="selectedSpace">
              <h3>{{ selectedSpace.name }} - 文档结构 <span class="space-id">({{ selectedSpace.space_id }})</span></h3>
              <div class="space-stats" v-if="selectedSpace.subscribed">
                <el-tag type="success" size="small">已订阅文档: {{ selectedSpace.doc_count || 0 }} 个</el-tag>
                <el-tag type="info" size="small" v-if="selectedSpace.last_sync_time">
                  最后同步: {{ formatDate(selectedSpace.last_sync_time) }}
                </el-tag>
              </div>
            </div>
            <div class="tree-container">
              <el-tree
                v-if="selectedSpace"
                :data="nodeTree"
                :props="defaultProps"
                :load="loadNode"
                lazy
                node-key="node_token"
                :default-expand-all="false"
                :highlight-current="true"
                class="outline-tree"
                @node-click="handleNodeClick"
              >
                <template #default="{ node, data }">
                  <div class="custom-tree-node">
                    <span class="node-icon">
                      <el-icon v-if="data.has_child"><FolderOpened /></el-icon>
                      <el-icon v-else><Document /></el-icon>
                    </span>
                    <span class="node-title">{{ data.title }}</span>
                    <div class="node-actions">
                      <span v-if="data.obj_type && isPreviewable(data.obj_type)" class="preview-btn" @click.stop="previewDoc(data)">
                        <el-icon><View /></el-icon>
                      </span>
                      <span class="node-type" v-if="data.obj_type">
                        <el-tag size="small" :type="getNodeTypeTag(data.obj_type)">
                          {{ getNodeTypeName(data.obj_type) }}
                        </el-tag>
                      </span>
                    </div>
                  </div>
                </template>
              </el-tree>
              <div v-else class="no-space-selected">
                <el-empty description="请选择一个知识空间查看文档结构" :image-size="100" />
              </div>
            </div>
          </div>
        </el-col>
      </el-row>

    </el-card>
    
    <!-- 文档预览对话框 -->
    <doc-preview
      v-model="showDocPreview"
      :doc-token="currentDocToken"
      :doc-type="currentDocType"
      :title="currentDocTitle"
      :app-id="selectedAppId"
      @close="closeDocPreview"
    />
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, computed } from 'vue'
import axios from 'axios'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Document, FolderOpened, View, ArrowDown } from '@element-plus/icons-vue'
import DocPreview from '@/components/DocPreview.vue'

const apps = ref([])
const selectedAppId = ref('')
const spaces = ref([])
const loading = ref(false)
const hasMore = ref(false)
const pageToken = ref('')
const nodeTree = ref([])
const selectedSpace = ref(null)
const nodeLoading = ref(false)
const subscriptionsLoading = ref(false)

// 分页相关
const currentPage = ref(1)
const pageSize = ref(20)

// 计算属性：当前页的空间列表
const paginatedSpaces = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return spaces.value.slice(start, end)
})

const defaultProps = {
  label: 'title',
  children: 'children',
  isLeaf: (data) => !data.has_child
}

// 格式化日期
const formatDate = (dateString) => {
  if (!dateString) return '';
  const date = new Date(dateString);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
}

// 缓存相关函数
const CACHE_KEY = 'wiki_nodes_cache'
const CACHE_EXPIRE_KEY = 'wiki_nodes_cache_expire'
const CACHE_EXPIRE_TIME = 24 * 60 * 60 * 1000 // 1天的毫秒数

// 从localStorage加载缓存
const loadCacheFromStorage = () => {
  try {
    const cacheStr = localStorage.getItem(CACHE_KEY)
    const expireStr = localStorage.getItem(CACHE_EXPIRE_KEY)
    
    if (!cacheStr || !expireStr) return new Map()
    
    const expireTime = parseInt(expireStr)
    if (Date.now() > expireTime) {
      // 缓存已过期，清除
      localStorage.removeItem(CACHE_KEY)
      localStorage.removeItem(CACHE_EXPIRE_KEY)
      return new Map()
    }
    
    // 将JSON转换回Map
    const cacheObj = JSON.parse(cacheStr)
    const cacheMap = new Map()
    Object.keys(cacheObj).forEach(key => {
      cacheMap.set(key, cacheObj[key])
    })
    
    return cacheMap
  } catch (error) {
    console.error('加载缓存失败:', error)
    return new Map()
  }
}

// 保存缓存到localStorage
const saveCacheToStorage = (cache) => {
  try {
    // 将Map转换为普通对象以便JSON序列化
    const cacheObj = {}
    cache.forEach((value, key) => {
      cacheObj[key] = value
    })
    
    localStorage.setItem(CACHE_KEY, JSON.stringify(cacheObj))
    localStorage.setItem(CACHE_EXPIRE_KEY, String(Date.now() + CACHE_EXPIRE_TIME))
  } catch (error) {
    console.error('保存缓存失败:', error)
  }
}

// 初始化缓存
const nodeCache = ref(loadCacheFromStorage())

// 清空缓存
const clearCache = () => {
  nodeCache.value.clear()
  localStorage.removeItem(CACHE_KEY)
  localStorage.removeItem(CACHE_EXPIRE_KEY)
}

// 添加到缓存并保存
const addToCache = (key, value) => {
  nodeCache.value.set(key, value)
  saveCacheToStorage(nodeCache.value)
}

const loadApps = async () => {
  try {
    const response = await axios.get('/api/v1/test/apps')
    apps.value = response.data.apps
    
    // 自动选择第一个应用并加载知识空间列表
    if (apps.value.length > 0 && !selectedAppId.value) {
      selectedAppId.value = apps.value[0].app_id
      // 加载第一个应用的知识空间列表
      await loadSpaces(selectedAppId.value)
    }
  } catch (error) {
    ElMessage.error('加载应用列表失败')
    console.error('加载应用列表失败:', error)
  }
}

const loadSpaces = async (newAppId = null) => {
  if (newAppId) {
    spaces.value = []
    pageToken.value = ''
  }
  
  if (!selectedAppId.value) return
  
  loading.value = true
  try {
    const params = { app_id: selectedAppId.value }
    if (pageToken.value) {
      params.page_token = pageToken.value
    }
    
    const response = await axios.get('/api/v1/wiki/spaces', { params })
    if (response.data.code === 0) {
      const data = response.data.data
      const newSpaces = newAppId ? data.items : [...spaces.value, ...data.items]
      
      // 为每个空间添加订阅状态属性
      newSpaces.forEach(space => {
        space.subscribed = false
        space.subscribing = false
        space.doc_count = 0
      })
      
      spaces.value = newSpaces
      hasMore.value = data.has_more
      pageToken.value = data.page_token
      
      // 加载订阅状态
      loadSubscriptionStatus()
    } else {
      ElMessage.error(response.data.msg || '获取知识空间列表失败')
    }
  } catch (error) {
    ElMessage.error('获取知识空间列表失败')
    console.error('获取知识空间列表失败:', error)
  } finally {
    loading.value = false
  }
}

// 加载知识空间订阅状态
const loadSubscriptionStatus = async () => {
  if (!selectedAppId.value || spaces.value.length === 0) return
  
  subscriptionsLoading.value = true
  try {
    const response = await axios.get('/api/v1/wiki/subscriptions', {
      params: { app_id: selectedAppId.value }
    })
    
    if (response.data.code === 0) {
      const subscriptions = response.data.data.items || []
      
      // 更新空间列表中的订阅状态
      spaces.value.forEach(space => {
        const subscription = subscriptions.find(sub => sub.space_id === space.space_id)
        if (subscription) {
          space.subscribed = subscription.status === 1
          space.doc_count = subscription.doc_count || 0
          space.last_sync_time = subscription.last_sync_time
        } else {
          space.subscribed = false
        }
      })
      
      // 如果当前选中的空间存在，也更新其订阅状态
      if (selectedSpace.value) {
        const subscription = subscriptions.find(sub => sub.space_id === selectedSpace.value.space_id)
        if (subscription) {
          selectedSpace.value.subscribed = subscription.status === 1
          selectedSpace.value.doc_count = subscription.doc_count || 0
          selectedSpace.value.last_sync_time = subscription.last_sync_time
        } else {
          selectedSpace.value.subscribed = false
        }
      }
    }
  } catch (error) {
    console.error('获取订阅状态失败:', error)
  } finally {
    subscriptionsLoading.value = false
  }
}

// 处理订阅状态变更
const handleSubscriptionChange = async (space, subscribed) => {
  if (!selectedAppId.value) return
  
  space.subscribing = true
  try {
    const response = await axios.post('/api/v1/wiki/subscriptions/update', {
      app_id: selectedAppId.value,
      space_id: space.space_id,
      status: subscribed ? 1 : 0
    })
    
    if (response.data.code === 0) {
      space.subscribed = subscribed
      
      // 如果是选中的空间，也更新其状态
      if (selectedSpace.value && selectedSpace.value.space_id === space.space_id) {
        selectedSpace.value.subscribed = subscribed
      }
      
      ElMessage.success(subscribed ? '已成功订阅知识空间' : '已取消订阅知识空间')
      
      // 如果是订阅操作，询问是否要批量订阅文档
      if (subscribed) {
        await ElMessageBox.confirm(
          '是否要批量订阅该知识空间下的所有文档？',
          '订阅确认',
          {
            confirmButtonText: '是',
            cancelButtonText: '否',
            type: 'info'
          }
        )
        .then(() => {
          batchSubscribeDocuments(space)
        })
        .catch(() => {
          // 用户取消批量订阅，不做任何操作
        })
      }
      
      // 重新加载订阅状态以获取最新的文档计数
      setTimeout(loadSubscriptionStatus, 1000)
    } else {
      // 恢复原状态
      space.subscribed = !subscribed
      ElMessage.error(response.data.msg || '更新订阅状态失败')
    }
  } catch (error) {
    // 恢复原状态
    space.subscribed = !subscribed
    console.error('更新订阅状态失败:', error)
    ElMessage.error('更新订阅状态失败')
  } finally {
    space.subscribing = false
  }
}

// 批量订阅知识空间下的文档
const batchSubscribeDocuments = async (space) => {
  if (!selectedAppId.value) return
  
  space.subscribing = true
  try {
    const response = await axios.post('/api/v1/documents/subscribe-space', {
      app_id: selectedAppId.value,
      space_id: space.space_id
    })
    
    if (response.data.code === 0) {
      const data = response.data.data
      ElMessage.success(`批量订阅完成: 共${data.total}个节点, ${data.success}个新订阅, ${data.already_subscribed}个已订阅`)
      
      // 更新文档计数
      space.doc_count = data.success + data.already_subscribed
      
      // 如果是选中的空间，也更新其状态
      if (selectedSpace.value && selectedSpace.value.space_id === space.space_id) {
        selectedSpace.value.doc_count = space.doc_count
      }
      
      // 重新加载订阅状态以获取最新的文档计数
      setTimeout(loadSubscriptionStatus, 1000)
    } else {
      ElMessage.error(response.data.msg || '批量订阅文档失败')
    }
  } catch (error) {
    console.error('批量订阅文档失败:', error)
    ElMessage.error('批量订阅文档失败')
  } finally {
    space.subscribing = false
  }
}

const loadMore = () => {
  loadSpaces()
}

const handleSpaceClick = (row) => {
  selectedSpace.value = row
  loadRootNodes(row.space_id)
}

const loadRootNodes = async (spaceId) => {
  nodeLoading.value = true
  try {
    // 不再清空缓存，而是检查是否有缓存
    const cacheKey = `root_${spaceId}`
    if (nodeCache.value.has(cacheKey)) {
      nodeTree.value = nodeCache.value.get(cacheKey)
      nodeLoading.value = false
      return
    }
    
    const response = await axios.get(`/api/v1/wiki/spaces/${spaceId}/nodes`, {
      params: { app_id: selectedAppId.value }
    })
    if (response.data.code === 0) {
      nodeTree.value = response.data.data.items
      addToCache(cacheKey, response.data.data.items)
    } else {
      ElMessage.error(response.data.msg || '获取文档结构失败')
    }
  } catch (error) {
    console.error('获取文档结构失败:', error)
    ElMessage.error('获取文档结构失败')
  } finally {
    nodeLoading.value = false
  }
}

const loadNode = async (node, resolve) => {
  // 根节点缓存
  if (node.level === 0) {
    if (selectedSpace.value) {
      const cacheKey = `root_${selectedSpace.value.space_id}`
      if (nodeCache.value.has(cacheKey)) {
        return resolve(nodeCache.value.get(cacheKey))
      }
    }
    return resolve(nodeTree.value)
  }
  
  // 子节点缓存
  const spaceId = selectedSpace.value.space_id
  const nodeToken = node.data.node_token
  const cacheKey = `${spaceId}_${nodeToken}`
  
  if (nodeCache.value.has(cacheKey)) {
    return resolve(nodeCache.value.get(cacheKey))
  }
  
  try {
    const response = await axios.get(`/api/v1/wiki/spaces/${spaceId}/nodes`, {
      params: {
        app_id: selectedAppId.value,
        parent_node_token: nodeToken
      }
    })
    if (response.data.code === 0) {
      const items = response.data.data.items
      addToCache(cacheKey, items)
      resolve(items)
    } else {
      resolve([])
      ElMessage.error(response.data.msg || '获取子节点失败')
    }
  } catch (error) {
    console.error('获取子节点失败:', error)
    ElMessage.error('获取子节点失败')
    resolve([])
  }
}

const getNodeTypeTag = (type) => {
  const typeMap = {
    'docx': 'primary',
    'sheet': 'success',
    'bitable': 'warning',
    'mindnote': 'info',
    'slides': 'danger'
  }
  return typeMap[type] || 'info'
}

const getNodeTypeName = (type) => {
  const typeMap = {
    'docx': '文档',
    'sheet': '表格',
    'bitable': '多维表格',
    'mindnote': '思维导图',
    'slides': '幻灯片'
  }
  return typeMap[type] || type
}

const handleAppChange = (newAppId) => {
  selectedSpace.value = null
  nodeTree.value = []
  loadSpaces(newAppId)
}

const refreshData = () => {
  // 只有点击刷新按钮才清空缓存
  clearCache()
  ElMessage.success('缓存已清空，正在重新加载数据')
  
  if (selectedSpace.value) {
    loadRootNodes(selectedSpace.value.space_id)
  } else {
    loadSpaces(selectedAppId.value)
  }
  
  // 重新加载订阅状态
  loadSubscriptionStatus()
}

// 文档预览相关
const showDocPreview = ref(false)
const currentDocToken = ref('')
const currentDocType = ref('docx')
const currentDocTitle = ref('文档预览')

// 判断文档类型是否可预览
const isPreviewable = (objType) => {
  // 移除sheet和bitable，不再支持表格预览
  const previewableTypes = ['docx', 'doc', 'mindnote', 'slides'] 
  return previewableTypes.includes(objType)
}

// 预览文档
const previewDoc = (data) => {
  if (data.obj_type && isPreviewable(data.obj_type)) {
    currentDocToken.value = data.obj_token
    currentDocType.value = data.obj_type
    currentDocTitle.value = data.title
    showDocPreview.value = true
  } else {
    ElMessage.info('该节点类型暂不支持预览')
  }
}

const handleNodeClick = (data) => {
  // 如果是没有子节点的可预览文档，点击节点时直接预览
  if (!data.has_child && data.obj_type && isPreviewable(data.obj_type)) {
    previewDoc(data)
  }
  // 其他情况下让树自动处理展开/折叠
}

const closeDocPreview = () => {
  showDocPreview.value = false
}

// 分页处理方法
const handleSizeChange = (newSize) => {
  pageSize.value = newSize
  currentPage.value = 1
}

const handleCurrentChange = (newPage) => {
  currentPage.value = newPage
}

const handleSchedulerCommand = async (command) => {
  // 处理调度器命令
  try {
    switch (command) {
      case 'status':
        // 查询调度器状态
        const statusResponse = await axios.get('/api/v1/scheduler/status')
        if (statusResponse.data.code === 0) {
          ElMessage.info(statusResponse.data.msg)
        } else {
          ElMessage.error('获取调度器状态失败')
        }
        break
        
      case 'start':
        // 启动调度器
        const startResponse = await axios.post('/api/v1/scheduler/start')
        if (startResponse.data.code === 0) {
          ElMessage.success(startResponse.data.msg)
        } else {
          ElMessage.error('启动调度器失败')
        }
        break
        
      case 'stop':
        // 停止调度器
        await ElMessageBox.confirm(
          '确定要停止定时任务吗？停止后将不再自动扫描订阅空间',
          '操作确认',
          {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            type: 'warning'
          }
        )
        
        const stopResponse = await axios.post('/api/v1/scheduler/stop')
        if (stopResponse.data.code === 0) {
          ElMessage.success(stopResponse.data.msg)
        } else {
          ElMessage.error('停止调度器失败')
        }
        break
        
      case 'manual-run':
        // 手动触发任务执行
        await ElMessageBox.confirm(
          '确定要立即执行订阅扫描任务吗？这将遍历所有已订阅空间的文档',
          '操作确认',
          {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            type: 'info'
          }
        )
        
        const runResponse = await axios.post('/api/v1/scheduler/manual-run')
        if (runResponse.data.code === 0) {
          ElMessage.success(runResponse.data.msg)
        } else {
          ElMessage.error('触发任务执行失败')
        }
        break
        
      default:
        console.error('未知命令:', command)
    }
  } catch (error) {
    if (error?.message !== 'Operation canceled by user') {
      console.error('处理调度器命令出错:', error)
      ElMessage.error(`操作失败: ${error.message || '未知错误'}`)
    }
  }
}

onMounted(async () => {
  await loadApps()
  
  // 如果已经选择了应用，加载订阅状态
  if (selectedAppId.value) {
    loadSubscriptionStatus()
  }
})

// 组件卸载前保存缓存
onBeforeUnmount(() => {
  saveCacheToStorage(nodeCache.value)
})
</script>

<style scoped>
.wiki-spaces {
  padding: 20px;
  height: calc(100vh - 40px);
  overflow: hidden;
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

.table-pagination {
  margin-top: 10px;
  display: flex;
  justify-content: center;
  height: 32px;
  flex-shrink: 0;
}

.load-more {
  margin-top: 10px;
  text-align: center;
  height: 32px;
  flex-shrink: 0;
}

.space-list {
  border-right: 1px solid #eee;
  padding-right: 20px;
  height: 600px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.space-list .el-table {
  flex: 1;
  min-height: 0;
}

.node-tree {
  padding-left: 20px;
  height: 600px;
  display: flex;
  flex-direction: column;
}

.tree-container {
  flex: 1;
  overflow-y: auto;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 10px;
  background-color: #fafafa;
  min-height: 0;
}

.tree-header {
  margin-bottom: 15px;
  padding-bottom: 10px;
  border-bottom: 1px solid #e4e7ed;
  flex-shrink: 0;
}

.tree-header h3 {
  margin: 0 0 10px 0;
  color: #303133;
  font-size: 16px;
}

.space-stats {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.no-space-selected {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #909399;
}

.custom-tree-node {
  flex: 1;
  display: flex;
  align-items: center;
  font-size: 14px;
  padding-right: 8px;
  min-height: 24px;
}

.node-icon {
  margin-right: 8px;
  color: #909399;
  font-size: 16px;
}

.node-title {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.node-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.preview-btn {
  cursor: pointer;
  color: #409EFF;
  transition: color 0.3s;
  font-size: 16px;
}

.preview-btn:hover {
  color: #66b1ff;
}

.node-type {
  margin-left: 0;
}

.outline-tree {
  height: 100%;
  overflow: auto;
}

.space-id {
  font-size: 0.8em;
  color: #909399;
  font-weight: normal;
}

/* Element Plus Card 内容区域样式调整 */
:deep(.el-card__body) {
  height: calc(100vh - 140px);
  overflow: hidden;
  padding: 20px;
}

/* Element Plus 表格样式调整 */
:deep(.el-table) {
  height: 100% !important;
}

:deep(.el-table .el-table__body-wrapper) {
  max-height: calc(100% - 40px) !important;
}

/* 响应式设计 */
@media (max-width: 1200px) {
  .space-list,
  .node-tree {
    height: 500px;
  }
  
  :deep(.el-card__body) {
    height: calc(100vh - 120px);
  }
}

@media (max-width: 768px) {
  .wiki-spaces {
    padding: 10px;
  }
  
  .space-list,
  .node-tree {
    height: 400px;
  }
  
  .space-list {
    padding-right: 10px;
  }
  
  .node-tree {
    padding-left: 10px;
  }
  
  :deep(.el-card__body) {
    height: calc(100vh - 100px);
    padding: 10px;
  }
}
</style> 