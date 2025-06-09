<template>
  <el-container class="layout-container">
    <el-aside width="200px">
      <el-menu
        router
        default-active="/"
        class="el-menu-vertical"
      >
        <el-menu-item index="/">
          <el-icon><HomeFilled /></el-icon>
          <span>首页</span>
        </el-menu-item>
        <el-menu-item index="/apps">
          <el-icon><Apps /></el-icon>
          <span>应用管理</span>
        </el-menu-item>
        <el-menu-item index="/wiki-spaces">
          <el-icon><Collection /></el-icon>
          <span>知识空间</span>
        </el-menu-item>
        <el-menu-item index="/callbacks">
          <el-icon><Bell /></el-icon>
          <span>回调管理</span>
        </el-menu-item>
        <el-menu-item index="/document-subscribe">
          <el-icon><Document /></el-icon>
          <span>文档订阅</span>
        </el-menu-item>
        <el-menu-item index="/logs">
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
  Connection,
  Bell,
  Notebook
} from '@element-plus/icons-vue'
</script>

<style scoped>
.layout-container {
  height: 100vh;
}

.el-aside {
  background-color: #304156;
}

.el-menu {
  border-right: none;
}

.el-header {
  background-color: #fff;
  border-bottom: 1px solid #dcdfe6;
  display: flex;
  align-items: center;
}

.el-menu-vertical {
  height: 100%;
}
</style> 