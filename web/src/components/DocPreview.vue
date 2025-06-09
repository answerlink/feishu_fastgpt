<template>
  <el-dialog
    v-model="visible"
    :title="title"
    width="80%"
    :fullscreen="fullscreen"
    :before-close="handleClose"
    class="doc-preview-dialog"
    top="5vh"
  >
    <div class="doc-preview-toolbar">
      <el-button :icon="FullScreen" circle @click="toggleFullscreen" :title="fullscreen ? '退出全屏' : '全屏'"></el-button>
      <el-button :icon="Download" circle @click="downloadMarkdown" :title="'下载Markdown'"></el-button>
    </div>
    
    <div class="doc-preview-container" v-loading="loading">
      <div class="markdown-body" v-html="renderedContent"></div>
    </div>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { marked } from 'marked'
import hljs from 'highlight.js'
import 'highlight.js/styles/github.css'
import axios from 'axios'
import { ElMessage } from 'element-plus'
import { FullScreen, Download } from '@element-plus/icons-vue'

// 配置marked
marked.setOptions({
  highlight: function(code, lang) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(code, { language: lang }).value
      } catch (e) {
        console.error(e)
      }
    }
    return hljs.highlightAuto(code).value
  },
  breaks: true,
  gfm: true
})

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  docToken: {
    type: String,
    default: ''
  },
  docType: {
    type: String,
    default: 'docx'
  },
  title: {
    type: String,
    default: '文档预览'
  },
  appId: {
    type: String,
    required: true
  }
})

const emit = defineEmits(['update:modelValue', 'close'])

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const content = ref('')
const loading = ref(false)
const fullscreen = ref(false)

const renderedContent = computed(() => {
  if (!content.value) return ''
  try {
    return marked(content.value)
  } catch (e) {
    console.error('Markdown渲染失败', e)
    return `<p class="error">Markdown渲染失败: ${e.message}</p>`
  }
})

const fetchDocContent = async () => {
  if (!props.docToken || !props.appId) return
  
  loading.value = true
  try {
    const response = await axios.get(`/api/v1/wiki/docs/${props.docToken}/content`, {
      params: {
        doc_type: props.docType,
        content_type: 'markdown',
        lang: 'zh',
        app_id: props.appId
      }
    })
    
    if (response.data.code === 0 && response.data.data.content) {
      content.value = response.data.data.content
    } else {
      ElMessage.error(response.data.msg || '获取文档内容失败')
      content.value = '# 获取文档内容失败'
    }
  } catch (error) {
    console.error('获取文档内容失败:', error)
    ElMessage.error('获取文档内容失败')
    content.value = '# 获取文档内容失败'
  } finally {
    loading.value = false
  }
}

const handleClose = () => {
  visible.value = false
  emit('close')
}

const toggleFullscreen = () => {
  fullscreen.value = !fullscreen.value
}

const downloadMarkdown = () => {
  if (!content.value) {
    ElMessage.warning('没有可下载的内容')
    return
  }
  
  const blob = new Blob([content.value], { type: 'text/markdown' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${props.title || '文档'}.md`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

watch(() => props.docToken, (newVal) => {
  if (newVal && visible.value) {
    fetchDocContent()
  }
})

watch(visible, (newVal) => {
  if (newVal && props.docToken) {
    fetchDocContent()
  } else {
    content.value = ''
  }
})
</script>

<style>
.doc-preview-dialog .el-dialog__body {
  padding: 0;
  position: relative;
}

.doc-preview-toolbar {
  position: absolute;
  top: 10px;
  right: 20px;
  z-index: 10;
  background: rgba(255, 255, 255, 0.7);
  padding: 5px;
  border-radius: 4px;
}

.doc-preview-container {
  height: 70vh;
  overflow-y: auto;
  padding: 20px;
}

/* GitHub风格的Markdown样式 */
.markdown-body {
  box-sizing: border-box;
  min-width: 200px;
  max-width: 980px;
  margin: 0 auto;
  padding: 45px;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif, "Apple Color Emoji", "Segoe UI Emoji";
  font-size: 16px;
  line-height: 1.5;
  word-wrap: break-word;
}

.markdown-body h1,
.markdown-body h2,
.markdown-body h3,
.markdown-body h4,
.markdown-body h5,
.markdown-body h6 {
  margin-top: 24px;
  margin-bottom: 16px;
  font-weight: 600;
  line-height: 1.25;
}

.markdown-body h1 {
  padding-bottom: 0.3em;
  font-size: 2em;
  border-bottom: 1px solid #eaecef;
}

.markdown-body h2 {
  padding-bottom: 0.3em;
  font-size: 1.5em;
  border-bottom: 1px solid #eaecef;
}

.markdown-body p,
.markdown-body blockquote,
.markdown-body ul,
.markdown-body ol,
.markdown-body dl,
.markdown-body table,
.markdown-body pre {
  margin-top: 0;
  margin-bottom: 16px;
}

.markdown-body blockquote {
  padding: 0 1em;
  color: #6a737d;
  border-left: 0.25em solid #dfe2e5;
}

.markdown-body code {
  padding: 0.2em 0.4em;
  margin: 0;
  font-size: 85%;
  background-color: rgba(27, 31, 35, 0.05);
  border-radius: 3px;
}

.markdown-body pre {
  padding: 16px;
  overflow: auto;
  font-size: 85%;
  line-height: 1.45;
  background-color: #f6f8fa;
  border-radius: 3px;
}

.markdown-body pre code {
  padding: 0;
  margin: 0;
  font-size: 100%;
  background-color: transparent;
  border: 0;
}

.markdown-body img {
  max-width: 100%;
  box-sizing: content-box;
}

.markdown-body table {
  display: block;
  width: 100%;
  overflow: auto;
  border-spacing: 0;
  border-collapse: collapse;
}

.markdown-body table th,
.markdown-body table td {
  padding: 6px 13px;
  border: 1px solid #dfe2e5;
}

.markdown-body table tr {
  background-color: #fff;
  border-top: 1px solid #c6cbd1;
}

.markdown-body table tr:nth-child(2n) {
  background-color: #f6f8fa;
}
</style> 