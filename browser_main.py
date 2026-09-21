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

def make_driver():
    o=Options()
    o.add_argument("--disable-notifications")
    o.add_argument("--disable-popup-blocking")
    o.add_argument("--start-maximized")
    return webdriver.Chrome(options=o)

def clean(driver, main):
    for h in list(driver.window_handles):
        if h != main:
            try: driver.switch_to.window(h); driver.close()
            except: pass
    try: driver.switch_to.window(main)
    except: pass
    for sel in ["button[aria-label*='닫기']","button[aria-label*='Close']","[class*='close']","[id*='close']"]:
        try:
            for e in driver.find_elements(By.CSS_SELECTOR,sel)[:10]:
                if e.is_displayed():
                    try: driver.execute_script("arguments[0].click();",e)
                    except: pass
        except: pass

def body(driver):
    try: return driver.find_element(By.TAG_NAME,"body").text
    except: return ""

def address(text):
    lines=[x.strip() for x in text.splitlines() if x.strip()]
    for i,x in enumerate(lines):
        if x in ("주소","도로명주소","지번주소","소재지") and i+1<len(lines): return lines[i+1]
    for x in lines:
        if len(x)>8 and re.search(r"(특별시|광역시|특별자치시|특별자치도|도)\s+.+",x) and re.search(r"(대로|로|길)\s*\d+",x):
            if not any(k in x for k in ("전산화번호","검색 준비","검색 중","지도에서")): return x
    return ""

def search(driver,code):
    main=driver.current_window_handle
    driver.get(URL)
    WebDriverWait(driver,25).until(EC.presence_of_element_located((By.CSS_SELECTOR,"input")))
    clean(driver,main)
    target=None
    for e in driver.find_elements(By.CSS_SELECTOR,"input"):
        if e.is_displayed() and (e.get_attribute("type") or "")!="file" and "전산화번호" in (e.get_attribute("placeholder") or ""):
            target=e; break
    if not target: return ""
    target.click(); target.clear(); target.send_keys(code)
    clicked=False
    try:
        form=target.find_element(By.XPATH,"./ancestor::form[1]")
        for b in form.find_elements(By.TAG_NAME,"button"):
            if b.is_displayed() and "검색" in b.text:
                driver.execute_script("arguments[0].click();",b); clicked=True; break
    except: pass
    if not clicked:
        target.send_keys(Keys.ENTER)
    end=time.time()+40
    while time.time()<end:
        clean(driver,main)
        t=body(driver)
        a=address(t)
        if a: return a
        for b in driver.find_elements(By.TAG_NAME,"button"):
            try:
                if b.is_displayed() and "지도에서 보기" in b.text:
                    driver.execute_script("arguments[0].click();",b); time.sleep(1); break
            except: pass
        a=address(body(driver))
        if a: return a
        time.sleep(.8)
    return ""

def run(path,status,bar,root):
    d=None
    try:
        df=pd.read_excel(path,header=None)
        if df.shape[1]<2: df[1]=""
        d=make_driver(); total=len(df)
        for i,v in enumerate(df.iloc[:,0].fillna("").astype(str)):
            code=v.strip().replace(" ","").upper(); status.set(f"{i+1}/{total}  {code}")
            if not CODE_RE.fullmatch(code): df.iat[i,1]="형식오류(8자리 확인)"
            else:
                try: df.iat[i,1]=search(d,code) or "검색실패"
                except Exception as e: df.iat[i,1]="검색오류: "+type(e).__name__
            bar["value"]=(i+1)*100/max(total,1); root.update_idletasks()
        out=os.path.splitext(path)[0]+"_주소결과.xlsx"; df.to_excel(out,index=False,header=False)
        status.set("완료"); root.after(0,lambda:messagebox.showinfo("완료",f"결과 파일:\n{out}"))
    except Exception as e:
        status.set("오류 발생"); root.after(0,lambda d=str(e):messagebox.showerror("오류",d)); print(traceback.format_exc())
    finally:
        if d:
            try:d.quit()
            except:pass

def main():
    r=tk.Tk(); r.title("전산화번호 → 주소 찾기"); r.geometry("700x300"); r.resizable(False,False)
    p=tk.StringVar(); s=tk.StringVar(value="엑셀 파일을 선택하세요.")
    ttk.Label(r,text="전산화번호 주소 찾기",font=("맑은 고딕",18,"bold")).pack(pady=(18,10))
    row=ttk.Frame(r); row.pack(fill="x",padx=25)
    ttk.Entry(row,textvariable=p).pack(side="left",fill="x",expand=True)
    ttk.Button(row,text="엑셀 선택",command=lambda:p.set(filedialog.askopenfilename(filetypes=[("Excel 파일","*.xlsx")]))).pack(side="left",padx=8)
    bar=ttk.Progressbar(r,length=630,mode="determinate"); bar.pack(pady=20)
    ttk.Label(r,textvariable=s).pack()
    def start():
        if not os.path.isfile(p.get()): messagebox.showwarning("확인","엑셀 파일을 먼저 선택하세요."); return
        threading.Thread(target=run,args=(p.get(),s,bar,r),daemon=True).start()
    ttk.Button(r,text="검색 시작",command=start).pack(pady=15); r.mainloop()
if __name__=="__main__": main()
