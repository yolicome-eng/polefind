import os
import re
import sys
import time
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

URL="https://elecmap.kr/search/single"
PATTERN=re.compile(r"^\d{4}[A-Za-z]\d{3}$")

def make_driver():
    o=Options()
    o.add_argument("--headless=new"); o.add_argument("--disable-gpu")
    o.add_argument("--no-sandbox"); o.add_argument("--disable-dev-shm-usage")
    o.add_argument("--window-size=1600,1200"); o.add_argument("--lang=ko-KR")
    return webdriver.Chrome(options=o)

def search_one(driver, code):
    driver.get(URL)
    inp=WebDriverWait(driver,15).until(EC.element_to_be_clickable((By.CSS_SELECTOR,"input[placeholder*='전산화번호']")))
    inp.clear(); inp.send_keys(code)
    buttons=driver.find_elements(By.XPATH,"//button[contains(normalize-space(.),'검색')]")
    for b in buttons:
        if b.is_displayed() and b.is_enabled():
            b.click(); break
    end=time.time()+8
    while time.time()<end:
        text=driver.find_element(By.TAG_NAME,"body").text
        for label in ("도로명주소","도로명 주소","주소","소재지"):
            m=re.search(re.escape(label)+r"\s*[:：]?\s*(.+)",text)
            if m and m.group(1).strip()!=code and len(m.group(1).strip())>4:
                return m.group(1).strip()
        m=re.search(r"[가-힣0-9·]+(?:시|군|구)\s+[가-힣0-9·]+(?:대로|로|길)\s+\d+(?:[-~]\d+)?(?:\s*\([^)]*\))?",text)
        if m: return m.group(0).strip()
        time.sleep(.4)
    return ""

def run(path,status,bar,root):
    driver=None
    try:
        df=pd.read_excel(path,header=None)
        if df.shape[1]<2: df[1]=""
        driver=make_driver()
        total=len(df)
        for i,v in enumerate(df.iloc[:,0].fillna("").astype(str)):
            code=v.strip().replace(" ","").upper()
            status.set(f"{i+1}/{total}  {code}")
            if not PATTERN.fullmatch(code):
                df.iat[i,1]="형식오류"
            else:
                try: df.iat[i,1]=search_one(driver,code) or "검색결과없음"
                except Exception: df.iat[i,1]="오류"
            bar["value"]=(i+1)*100/max(total,1); root.update_idletasks()
        driver.quit()
        out=os.path.splitext(path)[0]+"_주소결과.xlsx"
        df.to_excel(out,index=False,header=False)
        status.set("완료")
        root.after(0,lambda:messagebox.showinfo("완료",f"완료되었습니다.\n\n{out}"))
    except Exception as e:
        if driver:
            try: driver.quit()
            except Exception: pass
        status.set("오류")
        root.after(0,lambda:messagebox.showerror("오류",str(e)))

def main():
    root=tk.Tk(); root.title("전산화번호 → 주소 찾기"); root.geometry("560x230"); root.resizable(False,False)
    path=tk.StringVar(); status=tk.StringVar(value="엑셀 파일을 선택하세요.")
    ttk.Label(root,text="전산화번호 주소 찾기",font=("맑은 고딕",16,"bold")).pack(pady=(18,8))
    row=ttk.Frame(root); row.pack(fill="x",padx=25)
    ttk.Entry(row,textvariable=path).pack(side="left",fill="x",expand=True)
    ttk.Button(row,text="엑셀 선택",command=lambda:path.set(filedialog.askopenfilename(filetypes=[("Excel","*.xlsx")]))).pack(side="left",padx=(8,0))
    bar=ttk.Progressbar(root,length=500,mode="determinate"); bar.pack(pady=18)
    ttk.Label(root,textvariable=status).pack()
    def start():
        if not path.get() or not os.path.isfile(path.get()):
            messagebox.showwarning("확인","엑셀 파일을 먼저 선택하세요."); return
        threading.Thread(target=run,args=(path.get(),status,bar,root),daemon=True).start()
    ttk.Button(root,text="검색 시작",command=start).pack(pady=12)
    root.mainloop()
if __name__=="__main__": main()
