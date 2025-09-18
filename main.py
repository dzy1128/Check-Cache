from fastapi import FastAPI, BackgroundTasks
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
        logging.StreamHandler(),
        logging.FileHandler("cache_checker.log")
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

# 执行工作流
async def execute_workflow(server_url: str):
    """执行缓存模型工作流"""
    workflow_data = load_workflow()
    if not workflow_data:
        logger.error("无法执行工作流，工作流数据为空")
        return False
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            url = f"{server_url}/api/queue"
            response = await client.post(url, json={"prompt": workflow_data})
            if response.status_code == 200:
                logger.info(f"成功提交工作流到服务器: {server_url}")
                return True
            else:
                logger.error(f"提交工作流失败: {response.status_code}, {response.text}")
                return False
    except Exception as e:
        logger.error(f"执行工作流异常: {e}")
        return False

# 检查并执行工作流的主函数
async def check_and_execute(server_url: str):
    """检查缓存状态并在需要时执行工作流"""
    logger.info(f"检查服务器缓存状态: {server_url}")
    cache_loaded = await check_cache_status(server_url)
    
    if not cache_loaded:
        logger.info(f"服务器缓存未加载，开始执行缓存工作流: {server_url}")
        success = await execute_workflow(server_url)
        if success:
            logger.info(f"成功执行缓存工作流: {server_url}")
        else:
            logger.error(f"执行缓存工作流失败: {server_url}")
    else:
        logger.info(f"服务器缓存已加载，无需执行工作流: {server_url}")

# 定时任务，检查所有服务器
async def scheduled_check():
    """定时检查所有服务器的缓存状态"""
    for server in settings.servers:
        await check_and_execute(server)

@app.on_event("startup")
async def startup_event():
    """应用启动时执行的事件"""
    # 添加定时任务，按照配置的间隔检查服务器
    scheduler.add_job(scheduled_check, 'interval', minutes=settings.check_interval_minutes)
    scheduler.start()
    logger.info("缓存检查定时任务已启动")
    
    # 应用启动时立即执行一次检查
    asyncio.create_task(scheduled_check())

@app.get("/")
async def root():
    """API根路径"""
    return {"message": "ComfyUI Cache Checker API"}

@app.get("/status")
async def status():
    """获取所有服务器的状态"""
    results = []
    for server in settings.servers:
        cache_loaded = await check_cache_status(server)
        results.append({
            "server": server,
            "cache_loaded": cache_loaded
        })
    return {"servers": results}

@app.post("/check/{server_index}")
async def check_server(server_index: int, background_tasks: BackgroundTasks):
    """手动触发检查特定服务器"""
    if server_index < 0 or server_index >= len(settings.servers):
        return {"error": "服务器索引无效"}
    
    server_url = settings.servers[server_index]
    background_tasks.add_task(check_and_execute, server_url)
    return {"message": f"已触发对服务器 {server_url} 的检查"}

@app.post("/check/all")
async def check_all(background_tasks: BackgroundTasks):
    """手动触发检查所有服务器"""
    background_tasks.add_task(scheduled_check)
    return {"message": "已触发对所有服务器的检查"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=True)