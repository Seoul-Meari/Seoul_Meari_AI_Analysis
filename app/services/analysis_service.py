import re
import json
import requests
from PIL import Image
from io import BytesIO
from google import genai
import boto3
from app.core.config import settings

client = genai.Client(api_key=settings.gemini_api_key)

# IAM Role을 사용하여 S3 클라이언트 생성
s3_client = boto3.client(
    's3',
    region_name=settings.AWS_REGION
)


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

def save_location_data(gps_data: dict, image_url: str):
    """위치 데이터를 데이터베이스에 저장합니다."""
    try:
        # 여기에 데이터베이스 저장 로직을 추가할 수 있습니다
        # 예: PostgreSQL, MongoDB 등
        
        location_record = {
            "image_url": image_url,
            "latitude": gps_data.get('latitude_decimal'),
            "longitude": gps_data.get('longitude_decimal'),
            "coordinates": gps_data.get('coordinates'),
            "altitude": gps_data.get('GPSAltitude'),
            "speed": gps_data.get('GPSSpeed'),
            "direction": gps_data.get('GPSImgDirection'),
            "timestamp": gps_data.get('GPSTimeStamp'),
            "created_at": "now()"  # 실제로는 현재 시간
        }
        
        # TODO: 실제 데이터베이스 저장 구현
        print(f"위치 데이터 저장: {location_record}")
        
        return {
            "success": True,
            "message": "위치 데이터가 저장되었습니다.",
            "location_id": "generated_id"  # 실제로는 생성된 ID
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"위치 데이터 저장 오류: {str(e)}"
        }

def analyze_image(image_url: str, save_location: bool = True):
    # 이미지 메타데이터 추출
    metadata_result = get_image_metadata_from_url(image_url)
    metadata = metadata_result.get("metadata") if metadata_result["success"] else None
    
    # GPS 데이터 추출 (API 응답에서 gps_data 사용)
    gps_data = None
    if metadata and "gps" in metadata:
        # API 응답과 동일한 방식으로 GPS 데이터 매핑
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
    
    # 위치 데이터가 있고 저장 옵션이 활성화된 경우 저장
    location_saved = None
    if gps_data and save_location:
        location_result = save_location_data(gps_data, image_url)
        location_saved = location_result
    
    # AI 이미지 분석
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            {
                image_url,
                """ 당신은 도시 환경 데이터용 비전 분석가입니다. 
                    목표: 이미지에 '무단투기 의심 쓰레기봉투'가 있는지 판별하고, 아래 JSON 스키마로만 답하십시오.
                    판별 규칙(요지):
                    - '쓰레기봉투'는 내용물이 든 봉투형 포장(비닐/플라스틱)이 바닥/길가/전봇대 주변 등에 놓인 상태를 말합니다.
                    - 합법 배출 요소(예: 공식 스티커, 지정된 수거함/배출장소 내부)는 무단투기에서 제외합니다.
                    - 혼동 주의: 쇼핑백, 비닐 포장, 의류 가방, 검은 그림자/반사, 개 배설물 봉투 디스펜서, 건축 폐포 자루 등.

                    응답 형식:
                    - 반드시 'JSON만' 출력합니다. 여는 중괄호로 시작해 닫는 중괄호로 끝나야 합니다.
                    {
                        "type": "image_url",
                        "tag" : "trash_bag",
                        "image_url": "쓰레기 봉투가 있는 이미지 url"
                    }
                    """
            },
        ],
    )

    # response에서 ```json 또는 ```로 시작하는 부분과 ```로 끝나는 부분을 모두 제거
    response_text = resp.text.strip()
    response_text = re.sub(r"^```json\s*|^```\s*|```$", "", response_text, flags=re.MULTILINE)
    if not response_text:
        return {
            "type": "error",
            "message": "AI가 응답을 생성하지 못했습니다.",
            "metadata": metadata
        }
    try:
        response = json.loads(response_text)
        # 메타데이터 추가
        if metadata:
            response["metadata"] = metadata
        # GPS 데이터 추가
        if gps_data:
            response["gps_data"] = gps_data
        # 위치 저장 정보 추가
        if location_saved:
            response["location_saved"] = location_saved
        return response
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
