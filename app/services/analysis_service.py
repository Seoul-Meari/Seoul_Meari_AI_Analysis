import re
import json
import requests
from PIL import Image
from io import BytesIO
import boto3
from botocore.config import Config
from app.core.config import settings
from app.models.complaints import insert_complaint
from sqlalchemy.orm import Session
from app.db.session import get_db
from fastapi import Depends
from urllib.parse import urlparse, unquote

#BedRock Client 생성
bedrock_client = boto3.client(
    'bedrock-runtime',
    region_name=settings.AWS_BEDROCK_REGION
)

# IAM Role을 사용하여 S3 클라이언트 생성
s3_client = boto3.client(
    's3',
    region_name=settings.AWS_REGION,
    config=Config(
        signature_version="s3v4",
        s3={
            'addressing_style': 'virtual'
        }
    )
)

# S3에서 이미지 URL 목록을 가져옵니다.
def get_s3_image_urls(limit: int = 50, prefix: str = "", start_key: str = None, end_key: str = None):
    """S3에서 이미지 URL 목록을 가져옵니다."""
    try:
        image_urls = []
        continuation_token = None
        while True:
            # S3 객체 목록 조회 (페이지네이션)
            params = {
                'Bucket': settings.S3_BUCKET_NAME,
                'Prefix': prefix,
                'MaxKeys': 1000  # 한 번에 많이 가져오기
            }
            
            if continuation_token: 
                params['ContinuationToken'] = continuation_token
                
            response = s3_client.list_objects_v2(**params)
            # print(f"response : {response}")
            if 'Contents' not in response:
                break
            for obj in response['Contents']:
                key = obj['Key']
                
                # 디렉터리 키는 건너뛰기
                if key.endswith('/'):
                    continue
                
                # 키에서 시간 부분만 추출 (upload_image/20250916/001240_객체태그_SLD_고유이름.jpg -> 001240)
                key_parts = key.split('/')
                print(f"key_parts : {key_parts}")
                
                if len(key_parts) >= 3 and key_parts[2]:  # 빈 문자열 체크 추가
                    time_key = key_parts[2].split('_')[0]  # 시간 부분만 (001240)
                    tag = key_parts[2].split('_')[1] if len(key_parts[2].split('_')) > 1 else None
                else:
                    continue  # 유효하지 않은 키는 건너뛰기
                
                # 시간 범위 필터링
                print(f"time_key: {time_key}")
                print(f"tag : {tag}")
                if start_key and time_key < start_key:
                    continue
                if end_key and time_key > end_key:
                    continue
                # 이미지 파일 확장자 필터링
                if key.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')):
                    # Presigned URL 생성
                    url = presigned_url(key)
                    print(f"url: {url}")
                    image_urls.append({
                        "key": key,
                        "url": f"{tag} : {url}",
                        "last_modified": obj['LastModified'].isoformat(),
                        "size": obj['Size']
                    })
                    
                    # limit 체크
                    if len(image_urls) >= limit:
                        break
            
            # limit 도달 시 중단
            if len(image_urls) >= limit:
                break
                
            # 다음 페이지 확인
            if 'NextContinuationToken' in response:
                continuation_token = response['NextContinuationToken']
            else:
                break
        # print(f"image_urls : {image_urls}")
        return {
            "success": True,
            "image_urls": image_urls[:limit],  # limit만큼만 반환
            "count": len(image_urls)
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"S3 이미지 목록 조회 오류: {str(e)}"
        }

def presigned_url(key: str):
    """S3 객체의 presigned URL을 생성합니다."""
    url = s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.S3_BUCKET_NAME, "Key": key},
        ExpiresIn=3600
    )
    return url


def extract_gps_data(exif_data):
    """EXIF 데이터에서 GPS 정보를 추출합니다."""
    try:
        # GPS 태그 ID (34853) 또는 'GPSInfo'로 찾기
        gps_tag = 34853
        gps_info = None
        
        if gps_tag in exif_data:
            gps_info = exif_data[gps_tag]
        elif 'GPSInfo' in exif_data:
            # GPSInfo가 문자열로 변환된 경우 처리
            gps_info_str = exif_data['GPSInfo']
            print(f"GPSInfo 문자열 발견: {gps_info_str}")
            # 문자열을 파싱하여 딕셔너리로 변환
            try:
                import ast
                gps_info = ast.literal_eval(gps_info_str)
            except:
                print("GPSInfo 문자열 파싱 실패")
                return None
        
        if gps_info is None:
            print("GPS 정보를 찾을 수 없습니다.")
            return None
            
        print(f"GPS 정보 발견: {gps_info}")
        
        # GPS 태그 매핑
        gps_tags = {
            1: 'GPSLatitudeRef',    # N/S
            2: 'GPSLatitude',       # 위도
            3: 'GPSLongitudeRef',   # E/W  
            4: 'GPSLongitude',      # 경도
            5: 'GPSAltitudeRef',    # 고도 참조
            6: 'GPSAltitude',       # 고도
            7: 'GPSTimeStamp',      # 시간
            12: 'GPSSpeedRef',      # 속도 참조
            13: 'GPSSpeed',         # 속도
            16: 'GPSImgDirectionRef', # 방향 참조
            17: 'GPSImgDirection',  # 방향
        }
        
        gps_data = {}
        print(f"GPS 태그 처리 시작. gps_info 타입: {type(gps_info)}")
        
        for tag_id, tag_name in gps_tags.items():
            # exif_data에서 tag_id가 있을경우 추가
            if tag_id in gps_info:
                value = gps_info[tag_id]
                print(f"태그 {tag_id} ({tag_name}): {value} (타입: {type(value)})")
                
                # IFDRational 타입을 문자열로 변환
                if hasattr(value, 'numerator') and hasattr(value, 'denominator'):
                    gps_data[tag_name] = f"{value.numerator}/{value.denominator}"
                elif isinstance(value, (list, tuple)):
                    # 리스트나 튜플인 경우 각 요소를 변환
                    converted_list = []
                    for item in value:
                        if hasattr(item, 'numerator') and hasattr(item, 'denominator'):
                            converted_list.append(f"{item.numerator}/{item.denominator}")
                        else:
                            converted_list.append(item)  # 문자열로 변환하지 않고 원본 유지
                    gps_data[tag_name] = converted_list
                else:
                    gps_data[tag_name] = value  # 문자열로 변환하지 않고 원본 유지
            else:
                print(f"태그 {tag_id} ({tag_name})가 GPS 정보에 없습니다.")
        
        # 위도/경도를 십진도로 변환
        if 'GPSLatitude' in gps_data and 'GPSLongitude' in gps_data:
            print(f"위도 변환: {gps_data['GPSLatitude']}")
            print(f"경도 변환: {gps_data['GPSLongitude']}")
            
            try:
                lat = convert_to_degrees(gps_data['GPSLatitude'])
                lon = convert_to_degrees(gps_data['GPSLongitude'])
                print(f"변환된 위도: {lat}, 경도: {lon}")
            
                # N/S, E/W 참조에 따라 부호 결정
                if gps_data.get('GPSLatitudeRef') == 'S':
                    lat = -lat
                if gps_data.get('GPSLongitudeRef') == 'W':
                    lon = -lon
                    
                gps_data['latitude_decimal'] = lat
                gps_data['longitude_decimal'] = lon
                
                # 좌표를 문자열로도 저장
                gps_data['coordinates'] = f"{lat:.6f}, {lon:.6f}"
                print(f"최종 좌표: {gps_data['coordinates']}")
            except Exception as e:
                print(f"좌표 변환 오류: {e}")
        else:
            print("위도 또는 경도 데이터가 없습니다.")
        
        return gps_data
        
    except Exception as e:
        print(f"GPS 데이터 추출 오류: {e}")
        return None

def convert_to_degrees(value):
    """DMS(도분초) 형식을 십진수로 변환합니다."""
    print(f"convert_to_degrees 입력: {value} (타입: {type(value)})")
    
    def parse_fraction(fraction_str):
        """분수 문자열을 float로 변환합니다."""
        if isinstance(fraction_str, str) and '/' in fraction_str:
            numerator, denominator = fraction_str.split('/')
            return float(numerator) / float(denominator)
        return float(fraction_str)
    
    if isinstance(value, tuple) and len(value) == 3:
        d, m, s = value
        print(f"튜플 처리: d={d}, m={m}, s={s}")
        return parse_fraction(d) + parse_fraction(m) / 60.0 + parse_fraction(s) / 3600.0
    elif isinstance(value, list) and len(value) == 3:
        # 문자열로 변환된 경우 처리
        d, m, s = value
        print(f"리스트 처리: d={d}, m={m}, s={s}")
        return parse_fraction(d) + parse_fraction(m) / 60.0 + parse_fraction(s) / 3600.0
    else:
        print(f"단일 값 처리: {value}")
        return parse_fraction(value)

# 메타데이터 추출
def get_image_metadata_from_url(image_url: str):
    """이미지 URL에서 메타데이터를 추출합니다."""
    try:
        # 이미지 다운로드
        response = requests.get(image_url, timeout=30)
        response.raise_for_status()
        
        # 이미지 정보 추출
        image_data = BytesIO(response.content)
        image = Image.open(image_data)
        
        # 기본 메타데이터
        metadata = {
            "url": image_url,
            "content_type": response.headers.get('content-type', 'unknown'),
            "content_length": len(response.content),
            "format": image.format,
            "mode": image.mode,
            "size": image.size,
            "width": image.width,
            "height": image.height,
        }
        
        # EXIF 데이터 추출
        if hasattr(image, '_getexif') and image._getexif() is not None:
            exif_data = image._getexif()
            # 원본 EXIF 데이터는 직렬화 문제로 제외
            # metadata["exif"] = exif_data
            
            # GPS 위치 데이터 추출 (원본 exif_data 사용)
            gps_data = extract_gps_data(exif_data)
            if gps_data:
                metadata["gps"] = gps_data
            
            # 주요 EXIF 정보 추출
            if exif_data:
                exif_info = {}
                for tag_id, value in exif_data.items():
                    tag = Image.ExifTags.TAGS.get(tag_id, tag_id)
                    # 직렬화 추가
                    # IFDRational 타입을 문자열로 변환
                    if hasattr(value, 'numerator') and hasattr(value, 'denominator'):
                        exif_info[tag] = f"{value.numerator}/{value.denominator}"
                    elif isinstance(value, (list, tuple)):
                        # 리스트나 튜플인 경우 각 요소를 변환
                        converted_list = []
                        for item in value:
                            if hasattr(item, 'numerator') and hasattr(item, 'denominator'):
                                converted_list.append(f"{item.numerator}/{item.denominator}")
                            else:
                                converted_list.append(str(item))
                        exif_info[tag] = converted_list
                    else:
                        exif_info[tag] = str(value)
                metadata["exif_info"] = exif_info
        
        # HTTP 헤더 정보
        metadata["http_headers"] = {
            "content_type": response.headers.get('content-type'),
            "content_length": response.headers.get('content-length'),
            "last_modified": response.headers.get('last-modified'),
            "etag": response.headers.get('etag'),
            "server": response.headers.get('server'),
        }
        
        return {
            "success": True,
            "metadata": metadata
        }
        
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": f"이미지 다운로드 오류: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"이미지 처리 오류: {str(e)}"
        }

def analyze_image(image_urls: list, save_location: bool = True, image_key_list: list | None = None, db: Session = None):
    # 이미지 메타데이터 추출 (URL과 1대1 매핑)
    image_data_list = []
    image_urls_list = []
    # image_key_list 형식: "<url> : <key>" → 빠른 조회용 맵 구성
    url_to_key = {}
    try:
        for pair in image_key_list or []:
            if isinstance(pair, str) and " : " in pair:
                url_part, key_part = pair.split(" : ", 1)
                url_part = url_part.strip()
                key_part = key_part.strip()
                # url_part가 "tag : <url>" 형식일 수 있으므로 실제 URL로 보정
                if " : " in url_part and url_part.split(": ", 1)[1].startswith("http"):
                    url_part = url_part.split(": ", 1)[1]
                url_to_key[url_part] = key_part
    except Exception:
        pass
    for image_url in image_urls:
        # 입력이 "태그 : URL" 형식일 수 있으므로 실제 URL과 태그를 분리
        original_input = image_url
        actual_input_url = original_input.split(" : ", 1)[1] if " : " in original_input else original_input
        tag = original_input.split(" : ")[0]

        # 메타데이터는 실제 URL로 조회
        metadata_result = get_image_metadata_from_url(actual_input_url)
        metadata = metadata_result.get("metadata") if metadata_result.get("success") else None

        # 프롬프트에는 원본 형식 유지(태그:URL), 내부 매칭은 실제 URL 기준
        image_urls_list.append(original_input)
        # URL과 메타데이터를 함께 저장
        image_data = {
            "url": actual_input_url,
            "metadata": metadata,
            "tag" : tag,
            "gps_data": None
        }
        # GPS 데이터 변환 (있는 경우)
        if metadata and "gps" in metadata:
            gps_raw = metadata["gps"]
            
            def parse_fraction(value):
                """분수 문자열을 float로 변환합니다."""
                if value is None:
                    return None
                if isinstance(value, str) and '/' in value:
                    numerator, denominator = value.split('/')
                    return float(numerator) / float(denominator)
                return float(value) if value is not None else None
            
            def format_timestamp(value):
                """타임스탬프를 문자열로 변환합니다."""
                if value is None:
                    return None
                if isinstance(value, (list, tuple)):
                    return f"{value[0]}:{value[1]}:{value[2]}"
                return str(value)
            
            gps_data = {
                "latitude_decimal": gps_raw.get("latitude_decimal"),
                "longitude_decimal": gps_raw.get("longitude_decimal"),
                "coordinates": gps_raw.get("coordinates"),
                "altitude": parse_fraction(gps_raw.get("GPSAltitude")),
                "speed": parse_fraction(gps_raw.get("GPSSpeed")),
                "direction": parse_fraction(gps_raw.get("GPSImgDirection")),
                "timestamp": format_timestamp(gps_raw.get("GPSTimeStamp"))
            }
            image_data["gps_data"] = gps_data
        
        image_data_list.append(image_data)
    
    # 편의를 위해 기존 변수명 유지
    metadata = [data["metadata"] for data in image_data_list]
    gps_data = [data["gps_data"] for data in image_data_list]
    # 위치 데이터가 있고 저장 옵션이 활성화된 경우 저장
    location_saved = None
    image_urls_list_text = "\n".join(image_urls_list)
    print(f"image_urls_list_text length: {len(image_urls_list_text)}")
    # AI 이미지 분석
    try:
        print("Calling Bedrock converse...")
        resp = bedrock_client.converse(
            modelId="amazon.nova-micro-v1:0",
            messages=[
                {
                    "role": "user",
                    "content":[
                        {
                            "text": f"""너는 도시 환경 데이터용 자동 민원 생성기다. 
목표: 이미지들의 태그를 참조해서 url을 분석하고 자세한설명, 위험도, 해결방법을 알려줘.
결과물은 입력된 순서대로 순차적으로 출력해. 입력은 태그 : url과 같은 형식으로 입력돼
출력할때는 태그 정보는 빼고 url만 출력해

분석할 이미지 목록:
{image_urls_list_text}

판별 규칙(요지):
- '쓰레기봉투'는 내용물이 든 봉투형 포장(비닐/플라스틱)이 바닥/길가/전봇대 주변 등에 놓인 상태를 말합니다.
- 합법 배출 요소(예: 공식 스티커, 지정된 수거함/배출장소 내부)는 무단투기에서 제외합니다.
- 혼동 주의: 쇼핑백, 비닐 포장, 의류 가방, 검은 그림자/반사, 개 배설물 봉투 디스펜서, 건축 폐포 자루 등.
- 포트홀은 도로 주변에 있는 포트홀을 말합니다.
- danger에는 해당 민원에 대한 위험성을 말한다
- solution에는 해당 민원에 대한 권장조치를 말한다.
- detail에는 해당 민원에 대한 상세 설명을 말한다.

응답 형식:
- 반드시 'JSON 배열만' 출력합니다. [로 시작해서 ]로 끝나야 해.
[
    {{
        "image_url": "쓰레기 봉투가 있는 이미지 url",
        "detail": "해당 민원에 대한 상세 설명",
        "danger": "해당 민원에 대한 위험성",
        "solution": "해당 민원에 대한 권장조치"
    }},
    {{
        "image_url": "포트홀이 있는 이미지 url",
        "detail": "해당 민원에 대한 상세 설명",
        "danger": "해당 민원에 대한 위험성",
        "solution": "해당 민원에 대한 권장조치"
    }}
]"""
                        }
                    ]
                },
            ],
        )
        print("Bedrock converse done")
        print(resp)
    except Exception as e:
        import traceback
        print(f"Bedrock converse error: {e}")
        traceback.print_exc()
        return {
            "type": "error",
            "message": f"BedRock 호출 오류: {str(e)}",
            "metadata": metadata
        }
    # BedRock 응답에서 텍스트 추출
    try:
        out_blocks = resp["output"]["message"]["content"]
        response_text = "".join(block["text"] for block in out_blocks if "text" in block)
    except (KeyError, IndexError) as e:
        return {
            "type": "error",
            "message": f"BedRock 응답 파싱 오류: {str(e)}",
            "metadata": metadata
        }
    
    # response에서 ```json 또는 ```로 시작하는 부분과 ```로 끝나는 부분을 모두 제거
    response_text = re.sub(r"^```json\s*|^```\s*|```$", "", response_text, flags=re.MULTILINE)
    if not response_text:
        return {
            "type": "error",
            "message": "AI가 응답을 생성하지 못했습니다.",
            "metadata": metadata
        }
    
    try:
        # JSON 배열로 파싱
        responses = json.loads(response_text)
        
        # 결과를 저장할 리스트
        final_results = []
        saved_complaints = []
        
        for response in responses:
            print(F"response : {response}")
            image_url = response.get("image_url")
            if image_url:
                # BedRock 응답에서 실제 URL 추출
                actual_url = image_url.split(" : ", 1)[1] if " : " in image_url else image_url
                
                # 해당 URL의 이미지 데이터 찾기
                for image_data in image_data_list:
                    if image_data["url"] == actual_url:
                        s3_key = url_to_key.get(actual_url)
                        if not s3_key and actual_url:
                            try:
                                # presigned URL에서 S3 key 추출
                                parsed = urlparse(actual_url)
                                # parsed.path는 "/upload_image/..." 형태이므로 선행 '/' 제거 후 디코딩
                                s3_key = unquote(parsed.path.lstrip('/')) or None
                            except Exception:
                                s3_key = None
                        # GPS 데이터 안전하게 추출
                        gps_data = image_data.get("gps_data")
                        
                        final_result = {
                            "tag": image_data["tag"],
                            "image_url": image_url,
                            "detail": response.get("detail"),
                            "danger": response.get("danger"),
                            "solution": response.get("solution"),
                            "gps_data": gps_data,
                            "metadata": image_data.get("metadata"),
                            "s3_key": s3_key
                        }
                        final_results.append(final_result)
                        
                        # DB에 민원 저장 (db가 제공된 경우): GPS 없으면 None으로 저장
                        if db:
                            try:
                                latitude = gps_data.get("latitude_decimal") if gps_data else None
                                longitude = gps_data.get("longitude_decimal") if gps_data else None
                                altitude = gps_data.get("altitude") if gps_data else None
                                direction = gps_data.get("direction") if gps_data else None
                                # GPS 타임스탬프는 포맷이 다를 수 있어 일단 None 처리
                                timestamp = None

                                complaint_result = insert_complaint(
                                    db, latitude, longitude, 0, altitude, 0,
                                    direction, timestamp, s3_key,
                                    response.get("danger"), response.get("solution"),
                                    response.get("detail"),
                                    image_data["tag"]
                                )
                                saved_complaints.append(complaint_result)
                            except Exception as e:
                                print(f"민원 저장 오류: {e}")
                        break
        
        return {
            "success": True,
            "results": final_results,
            "total_count": len(image_data_list),
            "detected_count": len(final_results),
            "saved_complaints": len(saved_complaints),
            "metadata": metadata
        }
            
    except json.JSONDecodeError as e:
        # JSON 파싱 실패 시 기본 응답 반환
        return {
            "type": "error",
            "message": f"JSON 파싱 오류: {str(e)}",
            "raw_response": response_text,
            "metadata": metadata,
            "gps_data": gps_data,
            "location_saved": location_saved
        }

def batch_analyze_images(limit: int = 50, prefix: str = "", start_key: str = None, end_key: str = None, save_location: bool = True, db: Session = None):
    """S3에서 이미지들을 목록으로 분석"""
    try:
        # S3에서 이미지 URL 목록 가져오기
        s3_result = get_s3_image_urls(limit, prefix, start_key, end_key)
        if not s3_result["success"]:
            return s3_result
        
        image_urls = s3_result["image_urls"]
        if not image_urls:
            return {
                "success": True,
                "message": "분석할 이미지가 없습니다.",
                "results": [],
                "total_count": 0,
                "success_count": 0,
                "error_count": 0
            }
        
        # URL 리스트 추출
        image_url_list = [img["url"] for img in image_urls]
        image_key_list = [f"{img['url']} : {img['key']}" for img in image_urls]
        # 배치 분석 실행
        print(f"image_url_list: {image_url_list}")
        print(f"image_key_list: {image_key_list}")
        analysis_result = analyze_image(image_url_list, save_location, image_key_list, db)
        
        # S3 정보를 결과에 추가
        if analysis_result.get("success") and "results" in analysis_result:
            for i, result in enumerate(analysis_result["results"]):
                if i < len(image_urls):
                    result["s3_info"] = {
                        "key": image_urls[i]["key"],
                        "last_modified": image_urls[i]["last_modified"],
                        "size": image_urls[i]["size"]
                    }
        
        return analysis_result
    except Exception as e:
        return {
            "success": False,
            "error": f"배치 분석 오류: {str(e)}"
        }

def analyze_and_save_db_test(image_urls: list[str], db: Session = None):
    """여러 이미지 URL을 분석하고 DB에 저장하는 테스트 함수"""
    try:
        # 이미지 분석 실행
        analysis_result = analyze_image(image_urls, save_location=True, db=db)
        
        if analysis_result.get("success"):
            return {
                "success": True,
                "message": f"{len(image_urls)}개 이미지 분석 완료",
                "total_images": len(image_urls),
                "detected_complaints": analysis_result.get("detected_count", 0),
                "saved_complaints": analysis_result.get("saved_complaints", 0),
                "results": analysis_result.get("results", [])
            }
        else:
            return analysis_result
            
    except Exception as e:
        return {
            "success": False,
            "error": f"분석 및 저장 오류: {str(e)}"
        }
