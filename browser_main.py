import os,re,time,threading,tkinter as tk,pandas as pd
from tkinter import filedialog,messagebox,ttk
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import Select
URL="https://elecmap.kr/search/single"
REGIONS=["1권역 (경기·충청·대전·세종)","2권역 서부 (강원 서부)","2권역 동부 (강원 동부)","3권역 전북","3권역 전남","4권역 경북","4권역 경남","남해서부","울릉도","제주"]
REGION_ALIASES={
"1권역 (경기·충청·대전·세종)":["1권역","경기","충청","대전","세종"],
"2권역 서부 (강원 서부)":["2권역 서부","강원 서부"],
"2권역 동부 (강원 동부)":["2권역 동부","강원 동부"],
"3권역 전북":["3권역 전북","전북"],"3권역 전남":["3권역 전남","전남"],
"4권역 경북":["4권역 경북","경북"],"4권역 경남":["4권역 경남","경남"],
"남해서부":["남해서부"],"울릉도":["울릉도"],"제주":["제주"]}
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
def _scroll_to_element(d,e):
    try:
        d.execute_script("""
        const el=arguments[0];
        let p=el;
        for(let i=0;i<8 && p;i++,p=p.parentElement){
          try{
            const st=getComputedStyle(p);
            if((st.overflowY==='auto'||st.overflowY==='scroll'||st.overflow==='auto'||st.overflow==='scroll') && p.scrollHeight>p.clientHeight){
              p.scrollTop=Math.max(0,p.scrollHeight-p.clientHeight);
            }
          }catch(_){}
        }
        el.scrollIntoView({block:'center',inline:'center'});
        """,e)
        time.sleep(.15)
        return True
    except: return False
def click(d,label):
    for e in d.find_elements(By.XPATH,"//*[self::button or self::a or @role='button' or self::input]"):
        try:
            if shown(e) and norm(e.get_attribute("value") or e.text)==label:
                _scroll_to_element(d,e)
                try:
                    ActionChains(d).move_to_element(e).pause(.08).click().perform()
                except:
                    d.execute_script("arguments[0].click();",e)
                time.sleep(.3);return True
        except:pass
    return False
def click_search_start(d,wait=15):
    # 실제 영상처럼 배너가 위에 있어도 모달 내부를 아래로 자동 스크롤한 뒤
    # 카운트다운이 끝나면 '검색 시작'을 누른다.
    end=time.time()+wait
    while time.time()<end:
        if alert(d): continue
        try:
            els=d.find_elements(By.XPATH,"//*[self::button or self::a or @role='button' or self::input]")
            for e in els:
                try:
                    if not shown(e): continue
                    t=norm(e.get_attribute("value") or e.text)
                    if t=="검색 시작":
                        _scroll_to_element(d,e)
                        # disabled/aria-disabled 상태면 카운트다운을 더 기다린다.
                        dis=(e.get_attribute("disabled") is not None or
                             (e.get_attribute("aria-disabled") or "").lower()=="true")
                        if dis: continue
                        try:
                            ActionChains(d).move_to_element(e).pause(.1).click().perform()
                        except:
                            d.execute_script("arguments[0].click();",e)
                        time.sleep(.7)
                        return True
                except: pass
        except: pass
        # 배너가 있는 모달/스크롤 영역은 계속 아래로 내려준다.
        try:
            d.execute_script("""
            [...document.querySelectorAll('*')].forEach(p=>{
              try{
                const s=getComputedStyle(p),r=p.getBoundingClientRect();
                if(r.width>150 && r.height>80 && p.scrollHeight>p.clientHeight &&
                   (s.overflowY==='auto'||s.overflowY==='scroll'||s.overflow==='auto'||s.overflow==='scroll')){
                  p.scrollTop=Math.min(p.scrollHeight-p.clientHeight,p.scrollTop+Math.max(250,p.clientHeight*0.85));
                }
              }catch(_){}
            });
            """)
        except: pass
        time.sleep(.35)
    return False
CLOSE_WORDS={"×","✕","X","닫기","확인","취소","닫기","close","CLOSE","OK","확인하기"}
DONE_WORDS=("찾기 완료","검색 완료","검색이 완료","완료되었습니다","검색을 완료")
def _click_visible_close(d):
    # 일반 DOM의 닫기/확인 버튼을 먼저 찾는다.
    for e in d.find_elements(By.XPATH,"//*[self::button or self::a or @role='button' or self::input]"):
        try:
            if not shown(e): continue
            t=norm(e.get_attribute("aria-label") or e.get_attribute("title") or e.get_attribute("value") or e.text)
            if t in CLOSE_WORDS or any(x in t.lower() for x in ("close","dismiss")):
                d.execute_script("arguments[0].scrollIntoView({block:'center'});",e)
                d.execute_script("arguments[0].click();",e);time.sleep(.25);return True
        except: pass
    return False
def _click_fixed_overlay_close(d):
    # 화면을 덮는 fixed/sticky 모달/배너의 닫기 버튼을 z-index 순으로 찾는다.
    js="""
    const words=['×','✕','x','닫기','확인','취소','close','dismiss','ok'];
    const els=[...document.querySelectorAll('button,a,[role=button],input[type=button],input[type=submit]')];
    const good=els.filter(e=>{
      const s=getComputedStyle(e), r=e.getBoundingClientRect();
      if(s.display==='none'||s.visibility==='hidden'||r.width<8||r.height<8)return false;
      const z=parseInt(s.zIndex)||0;
      if(s.position!=='fixed'&&s.position!=='sticky'&&z<10)return false;
      const t=(e.getAttribute('aria-label')||e.getAttribute('title')||e.value||e.innerText||'').trim().toLowerCase();
      return words.includes(t)||t.includes('close')||t.includes('dismiss')||t==='x';
    }).sort((a,b)=>(parseInt(getComputedStyle(b).zIndex)||0)-(parseInt(getComputedStyle(a).zIndex)||0));
    if(good.length){good[0].click();return true} return false;
    """
    try:return bool(d.execute_script(js))
    except:return False
def _done_popup(d):
    b=body(d)
    if any(x in b for x in DONE_WORDS):
        # 완료 팝업 안의 확인/닫기만 누른다.
        return _click_visible_close(d) or _click_fixed_overlay_close(d)
    return False
def popups(d):
    # 광고/배너는 닫지 않는다. 영상과 동일하게 모달 안을 아래로 내리고
    # 카운트다운 종료 후 '검색 시작'을 누르는 흐름으로 처리한다.
    for _ in range(4):
        if alert(d): continue
        b=body(d)
        if ("검색 준비 중" in b or "전주 검색 준비 중" in b or "5초 후 검색이 시작됩니다"):
            click_search_start(d,15)
            continue
        if "위치를 선택해주세요" in b and click(d,"확인"):
            continue
        if "선택한 권역에서 찾을 수 없어 다른 권역에서 검색했습니다" in b:
            if click(d,"취소") or click(d,"확인"): continue
        break
    return True
def region(d,r):
    aliases=REGION_ALIASES.get(r,[r])
    for _ in range(40):
        popups(d)
        selects=[s for s in d.find_elements(By.TAG_NAME,"select") if shown(s)]
        for s in selects:
            try:
                opts=s.find_elements(By.TAG_NAME,"option")
                for o in opts:
                    txt=norm(o.text)
                    if any(txt==a or a in txt for a in aliases):
                        try:
                            Select(s).select_by_visible_text(o.text)
                        except Exception:
                            d.execute_script("arguments[0].value=arguments[1];arguments[0].dispatchEvent(new Event('input',{bubbles:true}));arguments[0].dispatchEvent(new Event('change',{bubbles:true}));",s,o.get_attribute("value"))
                        time.sleep(1.0)
                        return True
            except Exception: pass
        time.sleep(.3)
    return False
def input_code(d,c):
    for e in d.find_elements(By.CSS_SELECTOR,"input"):
        try:
            if shown(e) and "전산화번호" in (e.get_attribute("placeholder") or ""):
                e.click();e.send_keys(Keys.CONTROL,"a");e.send_keys(c);return True
        except:pass
    return False
def _looks_address(s):
    s=norm(s)
    if len(s)<6 or len(s)>120:return False
    # 국내 지번/도로명 주소에서 흔히 등장하는 행정구역 + 번지/도로번호 패턴
    has_area=bool(re.search(r"(특별시|광역시|특별자치시|특별자치도|[가-힣]+도|[가-힣]+시|[가-힣]+군|[가-힣]+구)",s))
    has_place=bool(re.search(r"(읍|면|동|리|로|길|대로)",s))
    has_num=bool(re.search(r"\\d",s))
    return has_area and has_place and has_num
def extract(d,c):
    # 1) 결과 카드/마커 팝업 안에서 전산화번호 바로 아래 주소를 우선한다.
    try: els=d.find_elements(By.XPATH,"//*[contains(normalize-space(.),%r)]"%c)
    except: els=[]
    cand=[]
    for e in els:
        try:
            if not shown(e):continue
            p=e
            for _ in range(9):
                ls=[norm(x) for x in p.text.splitlines() if norm(x)]
                if c in " ".join(ls) and 2<=len(ls)<=30:cand.append(ls)
                p=p.find_element(By.XPATH,"..")
        except:pass
    seen=set()
    for ls in sorted(cand,key=len):
        key="\\n".join(ls)
        if key in seen: continue
        seen.add(key)
        for i,x in enumerate(ls):
            if c in x:
                for y in ls[i+1:i+10]:
                    if y not in UI and c not in y and _looks_address(y):
                        return y
    # 2) 주소가 카드의 다른 줄에 있으면 카드 전체에서 주소처럼 보이는 줄을 찾는다.
    for ls in sorted(cand,key=len):
        for y in ls:
            if y not in UI and c not in y and _looks_address(y):
                return y
    return ""
def mapclick(d):
    for _ in range(15):
        popups(d)
        if click(d,"지도에서 보기"):
            time.sleep(1);return True
        time.sleep(.4)
    return False
def marker(d,c):
    # 먼저 결과 카드 자체를 클릭해 주소 팝업을 연다.
    try:
        els=d.find_elements(By.XPATH,"//*[contains(normalize-space(.),%r)]"%c)
        for e in els:
            try:
                if not shown(e): continue
                p=e
                for _ in range(5):
                    if shown(p):
                        role=(p.get_attribute("role") or "").lower()
                        tag=(p.tag_name or "").lower()
                        cls=(p.get_attribute("class") or "").lower()
                        if role=="button" or tag in ("button","a") or any(x in cls for x in ("card","result","marker","popup","info")):
                            _scroll_to_element(d,p)
                            try: ActionChains(d).move_to_element(p).pause(.1).click().perform()
                            except: d.execute_script("arguments[0].click();",p)
                            time.sleep(.8)
                            if extract(d,c): return True
                    p=p.find_element(By.XPATH,"..")
            except: pass
    except: pass
    # 카드가 없으면 지도 마커를 클릭하고, 열린 팝업에서 주소를 읽는다.
    sels=["[class*='marker']","[class*='Marker']","[class*='cluster']","[aria-label*='전주']","[title*='전주']"]
    for _ in range(20):
        for s in sels:
            try:
                for e in d.find_elements(By.CSS_SELECTOR,s):
                    if shown(e):
                        _scroll_to_element(d,e)
                        try: ActionChains(d).move_to_element(e).pause(.1).click().perform()
                        except: d.execute_script("arguments[0].click();",e)
                        time.sleep(.8)
                        if extract(d,c): return True
            except:pass
        try:ActionChains(d).send_keys(Keys.TAB,Keys.ENTER).perform()
        except:pass
        time.sleep(.4)
        if extract(d,c): return True
    return False
def one(d,r,c):
    try: d.get(URL)
    except Exception: pass
    time.sleep(1.0);popups(d)
    if not region(d,r):return "권역선택실패"
    popups(d)
    if not input_code(d,c):return "입력실패"
    popups(d)
    if not click(d,"검색"):return "검색버튼실패"
    end=time.time()+45
    while time.time()<end:
        popups(d)
        a=extract(d,c)
        if a:return a
        if mapclick(d):
            marker(d,c);popups(d);a=extract(d,c)
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
        opts=Options()
        opts.add_experimental_option("prefs",{
            "profile.default_content_setting_values.geolocation":1,
            "profile.default_content_setting_values.notifications":1
        })
        opts.page_load_strategy="eager"
        d=webdriver.Chrome(options=opts)
        d.set_page_load_timeout(25)
        try:
            d.execute_cdp_cmd("Browser.grantPermissions",{
                "origin":"https://elecmap.kr",
                "permissions":["geolocation"]
            })
        except Exception:
            pass
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
    p=tk.StringVar();r=tk.StringVar(value="1권역 (경기·충청·대전·세종)");s=tk.StringVar(value="엑셀 파일을 선택하세요.")
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
