import os, re, sys, time, json, traceback, threading
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
    if getattr(sys, "frozen", False):
        base=getattr(sys,"_MEIPASS",os.path.dirname(sys.executable))
        for p in [
            os.path.join(base,"selenium","webdriver","common","windows","selenium-manager.exe"),
            os.path.join(base,"selenium-manager.exe")
        ]:
            if os.path.isfile(p):
                os.environ["SE_MANAGER_PATH"]=p
                break
    o=Options()
    o.add_argument("--headless=new")
    o.add_argument("--disable-gpu")
    o.add_argument("--no-sandbox")
    o.add_argument("--disable-dev-shm-usage")
    o.add_argument("--window-size=1600,1200")
    o.add_argument("--lang=ko-KR")
    o.set_capability("goog:loggingPrefs", {"performance":"ALL","browser":"ALL"})
    return webdriver.Chrome(options=o)

def dump_logs(driver, fp):
    try:
        logs=driver.get_log("performance")
        for item in logs:
            try:
                msg=json.loads(item["message"])["message"]
                method=msg.get("method","")
                p=msg.get("params",{})
                if method=="Network.requestWillBeSent":
                    r=p.get("request",{})
                    typ=p.get("type","")
                    if typ in ("Fetch","XHR") or "/api/" in r.get("url","") or "elecmap" in r.get("url",""):
                        fp.write("\nREQUEST\n")
                        fp.write("TYPE: "+str(typ)+"\n")
                        fp.write("METHOD: "+str(r.get("method"))+"\n")
                        fp.write("URL: "+str(r.get("url"))+"\n")
                        if r.get("postData"): fp.write("POSTDATA: "+r.get("postData")+"\n")
                        fp.write("HEADERS: "+json.dumps(r.get("headers",{}),ensure_ascii=False)+"\n")
                elif method=="Network.responseReceived":
                    r=p.get("response",{})
                    typ=p.get("type","")
                    if typ in ("Fetch","XHR") or "/api/" in r.get("url","") or "elecmap" in r.get("url",""):
                        fp.write("\nRESPONSE\n")
                        fp.write("TYPE: "+str(typ)+"\n")
                        fp.write("STATUS: "+str(r.get("status"))+"\n")
                        fp.write("URL: "+str(r.get("url"))+"\n")
            except Exception:
                pass
    except Exception as e:
        fp.write("\nLOG ERROR: "+repr(e)+"\n")

def click_search(driver):
    for b in driver.find_elements(By.XPATH,"//button[contains(normalize-space(.),'검색')]"):
        try:
            if b.is_displayed() and b.is_enabled():
                driver.execute_script("arguments[0].click();",b)
                return True
        except: pass
    return False

def run(path,status,root):
    driver=None
    out=os.path.splitext(path)[0]+"_진단.txt"
    try:
        df=pd.read_excel(path,header=None)
        codes=[str(x).strip().replace(" ","").upper() for x in df.iloc[:,0].fillna("") if str(x).strip()]
        if not codes: raise ValueError("첫 번째 열에 전산화번호가 없습니다.")
        code=codes[0]
        status.set("Chrome 준비 중...")
        driver=make_driver()
        with open(out,"w",encoding="utf-8") as fp:
            fp.write("ElecMap 진단 파일\n")
            fp.write("TEST CODE: "+code+"\nURL: "+URL+"\n")
            driver.get(URL)
            time.sleep(2)
            dump_logs(driver,fp)
            inp=WebDriverWait(driver,20).until(EC.element_to_be_clickable((By.CSS_SELECTOR,"input[placeholder*='전산화번호']")))
            inp.clear(); inp.send_keys(code)
            fp.write("\n\nAFTER INPUT BODY:\n"+driver.find_element(By.TAG_NAME,"body").text+"\n")
            dump_logs(driver,fp)
            click_search(driver)
            fp.write("\n\nAFTER SEARCH CLICK BODY:\n"+driver.find_element(By.TAG_NAME,"body").text+"\n")
            for n in range(35):
                time.sleep(0.5)
                dump_logs(driver,fp)
                body=driver.find_element(By.TAG_NAME,"body").text
                fp.write("\n--- BODY "+str(n)+" ---\n"+body+"\n")
                if "검색결과" in body or "지도에서 보기" in body or "검색 완료" in body:
                    try:
                        for b in driver.find_elements(By.XPATH,"//button[contains(normalize-space(.),'지도에서 보기')]"):
                            if b.is_displayed() and b.is_enabled():
                                driver.execute_script("arguments[0].click();",b); time.sleep(1); break
                    except: pass
            fp.write("\n\nFINAL HTML:\n"+driver.page_source[:300000])
            try: driver.save_screenshot(out.replace(".txt",".png"))
            except: pass
            dump_logs(driver,fp)
        status.set("진단 완료")
        driver.quit()
        root.after(0,lambda:messagebox.showinfo("진단 완료",f"첫 번째 번호 1개만 테스트했습니다.\n\n진단 파일:\n{out}\n\n이 파일을 보내주시면 실제 검색 API를 확인해서 다음 버전을 만들겠습니다."))
    except Exception as e:
        if driver:
            try: driver.quit()
            except: pass
        status.set("오류")
        root.after(0,lambda d=str(e):messagebox.showerror("오류",d))

def main():
    root=tk.Tk(); root.title("ElecMap 검색 진단"); root.geometry("680x250"); root.resizable(False,False)
    path=tk.StringVar(); status=tk.StringVar(value="엑셀 파일을 선택하세요.")
    ttk.Label(root,text="ElecMap 실제 검색 방식 확인",font=("맑은 고딕",17,"bold")).pack(pady=(20,12))
    row=ttk.Frame(root); row.pack(fill="x",padx=25)
    ttk.Entry(row,textvariable=path).pack(side="left",fill="x",expand=True)
    ttk.Button(row,text="엑셀 선택",command=lambda:path.set(filedialog.askopenfilename(filetypes=[("Excel","*.xlsx")]))).pack(side="left",padx=8)
    ttk.Label(root,textvariable=status).pack(pady=20)
    def start():
        if not os.path.isfile(path.get()):
            messagebox.showwarning("확인","엑셀 파일을 먼저 선택하세요."); return
        threading.Thread(target=run,args=(path.get(),status,root),daemon=True).start()
    ttk.Button(root,text="진단 시작",command=start).pack()
    root.mainloop()
if __name__=="__main__": main()
