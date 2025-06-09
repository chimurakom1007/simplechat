import json
import os
import urllib.request
import urllib.error
import boto3
import re
from botocore.exceptions import ClientError

# 環境変数から外部APIのURLを取得
EXTERNAL_API_URL = os.environ.get("EXTERNAL_API_URL", "https://ebb7-34-56-215-37.ngrok-free.app/generate")

# Lambdaコンテキストからリージョンを抽出（未使用だけど一応残す）
def extract_region_from_arn(arn):
    match = re.search(r'arn:aws:lambda:([^:]+):', arn)
    if match:
        return match.group(1)
    return "us-east-1"

# グローバル変数としてクライアントを初期化（初期値）
bedrock_client = None

def lambda_handler(event, context):
    try:
        # コンテキストから実行リージョンを取得し、クライアントを初期化
        global bedrock_client
        if bedrock_client is None:
            region = extract_region_from_arn(context.invoked_function_arn)
            bedrock_client = boto3.client('bedrock-runtime', region_name=region)
            print(f"Initialized Bedrock client in region: {region}")
            
        print("Received event:", json.dumps(event))

        # ユーザー情報（オプション、今回は使わないけどログだけ）
        user_info = None
        if 'requestContext' in event and 'authorizer' in event['requestContext']:
            user_info = event['requestContext']['authorizer']['claims']
            print(f"Authenticated user: {user_info.get('email') or user_info.get('cognito:username')}")

        # リクエストボディを取得
        body = json.loads(event['body'])
        message = body['message']
        conversation_history = body.get('conversationHistory', [])

        print("Processing message:", message)
        #今回は直接messageを渡す
        #generete側のスキーマに合わせる
        request_payload = {
            "prompt": message,
            "max_new_tokens": 512,
            "do_sample": True,
            "temperature": 0.7,
            "top_p": 0.9
        }

        # 外部APIへのPOSTリクエスト準備
        payload_bytes = json.dumps(request_payload).encode('utf-8')
        headers = {
            'Content-Type': 'application/json'
        }
        #標準ライブラリを使用
        req = urllib.request.Request(
            url=EXTERNAL_API_URL,
            data=payload_bytes,
            headers=headers,
            method='POST'
        )

        # APIリクエスト送信
        try:
            with urllib.request.urlopen(req) as response:
                response_data = response.read()
                response_body = json.loads(response_data)
        except urllib.error.HTTPError as e:
            error_message = e.read().decode()
            print(f"HTTP error: {e.code} - {error_message}")
            raise Exception(f"External API HTTP error {e.code}: {error_message}")
        except urllib.error.URLError as e:
            print(f"URL error: {e.reason}")
            raise Exception(f"External API URL error: {e.reason}")

        print("External API response:", response_body)

        # 外部APIのレスポンスからアシスタントの応答を取得
        if 'generated_text' not in response_body:
            raise Exception("Missing 'generated_text' in external API response")
        
        assistant_response = response_body['generated_text'].replace("\\n", "\n")
        response_time = response_body['response_time']
        formatted_time = f'{response_time:.3f}'

        if not assistant_response:
            raise Exception("No 'response' field found in external API response")

        # 正常レスポンスを返却
        
        # 成功レスポンスの返却
        # "body"の部分は各辞書の値は全体でstrではいけないのでjson.dumpsで全体をjson形式のstrにする
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                "Access-Control-Allow-Methods": "OPTIONS,POST"
            },
            "body": json.dumps({
                "success": True,
                "response": assistant_response,  # ←文字列そのまま
                "response_time": formatted_time
            }) 
        }
        
    except Exception as error:
        print("Error:", str(error))
        
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                "Access-Control-Allow-Methods": "OPTIONS,POST"
            },
            "body": json.dumps({
                "success": False,
                "error": str(error)
            })
        }