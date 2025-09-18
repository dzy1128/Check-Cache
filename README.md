# ComfyUI 缓存检查器

这是一个用于自动检查和执行ComfyUI工作流的工具，主要用于确保多台服务器上的模型缓存已正确加载。

## 功能

- 自动检查多台ComfyUI服务器的缓存状态
- 当发现缓存未加载时，自动执行缓存模型工作流
- 支持定时检查和手动触发检查
- 提供API接口查看服务器状态

## 安装

1. 安装依赖：

```bash
pip install -r requirements.txt
```

2. 配置服务器列表：

编辑`config.py`文件或创建`.env`文件设置服务器列表和其他配置。

3. 准备工作流文件：

将用于加载缓存的工作流保存为JSON格式，放在`workflow.json`文件中。

## 使用方法

启动服务：

```bash
python main.py
```

### API接口

- `GET /`: 检查API是否正常运行
- `GET /status`: 获取所有服务器的缓存状态
- `POST /check/{server_index}`: 手动触发检查特定服务器
- `POST /check/all`: 手动触发检查所有服务器

## 配置选项

- `host`: 服务器监听地址，默认为"0.0.0.0"
- `port`: 服务器监听端口，默认为8000
- `servers`: ComfyUI服务器列表
- `workflow_path`: 工作流JSON文件路径
- `check_interval_minutes`: 自动检查间隔（分钟），默认为30分钟