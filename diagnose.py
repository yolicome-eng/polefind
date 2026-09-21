import os, time, json, traceback, threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

URL="https://elecmap.kr/search/single"

def make_driver():
    o=Options()
    o.add_argument("--start-maximized")
    o.add_argument("--disable-notifications")
    o.add_argument("--lang=ko-KR")
    o.set_capability("goog:loggingPrefs", {"performance":"ALL","browser":"ALL"})
    o.set_capability("unhandledPromptBehavior","dismiss")
    return webdriver.Chrome(options=o)

def dump(driver, fp, label):
    fp.write("\n\n===== "+label+" =====\n")
    try:
        fp.write("TITLE: "+driver.title+"\nURL: "+driver.current_url+"\n")
    except: pass
    try:
        fp.write("WINDOWS: "+json.dumps([(h, (driver.switch_to.window(h), driver.title, driver.current_url)[1:]) for h in driver.window_handles], ensure_ascii=False)+"\n")
    except:
        pass
    try:
        fp.write("BODY:\n"+driver.find_element(By.TAG_NAME,"body").text[:50000]+"\n")
    except: pass
    try:
        fp.write("HTML:\n"+driver.page_source[:120000]+"\n")
    except: pass
    try:
        logs=driver.get_log("browser")
        if logs: fp.write("BROWSER LOGS:\n"+json.dumps(logs,ensure_ascii=False)+"\n")
    except: pass
    try:
        for item in driver.get_log("performance"):
            msg=json.loads(item["message"])["message"]
            if msg.get("method") in ("Network.requestWillBeSent","Network.responseReceived"):
                p=msg.get("params",{})
                obj=p.get("request",p.get("response",{}))
                url=obj.get("url","")
                typ=p.get("type","")
                if url and ("elecmap" in url or typ in ("Fetch","XHR","Document","Script")):
                    fp.write("NET "+msg["method"]+" TYPE="+str(typ)+" URL="+url+"\n")
                    if msg.get("method")=="Network.requestWillBeSent":
                        r=p.get("request",{})
                        if r.get("postData"): fp.write("POST="+r["postData"]+"\n")
    except: pass

def close_extra_windows(driver, main):
    for h in list(driver.window_handles):
        if h != main:
            try:
                driver.switch_to.window(h)
                driver.close()
            except: pass
    try: driver.switch_to.window(main)
    except: pass

def run(path,status,root):
    driver=None
    base=os.path.splitext(path)[0]
    txt=base+"_진단2.txt"
    png=base+"_진단2.png"
    try:
        df=pd.read_excel(path,header=None)
        vals=[str(x).strip().replace(" ","").upper() for x in df.iloc[:,0].fillna("") if str(x).strip()]
        if not vals: raise ValueError("첫 번째 열에 전산화번호가 없습니다.")
        code=vals[0]
        status.set("실제 Chrome 실행 중...")
        driver=make_driver()
        main=None
        with open(txt,"w",encoding="utf-8") as fp:
            fp.write("ElecMap 실제 브라우저 진단\nTEST CODE="+code+"\n")
            driver.get(URL)
            main=driver.current_window_handle
            time.sleep(3)
            dump(driver,fp,"PAGE OPEN")
            inp=WebDriverWait(driver,25).until(EC.element_to_be_clickable((By.CSS_SELECTOR,"input[placeholder*='전산화번호']")))
            inp.clear(); inp.send_keys(code)
            dump(driver,fp,"AFTER INPUT")
            buttons=driver.find_elements(By.XPATH,"//button[contains(normalize-space(.),'검색')]")
            for b in buttons:
                try:
                    if b.is_displayed() and b.is_enabled():
                        driver.execute_script("arguments[0].click();",b)
                        break
                except: pass
            for i in range(50):
                time.sleep(0.6)
                try:
                    driver.switch_to.window(main)
                except: pass
                close_extra_windows(driver,main)
                dump(driver,fp,"AFTER CLICK %02d"%i)
            try: driver.save_screenshot(png)
            except: pass
        driver.quit()
        status.set("진단 완료")
        root.after(0,lambda:messagebox.showinfo("진단 완료","첫 번째 번호 1건만 실제 Chrome으로 확인했습니다.\n\n진단 TXT와 PNG가 엑셀 파일과 같은 폴더에 생성되었습니다."))
    except Exception as e:
        if driver:
            try: driver.quit()
            except: pass
        status.set("오류")
        root.after(0,lambda d=str(e):messagebox.showerror("오류",d))

def main():
    root=tk.Tk(); root.title("ElecMap 실제 검색 진단"); root.geometry("700x260"); root.resizable(False,False)
    path=tk.StringVar(); status=tk.StringVar(value="엑셀 파일을 선택하세요.")
    ttk.Label(root,text="ElecMap 실제 Chrome 검색 진단",font=("맑은 고딕",17,"bold")).pack(pady=(20,12))
    row=ttk.Frame(root); row.pack(fill="x",padx=25)
    ttk.Entry(row,textvariable=path).pack(side="left",fill="x",expand=True)
    ttk.Button(row,text="엑셀 선택",command=lambda:path.set(filedialog.askopenfilename(filetypes=[("Excel","*.xlsx")]))).pack(side="left",padx=8)
    ttk.Label(root,textvariable=status).pack(pady=20)
    def start():
        if not os.path.isfile(path.get()): messagebox.showwarning("확인","엑셀 파일을 먼저 선택하세요."); return
        threading.Thread(target=run,args=(path.get(),status,root),daemon=True).start()
    ttk.Button(root,text="진단 시작",command=start).pack()
    root.mainloop()
if __name__=="__main__": main()
