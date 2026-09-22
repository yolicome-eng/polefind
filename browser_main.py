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
    o.add_argument("--disable-notifications"); o.add_argument("--disable-popup-blocking")
    o.add_argument("--start-maximized"); o.add_argument("--lang=ko-KR")
    o.set_capability("unhandledPromptBehavior","ignore")
    return webdriver.Chrome(options=o)

def txt(e):
    try: return (e.text or "").strip()
    except: return ""

def page_text(d):
    try: return d.find_element(By.TAG_NAME,"body").text
    except: return ""

def real_address(text):
    lines=[re.sub(r"\s+"," ",x).strip() for x in text.splitlines() if x.strip()]
    bad={"강원 동부","강원동부","검색 중...","검색 준비 중...","검색 시작","지도에서 보기","전산화번호"}
    def ok(x):
        if x in bad or len(x)<7 or len(x)>180: return False
        if re.fullmatch(r"(서울|경기|인천|강원|충북|충남|전북|전남|경북|경남)(\s*(동부|서부|남부|북부|권))?",x): return False
        has_num=bool(re.search(r"(대로|로|길)\s*\d+(?:-\d+)?",x) or re.search(r"(읍|면|동|리)\s*\d+(?:-\d+)?",x))
        has_area=bool(re.search(r"(특별시|광역시|특별자치시|특별자치도|도|시|군|구)",x))
        return has_num and has_area
    labels={"주소","도로명주소","지번주소","소재지","도로명 주소","지번 주소"}
    for i,x in enumerate(lines):
        if x in labels:
            for y in lines[i+1:i+5]:
                if ok(y): return y
    # Prefer lines close to the searched code.
    for i,x in enumerate(lines):
        if re.search(r"전산화번호",x):
            for y in lines[i:i+8]:
                if ok(y): return y
    for x in lines:
        if ok(x): return x
    return ""

def choose_region(d, region):
    deadline=time.time()+12
    while time.time()<deadline:
        # Native select: select the option by visible text, not by guessed value.
        for s in d.find_elements(By.CSS_SELECTOR,"select"):
            try:
                if not s.is_displayed(): continue
                opts=s.find_elements(By.TAG_NAME,"option")
                match=next((o for o in opts if o.text.strip()==region or region in o.text.strip()),None)
                if match:
                    try:
                        Select(s).select_by_visible_text(match.text.strip())
                    except:
                        d.execute_script("arguments[0].value=arguments[1];arguments[0].dispatchEvent(new Event('change',{bubbles:true}));",s,match.get_attribute("value"))
                    time.sleep(.8)
                    return True
            except: pass
        # Custom dropdowns.
        for e in d.find_elements(By.XPATH,"//*[self::button or @role='option' or @role='button']"):
            try:
                if e.is_displayed() and txt(e)==region:
                    d.execute_script("arguments[0].click();",e); time.sleep(.5); return True
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

def click_visible_text(d, text):
    for e in d.find_elements(By.XPATH,"//*[self::button or self::a or @role='button']"):
        try:
            if e.is_displayed() and text in txt(e):
                d.execute_script("arguments[0].click();",e); return True
        except: pass
    return False

def inspect_all_windows(d, main, code):
    # Never close a result window. Search every open window and every iframe.
    handles=list(d.window_handles)
    for h in handles:
        try:
            d.switch_to.window(h)
            for frame in [None]+d.find_elements(By.TAG_NAME,"iframe"):
                try:
                    d.switch_to.default_content()
                    if frame is not None: d.switch_to.frame(frame)
                    t=page_text(d)
                    if code in t:
                        a=real_address(t)
                        if a: return a
                    a=real_address(t)
                    if a: return a
                except: pass
            d.switch_to.default_content()
        except: pass
    try: d.switch_to.window(main)
    except: pass
    return ""

def search_one(d, code, region):
    d.get(URL)
    WebDriverWait(d,30).until(EC.presence_of_element_located((By.TAG_NAME,"body")))
    time.sleep(1)
    choose_region(d,region)

    target=WebDriverWait(d,20).until(lambda x: next((e for e in x.find_elements(By.CSS_SELECTOR,"input") if e.is_displayed() and "전산화번호" in (e.get_attribute("placeholder") or "")),None))
    target.click(); target.clear(); target.send_keys(code)

    # Click the actual single-search button.
    buttons=d.find_elements(By.XPATH,"//button[contains(normalize-space(.),'검색')]")
    clicked=False
    for b in buttons:
        try:
            if b.is_displayed() and b.is_enabled():
                d.execute_script("arguments[0].click();",b); clicked=True; break
        except: pass
    if not clicked: target.send_keys(Keys.ENTER)

    main=d.current_window_handle
    deadline=time.time()+65
    map_clicked=False
    while time.time()<deadline:
        dismiss_prompt(d)
        a=inspect_all_windows(d,main,code)
        if a: return a

        # Wait for the site's result and then explicitly open "지도에서 보기".
        try:
            for b in d.find_elements(By.XPATH,"//*[self::button or self::a or @role='button']"):
                if b.is_displayed() and "지도에서 보기" in txt(b):
                    before=set(d.window_handles)
                    d.execute_script("arguments[0].click();",b)
                    map_clicked=True
                    time.sleep(1.2)
                    after=set(d.window_handles)
                    for h in after-before:
                        try: d.switch_to.window(h); break
                        except: pass
                    break
        except: pass

        a=inspect_all_windows(d,main,code)
        if a: return a

        # If the map is inline, click only elements whose accessible text/title indicates a marker.
        try:
            d.switch_to.window(main)
            sels=["[aria-label*='마커']","[aria-label*='marker']","[title*='주소']","[title*='전주']","[class*='marker']","[class*='Marker']"]
            for sel in sels:
                found=False
                for e in d.find_elements(By.CSS_SELECTOR,sel):
                    try:
                        if e.is_displayed():
                            d.execute_script("arguments[0].click();",e); found=True; break
                    except: pass
                if found: break
        except: pass
        a=inspect_all_windows(d,main,code)
        if a: return a
        time.sleep(.8)

    try: d.switch_to.window(main)
    except: pass
    return ""

def run(path,region,status,bar,root):
    d=None
    try:
        df=pd.read_excel(path,header=None)
        if df.shape[1]<2: df[1]=""
        # Skip a header row instead of turning it into an error result.
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
            if n%2==0: df.to_excel(out,index=False,header=False)
            bar["value"]=n*100/max(total,1); root.update_idletasks()
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
    r=tk.Tk(); r.title("전산화번호 → 주소 찾기"); r.geometry("700x380"); r.resizable(False,False)
    p=tk.StringVar(); region=tk.StringVar(value="경기"); s=tk.StringVar(value="엑셀 파일과 검색 권역을 선택하세요.")
    ttk.Label(r,text="전산화번호 주소 찾기",font=("맑은 고딕",18,"bold")).pack(pady=(18,8))
    ttk.Label(r,text="① 검색 권역을 먼저 선택하세요").pack()
    ttk.Combobox(r,textvariable=region,values=REGIONS,state="readonly",width=18).pack(pady=7)
    row=ttk.Frame(r); row.pack(fill="x",padx=25,pady=8)
    ttk.Entry(row,textvariable=p).pack(side="left",fill="x",expand=True)
    ttk.Button(row,text="엑셀 선택",command=lambda:p.set(filedialog.askopenfilename(filetypes=[("Excel 파일","*.xlsx")]))).pack(side="left",padx=8)
    bar=ttk.Progressbar(r,length=630,mode="determinate"); bar.pack(pady=18)
    ttk.Label(r,textvariable=s).pack()
    def start():
        if not os.path.isfile(p.get()):
            messagebox.showwarning("확인","엑셀 파일을 먼저 선택하세요."); return
        threading.Thread(target=run,args=(p.get(),region.get(),s,bar,r),daemon=True).start()
    ttk.Button(r,text="검색 시작",command=start).pack(pady=15)
    r.mainloop()

if __name__=="__main__": main()
