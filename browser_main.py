import os,re,time,threading,tkinter as tk,pandas as pd
from tkinter import filedialog,messagebox,ttk
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import Select
URL="https://elecmap.kr/search/single"
REGIONS=["서울","경기","인천","강원","충북","충남","전북","전남","경북","경남"]
UI={"검색","검색 시작","지도에서 보기","확인","취소","×","검색 중...","검색 준비 중...","전산화번호","주소","도로명주소","지번주소"}
def norm(x): return re.sub(r"\\s+"," ",str(x or "")).strip()
def shown(e):
    try:return e.is_displayed() and e.is_enabled()
    except:return False
def body(d):
    try:return norm(d.find_element(By.TAG_NAME,"body").text)
    except:return ""
def alert(d):
    try:a=d.switch_to.alert;s=a.text;a.accept();return s
    except:return ""
def click(d,label):
    for e in d.find_elements(By.XPATH,"//*[self::button or self::a or @role='button' or self::input]"):
        try:
            if shown(e) and norm(e.get_attribute("value") or e.text)==label:
                d.execute_script("arguments[0].scrollIntoView({block:'center'});",e)
                ActionChains(d).move_to_element(e).pause(.08).click().perform();time.sleep(.3);return True
        except:pass
    return False
def popups(d):
    for _ in range(8):
        if alert(d):continue
        b=body(d)
        if "위치를 선택해주세요" in b and click(d,"확인"):continue
        if "선택한 권역에서 찾을 수 없어 다른 권역에서 검색했습니다" in b and (click(d,"취소") or click(d,"확인")):continue
        break
def region(d,r):
    for _ in range(30):
        popups(d)
        for s in d.find_elements(By.TAG_NAME,"select"):
            try:
                if not shown(s):continue
                for o in s.find_elements(By.TAG_NAME,"option"):
                    if norm(o.text)==r or norm(o.text).startswith(r+" "):
                        try:Select(s).select_by_visible_text(o.text)
                        except:d.execute_script("arguments[0].value=arguments[1];arguments[0].dispatchEvent(new Event('change',{bubbles:true}));",s,o.get_attribute("value"))
                        time.sleep(.7);return True
            except:pass
        time.sleep(.25)
    return False
def input_code(d,c):
    for e in d.find_elements(By.CSS_SELECTOR,"input"):
        try:
            if shown(e) and "전산화번호" in (e.get_attribute("placeholder") or ""):
                e.click();e.send_keys(Keys.CONTROL,"a");e.send_keys(c);return True
        except:pass
    return False
def extract(d,c):
    try: els=d.find_elements(By.XPATH,"//*[contains(normalize-space(.),%r)]"%c)
    except: els=[]
    cand=[]
    for e in els:
        try:
            if not shown(e):continue
            p=e
            for _ in range(7):
                ls=[norm(x) for x in p.text.splitlines() if norm(x)]
                if c in " ".join(ls) and 2<=len(ls)<=20:cand.append(ls)
                p=p.find_element(By.XPATH,"..")
        except:pass
    for ls in sorted(cand,key=len):
        for i,x in enumerate(ls):
            if c in x:
                for y in ls[i+1:i+6]:
                    if y not in UI and c not in y and len(y)>=5:return y
    return ""
def mapclick(d):
    for _ in range(15):
        popups(d)
        if click(d,"지도에서 보기"):
            time.sleep(1);return True
        time.sleep(.4)
    return False
def marker(d):
    sels=["[class*='marker']","[class*='Marker']","[class*='cluster']","[aria-label*='전주']","[title*='전주']"]
    for _ in range(15):
        popups(d)
        for s in sels:
            try:
                for e in d.find_elements(By.CSS_SELECTOR,s):
                    if shown(e):
                        ActionChains(d).move_to_element(e).pause(.1).click().perform();time.sleep(.7);return True
            except:pass
        try:ActionChains(d).send_keys(Keys.TAB,Keys.ENTER).perform()
        except:pass
        time.sleep(.4)
    return False
def one(d,r,c):
    d.get(URL);time.sleep(1.2);popups(d)
    if not region(d,r):return "권역선택실패"
    if not input_code(d,c):return "입력실패"
    if not click(d,"검색"):return "검색버튼실패"
    end=time.time()+45
    while time.time()<end:
        popups(d)
        a=extract(d,c)
        if a:return a
        if mapclick(d):
            marker(d);popups(d);a=extract(d,c)
            if a:return a
        time.sleep(.6)
    return "검색결과없음"
def job(path,r,status):
    d=None
    try:
        df=pd.read_excel(path,header=None);out=df.copy()
        if out.shape[1]<2:out[1]=""
        else:out[out.shape[1]]=""
        col=out.shape[1]-1
        codes=[norm(x) for x in df.iloc[:,0] if re.fullmatch(r"[A-Za-z0-9]{8}",norm(x))]
        if not codes:raise ValueError("첫 번째 열에 8자리 전산화번호가 없습니다.")
        d=webdriver.Chrome(options=(lambda o:o)(Options()))
        d.maximize_window()
        total=len(codes)
        for i,c in enumerate(codes,1):
            status.set(f"{i}/{total}  {c} 검색 중...")
            try:a=one(d,r,c)
            except Exception as e:a="오류"
            for k in range(len(out)):
                if norm(out.iat[k,0])==c:out.iat[k,col]=a;break
            if i%2==0:
                base,_=os.path.splitext(path);out.to_excel(base+"_주소결과.xlsx",index=False,header=False)
        base,_=os.path.splitext(path);res=base+"_주소결과.xlsx";out.to_excel(res,index=False,header=False)
        status.set("완료");messagebox.showinfo("완료","주소 검색이 끝났습니다.\\n\\n"+res)
    except Exception as e:status.set("오류");messagebox.showerror("오류",str(e))
    finally:
        try:d.quit()
        except:pass
def main():
    root=tk.Tk();root.title("전산화번호 → 주소 자동검색");root.geometry("470x230");root.resizable(False,False)
    p=tk.StringVar();r=tk.StringVar(value="경기");s=tk.StringVar(value="엑셀 파일을 선택하세요.")
    tk.Label(root,text="엑셀 파일").pack(pady=(18,4));fr=tk.Frame(root);fr.pack(fill="x",padx=20)
    tk.Entry(fr,textvariable=p).pack(side="left",fill="x",expand=True)
    def pick():
        x=filedialog.askopenfilename(filetypes=[("Excel","*.xlsx")])
        if x:p.set(x)
    tk.Button(fr,text="찾기",command=pick,width=8).pack(side="left",padx=6)
    tk.Label(root,text="검색 권역").pack(pady=(14,4));ttk.Combobox(root,textvariable=r,values=REGIONS,state="readonly",width=18).pack()
    def start():
        if not p.get() or not os.path.exists(p.get()):messagebox.showwarning("확인","엑셀 파일을 선택하세요.");return
        threading.Thread(target=job,args=(p.get(),r.get(),s),daemon=True).start()
    tk.Button(root,text="검색 시작",command=start,width=20,height=2).pack(pady=12);tk.Label(root,textvariable=s).pack();root.mainloop()
if __name__=="__main__":main()
