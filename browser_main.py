import os
import re
import threading
import time
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

URL = "https://elecmap.kr/search/single"
CODE_RE = re.compile(r"^[A-Za-z0-9]{8}$")
REGIONS = ["서울", "경기", "인천", "강원", "충북", "충남", "전북", "전남", "경북", "경남"]

def make_driver():
    o = Options()
    o.add_argument("--disable-notifications")
    o.add_argument("--disable-popup-blocking")
    o.add_argument("--start-maximized")
    o.add_argument("--lang=ko-KR")
    o.set_capability("unhandledPromptBehavior", "dismiss")
    return webdriver.Chrome(options=o)

def visible_text(e):
    try:
        return (e.text or "").strip()
    except:
        return ""

def clean(driver, main):
    try:
        for h in list(driver.window_handles):
            if h != main:
                try:
                    driver.switch_to.window(h)
                    driver.close()
                except:
                    pass
        driver.switch_to.window(main)
    except:
        pass
    selectors = [
        "button[aria-label*='닫기']", "button[aria-label*='Close']",
        "[role='dialog'] button", "[class*='modal'] button",
        "[class*='Modal'] button"
    ]
    for sel in selectors:
        try:
            for e in driver.find_elements(By.CSS_SELECTOR, sel)[:20]:
                if not e.is_displayed():
                    continue
                t = visible_text(e)
                if any(k in t for k in ("닫기", "취소", "Close", "확인")):
                    try:
                        driver.execute_script("arguments[0].click();", e)
                    except:
                        pass
        except:
            pass

def body(driver):
    try:
        return driver.find_element(By.TAG_NAME, "body").text
    except:
        return ""

def extract_address(text):
    # Only accept a real Korean road-name or lot-number address.
    # Region labels such as "강원 동부" must never be written as an address.
    lines = [re.sub(r"\\s+", " ", x).strip() for x in text.splitlines() if x.strip()]
    region_only = re.compile(r"^(서울|경기|인천|강원|충북|충남|전북|전남|경북|경남)(?:\\s+(?:동부|서부|남부|북부|권))?$")
    bad = ("전산화번호", "검색 준비", "검색 중", "검색 시작", "지도에서 보기", "검색결과", "강원 동부")

    def valid(x):
        x = x.strip()
        if not x or len(x) < 8 or len(x) > 160:
            return False
        if region_only.fullmatch(x) or any(x == b for b in bad):
            return False
        road = re.search(r"(?:대로|로|길)\\s*\\d+(?:-\\d+)?", x)
        lot = re.search(r"(?:읍|면|동|리)\\s*\\d+(?:-\\d+)?", x)
        prefix = re.search(r"(?:특별시|광역시|특별자치시|특별자치도|도|시|군|구)", x)
        return bool((road or lot) and prefix)

    labels = ("주소", "도로명주소", "지번주소", "소재지", "도로명 주소", "지번 주소")
    for i, x in enumerate(lines):
        if x in labels:
            for nxt in lines[i + 1:i + 4]:
                if valid(nxt):
                    return nxt

    for x in lines:
        if valid(x):
            return x
    return ""

def choose_region(driver, region):
    terms = [region, region + "권"]
    # Native/select controls
    for sel in driver.find_elements(By.CSS_SELECTOR, "select"):
        try:
            if not sel.is_displayed():
                continue
            for opt in sel.find_elements(By.TAG_NAME, "option"):
                if any(t in (opt.text or "") for t in terms):
                    driver.execute_script("arguments[0].value=arguments[1]; arguments[0].dispatchEvent(new Event('change',{bubbles:true}));", sel, opt.get_attribute("value"))
                    return True
        except:
            pass
    # Visible buttons/labels/cards
    candidates = driver.find_elements(By.XPATH, "//*[self::button or self::label or @role='button' or @role='option']")
    for e in candidates:
        try:
            if e.is_displayed() and any(t == visible_text(e) or t in visible_text(e) for t in terms):
                driver.execute_script("arguments[0].click();", e)
                time.sleep(0.4)
                return True
        except:
            pass
    return False

def handle_dialogs(driver, region):
    chosen = False
    for _ in range(6):
        try:
            alerts = driver.switch_to.alert
            txt = alerts.text
            if "위치" in txt or "권역" in txt or "지역" in txt:
                alerts.accept()
                time.sleep(0.4)
                continue
            alerts.accept()
            continue
        except:
            pass
        try:
            dialogs = driver.find_elements(By.XPATH, "//*[(@role='dialog' or contains(@class,'modal') or contains(@class,'Modal')) and not(contains(@style,'display: none'))]")
            for d in dialogs:
                if not d.is_displayed():
                    continue
                dt = visible_text(d)
                if "위치" in dt or "권역" in dt or "지역" in dt:
                    chosen = choose_region(driver, region) or chosen
                    for b in d.find_elements(By.TAG_NAME, "button"):
                        bt = visible_text(b)
                        if b.is_displayed() and any(k in bt for k in ("확인", "선택", "적용", "확정")):
                            driver.execute_script("arguments[0].click();", b)
                            break
                    time.sleep(0.7)
        except:
            pass
        if chosen:
            break
        time.sleep(0.3)
    return chosen

def click_map_marker(driver):
    selectors = [
        "[class*='marker']", "[class*='Marker']", "[aria-label*='마커']",
        "[aria-label*='marker']", "[title*='주소']", "[title*='위치']"
    ]
    for sel in selectors:
        try:
            for e in driver.find_elements(By.CSS_SELECTOR, sel)[:20]:
                if e.is_displayed():
                    driver.execute_script("arguments[0].click();", e)
                    time.sleep(0.6)
                    return True
        except:
            pass
    return False

def search(driver, code, region):
    main = driver.current_window_handle
    driver.get(URL)
    WebDriverWait(driver, 25).until(EC.presence_of_element_located((By.CSS_SELECTOR, "input")))
    handle_dialogs(driver, region)
    target = None
    for e in driver.find_elements(By.CSS_SELECTOR, "input"):
        try:
            ph = e.get_attribute("placeholder") or ""
            typ = e.get_attribute("type") or ""
            if e.is_displayed() and typ != "file" and "전산화번호" in ph:
                target = e
                break
        except:
            pass
    if not target:
        return ""
    target.click()
    target.clear()
    target.send_keys(code)
    try:
        buttons = driver.find_elements(By.XPATH, "//button[contains(normalize-space(.),'검색')]")
        for b in buttons:
            if b.is_displayed() and b.is_enabled():
                driver.execute_script("arguments[0].click();", b)
                break
        else:
            target.send_keys(Keys.ENTER)
    except:
        target.send_keys(Keys.ENTER)

    end = time.time() + 50
    while time.time() < end:
        handle_dialogs(driver, region)
        try:
            driver.switch_to.window(main)
        except:
            pass
        t = body(driver)
        a = extract_address(t)
        if a:
            return a
        # The site may expose the result behind a map button.
        for b in driver.find_elements(By.TAG_NAME, "button"):
            try:
                if b.is_displayed() and "지도에서 보기" in visible_text(b):
                    driver.execute_script("arguments[0].click();", b)
                    time.sleep(1)
                    break
            except:
                pass
        handle_dialogs(driver, region)
        click_map_marker(driver)
        a = extract_address(body(driver))
        if a:
            return a
        clean(driver, main)
        time.sleep(0.7)
    return ""

def run(path, region, status, bar, root):
    d = None
    try:
        df = pd.read_excel(path, header=None)
        if df.shape[1] < 2:
            df[1] = ""
        d = make_driver()
        total = len(df)
        for i, v in enumerate(df.iloc[:, 0].fillna("").astype(str)):
            code = v.strip().replace(" ", "").upper()
            status.set(f"{i+1}/{total}  {code}  [{region}]")
            if not CODE_RE.fullmatch(code):
                df.iat[i, 1] = "형식오류(8자리 확인)"
            else:
                try:
                    df.iat[i, 1] = search(d, code, region) or "검색실패"
                except Exception as e:
                    df.iat[i, 1] = "검색오류: " + type(e).__name__
            if (i + 1) % 5 == 0:
                out = os.path.splitext(path)[0] + "_주소결과.xlsx"
                df.to_excel(out, index=False, header=False)
            bar["value"] = (i + 1) * 100 / max(total, 1)
            root.update_idletasks()
        out = os.path.splitext(path)[0] + "_주소결과.xlsx"
        df.to_excel(out, index=False, header=False)
        status.set("완료")
        root.after(0, lambda: messagebox.showinfo("완료", f"결과 파일:\n{out}"))
    except Exception as e:
        status.set("오류 발생")
        root.after(0, lambda d=str(e): messagebox.showerror("오류", d))
        print(traceback.format_exc())
    finally:
        if d:
            try:
                d.quit()
            except:
                pass

def main():
    r = tk.Tk()
    r.title("전산화번호 → 주소 찾기")
    r.geometry("700x380")
    r.resizable(False, False)
    p = tk.StringVar()
    region = tk.StringVar(value="경기")
    s = tk.StringVar(value="엑셀 파일과 검색 권역을 선택하세요.")
    ttk.Label(r, text="전산화번호 주소 찾기", font=("맑은 고딕", 18, "bold")).pack(pady=(18, 8))
    ttk.Label(r, text="① 검색 권역을 먼저 선택하세요").pack()
    cb = ttk.Combobox(r, textvariable=region, values=REGIONS, state="readonly", width=18)
    cb.pack(pady=7)
    row = ttk.Frame(r)
    row.pack(fill="x", padx=25, pady=8)
    ttk.Entry(row, textvariable=p).pack(side="left", fill="x", expand=True)
    ttk.Button(row, text="엑셀 선택", command=lambda: p.set(filedialog.askopenfilename(filetypes=[("Excel 파일", "*.xlsx")]))).pack(side="left", padx=8)
    bar = ttk.Progressbar(r, length=630, mode="determinate")
    bar.pack(pady=18)
    ttk.Label(r, textvariable=s).pack()
    def start():
        if not os.path.isfile(p.get()):
            messagebox.showwarning("확인", "엑셀 파일을 먼저 선택하세요.")
            return
        threading.Thread(target=run, args=(p.get(), region.get(), s, bar, r), daemon=True).start()
    ttk.Button(r, text="검색 시작", command=start).pack(pady=15)
    r.mainloop()

if __name__ == "__main__":
    main()
