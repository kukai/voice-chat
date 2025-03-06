import requests
import json
import os
from typing import Dict, Any, Optional

class MCPController:
    def __init__(self):
        # ローカルサーバーのURLを使用
        self.base_url = "http://localhost:8000"
        self.api_key = "your-local-api-key"  # MCPサーバーで設定したものと同じキーを使用
        
        # 主要都市の日本語-英語マッピング
        self.city_mapping = {
            "東京": "Tokyo",
            "大阪": "Osaka",
            "京都": "Kyoto",
            "名古屋": "Nagoya",
            "横浜": "Yokohama",
            "神戸": "Kobe",
            "福岡": "Fukuoka",
            "札幌": "Sapporo",
            "仙台": "Sendai",
            "広島": "Hiroshima",
            "那覇": "Naha",
            "沖縄": "Naha"  # 沖縄の場合は那覇を返す
        }
        
    def _make_request(self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """APIリクエストを実行"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method == "GET":
                response = requests.get(url, headers=headers)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=data)
            
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"MCPリクエストエラー: {str(e)}")
            return {
                "status": "error",
                "error": {
                    "message": str(e),
                    "code": "REQUEST_ERROR"
                }
            }

    def get_weather(self, city: str = "東京") -> Dict[str, Any]:
        """天気情報を取得"""
        # 都市名を英語に変換
        en_city = self.city_mapping.get(city, "Tokyo")  # デフォルトは東京
        return self._make_request("GET", f"/weather/{en_city}")

    def get_system_info(self, info_type: str) -> Dict[str, Any]:
        """システム情報を取得"""
        return self._make_request("GET", f"/system/{info_type}")

    def get_time(self) -> Dict[str, Any]:
        """現在時刻を取得"""
        return self._make_request("GET", "/time")

    def get_health(self) -> Dict[str, Any]:
        """サーバーの健康状態を取得"""
        return self._make_request("GET", "/health")

    def get_commands(self) -> Dict[str, Any]:
        """利用可能なコマンド情報を取得"""
        return self._make_request("GET", "/commands")

    def get_status(self) -> Dict[str, Any]:
        """サーバーの状態とコマンド情報を取得"""
        try:
            # ヘルスチェック
            health = self.get_health()
            if health.get("status") != "success":
                return health
            
            # コマンド情報の取得
            commands = self.get_commands()
            if commands.get("status") != "success":
                return commands
            
            # 両方の情報を結合
            return {
                "status": "success",
                "data": {
                    "health": health.get("data", {}),
                    "commands": commands.get("data", {}).get("commands", {})
                }
            }
        except Exception as e:
            return {
                "status": "error",
                "error": {
                    "message": str(e),
                    "code": "STATUS_FETCH_ERROR"
                }
            } 