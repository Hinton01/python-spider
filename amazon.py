# encoding:utf-8
from bs4 import BeautifulSoup
import traceback
import requests
from eng2chs import readip
import sqlite3
from sqlite3 import IntegrityError
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import base64
import cgitb
from fake_useragent import UserAgent
from retrying import retry
cgitb.enable()


try:
    ua = UserAgent()
except:
    ua = UserAgent()
def init(first = True,pageurl = None):
    if first:
        url = 'https://www.amazon.cn/s?i=stripbooks&rh=n%3A658414051&lo=list&page=25&qid=1562399931&ref=sr_pg_24'
    else:
        url = pageurl
    res = req(url)
    if res == 'filed':
        res = req(url)

    html = BeautifulSoup(res.text)
    spider(html,url)

def spider(html,url):
    conn = sqlite3.connect(r'D:/anby/Flask/database/blog.db')
    #第一页
    books = html.find_all('a', attrs={"class": "s-access-detail-page"})
    #第一页之后
    if books == []:
        books = html.find_all('a', attrs={"class": "a-link-normal a-text-normal"})
    for book in books:
        try:
            link = book.attrs['href']
            # 第一页之后link无前缀
            if 's?i=stripbooks&rh=n%3A658390051' in link:
                continue
            if r'https://www.amazon.cn/' not in link:
                link = r'https://www.amazon.cn/' + link
            r = req(link)
            h = BeautifulSoup(r.text)
            booklink = h.find_all('a', attrs={"class": 'title-text'})
            if len(booklink) > 0:
                rlink = r'https://www.amazon.cn/' + booklink[0].attrs['href']
            else:
                continue
            r = req(rlink)
            h = BeautifulSoup(r.text)
            try:
                infos = h.find_all('div',attrs={"class":'content'})[0]
            except:
                infos = h.select('#detail_bullets_id > table > tbody > tr > td > div')[0]
            allinfo = []
            lis = infos.find_all('li')

            for li in lis:
                flag = 0
                #信息中无用项过滤
                for t in ['商品尺寸','商品重量','用户评分','商品排名','zg_hssr_rank']:
                    if t not in li.text:
                        pass
                    else:
                        flag += 1
                #包含:为正常信息 且flag为0代表有用信息
                if flag == 0 and ':' in li.text:
                    allinfo.append(li.text.strip())
                    if 'ISBN' in li.text:
                        isbn = li.text.split(':')[1]
                        #有多个ISBN的情况
                        if ',' in isbn:
                            isbn = [x for x in isbn.split(',') if len(x)==14][0]
                    if 'ASIN' in li.text:
                        itemno = li.text.split(':')[1]
                    else:
                        inemno = isbn

            allinfo = ('\n').join(allinfo).replace('\'','’')

            author = h.find('span',attrs={"class":'author'}).text.replace('\n','').replace('(作者)','').replace(',','')
            #图书标题 亚马逊个别书名后接括号里内容过长的删去
            try:
                title = h.find('span',attrs={"id":'productTitle'}).text.replace('\'','’')
            except:
                title = book.text.strip().replace('\'','’')

            for mark in ['(','（']:
                if mark in title:
                    try:
                        regs = re.search('\(.+\)',title).regs
                    except:
                        regs = re.search('（.+）', title).regs
                    for reg in regs:
                        if reg[1] - reg[0] > 5:
                            title = title[:reg[0]]

            #简介部分在iframe中 需使用selenimu动态获取
            try:
                chrome_options = Options()
                chrome_options.add_argument('--headless')
                chrome_options.add_argument('--disable-gpu')
                driver = webdriver.Chrome(chrome_options=chrome_options)
                driver.get(rlink)
                iframe = driver.find_elements_by_tag_name('iframe')[3]
                driver.switch_to.frame(iframe)  # 最重要的一步
                soup = BeautifulSoup(driver.page_source, "html.parser")
                intro = soup.select('#iframeContent')[0].text
                intro = intro.replace("'",'‘').strip()
            except:
                intro = '这是一本好书 好到不用看简介(其实是没有简介'

            #获取图书价格和当前购买页面链接
            try:
                price = h.find_all("span",attrs={"class":'a-size-base a-color-price a-color-price'})[0].text.strip().replace('￥','')
            except:
                price = h.select('#a-autoid-2-announce > span.a-color-base > span')
                if isinstance(price,list):
                    price = price[0].text.strip().replace('￥','')
            buy = '亚马逊\t' + price + '元\t' + rlink

            #图书封面
            cover = h.find('img',attrs={"class":'frontImage'}).attrs['src']
            if 'http' in cover:
                cover = req(cover).content
                cover = base64.b64encode(cover).decode('utf-8')
            else:
                cover = cover.replace('data:image/jpeg;base64,\n','')
            if 'data:image/jpeg;base64,' not in cover:
                cover += 'data:image/jpeg;base64,'

            #相关推荐书目 按ASIN码存储
            try:
                rec = h.find('div',attrs={"class":'similarities-aui-carousel'}).attrs['data-a-carousel-options']
                recs = re.search(r'"id_list".+:"]', rec, re.M | re.I).group(0)[11:-1].split(',')
                for i in range(len(recs)):
                    recs[i] = recs[i][1:-2]
                if len(recs) > 10:
                    recs = recs[:10]
                recnos = (' ').join(recs)
            except:#个别书籍无推荐数据
                recnos = ''
            c = conn.cursor()
            sql = "select * from abooks"
            id = len(c.execute(sql).fetchall()) + 1
            subno = itemno
            sql = "INSERT INTO abooks ('id','title','intro','isbn','cover','itemno','subno','recnos','infos','buy','author') \
                  VALUES ('%d','%s', '%s', '%s', '%s', '%s','%s','%s','%s','%s','%s');" \
                  % (id, title.replace('\'', '’'), intro.replace('\'', '’'), isbn, cover, itemno, subno,recnos, allinfo,buy,author.replace('\'', '’'))
            try:
                c.execute(sql)
            except IntegrityError as e:
                if e == 'UNIQUE constraint failed: books.isbn':
                    break
            conn.commit()
            print(title + '   成功')
        except:
            traceback.print_exc()
            print(book)
            continue
    #处理amazon反爬 爬完每一页获取下一页url
    nexturl = getnext(url)

    if nexturl != '':
        init(False, nexturl)

@retry(stop_max_attempt_number = 5)
def getnext(url):
    nhtml = BeautifulSoup(req(url).text)
    # 第一页
    nexturl = ''
    nextpage = nhtml.find('a', attrs={"id": 'pagnNextLink'})
    # 第一页之后
    if nextpage == None:
        nextpage = nhtml.find('li', attrs={"class": 'a-last'})
        try:
            nexturl = 'https://www.amazon.cn' + nextpage.next.attrs['href']
        except:
            traceback.print_exc()
    else:
        nexturl = 'https://www.amazon.cn' + nextpage.attrs['href']
    return nexturl

def getproxy():
    proxy = readip.readip()
    if proxy == 'Failed to get proxies':
        return getproxy()
    return proxy

#num为失败计数 相同链接可请求10次避免未知网络错误
def req(url,num=0):
    proxies = getproxy()
    headers = {'User-Agent': ua.random}
    try:
        res = requests.get(url=url, proxies=proxies, headers = headers, timeout=500)
    except:
        num = num + 1
        if num == 10:
            return 'filed'
        return req(url)
    return res

if __name__ == '__main__':
    init()
