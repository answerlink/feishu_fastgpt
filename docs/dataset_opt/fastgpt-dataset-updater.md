# FastGPT知识库描述更新工具

## 功能概述

FastGPT知识库描述更新工具用于批量扫描飞书app下的所有知识库，并根据知识库中的文件列表自动生成和更新知识库描述。

### 主要功能

- **递归扫描**：递归遍历所有可访问的文件夹和知识库
- **智能描述生成**：基于知识库中的文件列表，使用LLM生成合适的描述
- **灵活更新策略**：支持跳过已有描述或全量覆盖更新两种模式
- **预览模式**：支持干运行（dry run）模式，只分析不实际更新
- **详细统计**：提供完整的执行统计和错误报告

## 配置要求

### 必需配置

1. **FastGPT配置**
   ```json
   {
     "fastgpt_url": "http://127.0.0.1:3000",
     "fastgpt_key": "fastgpt-xxxxxxxxx"
   }
   ```

2. **摘要LLM配置**
   ```json
   {
     "summary_llm_api_url": "https://api.siliconflow.cn/v1/chat/completions",
     "summary_llm_api_key": "sk-xxxxxxxxx", 
     "summary_llm_model": "Qwen/Qwen3-32B"
   }
   ```

3. **数据集同步开关**
   ```json
   {
     "dataset_sync": true
   }
   ```

## API接口

### 1. 更新知识库描述

**接口地址**：`POST /api/v1/fastgpt-dataset-updater/update-dataset-descriptions`

**请求参数**：
```json
{
  "app_id": "cli_a0163xxx",       // 应用ID
  "skip_existing": true,          // 是否跳过已有描述的知识库
  "dry_run": false               // 是否仅预览，不实际更新
}
```

**参数说明**：
- `app_id`：飞书应用ID，必填
- `skip_existing`：更新策略，可选，默认`true`
  - `true`：如果知识库已有描述就跳过
  - `false`：全量覆盖更新所有知识库的描述
- `dry_run`：运行模式，可选，默认`false`
  - `true`：只扫描和分析，不实际更新（预览模式）
  - `false`：实际执行更新操作

**响应示例**：
```json
{
  "code": 200,
  "message": "更新完成",
  "data": {
    "scanned_folders": 5,          // 扫描的文件夹数量
    "scanned_datasets": 12,        // 扫描的知识库数量
    "existing_descriptions": 3,     // 已有描述的知识库数量
    "skipped_datasets": 3,         // 跳过的知识库数量
    "updated_datasets": 7,         // 成功更新的知识库数量
    "failed_updates": 2,           // 更新失败的知识库数量
    "errors": ["错误信息1", "错误信息2"]
  }
}
```

### 2. 查询配置状态

**接口地址**：`GET /api/v1/fastgpt-dataset-updater/description-update-status/{app_id}`

**响应示例**：
```json
{
  "code": 200,
  "message": "查询成功",
  "data": {
    "app_id": "cli_a0163xxx",
    "app_name": "测试应用",
    "has_fastgpt_config": true,      // 是否配置了FastGPT
    "has_summary_llm_config": true,  // 是否配置了摘要LLM
    "fastgpt_url": "http://127.0.0.1:3000",
    "summary_llm_model": "Qwen/Qwen3-32B",
    "dataset_sync_enabled": true,    // 是否启用数据集同步
    "ready_for_update": true         // 是否准备就绪可以执行更新
  }
}
```

## 使用示例

### 1. 预览模式（推荐首次使用）

```bash
curl -X POST "http://localhost:8000/api/v1/fastgpt-dataset-updater/update-dataset-descriptions" \
  -H "Content-Type: application/json" \
  -d '{
    "app_id": "cli_a0163xxx",
    "skip_existing": true,
    "dry_run": true
  }'
```

### 2. 跳过已有描述模式

```bash
curl -X POST "http://localhost:8000/api/v1/fastgpt-dataset-updater/update-dataset-descriptions" \
  -H "Content-Type: application/json" \
  -d '{
    "app_id": "cli_a0163xxx",
    "skip_existing": true,
    "dry_run": false
  }'
```

### 3. 全量覆盖更新模式

```bash
curl -X POST "http://localhost:8000/api/v1/fastgpt-dataset-updater/update-dataset-descriptions" \
  -H "Content-Type: application/json" \
  -d '{
    "app_id": "cli_a0163xxx",
    "skip_existing": false,
    "dry_run": false
  }'
```

### 4. 查询配置状态

```bash
curl "http://localhost:8000/api/v1/fastgpt-dataset-updater/description-update-status/cli_a0163xxx"
```

## 工作流程

1. **配置验证**：检查FastGPT和摘要LLM配置是否完整
2. **递归扫描**：从根目录开始递归遍历所有文件夹和知识库
3. **策略判断**：根据`skip_existing`参数决定是否跳过已有描述的知识库
4. **文件分析**：获取知识库中的所有文件列表
5. **描述生成**：调用LLM根据文件列表生成描述
6. **批量更新**：更新知识库的描述信息
7. **统计报告**：生成详细的执行统计和错误报告

## 注意事项

1. **配置检查**：使用前请确保所有必需配置都已正确设置
2. **预览模式**：首次使用建议开启`dry_run`模式预览效果
3. **LLM调用**：会消耗LLM API调用次数，请注意成本控制
4. **网络超时**：大量知识库更新可能需要较长时间，请耐心等待
5. **错误处理**：单个知识库更新失败不会影响其他知识库的处理

## 错误排查

### 常见错误

1. **"未找到应用配置"**
   - 检查`app_id`是否正确
   - 确认应用配置已加载

2. **"未配置FastGPT相关参数"**
   - 检查`fastgpt_url`和`fastgpt_key`配置
   - 确认FastGPT服务可访问

3. **"未配置摘要LLM相关参数"**
   - 检查摘要LLM所有配置项
   - 确认LLM API服务可访问

4. **"LLM未生成有效描述"**
   - 检查LLM API是否正常
   - 检查提示词是否合适
   - 确认网络连接稳定

### 日志查看

系统会记录详细的执行日志，可通过以下方式查看：
- 控制台输出
- 日志文件：`logs/app_{app_name}_{app_id}.log`

## 最佳实践

1. **分批处理**：对于大量知识库，建议分批次处理
2. **定期更新**：建议定期执行更新以保持描述的时效性
3. **描述优化**：根据实际效果调整LLM提示词
4. **监控成本**：关注LLM API调用次数和成本
5. **备份重要数据**：重要知识库建议先备份再更新 