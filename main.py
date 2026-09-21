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


def extract_address(driver, body, code):
    # ElecMap 결과는 일반 텍스트/숨겨진 카드/버튼 속성 중 한 곳에 표시될 수 있습니다.
    chunks = [body]
    try:
        chunks.append(driver.find_element(By.TAG_NAME, "html").get_attribute("innerHTML") or "")
    except Exception:
        pass

    text = "\n".join(chunks)

    # 라벨 기반 우선 추출
    labels = ("도로명주소", "도로명 주소", "지번주소", "지번 주소", "주소", "소재지")
    for label in labels:
        for m in re.finditer(re.escape(label) + r"\s*[:：]?\s*([^\n<]{5,200})", text, re.IGNORECASE):
            value = re.sub(r"\s+", " ", m.group(1)).strip()
            value = re.sub(r"<[^>]+>", " ", value).strip()
            if value and value != code and len(value) > 4:
                road = ROAD_ADDR_RE.search(value)
                if road:
                    return road.group(0).strip()
                lot = LOT_ADDR_RE.search(value)
                if lot:
                    return lot.group(0).strip()

    # 페이지 전체에서 주소 패턴 검색
    for rx in (ROAD_ADDR_RE, LOT_ADDR_RE):
        m = rx.search(text)
        if m:
            return m.group(0).strip()

    # 지도/검색 결과 요소의 title, aria-label, data-* 속성도 확인
    try:
        for el in driver.find_elements(By.XPATH, "//*[@title or @aria-label or @data-address or @data-name]"):
            attrs = [
                el.get_attribute("title"),
                el.get_attribute("aria-label"),
                el.get_attribute("data-address"),
                el.get_attribute("data-name"),
            ]
            for value in attrs:
                if not value:
                    continue
                for rx in (ROAD_ADDR_RE, LOT_ADDR_RE):
                    m = rx.search(value)
                    if m:
                        return m.group(0).strip()
    except Exception:
        pass

    return ""


def click_visible_button(driver, labels):
    for label in labels:
        xpath = f"//button[normalize-space(.)='{label}' or contains(normalize-space(.),'{label}')]"
        for b in driver.find_elements(By.XPATH, xpath):
            try:
                if b.is_displayed() and b.is_enabled():
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", b)
                    driver.execute_script("arguments[0].click();", b)
                    return True
            except Exception:
                continue
    return False


def search_one(driver, code):
    driver.get(URL)

    inp = WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "input[placeholder*='전산화번호']")
        )
    )
    inp.clear()
    inp.send_keys(code)

    # 입력창과 같은 form의 검색 버튼을 우선 사용합니다.
    clicked = False
    try:
        form = inp.find_element(By.XPATH, "ancestor::form[1]")
        for b in form.find_elements(By.XPATH, ".//button"):
            try:
                if b.is_displayed() and b.is_enabled():
                    driver.execute_script("arguments[0].click();", b)
                    clicked = True
                    break
            except Exception:
                pass
    except Exception:
        pass

    if not clicked:
        clicked = click_visible_button(driver, ("검색",))

    if not clicked:
        inp.send_keys("\n")

    # ElecMap은 검색 후 별도의 '검색 시작' 버튼을 띄우는 경우가 있습니다.
    # 이 버튼을 누르지 않으면 실제 데이터 검색이 시작되지 않습니다.
    end = time.time() + 25
    while time.time() < end:
        click_visible_button(driver, ("검색 시작",))

        body = driver.find_element(By.TAG_NAME, "body").text
        result = extract_address(driver, body, code)
        if result:
            return result

        # 결과가 지도에만 표시되는 경우 '지도에서 보기'를 눌러 주소 카드/팝업을 엽니다.
        if "검색결과" in body or "검색 완료" in body or "지도에서 보기" in body:
            click_visible_button(driver, ("지도에서 보기",))
            time.sleep(0.5)
            body = driver.find_element(By.TAG_NAME, "body").text
            result = extract_address(driver, body, code)
            if result:
                return result

        time.sleep(0.5)

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
