import speech_recognition as sr
import openai
import os
from dotenv import load_dotenv
import pygame
import time
import json
import logging
import sys
import sounddevice as sd
import numpy as np
from io import BytesIO
import wave
from mcp_controller import MCPController
from typing import List, Dict, Any, Generator

# 環境変数の読み込み
load_dotenv(verbose=True)

# ロガーの設定
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('voice_chat.log')
    ]
)
logger = logging.getLogger('voice_chat_ai')

# OpenAI APIキーを環境変数から取得
openai.api_key = os.getenv('OPENAI_API_KEY')

# MCPコントローラーのインスタンスを作成
mcp = MCPController()

# グローバル変数の追加（ファイルの先頭付近に追加）
is_speaking = False

def stream_audio_data(audio_data: bytes, sample_rate: int = 24000):
    """音声データをリアルタイムでストリーミング再生"""
    global is_speaking
    is_speaking = True
    
    try:
        # BytesIOを使用してバイトデータをwavファイルとして読み込む
        with wave.open(BytesIO(audio_data), 'rb') as wf:
            # WAVファイルのパラメータを取得
            channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            rate = wf.getframerate()
            
            # 全データを一度に読み込み
            audio_data = wf.readframes(wf.getnframes())
            
            # データ型を設定
            if sampwidth == 2:
                dtype = np.int16
            elif sampwidth == 4:
                dtype = np.int32
            else:
                raise ValueError(f"サポートされていないサンプル幅です: {sampwidth}")
            
            # バイトデータをnumpy配列に変換
            samples = np.frombuffer(audio_data, dtype=dtype)
            
            # 正規化（-1.0から1.0の範囲に）
            if dtype == np.int16:
                samples = samples.astype(np.float32) / 32768.0
            elif dtype == np.int32:
                samples = samples.astype(np.float32) / 2147483648.0
            
            # チャンネル数に応じて整形
            if channels == 2:
                samples = samples.reshape(-1, 2)
            else:
                samples = samples.reshape(-1, 1)
            
            # ブロックサイズの設定
            block_size = int(rate * 0.05)  # 50msブロック
            
            # コールバック関数
            current_frame = [0]  # ミュータブルな参照用
            
            def callback(outdata, frames, time, status):
                if status:
                    logger.warning(f'ストリーミングステータス: {status}')
                
                start = current_frame[0]
                end = start + frames
                
                if start >= len(samples):
                    raise sd.CallbackStop()
                
                if end > len(samples):
                    outdata[:len(samples)-start] = samples[start:]
                    outdata[len(samples)-start:] = 0
                    raise sd.CallbackStop()
                else:
                    outdata[:] = samples[start:end]
                
                current_frame[0] = end
            
            # ストリームを開始
            with sd.OutputStream(
                channels=channels,
                dtype=np.float32,
                samplerate=rate,
                blocksize=block_size,
                callback=callback
            ) as stream:
                while stream.active and current_frame[0] < len(samples) and is_speaking:
                    sd.sleep(100)
                    
    except Exception as e:
        logger.error(f"音声ストリーミングエラー: {str(e)}", exc_info=True)
    finally:
        is_speaking = False

def speak_text(text: str):
    """テキストを音声に変換して再生する"""
    try:
        # 一時ファイルのパス
        output_file = "response.mp3"
        
        # OpenAI TTS APIを使用して音声を生成
        client = openai.OpenAI()
        response = client.audio.speech.create(
            model="tts-1",
            voice="nova",
            input=text,
            speed=1
        )
        
        # 音声ファイルを保存
        response.stream_to_file(output_file)
        
        # 音声を再生
        pygame.mixer.init()
        pygame.mixer.music.load(output_file)
        pygame.mixer.music.play()
        
        # 再生が終わるまで待機
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)
            
        # クリーンアップ
        pygame.mixer.quit()
        os.remove(output_file)
        
    except Exception as e:
        logger.error(f"音声出力エラー: {str(e)}", exc_info=True)

def get_command_keywords() -> List[str]:
    """MCPサーバーからコマンドキーワードを取得"""
    try:
        status = mcp.get_status()
        logger.debug(f"MCPステータス: {status}")
        
        if status.get("status") == "success" and "commands" in status.get("data", {}):
            commands_data = status["data"]["commands"]
            keywords = []
            
            # コマンド情報から基本キーワードを抽出
            for command_name, command_info in commands_data.items():
                logger.debug(f"処理中のコマンド: {command_name}")
                keywords.append(command_name)
                
                # 例文からもキーワードを抽出
                if "examples" in command_info:
                    for example in command_info["examples"]:
                        # 「〜して」「〜て」を除去し、キーワードを抽出
                        base_example = example.replace('して', '').replace('て', '').strip()
                        # スペースで分割して主要な名詞を抽出
                        words = base_example.split()
                        for word in words:
                            if word not in ['を', 'の', 'は', 'が']:
                                keywords.append(word)
            
            logger.debug(f"抽出された基本キーワード: {keywords}")
            
            # ひらがな変換も追加
            additional_keywords = []
            for keyword in keywords:
                if 'ヘルプ' in keyword:
                    additional_keywords.append('へるぷ')
                elif 'メモリ' in keyword:
                    additional_keywords.append('めもり')
                elif keyword.upper() == 'CPU':
                    additional_keywords.append('cpu')
                elif '天気' in keyword:
                    additional_keywords.append('てんき')
            
            final_keywords = list(set(keywords + additional_keywords))
            logger.debug(f"最終的なキーワードリスト: {final_keywords}")
            return final_keywords
            
    except Exception as e:
        logger.error(f"キーワード取得エラー: {str(e)}", exc_info=True)
        return []

def format_response_for_human(result: Dict[str, Any]) -> str:
    """MCPサーバーからのレスポンスを人間が理解しやすい形式に変換"""
    try:
        # レスポンスをJSON文字列に変換
        result_json = json.dumps(result, ensure_ascii=False)
        
        # デバッグログとして元のメッセージを出力
        logger.info(f"元のレスポンス: {result_json}")
        
        # LLMを使用してレスポンスを人間が読みやすい形式に変換
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": """あなたはシステム情報を人間が理解しやすい日本語に変換するアシスタントです。
                以下のガイドラインに従ってください：
                1. 数値は小数点以下1桁までに丸めて表示
                2. パーセンテージは整数で表示
                3. 重要な情報のみを簡潔に説明
                4. 単位は適切に付加（GB, MB, %など）
                5. 推測や追加の情報は含めない
                6. 入力されたJSONデータに含まれる情報のみを使用
                7. 重複した情報は1回だけ表示
                8. ファイル一覧を表示する場合：
                   - lsコマンドの出力をそのまま表示
                   - 前置きは「現在のディレクトリの内容：」のみとする
                9. 時刻情報を表示する場合：
                   - 日付、時刻、曜日を自然な日本語で表示
                   - 「ただいまの時刻は」と前置きを付ける。「このシステムの情報は」などの前置きは不要
                   - タイムゾーンは特に指定がない限り省略
                10. 天気情報を表示する場合：
                    - 都市名、天気、気温、湿度を自然な日本語で表示
                    - 「〜の天気は」という形式で表示"""},
                {"role": "user", "content": f"以下のシステム情報を簡潔な日本語で説明してください：\n{result_json}"}
            ],
            temperature=0.3  # より決定論的な応答を生成
        )
        formatted_response = response.choices[0].message.content
        logger.debug(f"変換後のレスポンス: {formatted_response}")
        return formatted_response
    except Exception as e:
        logger.error(f"レスポンス変換エラー: {str(e)}", exc_info=True)
        # エラーの場合は、元のデータを整形して返す
        try:
            return json.dumps(result, ensure_ascii=False, indent=2)
        except:
            return str(result)

def natural_to_mcp_request(text: str) -> Dict[str, Any]:
    """自然文をMCPリクエストに変換"""
    try:
        # サーバーから利用可能なコマンド情報を取得
        status = mcp.get_status()
        if status.get("status") != "success" or "commands" not in status.get("data", {}):
            logger.error("コマンド情報の取得に失敗しました")
            return {
                "command": "error",
                "parameters": {
                    "message": "コマンド情報を取得できませんでした"
                }
            }
            
        commands_data = status["data"]["commands"]
        
        # コマンド情報をプロンプトに変換
        commands_info = []
        for cmd_name, cmd_info in commands_data.items():
            cmd_desc = {
                "name": cmd_name,
                "description": cmd_info["description"],
                "examples": cmd_info["examples"],
                "parameters": cmd_info["parameters"]
            }
            commands_info.append(cmd_desc)
            
        commands_json = json.dumps(commands_info, ensure_ascii=False, indent=2)
        
        # OpenAI APIを使用してリクエストを解析
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": f"""あなたは自然な日本語をMCPリクエストに変換するパーサーです。
以下のコマンドが利用可能です：

{commands_json}

ユーザーの入力を解析し、以下の形式でJSONレスポンスのみを返してください：

{{
    "command": "コマンド名",
    "parameters": {{
        "パラメータ名": "値"
    }}
}}

例：
入力：「東京の天気を教えて」
{{
    "command": "weather",
    "parameters": {{
        "city": "東京"
    }}
}}

入力：「CPUの使用率を確認して」
{{
    "command": "system",
    "parameters": {{
        "type": "cpu"
    }}
}}

入力：「ヘルプを表示して」または「コマンド一覧を見せて」
{{
    "command": "help",
    "parameters": {{}}
}}

パラメータが不要な場合は空のオブジェクトを返してください。
コマンドが認識できない場合は以下を返してください：
{{
    "command": "unknown",
    "parameters": {{
        "message": "コマンドを認識できませんでした"
    }}
}}"""},
                {"role": "user", "content": text}
            ],
            temperature=0.1  # より決定論的な応答を生成
        )
        
        # レスポンスをパース
        result = response.choices[0].message.content.strip()
        logger.debug(f"OpenAI解析結果: {result}")
        
        try:
            # 余分なテキストを削除してJSONのみを抽出
            json_start = result.find("{")
            json_end = result.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = result[json_start:json_end]
                parsed = json.loads(json_str)
                
                # 必須フィールドの存在確認
                if "command" not in parsed or "parameters" not in parsed:
                    logger.error("必須フィールドが欠落しています")
                    return {
                        "command": "error",
                        "parameters": {
                            "message": "レスポンスの形式が不正です"
                        }
                    }
                
                return parsed
            else:
                logger.error("JSONが見つかりませんでした")
                return {
                    "command": "error",
                    "parameters": {
                        "message": "レスポンスの解析に失敗しました"
                    }
                }
                
        except json.JSONDecodeError as e:
            logger.error(f"JSONパースエラー: {str(e)}")
            return {
                "command": "error",
                "parameters": {
                    "message": "レスポンスの解析に失敗しました"
                }
            }
            
    except Exception as e:
        logger.error(f"MCP変換エラー: {str(e)}", exc_info=True)
        return {
            "command": "error",
            "parameters": {
                "message": "内部エラーが発生しました"
            }
        }

def process_command(text: str) -> str:
    """音声コマンドを処理する"""
    try:
        # 自然文をMCPリクエストに変換
        request = natural_to_mcp_request(text)
        if not request:
            return "申し訳ありません。コマンドの解析に失敗しました。"
            
        logger.debug(f"変換されたリクエスト: {request}")
        
        # エラー処理
        if request["command"] == "error":
            return f"申し訳ありません。{request['parameters'].get('message', '不明なエラーが発生しました')}"
            
        # 不明なコマンド
        if request["command"] == "unknown":
            return "申し訳ありません。そのコマンドは認識できませんでした。「ヘルプを表示して」と言うと、利用可能なコマンドの一覧を表示します。"
            
        # ヘルプコマンド
        if request["command"] == "help":
            display_available_commands()
            return "上記が利用可能なコマンドの一覧です。"
        
        # コマンドを実行
        try:
            if request["command"] == "weather":
                city = request["parameters"].get("city", "東京")
                result = mcp.get_weather(city)
            elif request["command"] == "system":
                info_type = request["parameters"].get("type", "cpu")
                result = mcp.get_system_info(info_type)
            elif request["command"] == "time":
                result = mcp.get_time()
            else:
                logger.error(f"不明なコマンド: {request['command']}")
                return "申し訳ありません。そのコマンドは現在サポートされていません。"
                
            # エラーチェック
            if result.get("status") == "error":
                error_msg = result.get("error", {}).get("message", "不明なエラーが発生しました")
                return f"申し訳ありません。{error_msg}"
                
            # レスポンスを人間が理解しやすい形式に変換
            return format_response_for_human(result)
            
        except Exception as e:
            logger.error(f"コマンド実行エラー: {str(e)}", exc_info=True)
            return f"申し訳ありません。コマンドの実行中にエラーが発生しました: {str(e)}"
        
    except Exception as e:
        logger.error(f"コマンド処理エラー: {str(e)}", exc_info=True)
        return "申し訳ありません。予期せぬエラーが発生しました。"

def listen_to_speech():
    """マイクから音声を取得し、テキストに変換する"""
    recognizer = sr.Recognizer()
    
    with sr.Microphone() as source:
        print("聞き取っています...")
        audio = recognizer.listen(source)
        
    try:
        # Whisperを使用して音声認識（新しいAPI形式）
        audio_file = "temp_audio.wav"
        with open(audio_file, "wb") as f:
            f.write(audio.get_wav_data())
        
        client = openai.OpenAI()
        with open(audio_file, "rb") as audio_file:
            response = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
        
        os.remove("temp_audio.wav")
        return response.text
    except Exception as e:
        print(f"エラーが発生しました: {str(e)}")
        return None

def get_ai_response(text: str) -> str:
    """ChatGPTを使用して応答を生成する"""
    try:
        # Function callingのための関数定義
        functions = [
            {
                "name": "get_weather",
                "description": "指定された都市の天気情報を取得します",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                            "description": "天気を知りたい都市名（例：東京、大阪）"
                        }
                    },
                    "required": ["city"]
                }
            },
            {
                "name": "get_system_info",
                "description": "システム情報を取得します",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "info_type": {
                            "type": "string",
                            "description": "取得したい情報のタイプ（cpu, memory, files）",
                            "enum": ["cpu", "memory", "files"]
                        }
                    },
                    "required": ["info_type"]
                }
            },
            {
                "name": "get_time",
                "description": "現在の時刻情報を取得します",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        ]

        # OpenAI APIを呼び出し
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "あなたは音声対話AIアシスタントです。ユーザーの要求に応じて適切な情報を提供してください。"},
                {"role": "user", "content": text}
            ],
            functions=functions,
            function_call="auto"
        )

        # レスポンスを処理
        message = response.choices[0].message

        # 関数呼び出しが必要な場合
        if message.function_call:
            # 関数名と引数を取得
            function_name = message.function_call.name
            function_args = json.loads(message.function_call.arguments)

            # 関数を実行
            if function_name == "get_weather":
                result = mcp.get_weather(function_args.get("city", "東京"))
            elif function_name == "get_system_info":
                result = mcp.get_system_info(function_args.get("info_type"))
            elif function_name == "get_time":
                result = mcp.get_time()
            else:
                return "申し訳ありません。その操作は実行できません。"

            # 関数の結果を使って2回目の応答を生成
            second_response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "あなたは音声対話AIアシスタントです。ユーザーの要求に応じて適切な情報を提供してください。"},
                    {"role": "user", "content": text},
                    {"role": "function", "name": function_name, "content": json.dumps(result, ensure_ascii=False)},
                ],
                functions=functions
            )

            # 最終的な応答を返す
            return second_response.choices[0].message.content
        
        # 関数呼び出しが不要な場合は直接応答を返す
        return message.content

    except Exception as e:
        logger.error(f"エラーが発生しました: {str(e)}", exc_info=True)
        return "申し訳ありません。エラーが発生しました。"

def display_available_commands():
    """利用可能なコマンドを表示"""
    try:
        status = mcp.get_status()
        if status.get("status") == "success" and "commands" in status.get("data", {}):
            commands_data = status["data"]["commands"]
            print("\n利用可能なコマンド：")
            for command_name, command_info in commands_data.items():
                print(f"\n■ {command_info['description']}")
                if "examples" in command_info:
                    print("  例：")
                    for example in command_info["examples"]:
                        print(f"    - 「{example}」")
                if "parameters" in command_info and command_info["parameters"]:
                    print("  パラメータ：")
                    for param_name, param_desc in command_info["parameters"].items():
                        print(f"    - {param_name}: {param_desc}")
            print()
        else:
            print("\n警告: コマンド情報を取得できませんでした。\n")
            logger.error(f"コマンド情報取得失敗: {status}")
    except Exception as e:
        print(f"\n警告: MCPサーバーに接続できません: {str(e)}\n")
        logger.error(f"MCPサーバー接続エラー: {str(e)}", exc_info=True)

def main():
    """メイン関数"""
    try:
        print("音声対話AIを起動しました。")
        
        # 起動時にMCPサーバーから利用可能なコマンドを取得して表示
        display_available_commands()
        
        print("会話を始めてください。")
        print("終了するには Ctrl+C を押してください。")
        
        while True:
            try:
                # 音声入力を受け取る
                user_input = listen_to_speech()
                if user_input:
                    print(f"あなた: {user_input}")
                    
                    # AI応答を生成
                    ai_response = get_ai_response(user_input)
                    if ai_response:
                        print(f"AI: {ai_response}")
                        speak_text(ai_response)
                
            except KeyboardInterrupt:
                print("\nプログラムを終了します。")
                break
            except Exception as e:
                logger.error(f"エラーが発生しました: {str(e)}", exc_info=True)
                continue
    
    except Exception as e:
        logger.error(f"予期せぬエラーが発生しました: {str(e)}", exc_info=True)
    finally:
        # クリーンアップ処理
        try:
            pygame.quit()
        except:
            pass
        sys.exit(0)

if __name__ == "__main__":
    main() 