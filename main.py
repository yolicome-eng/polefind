import os
import re
import sys
import time
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

URL = "https://elecmap.kr/search/single"
PATTERN = re.compile(r"^\d{4}[A-Za-z]\d{3}$")

# 도로명주소: 서울특별시 강남구 테헤란로 123
#                 경기도 고양시 일산동구 중앙로 123-4
ROAD_ADDR_RE = re.compile(
    r"(?:[가-힣]+(?:특별시|광역시|특별자치시|도|특별자치도)\s+)?"
    r"[가-힣0-9·]+(?:시|군|구)"
    r"(?:\s+[가-힣0-9·]+(?:시|군|구|읍|면|동))?"
    r"\s+[가-힣0-9·]+(?:대로|로|길)\s+"
    r"\d+(?:-\d+)?(?:\s*\([^\n)]*\))?"
)

# 지번주소 보조: 서울특별시 강남구 역삼동 123-4
LOT_ADDR_RE = re.compile(
    r"(?:[가-힣]+(?:특별시|광역시|특별자치시|도|특별자치도)\s+)?"
    r"[가-힣0-9·]+(?:시|군|구)"
    r"(?:\s+[가-힣0-9·]+(?:시|군|구))?"
    r"\s+[가-힣0-9·]+(?:읍|면|동|리)\s+"
    r"\d+(?:-\d+)?"
)


def make_driver():
    # PyInstaller EXE 안에 포함된 Selenium Manager를 우선 사용
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        candidates = [
            os.path.join(base, "selenium", "webdriver", "common", "windows", "selenium-manager.exe"),
            os.path.join(base, "selenium-manager.exe"),
        ]
        for p in candidates:
            if os.path.isfile(p):
                os.environ["SE_MANAGER_PATH"] = p
                break

    o = Options()
    o.add_argument("--headless=new")
    o.add_argument("--disable-gpu")
    o.add_argument("--no-sandbox")
    o.add_argument("--disable-dev-shm-usage")
    o.add_argument("--window-size=1600,1200")
    o.add_argument("--lang=ko-KR")
    o.add_argument("--disable-notifications")
    o.add_argument("--disable-popup-blocking")
    return webdriver.Chrome(options=o)


def extract_address(body, code):
    # 1) 라벨 바로 뒤에 주소가 있는 경우
    labels = ("도로명주소", "도로명 주소", "지번주소", "지번 주소", "주소", "소재지")
    for label in labels:
        m = re.search(
            re.escape(label) + r"\s*[:：]?\s*([^\n]+)",
            body,
            flags=re.IGNORECASE,
        )
        if m:
            value = m.group(1).strip()
            if value and value != code and len(value) > 4:
                road = ROAD_ADDR_RE.search(value)
                if road:
                    return road.group(0).strip()
                lot = LOT_ADDR_RE.search(value)
                if lot:
                    return lot.group(0).strip()

        # 라벨 다음 줄에 주소가 있는 경우
        m = re.search(
            re.escape(label) + r"\s*[:：]?\s*\n\s*([^\n]+)",
            body,
            flags=re.IGNORECASE,
        )
        if m:
            value = m.group(1).strip()
            road = ROAD_ADDR_RE.search(value)
            if road:
                return road.group(0).strip()
            lot = LOT_ADDR_RE.search(value)
            if lot:
                return lot.group(0).strip()

    # 2) 페이지 전체에서 도로명주소를 직접 찾기
    m = ROAD_ADDR_RE.search(body)
    if m:
        return m.group(0).strip()

    # 3) 도로명주소가 없을 때 지번주소를 보조로 찾기
    m = LOT_ADDR_RE.search(body)
    if m:
        return m.group(0).strip()

    return ""


def search_one(driver, code):
    driver.get(URL)

    inp = WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "input[placeholder*='전산화번호']")
        )
    )
    inp.clear()
    inp.send_keys(code)

    # 검색 버튼을 정확히 찾아 클릭
    buttons = driver.find_elements(
        By.XPATH,
        "//button[normalize-space(.)='검색' or contains(normalize-space(.),'검색')]"
    )
    clicked = False
    for b in buttons:
        try:
            if b.is_displayed() and b.is_enabled():
                b.click()
                clicked = True
                break
        except Exception:
            continue

    if not clicked:
        inp.send_keys("\n")

    # 결과가 늦게 렌더링될 수 있으므로 최대 15초 대기
    end = time.time() + 15
    while time.time() < end:
        body = driver.find_element(By.TAG_NAME, "body").text
        result = extract_address(body, code)
        if result:
            return result
        time.sleep(0.4)

    return ""


def run(path, status, bar, root):
    driver = None
    try:
        df = pd.read_excel(path, header=None)
        if df.shape[1] < 2:
            df[1] = ""

        total = len(df)
        if total == 0:
            raise ValueError("엑셀 파일에 데이터가 없습니다.")

        status.set("Chrome 준비 중...")
        root.after(0, root.update_idletasks)

        driver = make_driver()

        for i, v in enumerate(df.iloc[:, 0].fillna("").astype(str)):
            code = v.strip().replace(" ", "").upper()
            status.set(f"{i + 1}/{total}  {code}")

            if not PATTERN.fullmatch(code):
                df.iat[i, 1] = "형식오류"
            else:
                try:
                    result = search_one(driver, code)
                    df.iat[i, 1] = result or "검색결과없음"
                except Exception as e:
                    df.iat[i, 1] = "검색오류: " + type(e).__name__

            bar["value"] = (i + 1) * 100 / max(total, 1)
            root.after(0, root.update_idletasks)

        out = os.path.splitext(path)[0] + "_주소결과.xlsx"
        df.to_excel(out, index=False, header=False)

        if driver:
            try:
                driver.quit()
            except Exception:
                pass

        status.set("완료")
        root.after(
            0,
            lambda: messagebox.showinfo(
                "완료",
                f"완료되었습니다.\n\n결과 파일:\n{out}"
            )
        )

    except Exception as e:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

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
        root,
        text="전산화번호 주소 찾기",
        font=("맑은 고딕", 18, "bold")
    ).pack(pady=(18, 10))

    row = ttk.Frame(root)
    row.pack(fill="x", padx=25)

    ttk.Entry(row, textvariable=path).pack(
        side="left", fill="x", expand=True
    )

    ttk.Button(
        row,
        text="엑셀 선택",
        command=lambda: path.set(
            filedialog.askopenfilename(
                filetypes=[("Excel 파일", "*.xlsx")]
            )
        ),
    ).pack(side="left", padx=(8, 0))

    bar = ttk.Progressbar(
        root,
        length=630,
        mode="determinate"
    )
    bar.pack(pady=20)

    ttk.Label(
        root,
        textvariable=status,
        font=("맑은 고딕", 10)
    ).pack()

    def start():
        if not path.get() or not os.path.isfile(path.get()):
            messagebox.showwarning(
                "확인",
                "엑셀 파일을 먼저 선택하세요."
            )
            return

        bar["value"] = 0
        status.set("준비 중...")
        threading.Thread(
            target=run,
            args=(path.get(), status, bar, root),
            daemon=True,
        ).start()

    ttk.Button(
        root,
        text="검색 시작",
        command=start
    ).pack(pady=15)

    root.mainloop()


if __name__ == "__main__":
    main()
