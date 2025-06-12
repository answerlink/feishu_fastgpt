<template>
  <el-container class="layout-container">
    <el-aside width="200px">
      <div class="menu-header">
        <h2>飞书Plus</h2>
        <p>多应用管理系统</p>
      </div>
      <el-menu
        router
        default-active="/home"
        class="el-menu-vertical"
      >
        <el-menu-item index="/home">
          <el-icon><HomeFilled /></el-icon>
          <span>首页</span>
        </el-menu-item>
        <el-menu-item index="/apps">
          <el-icon><Setting /></el-icon>
          <span>应用管理</span>
        </el-menu-item>
        <el-menu-item index="/wiki-spaces">
          <el-icon><Collection /></el-icon>
          <span>知识空间</span>
        </el-menu-item>
        <el-menu-item index="/document-subscribe">
          <el-icon><Document /></el-icon>
          <span>文档订阅</span>
        </el-menu-item>
        <el-menu-item index="/log-viewer">
          <el-icon><Notebook /></el-icon>
          <span>系统日志</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header>
        <h2>飞书Plus管理系统</h2>
      </el-header>
      <el-main>
        <router-view></router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  HomeFilled,
  Setting,
  Document,
  Collection,
  Notebook,
  Monitor
} from '@element-plus/icons-vue'
</script>

<style scoped>
.layout-container {
  height: 100vh;
}

.el-aside {
  background-color: #f5f7fa;
  border-right: 1px solid #e4e7ed;
}

.menu-header {
  padding: 20px 16px;
  text-align: center;
  background-color: #ffffff;
  border-bottom: 1px solid #e4e7ed;
  margin-bottom: 10px;
}

.menu-header h2 {
  margin: 0 0 5px 0;
  color: #303133;
  font-size: 18px;
  font-weight: 600;
}

.menu-header p {
  margin: 0;
  color: #606266;
  font-size: 12px;
}

.el-menu {
  border-right: none;
  background-color: transparent;
}

.el-menu-item {
  color: #303133;
  margin: 2px 8px;
  border-radius: 6px;
}

.el-menu-item:hover {
  background-color: #ecf5ff;
  color: #409eff;
}

.el-menu-item.is-active {
  background-color: #409eff;
  color: #ffffff;
}

.el-menu-item .el-icon {
  color: inherit;
}

.el-header {
  background-color: #fff;
  border-bottom: 1px solid #dcdfe6;
  display: flex;
  align-items: center;
}

/* 移除这个高度限制，避免不必要的滚动条 */
/* .el-menu-vertical {
  height: calc(100% - 80px);
} */
</style> 