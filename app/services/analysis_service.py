import os
from dotenv import load_dotenv
from openai import OpenAI
import re
import json

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def llm(ask: str):
    # 최신 권장: Responses API
    resp = client.chat.completions.create(
        model="gpt-4o",                 # 원하시는 모델로 교체 가능
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": ask}
        ],
        # instructions="역할 프롬프트를 쓰고 싶다면 여기에",
    )
    return {"output": resp.output_text}

def analyze_image(image_url: str):
    resp = client.chat.completions.create(
        model="gpt-4o",  # GPT-4 Vision 모델 사용
        messages=[
            {
                "role": "system", 
                "content": """너는 환경 감시 AI야. 길거리 이미지에서 쓰레기봉투만 탐지하고 
                    만약 쓰레기 봉투가 있을 경우 아래와 같은 json 형식으로 이미지 url을 다시 반환해줘줘.
                    {
                        "type": "image_url",
                        "image_url": "쓰레기 봉투가 있는 이미지 url"
                    }
                    """
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": image_url
                    }
                ]
            }
        ],
        max_tokens=1000
    )

    # response에서 ```json 또는 ```로 시작하는 부분과 ```로 끝나는 부분을 모두 제거
    response = re.sub(r"^```json\s*|^```\s*|```$", "", resp.choices[0].message.content.strip(), flags=re.MULTILINE)
    response = json.loads(response)
    return response
