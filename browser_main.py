import os, re, threading, time, traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

URL = "https://elecmap.kr/search/single"
CODE_RE = re.compile(r"^[A-Za-z0-9]{8}$")
REGIONS = ["서울","경기","인천","강원","충북","충남","전북","전남","경북","경남"]

def make_driver():
    o=Options()
    o.add_argument("--disable-notifications")
    o.add_argument("--disable-popup-blocking")
    o.add_argument("--start-maximized")
    o.add_argument("--lang=ko-KR")
    o.set_capability("unhandledPromptBehavior","ignore")
    return webdriver.Chrome(options=o)

def txt(e):
    try: return (e.text or "").strip()
    except: return ""

def visible(e):
    try: return e.is_displayed()
    except: return False

def lines(text):
    return [re.sub(r"\s+"," ",x).strip() for x in text.splitlines() if x.strip()]

def extract_under_code(d, code):
    """
    Do not guess an address format.
    Find the visible result containing the searched code and read the text
    immediately below that code. This mirrors the actual ElecMap result card.
    """
    stop = {"지도에서 보기","검색 시작","검색 중...","검색 준비 중...","검색결과"}
    candidates=[]
    try:
        # Exact/near-exact visible text nodes containing the searched code.
        elems=d.find_elements(By.XPATH,
            "//*[normalize-space()='%s' or contains(normalize-space(.),'%s')]" % (code, code))
        for e in elems:
            if not visible(e): continue
            try:
                t=txt(e)
                if code not in t: continue
                # Walk up a few ancestors and keep compact result cards.
                p=e
                for _ in range(6):
                    if p is None: break
                    pt=txt(p)
                    ls=lines(pt)
                    if code in pt and 2 <= len(ls) <= 12:
                        candidates.append(ls)
                    p=p.find_element(By.XPATH,"..")
            except: pass
    except: pass

    # Prefer the smallest card where code is followed by non-control text.
    for ls in sorted(candidates,key=len):
        for i,x in enumerate(ls):
            if code in x:
                following=[]
                for y in ls[i+1:]:
                    if y in stop: break
                    if code in y: continue
                    # Ignore generic UI-only lines.
                    if y in {"전산화번호","주소","도로명주소","지번주소"}: continue
                    following.append(y)
                    if len(following)>=3: break
                if following:
                    return " ".join(following)

    # Fallback: inspect visible body text, still using position below code.
    try:
        body=txt(d.find_element(By.TAG_NAME,"body"))
        ls=lines(body)
        for i,x in enumerate(ls):
            if code in x:
                following=[]
                for y in ls[i+1:i+5]:
                    if y in stop: break
                    if y and code not in y:
                        following.append(y)
                if following:
                    return " ".join(following)
    except: pass
    return ""

def choose_region(d, region):
    deadline=time.time()+15
    while time.time()<deadline:
        # The first select on ElecMap is the search-region selector.
        for s in d.find_elements(By.CSS_SELECTOR,"select"):
            try:
                if not visible(s): continue
                opts=s.find_elements(By.TAG_NAME,"option")
                match=next((o for o in opts if o.text.strip()==region or region in o.text.strip()),None)
                if match:
                    try:
                        Select(s).select_by_visible_text(match.text.strip())
                    except:
                        d.execute_script(
                            "arguments[0].value=arguments[1];"
                            "arguments[0].dispatchEvent(new Event('change',{bubbles:true}));",
                            s, match.get_attribute("value"))
                    time.sleep(.7)
                    return True
            except: pass
        time.sleep(.3)
    return False

def dismiss_prompt(d):
    # Handle both browser-native alerts and ElecMap's HTML dialogs.
    closed=False
    try:
        a=d.switch_to.alert
        a.accept()
        closed=True
    except: pass

    try:
        d.switch_to.default_content()
        # "위치를 선택해주세요" -> 확인 closes the warning and exposes
        # the location selector.  A search-fallback notice -> 취소 closes
        # the notice so the current result can be inspected.
        body=txt(d.find_element(By.TAG_NAME,"body"))
        wanted=[]
        if "위치를 선택해주세요" in body:
            wanted=["확인"]
        elif "선택한 권역에서 찾을 수 없어 다른 권역에서 검색했습니다" in body:
            wanted=["취소","확인"]
        else:
            wanted=["확인"]

        for label in wanted:
            for e in d.find_elements(By.XPATH,
                "//*[self::button or self::a or @role='button']"):
                try:
                    if visible(e) and txt(e).strip()==label:
                        d.execute_script("arguments[0].click();",e)
                        time.sleep(.5)
                        closed=True
                        break
                except: pass
            if closed: break
    except: pass
    return closed

def close_all_site_dialogs(d, max_rounds=6):
    # Some dialogs appear one after another. Keep clearing them before
    # trying to read/click the result.
    for _ in range(max_rounds):
        before=txt(d.find_element(By.TAG_NAME,"body")) if d.current_window_handle else ""
        changed=dismiss_prompt(d)
        if not changed:
            break
        time.sleep(.35)
    return True

