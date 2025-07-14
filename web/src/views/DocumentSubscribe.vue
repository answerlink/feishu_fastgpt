<template>
  <div class="document-container">
    <h1>文档事件订阅</h1>

    <el-tabs v-model="activeTab">
      <el-tab-pane label="单个文档订阅" name="single">
        <el-card class="doc-card">
          <template #header>
            <div class="card-header">
              <span>订阅单个文档事件</span>
            </div>
          </template>

          <el-form :model="subscribeForm" label-width="120px" :rules="rules" ref="subscribeFormRef">
            <el-form-item label="应用" prop="app_id">
              <el-select v-model="subscribeForm.app_id" placeholder="选择应用">
                <el-option 
                  v-for="app in appList" 
                  :key="app.app_id" 
                  :label="app.app_name || app.app_id" 
                  :value="app.app_id" 
                />
              </el-select>
            </el-form-item>
            
            <el-form-item label="文档Token" prop="file_token">
              <el-input v-model="subscribeForm.file_token" placeholder="输入文档Token，例如：doccnfYZzTlvXqZIGTdAHKabcef"/>
            </el-form-item>
            
            <el-form-item label="文档类型" prop="file_type">
              <el-select v-model="subscribeForm.file_type" placeholder="选择文档类型">
                <el-option label="新版文档" value="docx" />
                <el-option label="电子表格" value="sheet" />
                <el-option label="多维表格" value="bitable" />
                <el-option label="文件" value="file" />
              </el-select>
            </el-form-item>
            
            <el-form-item>
              <el-button type="primary" @click="handleSubscribe" :loading="subscribing">订阅</el-button>
              <el-button type="danger" @click="handleUnsubscribe" :loading="unsubscribing">取消订阅</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>
      
      <el-tab-pane label="批量订阅知识空间" name="batch">
        <el-card class="doc-card">
          <template #header>
            <div class="card-header">
              <span>批量订阅知识空间下所有文档</span>
            </div>
          </template>

          <el-form :model="batchForm" label-width="120px" :rules="batchRules" ref="batchFormRef">
            <el-form-item label="应用" prop="app_id">
              <el-select v-model="batchForm.app_id" placeholder="选择应用" @change="loadSpaces">
                <el-option 
                  v-for="app in appList" 
                  :key="app.app_id" 
                  :label="app.app_name || app.app_id" 
                  :value="app.app_id" 
                />
              </el-select>
            </el-form-item>
            
            <el-form-item label="知识空间" prop="space_id">
              <el-select 
                v-model="batchForm.space_id" 
                placeholder="选择知识空间" 
                :loading="spacesLoading"
                :disabled="!batchForm.app_id || spacesLoading"
              >
                <el-option 
                  v-for="space in spacesList" 
                  :key="space.space_id" 
                  :label="space.name" 
                  :value="space.space_id" 
                />
              </el-select>
            </el-form-item>
            
            <el-form-item>
              <el-button type="primary" @click="handleBatchSubscribe" :loading="batchSubscribing">
                批量订阅空间文档
              </el-button>
            </el-form-item>
          </el-form>
          
          <!-- 批量订阅结果展示 -->
          <div v-if="batchResult" class="batch-result">
            <el-divider>订阅结果</el-divider>
            <el-alert
              :title="batchResult.msg"
              :type="batchResult.code === 0 ? 'success' : 'error'"
              :description="getResultDescription(batchResult)"
              show-icon
              :closable="false"
            />
            
            <div class="result-details" v-if="batchResult.data && batchResult.data.details && batchResult.data.details.length > 0">
              <h4>详细结果：</h4>
              <el-table :data="batchResult.data.details" stripe style="width: 100%" max-height="300">
                <el-table-column prop="title" label="文档标题" />
                <el-table-column prop="obj_token" label="文档Token" width="180" show-overflow-tooltip />
                <el-table-column prop="obj_type" label="类型" width="100" />
                <el-table-column label="状态" width="100">
                  <template #default="scope">
                    <el-tag :type="getStatusType(scope.row.status)">
                      {{ getStatusText(scope.row.status) }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="error" label="错误信息" show-overflow-tooltip />
              </el-table>
            </div>
          </div>
        </el-card>
      </el-tab-pane>
      
      <el-tab-pane label="已订阅文档列表" name="subscribed">
        <el-card class="doc-card">
          <template #header>
            <div class="card-header">
              <span>已订阅文档列表</span>
              <div class="header-controls">
                <el-select
                  v-model="subscribedForm.app_id"
                  placeholder="选择应用"
                  style="width: 200px; margin-right: 10px;"
                  @change="loadSubscribedDocuments"
                >
                  <el-option 
                    v-for="app in appList" 
                    :key="app.app_id" 
                    :label="app.app_name || app.app_id" 
                    :value="app.app_id" 
                  />
                </el-select>
                <el-button
                  type="primary"
                  :icon="Refresh"
                  :loading="loadingSubscribed"
                  @click="loadSubscribedDocuments"
                  :disabled="!subscribedForm.app_id"
                >
                  刷新
                </el-button>
              </div>
            </div>
          </template>
          
          <div v-loading="loadingSubscribed">
            <el-table
              v-if="subscribedDocuments.length > 0"
              :data="subscribedDocuments"
              style="width: 100%"
              border
            >
              <el-table-column label="文档标题" min-width="150">
                <template #default="scope">
                  <span>{{ scope.row.title }}<span v-if="scope.row.file_token" class="token-suffix">({{ scope.row.file_token }})</span></span>
                </template>
              </el-table-column>
              <el-table-column prop="file_token" label="文档Token" min-width="180" show-overflow-tooltip />
              <el-table-column prop="file_type" label="类型" width="100" />
              <el-table-column label="文档最后编辑时间" width="180">
                <template #default="scope">
                  <span>{{ formatDateTime(scope.row.obj_edit_time) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="AI知识库更新时间" width="180">
                <template #default="scope">
                  <span>{{ formatDateTime(scope.row.aichat_update_time) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="120">
                <template #default="scope">
                  <el-tag :type="getSyncStatusType(scope.row)">
                    {{ getSyncStatusText(scope.row) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="200">
                <template #default="scope">
                  <div style="display: flex; gap: 5px;">
                    <el-button
                      type="primary"
                      size="small"
                      @click="handleSyncDocument(scope.row)"
                      :loading="scope.row.syncing"
                    >
                      同步
                    </el-button>
                    <el-button
                      type="danger"
                      size="small"
                      @click="handleUnsubscribeDocument(scope.row)"
                      :loading="scope.row.unsubscribing"
                    >
                      取消订阅
                    </el-button>
                  </div>
                </template>
              </el-table-column>
            </el-table>
            <div v-else class="no-data">
              <el-empty description="暂无已订阅文档" v-if="subscribedForm.app_id" />
              <el-empty description="请选择应用查看已订阅文档" v-else />
            </div>
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <el-card class="doc-card doc-info">
      <template #header>
        <div class="card-header">
          <span>文档事件列表</span>
        </div>
      </template>

      <div class="doc-info-content">
        <el-descriptions border column="2">
          <el-descriptions-item label="文件编辑事件">file.edit_v1</el-descriptions-item>
          <el-descriptions-item label="标题更新事件">file.title_update_v1</el-descriptions-item>
          <el-descriptions-item label="文件创建事件">file.created_in_folder_v1</el-descriptions-item>
          <el-descriptions-item label="文件删除事件">file.trashed_v1</el-descriptions-item>
        </el-descriptions>

        <div class="doc-tips">
          <h3>使用说明</h3>
          <ol>
            <li>订阅文档事件前，需要确保应用拥有文档的管理权限</li>
            <li>文档Token可以从文档URL中获取，例如：https://bytedance.feishu.cn/docs/<b>doccnfYZzTlvXqZIGTdAHKabcef</b></li>
            <li>订阅后，文档的编辑、标题更新、删除等事件将通过回调推送</li>
            <li>事件推送将自动通过回调模块接收处理，详见日志</li>
            <li>批量订阅功能会遍历空间中所有节点，仅订阅docx类型的文档</li>
            <li>系统会同时订阅每个文档的多种事件类型（编辑、标题更新、创建、删除等）</li>
          </ol>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import axios from 'axios'

export default {
  name: 'DocumentSubscribeView',

  setup() {
    const activeTab = ref('single')
    const subscribeFormRef = ref(null)
    const batchFormRef = ref(null)
    const appList = ref([])
    const spacesList = ref([])
    const subscribing = ref(false)
    const unsubscribing = ref(false)
    const spacesLoading = ref(false)
    const batchSubscribing = ref(false)
    const batchResult = ref(null)
    const subscribedDocuments = ref([])
    const loadingSubscribed = ref(false)

    const subscribeForm = reactive({
      app_id: '',
      file_token: '',
      file_type: 'docx'
    })

    const batchForm = reactive({
      app_id: '',
      space_id: ''
    })
    
    const subscribedForm = reactive({
      app_id: ''
    })

    const rules = {
      app_id: [
        { required: true, message: '请选择应用', trigger: 'change' }
      ],
      file_token: [
        { required: true, message: '请输入文档Token', trigger: 'blur' }
      ],
      file_type: [
        { required: true, message: '请选择文档类型', trigger: 'change' }
      ]
    }

    const batchRules = {
      app_id: [
        { required: true, message: '请选择应用', trigger: 'change' }
      ],
      space_id: [
        { required: true, message: '请选择知识空间', trigger: 'change' }
      ]
    }

    // 获取应用列表
    const getAppList = async () => {
      try {
        const response = await axios.get('/api/v1/test/apps')
        if (response.data && response.data.apps) {
          appList.value = response.data.apps
        }
      } catch (error) {
        console.error('获取应用列表失败:', error)
        ElMessage.error('获取应用列表失败，请检查网络连接')
      }
    }

    // 加载知识空间列表
    const loadSpaces = async () => {
      if (!batchForm.app_id) return
      
      spacesLoading.value = true
      spacesList.value = []
      
      try {
        const response = await axios.get('/api/v1/wiki/spaces', {
          params: { app_id: batchForm.app_id }
        })
        
        if (response.data.code === 0 && response.data.data && response.data.data.items) {
          spacesList.value = response.data.data.items
        } else {
          ElMessage.error(response.data.msg || '获取知识空间列表失败')
        }
      } catch (error) {
        console.error('获取知识空间列表失败:', error)
        ElMessage.error('获取知识空间列表失败，请查看控制台获取详细错误信息')
      } finally {
        spacesLoading.value = false
      }
    }

    // 订阅文档事件
    const handleSubscribe = async () => {
      if (!subscribeFormRef.value) return
      
      // 表单验证
      await subscribeFormRef.value.validate(async (valid) => {
        if (!valid) return
        
        subscribing.value = true
        try {
          const response = await axios.post('/api/v1/documents/subscribe', subscribeForm)
          
          if (response.data.code === 0) {
            ElMessage.success('文档事件订阅成功')
          } else {
            ElMessage.error(`订阅失败: ${response.data.msg || '未知错误'}`)
          }
        } catch (error) {
          console.error('订阅文档事件失败:', error)
          ElMessage.error('订阅文档事件失败，请查看控制台获取详细错误信息')
        } finally {
          subscribing.value = false
        }
      })
    }

    // 取消订阅文档事件
    const handleUnsubscribe = async () => {
      if (!subscribeFormRef.value) return
      
      // 表单验证
      await subscribeFormRef.value.validate(async (valid) => {
        if (!valid) return
        
        unsubscribing.value = true
        try {
          const response = await axios.post('/api/v1/documents/unsubscribe', subscribeForm)
          
          if (response.data.code === 0) {
            ElMessage.success('取消文档事件订阅成功')
          } else {
            ElMessage.error(`取消订阅失败: ${response.data.msg || '未知错误'}`)
          }
        } catch (error) {
          console.error('取消订阅文档事件失败:', error)
          ElMessage.error('取消订阅文档事件失败，请查看控制台获取详细错误信息')
        } finally {
          unsubscribing.value = false
        }
      })
    }
    
    // 批量订阅知识空间下所有文档
    const handleBatchSubscribe = async () => {
      if (!batchFormRef.value) return
      
      // 表单验证
      await batchFormRef.value.validate(async (valid) => {
        if (!valid) return
        
        batchSubscribing.value = true
        batchResult.value = null
        
        try {
          ElMessage.info('开始订阅知识空间文档，这可能需要一些时间...')
          
          const response = await axios.post('/api/v1/documents/subscribe-space', batchForm)
          batchResult.value = response.data
          
          if (response.data.code === 0) {
            ElMessage.success('批量订阅知识空间文档完成')
          } else {
            ElMessage.error(`批量订阅失败: ${response.data.msg || '未知错误'}`)
          }
        } catch (error) {
          console.error('批量订阅知识空间文档失败:', error)
          ElMessage.error('批量订阅知识空间文档失败，请查看控制台获取详细错误信息')
        } finally {
          batchSubscribing.value = false
        }
      })
    }
    
    // 获取结果描述
    const getResultDescription = (result) => {
      if (!result || !result.data) return ''
      
      return `共处理${result.data.total}个节点，成功订阅${result.data.success}个文档，失败${result.data.failed}个，跳过${result.data.skipped}个非文档节点`
    }

    // 获取状态类型
    const getStatusType = (status) => {
      switch(status) {
        case 'success':
          return 'success'
        case 'already_subscribed':
          return 'info'
        case 'failed':
          return 'danger'
        case 'skipped':
          return 'warning'
        default:
          return 'info'
      }
    }
    
    // 获取状态文本
    const getStatusText = (status) => {
      switch(status) {
        case 'success':
          return '成功'
        case 'already_subscribed':
          return '已订阅'
        case 'failed':
          return '失败'
        case 'skipped':
          return '跳过'
        default:
          return status || '未知'
      }
    }

    // 加载已订阅文档列表
    const loadSubscribedDocuments = async () => {
      if (!subscribedForm.app_id) return
      
      loadingSubscribed.value = true
      subscribedDocuments.value = []
      
      try {
        // 获取已订阅文档列表（API现在返回完整的文档信息，包括编辑时间和AI知识库更新时间）
        const response = await axios.get('/api/v1/documents/subscribed', {
          params: { app_id: subscribedForm.app_id }
        })
        
        if (response.data.code === 0 && response.data.data && response.data.data.items) {
          // 添加UI状态标志并设置文档列表
          subscribedDocuments.value = response.data.data.items.map(doc => ({
            ...doc,
            unsubscribing: false,
            syncing: false
          }));
        } else {
          ElMessage.error(response.data.msg || '获取已订阅文档列表失败')
        }
      } catch (error) {
        console.error('获取已订阅文档列表失败:', error)
        ElMessage.error('获取已订阅文档列表失败，请查看控制台获取详细错误信息')
      } finally {
        loadingSubscribed.value = false
      }
    }
    
    // 格式化日期时间
    const formatDateTime = (dateString) => {
      if (!dateString) return '未记录';
      const date = new Date(dateString);
      return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
    }
    
    // 获取同步状态类型
    const getSyncStatusType = (doc) => {
      if (!doc.obj_edit_time) return 'info';
      if (!doc.aichat_update_time) return 'danger';
      
      const editTime = new Date(doc.obj_edit_time);
      const updateTime = new Date(doc.aichat_update_time);
      
      return editTime > updateTime ? 'warning' : 'success';
    }
    
    // 获取同步状态文本
    const getSyncStatusText = (doc) => {
      if (!doc.obj_edit_time) return '未记录编辑';
      if (!doc.aichat_update_time) return '未同步';
      
      const editTime = new Date(doc.obj_edit_time);
      const updateTime = new Date(doc.aichat_update_time);
      
      return editTime > updateTime ? '需要同步' : '已同步';
    }
    
    // 取消订阅单个文档
    const handleUnsubscribeDocument = async (doc) => {
      try {
        await ElMessageBox.confirm(
          `确定要取消订阅文档 "${doc.title || doc.file_token}" 吗？`,
          '取消订阅确认',
          {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            type: 'warning'
          }
        );
        
        // 设置取消订阅中状态
        doc.unsubscribing = true;
        
        const response = await axios.post('/api/v1/documents/unsubscribe', {
          app_id: subscribedForm.app_id,
          file_token: doc.file_token,
          file_type: doc.file_type
        });
        
        if (response.data.code === 0) {
          ElMessage.success('取消订阅成功');
          // 重新加载文档列表
          loadSubscribedDocuments();
        } else {
          ElMessage.error(`取消订阅失败: ${response.data.msg || '未知错误'}`);
          doc.unsubscribing = false;
        }
      } catch (error) {
        if (error !== 'cancel') {
          console.error('取消订阅文档失败:', error);
          ElMessage.error('取消订阅文档失败，请查看控制台获取详细错误信息');
          doc.unsubscribing = false;
        }
      }
    }

    // 手动同步文档到AI知识库
    const handleSyncDocument = async (doc) => {
      try {
        // 设置同步中状态
        doc.syncing = true;
        
        const response = await axios.post('/api/v1/documents/sync-to-aichat', {
          app_id: subscribedForm.app_id,
          file_token: doc.file_token,
          file_type: doc.file_type
        });
        
        if (response.data.code === 0) {
          ElMessage.success(`文档"${doc.title || doc.file_token}"同步成功`);
          // 重新加载文档列表以获取最新数据
          await loadSubscribedDocuments();
        } else {
          ElMessage.error(`同步失败: ${response.data.msg || '未知错误'}`);
        }
      } catch (error) {
        console.error('同步文档失败:', error);
        ElMessage.error('同步文档失败，请查看控制台获取详细错误信息');
      } finally {
        doc.syncing = false;
      }
    }

    onMounted(() => {
      getAppList()
    })

    return {
      activeTab,
      subscribeFormRef,
      batchFormRef,
      appList,
      spacesList,
      subscribing,
      unsubscribing,
      spacesLoading,
      batchSubscribing,
      batchResult,
      subscribeForm,
      batchForm,
      subscribedForm,
      subscribedDocuments,
      loadingSubscribed,
      rules,
      batchRules,
      Refresh,
      handleSubscribe,
      handleUnsubscribe,
      loadSpaces,
      handleBatchSubscribe,
      loadSubscribedDocuments,
      formatDateTime,
      getSyncStatusType,
      getSyncStatusText,
      handleUnsubscribeDocument,
      handleSyncDocument,
      getResultDescription,
      getStatusType,
      getStatusText
    }
  }
}
</script>

<style scoped>
.document-container {
  padding: 20px;
}

.doc-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.doc-info-content {
  padding: 10px;
}

.doc-tips {
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

.batch-result {
  margin-top: 20px;
}

.result-details {
  margin-top: 15px;
}

h4 {
  margin-bottom: 10px;
}

.header-controls {
  display: flex;
  align-items: center;
}

.no-data {
  padding: 40px 0;
}

.token-suffix {
  color: #909399;
  font-size: 12px;
  margin-left: 8px;
  font-weight: normal;
}
</style> 