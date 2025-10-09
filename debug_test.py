#!/usr/bin/env python3
"""
调试测试 - 看看程序实际执行了什么
"""

import asyncio
import httpx
from main import check_cache_status, check_and_execute, execute_workflow

async def debug_test():
    """详细的调试测试"""
    
    test_server = "http://192.168.207.210:8288"
    
    print("=" * 80)
    print("调试测试")
    print("=" * 80)
    
    # 1. 检查缓存状态
    print("\n1. 检查缓存状态:")
    print("-" * 40)
    cache_loaded, auto_executing = await check_cache_status(test_server)
    print(f"缓存已加载: {cache_loaded}")
    print(f"自动执行中: {auto_executing}")
    
    # 2. 查看check_and_execute的行为
    print("\n2. 执行 check_and_execute:")
    print("-" * 40)
    await check_and_execute(test_server)
    
    # 3. 强制执行工作流（绕过检查）
    print("\n3. 强制执行工作流（绕过检查）:")
    print("-" * 40)
    success, message = await execute_workflow(test_server)
    print(f"执行结果: {success}")
    print(f"消息: {message}")
    
    # 4. 检查ComfyUI队列
    print("\n4. 检查ComfyUI队列状态:")
    print("-" * 40)
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{test_server}/api/queue")
        queue = response.json()
        print(f"运行中任务: {len(queue.get('queue_running', []))}")
        print(f"等待中任务: {len(queue.get('queue_pending', []))}")
        
        if queue.get('queue_running'):
            print("运行中的任务:")
            for task in queue['queue_running']:
                print(f"  - {task}")

if __name__ == "__main__":
    asyncio.run(debug_test())

