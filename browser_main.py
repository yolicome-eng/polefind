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
    try:
        a=d.switch_to.alert
        t=a.text
        a.accept()
        return t
    except: return ""

def click_map_marker(d):
    # Leaflet/Kakao/custom map markers: try the marker-like elements only.
    selectors=[
        ".leaflet-marker-icon",
        "[class*='marker']",
        "[class*='Marker']",
        "[aria-label*='마커']",
        "[aria-label*='marker']",
        "[title*='전주']",
        "[title*='주소']"
    ]
    for sel in selectors:
        try:
            for e in d.find_elements(By.CSS_SELECTOR,sel):
                if visible(e):
                    d.execute_script("arguments[0].scrollIntoView({block:'center'});",e)
                    d.execute_script("arguments[0].click();",e)
                    time.sleep(1.0)
                    return True
        except: pass
    return False

def inspect_result(d, code):
    # First read the result already displayed on the page.
    a=extract_under_code(d,code)
    if a: return a

    # Then click the site's map-view button and inspect the resulting view.
    try:
        for b in d.find_elements(By.XPATH,
            "//*[self::button or self::a or @role='button']"):
            if visible(b) and "지도에서 보기" in txt(b):
                before=set(d.window_handles)
                d.execute_script("arguments[0].click();",b)
                time.sleep(1.2)
                after=set(d.window_handles)
                for h in after-before:
                    try: d.switch_to.window(h); break
                    except: pass
                a=extract_under_code(d,code)
                if a: return a
                click_map_marker(d)
                a=extract_under_code(d,code)
                if a: return a
                # Return to all windows without closing anything.
                for h in list(d.window_handles):
                    try:
                        d.switch_to.window(h)
                        a=extract_under_code(d,code)
                        if a: return a
                    except: pass
                return ""
    except: pass
    return ""

def search_one(d, code, region):
    d.get(URL)
    WebDriverWait(d,30).until(EC.presence_of_element_located((By.TAG_NAME,"body")))
    time.sleep(1)
    choose_region(d,region)

    target=WebDriverWait(d,20).until(
        lambda x: next((e for e in x.find_elements(By.CSS_SELECTOR,"input")
                        if visible(e) and "전산화번호" in
                        (e.get_attribute("placeholder") or "")),None))
    target.click()
    target.clear()
    target.send_keys(code)

    clicked=False
    for b in d.find_elements(By.XPATH,"//button[contains(normalize-space(.),'검색')]"):
        try:
            if visible(b) and b.is_enabled():
                d.execute_script("arguments[0].click();",b)
                clicked=True
                break
        except: pass
    if not clicked:
        target.send_keys(Keys.ENTER)

    # Site explicitly waits before starting the search.
    deadline=time.time()+75
    while time.time()<deadline:
        dismiss_prompt(d)
        a=inspect_result(d,code)
        if a: return a
        time.sleep(.8)
    return ""

def run(path,region,status,bar,root):
    d=None
    try:
        df=pd.read_excel(path,header=None)
        if df.shape[1]<2: df[1]=""
        start=1 if len(df) and str(df.iat[0,0]).strip() in ("전산화번호","번호","코드") else 0
        d=make_driver()
        total=len(df)-start
        for n,i in enumerate(range(start,len(df)),1):
            code=str(df.iat[i,0]).strip().replace(" ","").upper()
            status.set(f"{n}/{total}  {code}  [{region}]")
            if not CODE_RE.fullmatch(code):
                df.iat[i,1]="형식오류(8자리 확인)"
            else:
                try:
                    a=search_one(d,code,region)
                    df.iat[i,1]=a or "검색실패"
                except Exception as e:
                    df.iat[i,1]="검색오류: "+type(e).__name__
            out=os.path.splitext(path)[0]+"_주소결과.xlsx"
            # Save frequently so progress is not lost.
            if n%2==0: df.to_excel(out,index=False,header=False)
            bar["value"]=n*100/max(total,1)
            root.update_idletasks()
        out=os.path.splitext(path)[0]+"_주소결과.xlsx"
        df.to_excel(out,index=False,header=False)
        status.set("완료")
        root.after(0,lambda:messagebox.showinfo("완료",f"결과 파일:\n{out}"))
    except Exception as e:
        status.set("오류 발생")
        root.after(0,lambda m=str(e):messagebox.showerror("오류",m))
        print(traceback.format_exc())
    finally:
        if d:
            try:d.quit()
            except:pass

def main():
    r=tk.Tk()
    r.title("전산화번호 → 주소 찾기")
    r.geometry("700x380")
    r.resizable(False,False)
    p=tk.StringVar()
    region=tk.StringVar(value="경기")
    s=tk.StringVar(value="엑셀 파일과 검색 권역을 선택하세요.")
    ttk.Label(r,text="전산화번호 주소 찾기",font=("맑은 고딕",18,"bold")).pack(pady=(18,8))
    ttk.Label(r,text="① 검색 권역을 먼저 선택하세요").pack()
    ttk.Combobox(r,textvariable=region,values=REGIONS,state="readonly",width=18).pack(pady=7)
    row=ttk.Frame(r); row.pack(fill="x",padx=25,pady=8)
    ttk.Entry(row,textvariable=p).pack(side="left",fill="x",expand=True)
    ttk.Button(row,text="엑셀 선택",
        command=lambda:p.set(filedialog.askopenfilename(filetypes=[("Excel 파일","*.xlsx")]))).pack(side="left",padx=8)
    bar=ttk.Progressbar(r,length=630,mode="determinate"); bar.pack(pady=18)
    ttk.Label(r,textvariable=s).pack()
    def start():
        if not os.path.isfile(p.get()):
            messagebox.showwarning("확인","엑셀 파일을 먼저 선택하세요."); return
        threading.Thread(target=run,args=(p.get(),region.get(),s,bar,r),daemon=True).start()
    ttk.Button(r,text="검색 시작",command=start).pack(pady=15)
    r.mainloop()

if __name__=="__main__": main()
