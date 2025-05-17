import json
import os
import re # re はリージョン抽出以外では不要かも
import urllib.request as urllib_request
import urllib.error

# FastAPIのエンドポイントURL (ngrokで公開されるURL)
# このURLはFastAPIを起動するたびに変わる可能性があります。
FASTAPI_BASE_URL = "https://71d8-34-86-134-14.ngrok-free.app/" # ★★★ 必ず最新のngrok URLに更新 ★★★
FASTAPI_GENERATE_PATH = "/generate"

def lambda_handler(event, context):
    try:
        print("Received event:", json.dumps(event))

        body = json.loads(event['body'])
        user_message = body['message']
        conversation_history = body.get('conversationHistory', [])

        # Bedrock (Titan Text Lite) のパラメータをFastAPIに渡
        # FastAPI側のBedrockProxyRequestのフィールド名に合わせる
        max_token_count = body.get('maxTokenCount', 512)
        temperature = body.get('temperature', 0.7)
        top_p = body.get('topP', 0.9)
        # stop_sequences = body.get('stopSequences', []) # 必要なら

        print(f"Processing message: '{user_message}' to be sent to FastAPI (Bedrock Proxy)")
        full_fastapi_url = FASTAPI_BASE_URL + FASTAPI_GENERATE_PATH
        print(f"Target FastAPI (Bedrock Proxy) endpoint: {full_fastapi_url}")

        # 会話履歴と現在のメッセージを結合してプロンプトを作成
        prompt_parts = []
        for entry in conversation_history:
            role = entry.get('role', 'User').capitalize()
            content = entry.get('content', '')
            prompt_parts.append(f"{role}: {content}")
        prompt_parts.append(f"User: {user_message}")
        prompt_parts.append("Bot:") # Titanモデルへの指示として
        final_prompt = "\n".join(prompt_parts)

        # FastAPI (Bedrockプロキシ) へのリクエストペイロード
        api_request_payload = {
            "prompt": final_prompt,
            "maxTokenCount": max_token_count,
            "temperature": temperature,
            "topP": top_p
            # "stopSequences": stop_sequences # 必要なら
        }
        print("Calling FastAPI (Bedrock Proxy) with payload:", json.dumps(api_request_payload))

        req = urllib_request.Request(
            full_fastapi_url,
            data=json.dumps(api_request_payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )

        assistant_response_text = ""
        with urllib_request.urlopen(req) as http_response:
            response_body_str = http_response.read().decode('utf-8')
            response_data_from_fastapi = json.loads(response_body_str)
            print("FastAPI (Bedrock Proxy) response data:", json.dumps(response_data_from_fastapi, default=str))

            if "generated_text" not in response_data_from_fastapi:
                raise Exception(f"FastAPI (Bedrock Proxy) からの応答に 'generated_text' が含まれていません。応答: {response_body_str}")
            assistant_response_text = response_data_from_fastapi["generated_text"]

        # 会話履歴の更新
        updated_conversation_history = conversation_history.copy()
        updated_conversation_history.append({"role": "user", "content": user_message})
        updated_conversation_history.append({"role": "assistant", "content": assistant_response_text})

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({
                "success": True,
                "response": assistant_response_text,
                "conversationHistory": updated_conversation_history
            })
        }

    except urllib.error.HTTPError as e:
        error_body = "No error body from FastAPI."
        try: error_body = e.read().decode()
        except: pass
        print(f"HTTPError calling FastAPI: {e.code} - {e.reason}. Body: {error_body}")
        return {"statusCode": e.code if hasattr(e, 'code') else 500, "body": json.dumps({"success": False, "error": f"FastAPI Error: {e.reason}", "details": error_body})}
    except Exception as error:
        print(f"Error: {str(error)}")
        traceback.print_exc()
        return {"statusCode": 500, "body": json.dumps({"success": False, "error": str(error)})}
