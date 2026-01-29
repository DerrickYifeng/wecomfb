# 📁 项目结构

```
wecom_feedback/
├── init_unity_catalog.py            # 初始化 Unity Catalog 表
├── test_api.py                      # API 测试脚本
├── requirements.txt                 # Python 依赖
├── .env.example                     # 环境变量示例
├── deploy_universal_api.sh          # Databricks 部署脚本
├── README.md                        # 项目文档
│
└── databricks_app/                  # Databricks 应用
    ├── api_app.py                   # REST API 服务 (含企业微信 Webhook)
    ├── app.py                       # Streamlit 管理界面
    ├── requirements.txt             # 应用依赖
    ├── databricks-api-app.yaml      # API 部署配置
    └── databricks-app.yaml          # 管理界面部署配置
```

## 核心文件说明

### 本地运行

- **init_unity_catalog.py** - 初始化数据库表脚本
- **test_api.py** - API 测试工具
- **.env** - 环境变量配置（需要自己创建）

### Databricks 应用

- **api_app.py** - Flask REST API，接收反馈并保存到 Unity Catalog，支持企业微信 Webhook 回调
- **app.py** - Streamlit 管理界面，查看和管理反馈
- **databricks-api-app.yaml** - API 服务的 Databricks Apps 配置
- **databricks-app.yaml** - 管理界面的 Databricks Apps 配置

## 数据流

```
企业微信群消息
    ↓ Webhook
api_app.py (Databricks)
    ↓ PySpark
Unity Catalog (Delta Lake)
    ↑ PySpark
app.py (Databricks)
    ↓
管理界面
```

## 配置文件

### .env
```bash
# Unity Catalog
STORAGE_BACKEND=uc
UC_CATALOG=dev
UC_SCHEMA=inner_feedback

# Databricks
DATABRICKS_HOST=https://your-workspace.cloud.databricks.com/
DATABRICKS_TOKEN=your_token

# Webhook
API_ENDPOINT=https://your-api-url/api/feedback
WEBHOOK_SECRET=your_secret
```

### databricks-api-app.yaml
API 服务的部署配置，包含：
- 启动命令（gunicorn）
- 环境变量
- Secrets 引用

### databricks-app.yaml
管理界面的部署配置，包含：
- 启动命令（streamlit）
- 环境变量
- Secrets 引用

## 依赖管理

### requirements.txt (根目录)
本地运行所需依赖：
- databricks-connect - Databricks 连接
- python-dotenv - 环境变量
- loguru - 日志
- requests - HTTP 客户端

### databricks_app/requirements.txt
Databricks 应用所需依赖：
- flask + gunicorn - API 服务
- streamlit - 管理界面
- databricks-connect - 数据连接
- pyspark - 数据处理
- plotly - 数据可视化
