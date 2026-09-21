import os
import re
import json
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pandas as pd
import requests

API_URL = "https://elecmap.kr/api/search"
CODE_RE = re.compile(r"^\d{4}[A-Za-z]\d{3}$")

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "https://elecmap.kr",
    "Referer": "https://elecmap.kr/search/single",
})

REGIONS = [f"region{i}" for i in range(1, 11)]


def flatten_values(obj, out=None):
    if out is None:
        out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                flatten_values(v, out)
            elif v is not None:
                out.append((str(k).lower(), str(v).strip()))
    elif isinstance(obj, list):
        for v in obj:
            flatten_values(v, out)
    return out


def find_address(data):
    pairs = flatten_values(data)
    preferred = (
        "roadaddress", "road_address", "roadaddr", "road_addr",
        "jibunaddress", "jibun_address", "address", "addr",
        "location", "fulladdress", "full_address"
    )

    # 주소로 보이는 키를 먼저 사용
    for key, value in pairs:
        key2 = key.replace("-", "_").replace(" ", "")
        if any(p.replace("_", "") in key2 for p in preferred):
            if len(value) >= 5 and not re.fullmatch(r"https?://.*", value):
                return value

    # 값 자체가 한국 주소처럼 보이는 경우
    for _, value in pairs:
        if re.search(r"(특별시|광역시|특별자치도|도)\s+.*(시|군|구)\s+.*(대로|로|길)\s*\d+", value):
            return value
        if re.search(r"(시|군|구)\s+.*(읍|면|동|리)\s+\d+", value):
            return value

    return ""


def find_coordinates(data):
    lat = lon = None
    pairs = flatten_values(data)
    for key, value in pairs:
        k = key.replace("_", "").replace("-", "")
        try:
            n = float(value)
        except Exception:
            continue
        if k in ("lat", "latitude") and -90 <= n <= 90:
            lat = n
        elif k in ("lon", "lng", "longitude") and -180 <= n <= 180:
            lon = n
    return lat, lon


def api_search(code):
    # ElecMap 공식 페이지는 권역을 모르면 전국 권역을 자동 검색합니다.
    # 우선 region 없이 요청하고, 실패하면 알려진 10개 권역을 순차적으로 확인합니다.
    payloads = [{"code": code}]
    payloads.extend({"code": code, "region": r} for r in REGIONS)

    last_error = None

    for payload in payloads:
        try:
            r = SESSION.post(API_URL, json=payload, timeout=15)
            r.raise_for_status()
            data = r.json()

            address = find_address(data)
            lat, lon = find_coordinates(data)

            # API가 주소를 직접 주는 경우
            if address:
                return address

            # 주소가 없더라도 좌표가 있으면 문자열로 보존해 실패로 버리지 않음
            if lat is not None and lon is not None:
                return f"좌표 {lat:.6f}, {lon:.6f}"

            # 성공/결과 구조인데 주소명이 다른 경우 원문에서 흔한 필드를 추가 탐색
            if isinstance(data, dict):
                for key in ("result", "data", "item", "pole"):
                    value = data.get(key)
                    if isinstance(value, dict):
                        address = find_address(value)
                        if address:
                            return address

        except Exception as e:
            last_error = e
            continue

    if last_error:
        return ""
    return ""


def run(path, status, bar, root):
    try:
        df = pd.read_excel(path, header=None)
        if df.shape[1] < 2:
            df[1] = ""

        total = len(df)
        if total == 0:
            raise ValueError("엑셀 파일에 데이터가 없습니다.")

        for i, v in enumerate(df.iloc[:, 0].fillna("").astype(str)):
            code = v.strip().replace(" ", "").upper()
            status.set(f"{i + 1}/{total}  {code}")

            if not CODE_RE.fullmatch(code):
                df.iat[i, 1] = "형식오류"
            else:
                try:
                    result = api_search(code)
                    df.iat[i, 1] = result or "검색결과없음"
                except Exception as e:
                    df.iat[i, 1] = "검색오류: " + type(e).__name__

            bar["value"] = (i + 1) * 100 / max(total, 1)
            root.after(0, root.update_idletasks)

        out = os.path.splitext(path)[0] + "_주소결과.xlsx"
        df.to_excel(out, index=False, header=False)

        status.set("완료")
        root.after(
            0,
            lambda: messagebox.showinfo(
                "완료",
                f"완료되었습니다.\n\n결과 파일:\n{out}"
            )
        )

    except Exception as e:
        detail = f"{type(e).__name__}: {e}"
        print(traceback.format_exc())
        status.set("오류 발생")
        root.after(
            0,
            lambda d=detail: messagebox.showerror(
                "오류 원인",
                "프로그램 실행 중 오류가 발생했습니다.\n\n" + d
            )
        )


def main():
    root = tk.Tk()
    root.title("전산화번호 → 주소 찾기")
    root.geometry("700x300")
    root.resizable(False, False)

    path = tk.StringVar()
    status = tk.StringVar(value="엑셀 파일을 선택하세요.")

    ttk.Label(
        root, text="전산화번호 주소 찾기",
        font=("맑은 고딕", 18, "bold")
    ).pack(pady=(18, 10))

    row = ttk.Frame(root)
    row.pack(fill="x", padx=25)

    ttk.Entry(row, textvariable=path).pack(side="left", fill="x", expand=True)

    ttk.Button(
        row, text="엑셀 선택",
        command=lambda: path.set(
            filedialog.askopenfilename(
                filetypes=[("Excel 파일", "*.xlsx")]
            )
        ),
    ).pack(side="left", padx=(8, 0))

    bar = ttk.Progressbar(root, length=630, mode="determinate")
    bar.pack(pady=20)

    ttk.Label(
        root, textvariable=status,
        font=("맑은 고딕", 10)
    ).pack()

    def start():
        if not path.get() or not os.path.isfile(path.get()):
            messagebox.showwarning("확인", "엑셀 파일을 먼저 선택하세요.")
            return

        bar["value"] = 0
        status.set("검색 준비 중...")
        threading.Thread(
            target=run,
            args=(path.get(), status, bar, root),
            daemon=True,
        ).start()

    ttk.Button(root, text="검색 시작", command=start).pack(pady=15)
    root.mainloop()


if __name__ == "__main__":
    main()
