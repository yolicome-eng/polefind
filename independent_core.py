"""Independent pole-grid coordinates and Kakao address conversion."""
import json, math, re, statistics, urllib.parse, urllib.request
from dataclasses import dataclass
from pyproj import Transformer

GRID = ("ABEF", "CDGH", "PQWX", "RSYZ")
LETTERS = {ch:(col,row) for row,line in enumerate(GRID) for col,ch in enumerate(line)}
REGION_EPSG = {"경기/충청":5186, "강원동부":5187, "강원서부":5186,
               "부산울산":5187}
KNOWN_ORIGINS = {"경기/충청":(199591.015-500, 499324.015)}
CODE = re.compile(r"^\d{4}[ABCD EFGH PQRS WXYZ]\d{3}$".replace(" ",""))

def parse(code):
    code=str(code).strip().upper()
    if not CODE.fullmatch(code): raise ValueError("전산화번호는 숫자 4자리 + A~Z 격자 문자 + 숫자 3자리여야 합니다.")
    xx, yy = int(code[:2]),int(code[2:4]); col,row=LETTERS[code[4]]
    return (xx-100 if xx>=50 else xx, yy-100 if yy>=50 else yy,
            col,row,int(code[5]),int(code[6]))

def grid_offset(code):
    xx,yy,col,row,small_x,small_y=parse(code)
    return xx*2000+col*500+small_x*50, yy*2000+(3-row)*500+small_y*50

def coordinates(code,region,origin):
    if region not in REGION_EPSG:raise ValueError("지원 권역을 선택하세요.")
    dx,dy=grid_offset(code)
    lon,lat=Transformer.from_crs(REGION_EPSG[region],4326,always_xy=True).transform(origin[0]+dx,origin[1]+dy)
    return lat,lon

def api(path,key,params):
    url="https://dapi.kakao.com/v2/local/"+path+"?"+urllib.parse.urlencode(params)
    request=urllib.request.Request(url,headers={"Authorization":"KakaoAK "+key.strip(),"User-Agent":"PoleAddressIndependent/1.0"})
    try:
        with urllib.request.urlopen(request,timeout=12) as response:return json.load(response)
    except urllib.error.HTTPError as e:
        if e.code in (401,403):raise ValueError("카카오 REST API 키 또는 지도 API 사용 설정을 확인하세요.") from e
        raise ValueError(f"카카오 주소 서비스 HTTP {e.code}") from e

def reverse_address(lat,lon,key):
    data=api("geo/coord2address.json",key,{"x":lon,"y":lat,"input_coord":"WGS84"})
    docs=data.get("documents",[])
    if not docs:raise ValueError("이 좌표에 주소가 없습니다.")
    item=docs[0]
    addr=item.get("address") or item.get("road_address") or {}
    return addr.get("address_name","")

def geocode(address,key):
    data=api("search/address.json",key,{"query":address,"size":5})
    docs=data.get("documents",[])
    if not docs:raise ValueError("샘플 주소를 좌표로 바꾸지 못했습니다: "+address)
    # Prefer an exact full name, then the first official result.
    compact=lambda s:re.sub(r"\s+","",s or "")
    item=next((d for d in docs if compact(d.get("address_name"))==compact(address)),docs[0])
    return float(item["y"]),float(item["x"])

@dataclass
class Calibration:
    origin:tuple
    sample_count:int
    median_error_m:float
    maximum_error_m:float
    status:str

def calibrate(region,samples,key):
    if region not in REGION_EPSG:raise ValueError("지원하지 않는 권역입니다.")
    epsg=REGION_EPSG[region]
    forward=Transformer.from_crs(4326,epsg,always_xy=True)
    observations=[]
    for code,address in samples:
        lat,lon=geocode(address,key);x,y=forward.transform(lon,lat);dx,dy=grid_offset(code)
        observations.append((x-dx,y-dy))
    if len(observations)<5:raise ValueError("권역별 샘플 주소가 최소 5개 필요합니다.")
    if region in KNOWN_ORIGINS:
        origin=KNOWN_ORIGINS[region]
    else:
        origin=tuple(statistics.median(p[i] for p in observations) for i in (0,1))
    errors=[math.hypot(p[0]-origin[0],p[1]-origin[1]) for p in observations]
    med=statistics.median(errors);maximum=max(errors)
    # An address denotes a parcel or building, not necessarily the pole. Require
    # multiple samples and conservative agreement before enabling bulk output.
    status="사용 가능" if med<=70 and maximum<=180 else "검증 필요"
    return Calibration(origin,len(samples),round(med,1),round(maximum,1),status)
