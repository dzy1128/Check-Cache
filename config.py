from pydantic_settings import BaseSettings
from typing import List
import os

class Settings(BaseSettings):
    # 服务器配置
    host: str = "0.0.0.0"
    port: int = 8000
    
    # 服务器列表
    servers: List[str] = ["http://27.148.182.150:8188", "http://27.148.182.149:8188", "http://27.148.182.148:8188", "http://27.148.182.147:8188", 
                          "http://27.148.182.146:8188", "http://27.148.182.145:8188", "http://27.148.182.144:8188"]
    
    # 工作流文件路径
    workflow_path: str = "缓存模型.json"
    
    # 检查间隔（秒）
    check_interval_seconds: int = 30
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()