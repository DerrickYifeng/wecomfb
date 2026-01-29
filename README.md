# 🏢 企业微信反馈收集系统 (WeCom Feedback)

一个简洁的企业微信群反馈收集系统，将用户反馈自动保存到 Databricks Unity Catalog。

## ✨ 特性

- 🤖 **企业微信 Webhook** - 通过企业微信机器人 Webhook 自动收集群内反馈
- 📊 **Unity Catalog 存储** - 数据保存到 Databricks Delta Lake
- 🔄 **实时同步** - 反馈即时保存到云端
- 📈 **可视化管理** - Streamlit 管理界面
- 🔌 **REST API** - 支持其他系统集成

## 🏗️ 架构

```
企业微信群 → 企业微信 Webhook → Databricks API → Unity Catalog
                                       ↓
                                 管理界面 (app.py)
```

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 到 `.env` 并填入你的配置：

```bash
# Unity Catalog 配置
STORAGE_BACKEND=uc
UC_CATALOG=dev
UC_SCHEMA=inner_feedback

# Databricks 连接
DATABRICKS_HOST=https://your-workspace.cloud.databricks.com/
DATABRICKS_TOKEN=your_databricks_token

# Webhook 配置
WEBHOOK_SECRET=your_webhook_secret
```

### 3. 初始化数据库表

```bash
python init_unity_catalog.py
```

这会在 Unity Catalog 中创建 `dev.inner_feedback.user_feedback` 表。

### 4. 配置企业微信 Webhook

1. 在企业微信管理后台创建群机器人
2. 获取 Webhook URL
3. 配置消息回调地址指向你的 API 服务

## 📝 使用方法

在企业微信群中 @机器人发送反馈：

```
@FeedbackBot 反馈: 系统在某功能页面会卡顿
@FeedbackBot bug: 登录按钮点击无反应
@FeedbackBot 建议: 希望增加批量操作功能
```

系统会：
1. 自动识别反馈类型（bug/建议/一般）
2. 保存到 Unity Catalog
3. 可选：通过 Webhook 回复确认消息

## 📊 数据表结构

```sql
CREATE TABLE dev.inner_feedback.user_feedback (
    feedback_id STRING NOT NULL,
    user_name STRING NOT NULL,
    user_id STRING,
    group_name STRING,
    group_id STRING,
    feedback_content STRING NOT NULL,
    feedback_type STRING,
    created_at TIMESTAMP NOT NULL,
    raw_message STRING,
    is_processed BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMP,
    notes STRING
) USING DELTA
```

## 🔧 本地开发

### 使用本地存储（无需 Databricks）

```bash
# 修改 .env
STORAGE_BACKEND=local
LOCAL_STORAGE_PATH=./data
```

### 启动 API 服务

```bash
cd databricks_app
python api_app.py
```

访问：http://localhost:8080

### 启动管理界面

```bash
cd databricks_app
streamlit run app.py
```

访问：http://localhost:8501

## 🚀 部署到 Databricks

### 1. 配置 Secrets

```bash
databricks secrets create-scope --scope feedback-scope

echo "https://your-workspace.cloud.databricks.com/" | \
  databricks secrets put --scope feedback-scope --key databricks-host

echo "your_token" | \
  databricks secrets put --scope feedback-scope --key databricks-token

echo "your_webhook_secret" | \
  databricks secrets put --scope feedback-scope --key webhook-secret
```

### 2. 部署 API 服务

```bash
databricks apps create \
  --name feedback-api \
  --source-code-path /Workspace/Users/your-email/feedback-api \
  --config-file databricks_app/databricks-api-app.yaml

databricks apps deploy feedback-api
```

### 3. 部署管理界面

```bash
databricks apps create \
  --name feedback-dashboard \
  --source-code-path /Workspace/Users/your-email/feedback-dashboard \
  --config-file databricks_app/databricks-app.yaml

databricks apps deploy feedback-dashboard
```

## 📊 查询数据

### 使用 SQL

```sql
-- 查看所有反馈
SELECT * FROM dev.inner_feedback.user_feedback
ORDER BY created_at DESC
LIMIT 10;

-- 统计反馈类型
SELECT feedback_type, COUNT(*) as count
FROM dev.inner_feedback.user_feedback
GROUP BY feedback_type;

-- 未处理的反馈
SELECT * FROM dev.inner_feedback.user_feedback
WHERE is_processed = FALSE
ORDER BY created_at DESC;
```

### 使用 Python

```python
from databricks.connect import DatabricksSession
import os
from dotenv import load_dotenv

load_dotenv()

spark = DatabricksSession.builder \
    .remote(
        host=os.getenv("DATABRICKS_HOST"),
        token=os.getenv("DATABRICKS_TOKEN")
    ) \
    .getOrCreate()

# 读取数据
df = spark.table("dev.inner_feedback.user_feedback")
df.show()

# 统计
df.groupBy("feedback_type").count().show()
```

## 🔌 API 接口

### 提交反馈

```bash
POST /api/feedback
Content-Type: application/json

{
  "user_name": "用户名称",
  "content": "反馈内容",
  "group_name": "群名称",
  "user_id": "用户ID"
}
```

### 批量提交

```bash
POST /api/feedback/batch
Content-Type: application/json

{
  "feedbacks": [
    {"user_name": "用户1", "content": "反馈1"},
    {"user_name": "用户2", "content": "反馈2"}
  ]
}
```

### 企业微信 Webhook 回调

```bash
POST /api/wecom/callback
Content-Type: application/json

# 企业微信会自动发送消息到此端点
```

### 获取统计

```bash
GET /api/stats
```

## 📁 项目结构

```
wecom_feedback/
├── init_unity_catalog.py      # 初始化数据库表
├── requirements.txt           # Python 依赖
├── .env.example              # 环境变量示例
├── databricks_app/           # Databricks 应用
│   ├── api_app.py           # REST API 服务 (含企业微信 Webhook)
│   ├── app.py               # Streamlit 管理界面
│   ├── requirements.txt     # 应用依赖
│   ├── databricks-api-app.yaml      # API 部署配置
│   └── databricks-app.yaml          # 管理界面部署配置
└── test_api.py              # API 测试脚本
```

## 🔍 故障排查

### 连接失败

```bash
❌ Failed to connect to Databricks
```

**解决方案**：
1. 检查 `DATABRICKS_HOST` 格式（需要 `https://` 和结尾的 `/`）
2. 检查 `DATABRICKS_TOKEN` 是否有效
3. 确保网络可以访问 Databricks

### 表不存在

```bash
❌ Table not found
```

**解决方案**：
```bash
python init_unity_catalog.py
```

### 权限错误

```bash
❌ Permission denied
```

**解决方案**：
1. 确保 token 有 Unity Catalog 访问权限
2. 检查 catalog 和 schema 的权限设置

### 企业微信 Webhook 验证失败

```bash
❌ Webhook signature mismatch
```

**解决方案**：
1. 检查 `WEBHOOK_SECRET` 是否与企业微信后台配置一致
2. 确保 API 服务可以被企业微信服务器访问

## 📚 技术栈

- **数据存储**: Databricks Unity Catalog (Delta Lake)
- **数据连接**: Databricks Connect (PySpark)
- **API 服务**: Flask + Gunicorn
- **管理界面**: Streamlit
- **消息接收**: 企业微信 Webhook

## 📄 许可证

MIT License

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！
