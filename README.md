# 音声対話AI アシスタント

このアプリケーションは、音声認識とOpenAI APIを使用して、システム情報の取得や管理を行うための音声対話インターフェースを提供します。

## 機能

- 音声コマンドによるシステム情報の取得
- リアルタイムの音声応答（OpenAI TTS APIを使用）
- システムリソース（CPU、メモリ）の監視
- ファイル一覧の表示
- 現在時刻の表示
- 天気情報の取得（OpenWeatherMap APIを使用）
- 自然な日本語での対話（GPT-3.5を使用）

## 必要要件

- Python 3.9以上
- マイク（音声入力用）
- スピーカー（音声出力用）
- OpenAI APIキー（GPT-3.5、Whisper、TTSに使用）
- OpenWeatherMap APIキー（天気情報の取得に使用）

## セットアップ

1. リポジトリをクローン
```bash
git clone [リポジトリURL]
cd voice-chat
```

2. 仮想環境を作成して有効化
```bash
python -m venv venv
# Windowsの場合
venv\Scripts\activate
# macOS/Linuxの場合
source venv/bin/activate
```

3. 必要なパッケージをインストール
```bash
pip install -r requirements.txt
```

4. 環境変数の設定
`.env`ファイルを作成し、以下の内容を設定：
```
OPENAI_API_KEY=your_api_key_here
OPENWEATHER_API_KEY=your_openweather_api_key_here
MCP_API_KEY=your-local-api-key
```

## 使用方法

1. MCPサーバーを起動
```bash
python mcp_server.py
```

2. 別のターミナルで音声対話AIを起動
```bash
python voice_chat_ai.py
```

3. 利用可能なコマンド例
- 「ヘルプを表示して」「コマンド一覧を見せて」
- 「CPUの使用率を確認して」
- 「メモリの使用状況を教えて」
- 「ファイルを見せて」
- 「時刻を教えて」「今何時？」
- 「天気を教えて」（東京の天気を表示）
- 「[都市名]の天気を教えて」（指定した都市の天気を表示）
  - 対応都市：東京、大阪、京都、名古屋、横浜、神戸、福岡、札幌、仙台、広島、那覇

## 注意事項

- OpenAI APIの使用料金
  - GPT-3.5 Turbo: $0.002/1K tokens
  - Whisper: $0.006/分
  - TTS: $0.015/1K文字
- OpenWeatherMap APIは無料枠あり（60回/分まで）
- 音声認識とTTSにはインターネット接続が必要
- マイクへのアクセス権限が必要

## トラブルシューティング

1. マイクが認識されない場合
   - システムの音声入力設定を確認
   - マイクのアクセス権限を確認

2. 音声が出力されない場合
   - システムの音声出力設定を確認
   - スピーカーの接続を確認
   - `pygame`の初期化状態を確認

3. APIエラーが発生する場合
   - 各APIキーが正しく設定されているか確認
   - インターネット接続を確認
   - レート制限に達していないか確認

4. MCPサーバーに接続できない場合
   - サーバーが起動しているか確認（デフォルト: http://localhost:8000）
   - `MCP_API_KEY`が正しく設定されているか確認

## ライセンス

MIT 