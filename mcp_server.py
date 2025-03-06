from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import uvicorn
import subprocess
import os
from typing import Dict, Any, List, Optional
from datetime import datetime
from pyowm import OWM
from pyowm.utils.config import get_default_config
import json
from dotenv import load_dotenv
import sys
import pykakasi
import logging

# 環境変数の読み込み
load_dotenv(verbose=True)

# 環境変数の確認
api_key = os.getenv('OPENWEATHER_API_KEY')
if not api_key:
    print("警告: OPENWEATHER_API_KEYが設定されていません")
    sys.exit(1)

app = FastAPI(title="MCP Local Server")
security = HTTPBearer()

# APIキーを環境変数から取得
API_KEY = os.getenv('MCP_API_KEY', "your-local-api-key")

class WeatherRequest(BaseModel):
    city: str = "Tokyo"

class SystemInfoRequest(BaseModel):
    info_type: str

def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> bool:
    if credentials.credentials != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True

class MCPServer:
    def __init__(self):
        # OpenWeatherMap APIの設定
        config_dict = get_default_config()
        config_dict['language'] = 'ja'
        self.owm = OWM(os.getenv('OPENWEATHER_API_KEY'), config_dict)
        self.mgr = self.owm.weather_manager()
        
        # 日本語-ローマ字変換器の初期化
        self.kks = pykakasi.Kakasi()

        # ロガーの設定
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('mcp_server.log')
            ]
        )
        self.logger = logging.getLogger('mcp_server')

    def get_weather(self, city: str = "Tokyo") -> Dict[str, Any]:
        """指定された都市の天気情報を取得"""
        try:
            print(f"天気情報の取得を開始: 都市名 = {city}")
            
            try:
                # 天気情報を直接取得
                weather = self.mgr.weather_at_place(f"{city},JP").weather
                print(f"天気情報取得成功: {weather}")
                
                # 天気情報を整形
                result = {
                    "status": "success",
                    "data": {
                        "city": city,
                        "weather": {
                            "description": weather.detailed_status,
                            "temperature": {
                                "current": weather.temperature('celsius').get('temp'),
                                "max": weather.temperature('celsius').get('temp_max', None),
                                "min": weather.temperature('celsius').get('temp_min', None)
                            },
                            "humidity": weather.humidity,
                            "wind_speed": weather.wind().get('speed'),
                            "clouds": weather.clouds
                        }
                    }
                }
                print(f"天気情報の取得成功: {json.dumps(result, ensure_ascii=False)}")
                return result
                
            except Exception as api_error:
                print(f"API呼び出しエラー: {str(api_error)}")
                raise ValueError(f"天気情報の取得に失敗しました: {str(api_error)}")
            
        except Exception as e:
            error_msg = f"天気情報の取得に失敗: {str(e)}"
            print(error_msg)
            return {
                "status": "error",
                "error": {
                    "message": error_msg,
                    "code": "WEATHER_FETCH_ERROR"
                }
            }

    def get_system_info(self, info_type: str) -> Dict[str, Any]:
        """システム情報を取得"""
        try:
            if info_type == "cpu":
                cpu_info = subprocess.check_output(["top", "-l", "1", "-n", "0"]).decode()
                return {
                    "status": "success",
                    "data": {
                        "type": "cpu",
                        "info": cpu_info
                    }
                }
            elif info_type == "memory":
                memory_info = subprocess.check_output(["vm_stat"]).decode()
                return {
                    "status": "success",
                    "data": {
                        "type": "memory",
                        "info": memory_info
                    }
                }
            elif info_type == "files":
                file_list = subprocess.check_output(["ls"]).decode()
                return {
                    "status": "success",
                    "data": {
                        "type": "files",
                        "info": file_list
                    }
                }
            else:
                return {
                    "status": "error",
                    "error": {
                        "message": f"不明な情報タイプ: {info_type}",
                        "code": "INVALID_INFO_TYPE"
                    }
                }
        except Exception as e:
            return {
                "status": "error",
                "error": {
                    "message": str(e),
                    "code": "SYSTEM_INFO_ERROR"
                }
            }

    def get_current_time(self) -> Dict[str, Any]:
        """現在時刻の情報を取得"""
        try:
            now = datetime.now()
            weekday_ja = ["月", "火", "水", "木", "金", "土", "日"][now.weekday()]
            
            return {
                "status": "success",
                "data": {
                    "datetime": {
                        "date": now.strftime("%Y-%m-%d"),
                        "time": now.strftime("%H:%M:%S"),
                        "weekday": weekday_ja,
                        "timestamp": now.timestamp(),
                        "timezone": "JST"
                    }
                }
            }
        except Exception as e:
            return {
                "status": "error",
                "error": {
                    "message": str(e),
                    "code": "TIME_FETCH_ERROR"
                }
            }

mcp_server = MCPServer()

@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """ヘルスチェックエンドポイント"""
    try:
        # 基本的なシステムチェック
        system_status = "healthy"
        
        # メモリ使用状況の確認
        memory_info = subprocess.check_output(["vm_stat"]).decode()
        if "Pages free" not in memory_info:
            system_status = "degraded"
            
        # CPU負荷の確認
        cpu_info = subprocess.check_output(["top", "-l", "1", "-n", "0"]).decode()
        if "CPU usage" not in cpu_info:
            system_status = "degraded"
            
        return {
            "status": "success",
            "data": {
                "status": system_status,
                "version": "1.0.0",
                "timestamp": datetime.now().isoformat(),
                "checks": {
                    "memory": "Pages free" in memory_info,
                    "cpu": "CPU usage" in cpu_info
                }
            }
        }
    except Exception as e:
        mcp_server.logger.error(f"ヘルスチェックエラー: {str(e)}")
        return {
            "status": "error",
            "error": {
                "message": "ヘルスチェックに失敗しました",
                "code": "HEALTH_CHECK_ERROR"
            }
        }

@app.get("/commands")
async def get_commands(
    authorized: bool = Depends(verify_token)
) -> Dict[str, Any]:
    """利用可能なコマンド情報を取得"""
    return {
        "status": "success",
        "data": {
            "commands": {
                "weather": {
                    "description": "天気情報を取得",
                    "examples": ["東京の天気を教えて", "大阪の天気は？", "天気を教えて"],
                    "parameters": {
                        "city": "都市名（デフォルト: 東京）"
                    }
                },
                "system": {
                    "description": "システム情報を取得",
                    "examples": ["CPUの使用率を確認して", "メモリの使用状況を教えて","ファイルを見せて"],
                    "parameters": {
                        "type": "情報タイプ（cpu, memory, files）"
                    }
                },
                "time": {
                    "description": "現在時刻を取得",
                    "examples": ["時刻を教えて", "今何時？"],
                    "parameters": {}
                }
            }
        }
    }

@app.get("/weather/{city}")
async def get_weather(
    city: str,
    authorized: bool = Depends(verify_token)
) -> Dict[str, Any]:
    """天気情報を取得"""
    return mcp_server.get_weather(city)

@app.get("/system/{info_type}")
async def get_system_info(
    info_type: str,
    authorized: bool = Depends(verify_token)
) -> Dict[str, Any]:
    """システム情報を取得"""
    return mcp_server.get_system_info(info_type)

@app.get("/time")
async def get_time(
    authorized: bool = Depends(verify_token)
) -> Dict[str, Any]:
    """現在時刻を取得"""
    return mcp_server.get_current_time()

def start_server():
    """サーバーを起動"""
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    start_server() 