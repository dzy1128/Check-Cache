#!/usr/bin/env python3
"""
最终测试 - 验证所有修复
"""

import asyncio
from main import check_and_execute, execute_workflow

async def final_test():
    """最终测试"""
    
    print("=" * 80)
    print("最终测试 - 验证修复")
    print("=" * 80)
    
    servers = [
        "http://192.168.207.210:8188",
        "http://192.168.207.210:8288",
        "http://192.168.207.210:8388",
        "http://192.168.207.210:8488"
    ]
    
    print("\n方案1: 测试check_and_execute（正常流程）")
    print("-" * 80)
    for server in servers[:2]:  # 只测试前两个
        print(f"\n测试: {server}")
        await check_and_execute(server)
    
    print("\n\n方案2: 强制执行工作流（确保能发送请求到ComfyUI）")
    print("-" * 80)
    server = "http://192.168.207.210:8488"
    print(f"强制执行: {server}")
    success, message = await execute_workflow(server)
    print(f"✓ 执行结果: {success}")
    print(f"✓ 消息: {message}")
    
    if success:
        print("\n✅ 工作流可以成功执行，ComfyUI已收到请求！")
    else:
        print("\n❌ 执行失败")

if __name__ == "__main__":
    asyncio.run(final_test())

