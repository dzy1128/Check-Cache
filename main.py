from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.responses import HTMLResponse
import httpx
import json
import time
import asyncio
import logging
from pydantic import BaseModel
from typing import List, Dict, Any
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import settings

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("cache_checker")

app = FastAPI(title="ComfyUI Cache Checker")
scheduler = AsyncIOScheduler()

# 加载工作流JSON
def load_workflow():
    try:
        with open(settings.workflow_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"加载工作流失败: {e}")
        return None

# 检查缓存状态
async def check_cache_status(server_url: str) -> bool:
    """检查服务器缓存状态，如果缓存已加载返回True，否则返回False"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            url = f"{server_url}/inspire/cache/determine"
            response = await client.get(url)
            if response.status_code == 200:
                return "缓存已加载" in response.text
            else:
                logger.error(f"检查缓存状态失败: {response.status_code}")
                return False
    except Exception as e:
        logger.error(f"检查缓存状态异常: {e}")
        return False

# 获取队列状态
async def get_queue_status(server_url: str, client: httpx.AsyncClient):
    """获取当前队列状态"""
    try:
        url = f"{server_url}/api/queue"
        response = await client.get(url)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        logger.error(f"获取队列状态异常: {e}")
        return None

# 获取执行历史
async def get_execution_history(server_url: str, prompt_id: str, client: httpx.AsyncClient):
    """获取特定prompt的执行历史"""
    try:
        url = f"{server_url}/api/history/{prompt_id}"
        response = await client.get(url)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        logger.error(f"获取执行历史异常: {e}")
        return None

# 等待工作流执行完成
async def wait_for_workflow_completion(server_url: str, prompt_id: str, timeout: int = None):
    """等待工作流执行完成并返回执行结果"""
    if timeout is None:
        timeout = settings.workflow_timeout_seconds
        
    async with httpx.AsyncClient(timeout=10.0) as client:
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            # 检查队列状态
            queue_status = await get_queue_status(server_url, client)
            if queue_status:
                # 检查是否还在队列中
                running_tasks = queue_status.get("queue_running", [])
                pending_tasks = queue_status.get("queue_pending", [])
                
                # 检查我们的任务是否还在运行中或等待中
                is_running = any(task[1]["prompt"][0] == prompt_id for task in running_tasks)
                is_pending = any(task[1]["prompt"][0] == prompt_id for task in pending_tasks)
                
                if not is_running and not is_pending:
                    # 任务已完成，获取执行历史
                    history = await get_execution_history(server_url, prompt_id, client)
                    if history and prompt_id in history:
                        execution_info = history[prompt_id]
                        status = execution_info.get("status", {})
                        
                        if status.get("status_str") == "success":
                            logger.info(f"工作流执行成功: {server_url}, prompt_id: {prompt_id}")
                            return True, "执行成功"
                        else:
                            error_messages = []
                            # 获取详细错误信息
                            for node_id, node_info in execution_info.get("outputs", {}).items():
                                if "error" in node_info:
                                    error_info = node_info["error"]
                                    error_msg = f"节点 {node_id}: {error_info.get('message', '未知错误')}"
                                    if "traceback" in error_info:
                                        error_msg += f"\n详细信息: {error_info['traceback']}"
                                    error_messages.append(error_msg)
                            
                            if not error_messages:
                                error_messages.append(f"执行失败，状态: {status}")
                            
                            error_text = "\n".join(error_messages)
                            logger.error(f"工作流执行失败: {server_url}, prompt_id: {prompt_id}\n{error_text}")
                            return False, error_text
            
            # 等待一段时间后再检查
            await asyncio.sleep(2)
        
        # 超时
        logger.error(f"工作流执行超时: {server_url}, prompt_id: {prompt_id}")
        return False, f"执行超时 ({timeout}秒)"

# 执行工作流
async def execute_workflow(server_url: str):
    """执行缓存模型工作流并等待完成"""
    workflow_data = load_workflow()
    if not workflow_data:
        logger.error("无法执行工作流，工作流数据为空")
        return False, "工作流数据为空"
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            url = f"{server_url}/api/queue"
            response = await client.post(url, json={"prompt": workflow_data})
            
            if response.status_code == 200:
                result = response.json()
                prompt_id = result.get("prompt_id")
                
                if not prompt_id:
                    logger.error(f"提交工作流成功但未获取到prompt_id: {server_url}")
                    return False, "未获取到prompt_id"
                
                logger.info(f"成功提交工作流到服务器: {server_url}, prompt_id: {prompt_id}")
                
                # 等待工作流执行完成
                success, message = await wait_for_workflow_completion(server_url, prompt_id)
                return success, message
            else:
                error_msg = f"提交工作流失败: {response.status_code}, {response.text}"
                logger.error(error_msg)
                return False, error_msg
                
    except Exception as e:
        error_msg = f"执行工作流异常: {e}"
        logger.error(error_msg)
        return False, error_msg

# 检查并执行工作流的主函数
async def check_and_execute(server_url: str):
    """检查缓存状态并在需要时执行工作流"""
    logger.info(f"检查服务器缓存状态: {server_url}")
    cache_loaded = await check_cache_status(server_url)
    
    if not cache_loaded:
        logger.info(f"服务器缓存未加载，开始执行缓存工作流: {server_url}")
        success, message = await execute_workflow(server_url)
        if success:
            logger.info(f"成功执行缓存工作流: {server_url} - {message}")
        else:
            logger.error(f"执行缓存工作流失败: {server_url} - {message}")
    else:
        logger.info(f"服务器缓存已加载，无需执行工作流: {server_url}")

# 定时任务，检查所有服务器（并行）
async def scheduled_check():
    """定时检查所有服务器的缓存状态（并行执行）"""
    tasks = [check_and_execute(server) for server in settings.servers]
    await asyncio.gather(*tasks)

@app.on_event("startup")
async def startup_event():
    """应用启动时执行的事件"""
    # 添加定时任务，按照配置的间隔检查服务器
    scheduler.add_job(scheduled_check, 'interval', seconds=settings.check_interval_seconds)
    scheduler.start()
    logger.info("缓存检查定时任务已启动")
    
    # 应用启动时立即执行一次检查
    asyncio.create_task(scheduled_check())

@app.get("/")
async def root():
    """API根路径"""
    return {"message": "ComfyUI Cache Checker API"}

@app.get("/status", response_class=HTMLResponse)
async def status():
    """获取所有服务器的状态（并行检查）并显示HTML界面"""
    tasks = [check_cache_status(server) for server in settings.servers]
    cache_statuses = await asyncio.gather(*tasks)
    
    results = []
    for server, cache_loaded in zip(settings.servers, cache_statuses):
        results.append({
            "server": server,
            "cache_loaded": cache_loaded
        })
    
    # 生成HTML页面
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>ComfyUI Cache Checker Status</title>
        <meta charset="UTF-8">
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 20px;
                background-color: #f5f5f5;
            }}
            .container {{
                max-width: 800px;
                margin: 0 auto;
                background-color: white;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            h1 {{
                color: #333;
                text-align: center;
            }}
            .server-item {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 10px;
                margin: 10px 0;
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: #f9f9f9;
            }}
            .status {{
                padding: 5px 10px;
                border-radius: 4px;
                color: white;
                font-weight: bold;
            }}
            .status.loaded {{
                background-color: #28a745;
            }}
            .status.not-loaded {{
                background-color: #dc3545;
            }}
            .buttons {{
                text-align: center;
                margin: 20px 0;
            }}
            button {{
                background-color: #007bff;
                color: white;
                border: none;
                padding: 10px 20px;
                margin: 0 10px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 16px;
            }}
            button:hover {{
                background-color: #0056b3;
            }}
            .refresh-btn {{
                background-color: #28a745;
            }}
            .refresh-btn:hover {{
                background-color: #1e7e34;
            }}
            .info {{
                text-align: center;
                color: #666;
                margin: 10px 0;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>ComfyUI Cache Checker Status</h1>
            <div class="info">
                检查间隔: {settings.check_interval_seconds}秒 | 服务器数量: {len(settings.servers)}
            </div>
            
            <div class="buttons">
                <button onclick="startCheck()">立即开始缓存检测</button>
                <button class="refresh-btn" onclick="refreshStatus()">刷新状态</button>
            </div>
            
            <div class="servers">
    """
    
    for result in results:
        status_class = "loaded" if result["cache_loaded"] else "not-loaded"
        status_text = "缓存已加载" if result["cache_loaded"] else "缓存未加载"
        html_content += f"""
                <div class="server-item">
                    <span>{result["server"]}</span>
                    <span class="status {status_class}">{status_text}</span>
                </div>
        """
    
    html_content += """
            </div>
        </div>
        
        <script>
            function startCheck() {
                fetch('/check/all', {
                    method: 'POST'
                })
                .then(response => response.json())
                .then(data => {
                    alert('缓存检测已启动！');
                    setTimeout(() => {
                        window.location.reload();
                    }, 2000);
                })
                .catch(error => {
                    alert('启动检测失败: ' + error);
                });
            }
            
            function refreshStatus() {
                window.location.reload();
            }
            
            // 自动刷新页面（每30秒）
            setInterval(() => {
                window.location.reload();
            }, 30000);
        </script>
    </body>
    </html>
    """
    
    return html_content

@app.get("/api/status")
async def api_status():
    """获取所有服务器的状态（JSON格式）"""
    tasks = [check_cache_status(server) for server in settings.servers]
    cache_statuses = await asyncio.gather(*tasks)
    
    results = []
    for server, cache_loaded in zip(settings.servers, cache_statuses):
        results.append({
            "server": server,
            "cache_loaded": cache_loaded
        })
    return {"servers": results}

@app.post("/check/all")
async def check_all():
    """手动触发检查所有服务器"""
    # 创建异步任务来执行检查，不阻塞响应
    asyncio.create_task(scheduled_check())
    return {"message": "已触发对所有服务器的检查"}

@app.post("/check/{server_index}")
async def check_server(server_index: int, background_tasks: BackgroundTasks):
    """手动触发检查特定服务器"""
    if server_index < 0 or server_index >= len(settings.servers):
        return {"error": "服务器索引无效"}
    
    server_url = settings.servers[server_index]
    background_tasks.add_task(check_and_execute, server_url)
    return {"message": f"已触发对服务器 {server_url} 的检查"}

@app.post("/check/all/background")
async def check_all_background(background_tasks: BackgroundTasks):
    """使用后台任务检查所有服务器"""
    background_tasks.add_task(scheduled_check)
    return {"message": "已触发对所有服务器的后台检查"}

@app.post("/execute/{server_index}")
async def execute_server_workflow(server_index: int):
    """手动执行特定服务器的工作流并获取详细结果"""
    if server_index < 0 or server_index >= len(settings.servers):
        return {"error": "服务器索引无效"}
    
    server_url = settings.servers[server_index]
    success, message = await execute_workflow(server_url)
    
    return {
        "server": server_url,
        "success": success,
        "message": message,
        "timestamp": time.time()
    }

@app.get("/api/detailed_status")
async def detailed_status():
    """获取所有服务器的详细状态，包括缓存状态"""
    results = []
    
    for i, server in enumerate(settings.servers):
        cache_loaded = await check_cache_status(server)
        
        result = {
            "server_index": i,
            "server": server,
            "cache_loaded": cache_loaded,
            "status": "缓存已加载" if cache_loaded else "缓存未加载",
            "timestamp": time.time()
        }
        results.append(result)
    
    return {"servers": results, "total_servers": len(settings.servers)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=True)